"""Small PCM helpers: bytes <-> numpy and resampling."""
from __future__ import annotations

import io
import wave
from math import gcd

import numpy as np


def pcm_to_int16(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2")


def int16_to_pcm(samples: np.ndarray) -> bytes:
    return np.asarray(samples, dtype="<i2").tobytes()


def float_to_int16(samples: np.ndarray) -> np.ndarray:
    return (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)


def resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Polyphase resampling (scipy) with a linear-interpolation fallback. Keeps dtype."""
    if src_rate == dst_rate or len(samples) == 0:
        return samples
    dtype = samples.dtype
    x = samples.astype(np.float32)
    try:
        from scipy.signal import resample_poly
        g = gcd(src_rate, dst_rate)
        y = resample_poly(x, dst_rate // g, src_rate // g)
    except ImportError:
        n = int(round(len(x) * dst_rate / src_rate))
        y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    if np.issubdtype(dtype, np.integer):
        return np.clip(np.round(y), -32768, 32767).astype(dtype)
    return y.astype(dtype)


def wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(int16_to_pcm(samples))
    return buf.getvalue()


def read_wav(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as w:
        return pcm_to_int16(w.readframes(w.getnframes())).copy(), w.getframerate()
