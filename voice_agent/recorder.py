"""Records both directions of a call and mixes them into one mono WAV."""
from __future__ import annotations

import time
from typing import Callable

import numpy as np

from .audio import pcm_to_int16, wav_bytes


class CallRecorder:
    """Places audio on a shared timeline (seconds since start) at the transport's rate.

    Caller audio arrives as a continuous stream, so it is appended back to back; if
    it falls behind the clock (a gap in the stream) it jumps forward. Agent audio is
    placed at the moment it was sent.
    """

    def __init__(self, sample_rate: int, clock: Callable[[], float] = time.monotonic,
                 max_seconds: float = 600):
        self.rate = sample_rate
        self.clock = clock
        self.t0 = clock()
        self.max_samples = int(max_seconds * sample_rate)
        self._inbound: list[tuple[int, np.ndarray]] = []
        self._outbound: list[tuple[int, np.ndarray]] = []
        self._in_pos = 0

    def _now_pos(self) -> int:
        return int((self.clock() - self.t0) * self.rate)

    def add_inbound(self, pcm: bytes) -> None:
        samples = pcm_to_int16(pcm).copy()
        if self._now_pos() - (self._in_pos + len(samples)) > self.rate // 2:
            self._in_pos = max(self._in_pos, self._now_pos() - len(samples))
        self._inbound.append((self._in_pos, samples))
        self._in_pos += len(samples)

    def add_outbound(self, pcm: bytes, at: float | None = None) -> None:
        pos = int(((at if at is not None else self.clock()) - self.t0) * self.rate)
        self._outbound.append((max(0, pos), pcm_to_int16(pcm).copy()))

    def mix(self) -> np.ndarray:
        chunks = self._inbound + self._outbound
        if not chunks:
            return np.zeros(0, dtype=np.int16)
        length = min(self.max_samples, max(pos + len(s) for pos, s in chunks))
        out = np.zeros(length, dtype=np.int32)
        for pos, s in chunks:
            if pos >= length:
                continue
            seg = s[: length - pos]
            out[pos:pos + len(seg)] += seg
        return np.clip(out, -32768, 32767).astype(np.int16)

    def wav(self) -> bytes:
        return wav_bytes(self.mix(), self.rate)
