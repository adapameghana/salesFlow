"""End-to-end session with fake transport/STT/TTS and the energy VAD (no models, no network)."""
import asyncio
import io
import wave
from datetime import date

import numpy as np

from voice_agent.brain import Brain
from voice_agent.heuristics import classify_heuristic
from voice_agent.pipeline import CallSession
from voice_agent.vad import EnergyVad, TurnDetector

from .conftest import make_ctx


def heuristic(text, ctx, expecting):
    return classify_heuristic(text, ctx.language, ctx.today, expecting)


class FakeTTS:
    def get(self, text, lang):
        return np.full(1600, 1000, dtype=np.int16)  # 0.1 s per sentence


class FakeSTT:
    def __init__(self, *texts):
        self.texts = list(texts)

    def transcribe(self, audio, language):
        assert audio.dtype == np.int16 and len(audio) > 0
        return self.texts.pop(0) if self.texts else ""


class FakePhone:
    """8 kHz transport. Says `speech_s` of 'speech' (noise) each time the agent starts listening."""
    sample_rate, chunk_ms, lead_ms = 8000, 20, 20

    def __init__(self, speak_turns: int):
        self.speak_turns = speak_turns
        self.written = 0
        self.events = []
        self.hung_up = False
        self._listening = asyncio.Event()
        self._rng = np.random.default_rng(0)

    async def read(self):
        await asyncio.sleep(0.002)
        if self.hung_up:
            return None
        frame = np.zeros(160, dtype=np.int16)
        if self._listening.is_set() and self.speak_turns > 0:
            self._speech_frames = getattr(self, "_speech_frames", 0) + 1
            if self._speech_frames <= 25:  # 0.5 s of speech
                frame = (self._rng.standard_normal(160) * 8000).astype(np.int16)
            elif self._speech_frames > 70:  # then silence long enough to end the turn
                self._listening.clear()
                self._speech_frames = 0
                self.speak_turns -= 1
        return frame.tobytes()

    async def write(self, pcm):
        self.written += len(pcm)

    async def event(self, payload):
        self.events.append(payload)
        if payload == {"type": "state", "state": "listening"}:
            self._listening.set()

    async def hangup(self):
        self.hung_up = True


def run_session(transport, stt, lang="en", silence=0.3):
    brain = Brain(make_ctx(lang), heuristic)
    session = CallSession(transport, brain, stt, FakeTTS(), EnergyVad(), silence_timeout=silence,
                          max_call_seconds=20)
    return asyncio.run(session.run())


def test_will_pay_call():
    phone = FakePhone(speak_turns=1)
    result = run_session(phone, FakeSTT("I will pay tomorrow"), silence=2.0)
    assert result.outcome.intent == "will_pay"
    assert result.outcome.promised_date == date(2026, 10, 23)
    speakers = [t.speaker for t in result.transcript]
    assert speakers == ["agent", "customer", "agent"]
    assert phone.hung_up and phone.written > 0
    assert {"type": "transcript", "speaker": "customer", "text": "I will pay tomorrow"} in phone.events
    with wave.open(io.BytesIO(result.recording_wav)) as w:
        assert w.getframerate() == 8000 and w.getnchannels() == 1 and w.getnframes() > 0


def test_no_response_call():
    phone = FakePhone(speak_turns=0)
    result = run_session(phone, FakeSTT())
    assert result.outcome.intent == "no_response"
    assert [t.speaker for t in result.transcript] == ["agent", "agent", "agent"]


def test_telugu_paid_flow():
    phone = FakePhone(speak_turns=2)
    result = run_session(phone, FakeSTT("కట్టేశాను", "ఫోన్ పే లో"), lang="te", silence=2.0)
    assert result.outcome.intent == "paid_claimed" and result.outcome.paid_method == "UPI"


def test_turn_detector_events():
    det = TurnDetector(EnergyVad(), end_silence_ms=300)
    speech = (np.random.default_rng(1).standard_normal(16000) * 8000).astype(np.int16)
    events = det.feed(np.zeros(8000, dtype=np.int16)) + det.feed(speech) + det.feed(
        np.zeros(16000, dtype=np.int16))
    kinds = [k for k, _ in events]
    assert kinds == ["speech_start", "utterance"]
    assert len(events[1][1]) >= 16000


class LongTTS(FakeTTS):
    def get(self, text, lang):  # 2 s per greeting sentence, short otherwise
        return np.full(16000 * 2 if "Clinic" in text or "pending" in text else 1600, 1000, np.int16)


class InterruptingPhone(FakePhone):
    """Starts talking once 0.3 s of the greeting has been sent, for 1 s, then stays silent."""

    async def read(self):
        await asyncio.sleep(0.005)
        if self.hung_up:
            return None
        self._n = getattr(self, "_n", 0)
        if self.written >= 4800 and self._n < 50:
            self._n += 1
            return (self._rng.standard_normal(160) * 8000).astype(np.int16).tobytes()
        return np.zeros(160, np.int16).tobytes()


def test_barge_in_stops_greeting():
    phone = InterruptingPhone(speak_turns=0)
    brain = Brain(make_ctx("en"), heuristic)
    session = CallSession(phone, brain, FakeSTT("sorry, wrong number"),
                          LongTTS(), EnergyVad(), silence_timeout=0.5, max_call_seconds=30)
    result = asyncio.run(session.run())
    first_agent_turn_bytes = 3 * 2 * 8000 * 2  # three 2 s sentences at 8 kHz
    assert result.transcript[1].speaker == "customer"
    assert result.transcript[1].ts < 3.0  # handled before the greeting would have finished
    assert phone.written < first_agent_turn_bytes
    assert result.outcome.intent == "wrong_number"
