"""Text to speech with AI4Bharat Indic Parler-TTS (supports en, hi, te, ta).

Generation follows the model card: the voice is steered by a natural-language
description; the prompt is the text to speak. Output is resampled to 16 kHz
(browser); the pipeline derives 8 kHz for the phone.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Protocol

import numpy as np

from .audio import float_to_int16, resample

log = logging.getLogger(__name__)
OUTPUT_RATE = 16000


class Synthesizer(Protocol):
    def synthesize(self, text: str, lang: str) -> np.ndarray:
        """int16 mono audio at 16 kHz."""


class ParlerTTS:
    def __init__(self, model: str, voice_description: Callable[[str], str], device: str = "auto"):
        self.model_name = model
        self.voice_description = voice_description
        self.requested_device = device
        self._model = None
        self._tok = None
        self._desc_tok = None
        self._device = "cpu"
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        import torch  # heavy, lazy
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer

        dev = self.requested_device
        if dev == "auto":
            dev = "cuda:0" if torch.cuda.is_available() else "cpu"
        self._device = dev
        log.info("Loading %s on %s", self.model_name, dev)
        self._model = ParlerTTSForConditionalGeneration.from_pretrained(self.model_name).to(dev)
        self._tok = AutoTokenizer.from_pretrained(self.model_name)
        self._desc_tok = AutoTokenizer.from_pretrained(self._model.config.text_encoder._name_or_path)

    def synthesize(self, text: str, lang: str) -> np.ndarray:
        self.load()
        import torch
        with self._lock, torch.no_grad():
            desc = self._desc_tok(self.voice_description(lang), return_tensors="pt").to(self._device)
            prompt = self._tok(text, return_tensors="pt").to(self._device)
            generation = self._model.generate(
                input_ids=desc.input_ids, attention_mask=desc.attention_mask,
                prompt_input_ids=prompt.input_ids, prompt_attention_mask=prompt.attention_mask,
            )
        audio = generation.cpu().numpy().squeeze().astype(np.float32)
        audio = resample(audio, self._model.config.sampling_rate, OUTPUT_RATE)
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak > 0:
            audio = audio / peak * 0.9  # consistent loudness on the phone line
        return float_to_int16(audio)
