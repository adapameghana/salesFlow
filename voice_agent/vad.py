"""Voice activity detection and turn detection (when the customer starts/stops talking).

Backends, best first: Silero VAD (`silero-vad` package), WebRTC VAD, then a
simple energy threshold (used in tests and as a last resort).
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Callable, Protocol

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME = 512  # 32 ms at 16 kHz (Silero's required window)
FRAME_MS = FRAME * 1000 / SAMPLE_RATE


class Vad(Protocol):
    def __call__(self, frame: np.ndarray) -> float:
        """Speech probability for one FRAME of float32 audio in [-1, 1]."""


class EnergyVad:
    def __init__(self, threshold_dbfs: float = -38.0):
        self.threshold = threshold_dbfs

    def __call__(self, frame: np.ndarray) -> float:
        rms = float(np.sqrt(np.mean(np.square(frame)) + 1e-12))
        db = 20 * np.log10(rms + 1e-12)
        return 1.0 if db > self.threshold else 0.0


class SileroVad:
    """Stateful per stream, so create one per call (cheap: ~2 MB model)."""

    def __init__(self) -> None:
        import torch
        from silero_vad import load_silero_vad
        self._torch = torch
        self.model = load_silero_vad()

    def __call__(self, frame: np.ndarray) -> float:
        with self._torch.no_grad():
            return float(self.model(self._torch.from_numpy(frame.astype(np.float32)), SAMPLE_RATE))


class WebRtcVad:
    def __init__(self, aggressiveness: int = 2):
        import webrtcvad
        self.vad = webrtcvad.Vad(aggressiveness)

    def __call__(self, frame: np.ndarray) -> float:
        pcm = (np.clip(frame[:480], -1, 1) * 32767).astype("<i2").tobytes()  # 30 ms
        return 1.0 if self.vad.is_speech(pcm, SAMPLE_RATE) else 0.0


def vad_factory(backend: str = "auto") -> Callable[[], Vad]:
    """Returns a constructor so each call gets its own (stateful) VAD."""
    order = {"silero": [SileroVad], "webrtc": [WebRtcVad], "energy": [EnergyVad]}.get(
        backend, [SileroVad, WebRtcVad, EnergyVad])
    for cls in order:
        try:
            cls()
            log.info("Using %s", cls.__name__)
            return cls
        except Exception as exc:  # missing optional dependency
            log.info("%s unavailable: %s", cls.__name__, exc)
    return EnergyVad


class TurnDetector:
    """Feeds 16 kHz audio through a VAD and emits events:
    ("speech_start", None) once speech is confirmed, ("utterance", int16 array) when it ends."""

    def __init__(self, vad: Vad, threshold: float = 0.5, start_ms: float = 96,
                 end_silence_ms: float = 700, min_speech_ms: float = 250,
                 max_utterance_s: float = 20, preroll_ms: float = 320):
        self.vad = vad
        self.threshold = threshold
        self.start_frames = max(1, round(start_ms / FRAME_MS))
        self.end_frames = max(1, round(end_silence_ms / FRAME_MS))
        self.min_frames = max(1, round(min_speech_ms / FRAME_MS))
        self.max_frames = round(max_utterance_s * 1000 / FRAME_MS)
        self._preroll: deque[np.ndarray] = deque(maxlen=max(self.start_frames, round(preroll_ms / FRAME_MS)))
        self._residual = np.zeros(0, dtype=np.int16)
        self._buf: list[np.ndarray] = []
        self._run = 0  # consecutive speech frames before start
        self._silence = 0
        self._speech_frames = 0
        self.in_speech = False

    @property
    def speech_ms(self) -> float:
        """Speech heard so far in the current utterance (audio time, not wall time)."""
        return self._speech_frames * FRAME_MS if self.in_speech else 0.0

    def reset(self) -> None:
        self._preroll.clear()
        self._buf, self._run, self._silence, self._speech_frames = [], 0, 0, 0
        self.in_speech = False

    def feed(self, samples: np.ndarray) -> list[tuple[str, np.ndarray | None]]:
        events: list[tuple[str, np.ndarray | None]] = []
        data = np.concatenate([self._residual, samples.astype(np.int16)])
        n = len(data) // FRAME * FRAME
        self._residual = data[n:]
        for i in range(0, n, FRAME):
            frame = data[i:i + FRAME]
            speech = self.vad(frame.astype(np.float32) / 32768.0) >= self.threshold
            if not self.in_speech:
                self._preroll.append(frame)
                self._run = self._run + 1 if speech else 0
                if self._run >= self.start_frames:
                    self.in_speech = True
                    self._buf = list(self._preroll)
                    self._speech_frames, self._silence = self._run, 0
                    events.append(("speech_start", None))
                continue
            self._buf.append(frame)
            if speech:
                self._speech_frames += 1
                self._silence = 0
            else:
                self._silence += 1
            if self._silence >= self.end_frames or len(self._buf) >= self.max_frames:
                if self._speech_frames >= self.min_frames:
                    events.append(("utterance", np.concatenate(self._buf)))
                self.reset()
        return events
