"""Speech to text with faster-whisper, language forced to the order's language."""
from __future__ import annotations

import logging
import threading

import numpy as np

log = logging.getLogger(__name__)


def pick_device(requested: str) -> str:
    if requested in ("cuda", "cpu"):
        return requested
    try:
        import ctranslate2
        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        return "cpu"


class WhisperSTT:
    def __init__(self, model: str = "large-v3", device: str = "auto", compute_type: str = "auto"):
        self.model_name = model
        self.device = pick_device(device)
        self.compute_type = (compute_type if compute_type != "auto"
                             else ("float16" if self.device == "cuda" else "int8"))
        self._model = None
        self._lock = threading.Lock()  # one transcription at a time per model

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is None:
            from faster_whisper import WhisperModel  # heavy, lazy
            log.info("Loading Whisper %s on %s (%s)", self.model_name, self.device, self.compute_type)
            self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)

    def transcribe(self, audio16k: np.ndarray, language: str) -> str:
        """audio16k: int16 or float32 mono 16 kHz. Returns '' for silence/noise."""
        self.load()
        audio = audio16k.astype(np.float32)
        if audio16k.dtype == np.int16:
            audio /= 32768.0
        with self._lock:
            segments, _ = self._model.transcribe(
                audio, language=language, beam_size=5, vad_filter=False,
                condition_on_previous_text=False, temperature=0.0,
            )
            texts = [s.text for s in segments
                     # drop likely hallucinations on noise
                     if not (s.no_speech_prob > 0.6 and s.avg_logprob < -1.0)]
        return " ".join(t.strip() for t in texts).strip()
