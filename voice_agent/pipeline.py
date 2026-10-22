"""The realtime call session, shared by phone (AudioSocket) and browser (WebSocket).

A lean asyncio pipeline instead of Pipecat, so every step is explicit and testable:

    transport audio -> resample to 16 kHz -> VAD turn detector -> utterance
        -> Whisper STT -> Brain (Ollama classifier + fixed phrases) -> reply text
        -> sentence-by-sentence TTS (cached) -> resample -> paced playback -> transport

Barge-in: if the customer talks over an interruptible reply for ~250 ms, playback
stops and their utterance is handled. Silence for SILENCE_TIMEOUT after the agent
finishes counts as "no speech" (reprompt once, then close). The whole call is
capped at MAX_CALL_SECONDS.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from .audio import int16_to_pcm, pcm_to_int16, resample
from .brain import Brain, Outcome, Reply
from .models import TranscriptEntry
from .phrases import split_sentences
from .recorder import CallRecorder
from .vad import SAMPLE_RATE as VAD_RATE
from .vad import TurnDetector, Vad

log = logging.getLogger(__name__)


class Transport(Protocol):
    """Where call audio comes from and goes to."""

    sample_rate: int  # PCM s16le mono rate used on this transport
    chunk_ms: int  # size of audio chunks written
    lead_ms: int  # how far ahead of real time audio may be sent

    async def read(self) -> bytes | None:
        """Next chunk of customer audio; None when the call/connection ended."""

    async def write(self, pcm: bytes) -> None: ...

    async def event(self, payload: dict[str, Any]) -> None:
        """Side-channel JSON (browser only; phone transports ignore it)."""

    async def hangup(self) -> None: ...


class SpeechToText(Protocol):
    def transcribe(self, audio16k: np.ndarray, language: str) -> str: ...


class SpeechSource(Protocol):
    def get(self, text: str, lang: str) -> np.ndarray:
        """int16 mono 16 kHz audio for text."""


@dataclass
class SessionResult:
    outcome: Outcome
    transcript: list[TranscriptEntry] = field(default_factory=list)
    duration_seconds: float = 0.0
    recording_wav: bytes | None = None
    error: str | None = None


def _swallow(task: asyncio.Future) -> None:
    if not task.cancelled():
        task.exception()


class CallSession:
    def __init__(self, transport: Transport, brain: Brain, stt: SpeechToText, tts: SpeechSource,
                 vad: Vad, *, max_call_seconds: float = 120, silence_timeout: float = 8.0,
                 vad_threshold: float = 0.5, barge_in_ms: float = 250, record: bool = True):
        self.tr = transport
        self.brain = brain
        self.lang = brain.lang
        self.stt = stt
        self.tts = tts
        self.detector = TurnDetector(vad, threshold=vad_threshold)
        self.max_call_seconds = max_call_seconds
        self.silence_timeout = silence_timeout
        self.barge_in_ms = barge_in_ms
        self.recorder = CallRecorder(transport.sample_rate, max_seconds=max_call_seconds + 60) if record else None
        self.transcript: list[TranscriptEntry] = []
        self._events: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self._get_task: asyncio.Future | None = None
        self._speaking = False
        self._interruptible = True
        self._barge_in = asyncio.Event()
        self._hung_up = False
        self.t0 = time.monotonic()

    # ------------------------------------------------------------ main loop
    async def run(self) -> SessionResult:
        self.t0 = time.monotonic()
        if self.recorder:
            self.recorder.t0 = self.t0
        deadline = self.t0 + self.max_call_seconds
        reader = asyncio.create_task(self._read_loop())
        error = None
        try:
            await self._speak(self.brain.greeting())
            while not self.brain.done and not self._hung_up:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    await self._speak(self.brain.on_timeout())
                    break
                event = await self._next_event(min(self.silence_timeout, remaining))
                if event is None:  # nothing heard within the wait
                    if (time.monotonic() >= deadline or self.detector.in_speech
                            or not self._events.empty()):
                        continue  # time cap handled above / customer is mid-sentence
                    reply = self.brain.on_silence()
                elif event[0] == "hangup":
                    break
                elif event[0] == "speech_start":
                    continue  # wait for the end of the utterance
                else:
                    reply = await self._handle_utterance(event[1])
                await self._speak(reply)
        except Exception as exc:  # keep the result: whatever we learned still gets posted
            log.exception("Call session failed")
            error = f"{type(exc).__name__}: {exc}"
        finally:
            if self._hung_up:
                self.brain.on_hangup()
            reader.cancel()
            if self._get_task is not None:
                self._get_task.cancel()
            try:
                await self.tr.hangup()
            except Exception:
                pass
        if not self.brain.done:
            self.brain.on_hangup()
        return SessionResult(
            outcome=self.brain.outcome(), transcript=self.transcript,
            duration_seconds=time.monotonic() - self.t0,
            recording_wav=self.recorder.wav() if self.recorder else None, error=error,
        )

    async def _handle_utterance(self, audio16k: np.ndarray) -> Reply:
        await self._state("thinking")
        text = await asyncio.to_thread(self.stt.transcribe, audio16k, self.lang)
        if text:
            await self._add_transcript("customer", text)
        log.info("Customer: %s", text or "(nothing recognised)")
        return await asyncio.to_thread(self.brain.on_customer, text)

    async def _next_event(self, timeout: float) -> tuple[str, Any] | None:
        # A persistent get() task: cancelling it on timeout could drop an event that
        # arrived at the same instant (e.g. an utterance ending just as the timer fires).
        if self._get_task is None:
            self._get_task = asyncio.ensure_future(self._events.get())
        done, _ = await asyncio.wait({self._get_task}, timeout=max(0.01, timeout))
        if not done:
            return None
        task, self._get_task = self._get_task, None
        return task.result()

    # ------------------------------------------------------------ input
    async def _read_loop(self) -> None:
        while True:
            pcm = await self.tr.read()
            if pcm is None:
                self._hung_up = True
                self._barge_in.set()
                await self._events.put(("hangup", None))
                return
            if self.recorder:
                self.recorder.add_inbound(pcm)
            samples = resample(pcm_to_int16(pcm), self.tr.sample_rate, VAD_RATE)
            for event in self.detector.feed(samples):
                await self._events.put(event)
            # Barge-in needs sustained speech, so line echo or a cough does not cut us off.
            if self._speaking and self._interruptible and self.detector.speech_ms >= self.barge_in_ms:
                self._barge_in.set()

    # ------------------------------------------------------------ output
    async def _state(self, state: str) -> None:
        await self.tr.event({"type": "state", "state": state})

    async def _add_transcript(self, speaker: str, text: str) -> None:
        self.transcript.append(TranscriptEntry(speaker, text, time.monotonic() - self.t0))
        await self.tr.event({"type": "transcript", "speaker": speaker, "text": text})

    async def _speak(self, reply: Reply) -> None:
        if not reply.text or self._hung_up:
            return
        log.info("Agent: %s", reply.text)
        await self._add_transcript("agent", reply.text)
        await self._state("speaking")
        self._speaking, self._interruptible = True, reply.interruptible
        self._barge_in.clear()
        sentences = split_sentences(reply.text)
        pending = asyncio.ensure_future(asyncio.to_thread(self.tts.get, sentences[0], self.lang))
        try:
            for i in range(len(sentences)):
                audio = await pending
                if i + 1 < len(sentences):  # synthesize the next sentence while this one plays
                    pending = asyncio.ensure_future(
                        asyncio.to_thread(self.tts.get, sentences[i + 1], self.lang))
                if not await self._play(audio):
                    break
        finally:
            pending.add_done_callback(_swallow)
            self._speaking = False
        if not self._hung_up:
            await self._state("listening")

    async def _play(self, audio16k: np.ndarray) -> bool:
        """Send audio paced in real time. False if interrupted (barge-in or hangup)."""
        rate = self.tr.sample_rate
        pcm = int16_to_pcm(resample(audio16k, 16000, rate))
        chunk_bytes = rate * self.tr.chunk_ms // 1000 * 2
        chunk_s = self.tr.chunk_ms / 1000
        lead_s = self.tr.lead_ms / 1000
        start = time.monotonic()
        for n, i in enumerate(range(0, len(pcm), chunk_bytes)):
            if self._hung_up or (self._interruptible and self._barge_in.is_set()):
                return False
            delay = start + n * chunk_s - lead_s - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            data = pcm[i:i + chunk_bytes]
            await self.tr.write(data)
            if self.recorder:
                self.recorder.add_outbound(data, at=start + n * chunk_s)
        end = start + len(pcm) / 2 / rate
        while time.monotonic() < end:  # let the buffered tail play out
            if self._hung_up or (self._interruptible and self._barge_in.is_set()):
                return False
            await asyncio.sleep(min(0.02, max(0.0, end - time.monotonic())))
        return True
