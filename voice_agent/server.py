"""HTTP/WebSocket API of the voice agent.

    POST /calls   backend asks for a phone call (202, queued, one call at a time)
    GET  /health  models loaded? Asterisk and Ollama reachable?
    WS   /test    browser test call (16 kHz PCM both ways), see docs/PAYMENT_REMINDERS.md

Run:  python -m voice_agent.server      (from the repository root)
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .asterisk_ari import AriClient
from .audiosocket import AudioSocketServer
from .brain import Brain
from .config import Settings, get_settings
from .llm import OllamaClassifier, ollama_reachable
from .models import CallContext
from .phrases import split_sentences
from .pipeline import CallSession, SessionResult, Transport
from .result_client import BackendClient, build_result_payload, check_secret, verify_token
from .stt import WhisperSTT
from .tts import ParlerTTS
from .tts_cache import CachedTTS
from .vad import vad_factory

log = logging.getLogger("voice_agent")


class CallRequest(BaseModel):
    call_id: int
    phone: str
    context: dict[str, Any]


class Services:
    """Process-wide singletons: models are loaded once and shared by all calls."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.stt = WhisperSTT(settings.whisper_model, settings.whisper_device, settings.whisper_compute_type)
        self.tts_engine = ParlerTTS(settings.tts_model, settings.voice_description, settings.tts_device)
        self.tts = CachedTTS(self.tts_engine, settings.cache_dir,
                             lambda lang: f"{settings.tts_model}|{settings.voice_description(lang)}")
        self.classifier = OllamaClassifier(settings.ollama_url, settings.ollama_model,
                                           settings.ollama_timeout_seconds, settings.use_llm)
        self.make_vad = vad_factory(settings.vad_backend)
        self.ari = AriClient(settings.ari_url, settings.ari_user, settings.ari_password, settings.ari_app)
        self.audiosocket = AudioSocketServer(settings.audiosocket_host, settings.audiosocket_port)
        self.audiosocket_listening = False
        self.backend = BackendClient(settings.backend_url, settings.voice_agent_secret)
        self.queue: asyncio.Queue[CallRequest] = asyncio.Queue()
        self.current_call: int | None = None
        self.load_error: str | None = None
        self._load_lock = threading.Lock()

    def ensure_loaded(self) -> None:
        """Load STT and TTS (blocking; call from a thread)."""
        with self._load_lock:
            try:
                self.stt.load()
                self.tts_engine.load()
                self.load_error = None
            except Exception as exc:
                self.load_error = f"{type(exc).__name__}: {exc}"
                raise

    def preload(self) -> None:
        try:
            self.ensure_loaded()
            self.warm_llm()
            self.tts.warm(self.settings.warm_lang_list)
        except Exception:
            log.exception("Model preload failed")

    def warm_llm(self) -> None:
        """Ollama loads the model on its first request (5-10 s on a CPU); do that now, not mid-call."""
        if not self.settings.use_llm:
            return
        from datetime import date
        ctx = CallContext(order_id=None, order_number="0", customer_name="", language="en",
                          balance=1.0, business_name="", today=date.today())
        self.classifier("I will pay tomorrow", ctx, "payment_answer")
        log.info("Ollama model %s is warm", self.settings.ollama_model)

    def new_session(self, transport: Transport, ctx: CallContext) -> CallSession:
        s = self.settings
        brain = Brain(ctx, self.classifier, max_turns=s.max_customer_turns)
        return CallSession(transport, brain, self.stt, self.tts, self.make_vad(),
                           max_call_seconds=s.max_call_seconds,
                           silence_timeout=s.silence_timeout_seconds,
                           vad_threshold=s.vad_threshold, record=s.include_recording)

    def prepare_greeting(self, ctx: CallContext) -> None:
        """Synthesize the personalised greeting before dialling so it plays instantly."""
        for sentence in split_sentences(Brain(ctx, self.classifier).greeting().text):
            self.tts.get(sentence, ctx.language)


def result_payload(status: str, result: SessionResult | None = None, error: str | None = None
                   ) -> dict[str, Any]:
    if result is None:
        summaries = {"no_answer": "The customer did not answer.", "busy": "The line was busy.",
                     "failed": "The call could not be placed."}
        return build_result_payload(status=status, summary=summaries.get(status, ""), error=error)
    o = result.outcome
    return build_result_payload(
        status=status, intent=o.intent, promised_date=o.promised_date, summary=o.summary,
        transcript=result.transcript, duration_seconds=result.duration_seconds,
        recording_wav=result.recording_wav, error=error or result.error,
    )


async def run_phone_call(svc: Services, req: CallRequest) -> None:
    s = svc.settings
    ctx = CallContext.from_dict(req.context)
    call_uuid = str(uuid.uuid4())
    try:
        await asyncio.to_thread(svc.ensure_loaded)
        await asyncio.to_thread(svc.prepare_greeting, ctx)
    except Exception as exc:
        await svc.backend.post_result(req.call_id, result_payload("failed", error=f"models: {exc}"))
        return
    if not svc.audiosocket_listening:
        await svc.backend.post_result(req.call_id, result_payload(
            "failed", error="AudioSocket server is not listening"))
        return
    answered = svc.audiosocket.expect(call_uuid)
    try:
        res = await svc.ari.originate_and_wait(
            endpoint=s.asterisk_endpoint_template.format(phone=req.phone),
            context=s.asterisk_context, extension=s.asterisk_extension, call_uuid=call_uuid,
            answered=answered, ring_timeout=s.ring_timeout_seconds, caller_id=s.asterisk_caller_id,
        )
    finally:
        svc.audiosocket.forget(call_uuid)
    log.info("Call %s (%s): %s", req.call_id, req.phone[-4:].rjust(10, "*"), res.status)
    if res.status != "answered":
        await svc.backend.post_result(req.call_id, result_payload(res.status, error=res.error))
        return
    result = await svc.new_session(res.connection, ctx).run()
    await svc.backend.post_result(req.call_id, result_payload("answered", result))


async def call_worker(svc: Services) -> None:
    """Phone calls go out strictly one at a time (one SIM / one line)."""
    while True:
        req = await svc.queue.get()
        svc.current_call = req.call_id
        try:
            await run_phone_call(svc, req)
        except Exception as exc:
            log.exception("Call %s failed", req.call_id)
            await svc.backend.post_result(req.call_id, result_payload("failed", error=str(exc)))
        finally:
            svc.current_call = None
            svc.queue.task_done()


class WebSocketTransport:
    """Browser test call: binary frames are 16 kHz mono s16le PCM; text frames are JSON."""

    sample_rate = 16000
    chunk_ms = 40
    lead_ms = 200  # small, so barge-in stops the browser's playback quickly

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.closed = False
        self._odd = b""  # a frame with an odd byte count leaves half a sample behind

    async def read(self) -> bytes | None:
        while not self.closed:
            try:
                msg = await self.ws.receive()
            except (WebSocketDisconnect, RuntimeError):
                self.closed = True
                return None
            if msg.get("type") == "websocket.disconnect":
                self.closed = True
                return None
            if msg.get("bytes"):
                data = self._odd + msg["bytes"]
                cut = len(data) // 2 * 2
                self._odd = data[cut:]
                if cut:
                    return data[:cut]
            elif msg.get("text"):
                try:
                    if json.loads(msg["text"]).get("type") == "hangup":
                        self.closed = True
                        return None
                except (ValueError, AttributeError):
                    pass
        return None

    async def write(self, pcm: bytes) -> None:
        if not self.closed:
            try:
                await self.ws.send_bytes(pcm)
            except Exception:
                self.closed = True

    async def event(self, payload: dict[str, Any]) -> None:
        if not self.closed:
            try:
                await self.ws.send_json(payload)
            except Exception:
                self.closed = True

    async def hangup(self) -> None:
        pass  # the endpoint sends "end" and closes the socket afterwards


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = Services(settings)
        app.state.svc = svc
        try:
            await svc.audiosocket.start()
            svc.audiosocket_listening = True
        except OSError as exc:
            log.error("AudioSocket server could not start: %s (phone calls disabled)", exc)
        worker = asyncio.create_task(call_worker(svc))
        if settings.preload_models:
            threading.Thread(target=svc.preload, name="model-preload", daemon=True).start()
        if not settings.voice_agent_secret:
            log.warning("VOICE_AGENT_SECRET is empty: all requests will be rejected")
        yield
        worker.cancel()
        await svc.audiosocket.stop()

    app = FastAPI(title="Payment reminder voice agent", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_methods=["*"],
                       allow_headers=["*"])

    @app.post("/calls", status_code=202)
    async def place_call(req: CallRequest, x_agent_secret: str | None = Header(default=None)):
        svc: Services = app.state.svc
        if not check_secret(settings.voice_agent_secret, x_agent_secret):
            raise HTTPException(status_code=401, detail="bad agent secret")
        if not (req.phone.isdigit() and len(req.phone) == 10):
            raise HTTPException(status_code=422, detail="phone must be 10 digits")
        await svc.queue.put(req)
        return JSONResponse({"accepted": True}, status_code=202)

    @app.get("/health")
    async def health():
        svc: Services = app.state.svc
        asterisk_ok, ollama_ok = await asyncio.gather(
            svc.ari.reachable(), asyncio.to_thread(ollama_reachable, settings.ollama_url))
        return {
            "ok": svc.load_error is None,
            "models": {"stt": svc.stt.loaded, "tts": svc.tts_engine.loaded,
                       "vad": getattr(svc.make_vad, "__name__", "?"), "error": svc.load_error,
                       "tts_cache": {"warmed": svc.tts.warmed, "total": svc.tts.warm_total}},
            "asterisk": asterisk_ok,
            "audiosocket": svc.audiosocket_listening,
            "ollama": ollama_ok,
            "current_call": svc.current_call,
            "queued_calls": svc.queue.qsize(),
        }

    @app.websocket("/test")
    async def browser_test(ws: WebSocket):
        svc: Services = app.state.svc
        raw_id, token = ws.query_params.get("call_id", ""), ws.query_params.get("token")
        if not raw_id.isdigit() or not verify_token(settings.voice_agent_secret, raw_id, token):
            await ws.close(code=4401)
            return
        call_id = int(raw_id)
        await ws.accept()
        transport = WebSocketTransport(ws)
        try:
            data = await svc.backend.get_context(call_id)
            ctx = CallContext.from_dict(data["context"])
        except Exception as exc:
            log.warning("Could not load context for test call %s: %s", call_id, exc)
            await transport.event({"type": "end", "intent": None, "summary": "Could not load the call context."})
            await ws.close()
            return
        await transport.event({"type": "state", "state": "thinking"})  # models may still be loading
        try:
            await asyncio.to_thread(svc.ensure_loaded)
            await asyncio.to_thread(svc.prepare_greeting, ctx)
        except Exception as exc:
            await transport.event({"type": "end", "intent": None, "summary": f"Voice models unavailable: {exc}"})
            await ws.close()
            return
        result = await svc.new_session(transport, ctx).run()
        await transport.event({"type": "end", "intent": result.outcome.intent,
                               "summary": result.outcome.summary})
        try:
            await ws.close()
        except Exception:
            pass
        # Status is ignored for browser calls (the backend keeps 'test').
        await svc.backend.post_result(call_id, result_payload("answered", result))

    return app


app = create_app()


def main() -> None:
    import uvicorn
    s = get_settings()
    # On CPU, speech synthesis can keep the event loop busy for longer than uvicorn's default
    # 20 s WebSocket ping timeout, which would drop browser test calls mid-greeting.
    uvicorn.run(app, host=s.host, port=s.port, log_level=s.log_level.lower(),
                ws_ping_interval=20, ws_ping_timeout=300)


if __name__ == "__main__":
    main()
