"""Disk + memory cache in front of a synthesizer.

Keys are a hash of (model, voice description, language, text), so changing the
voice regenerates audio. Fixed phrases are pre-generated at startup so most of
a call plays without waiting for TTS.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from .audio import read_wav, wav_bytes
from .phrases import LANGS, static_sentences
from .tts import OUTPUT_RATE, Synthesizer

log = logging.getLogger(__name__)


def cache_key(text: str, lang: str, voice: str) -> str:
    return hashlib.sha256(f"{voice}\x00{lang}\x00{text}".encode("utf-8")).hexdigest()[:32]


class CachedTTS:
    def __init__(self, synth: Synthesizer, cache_dir: Path, voice_id: Callable[[str], str],
                 memory_items: int = 512):
        self.synth = synth
        self.dir = Path(cache_dir) / "tts"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.voice_id = voice_id  # lang -> string identifying model + voice
        self._mem: dict[str, np.ndarray] = {}
        self._memory_items = memory_items
        self._lock = threading.Lock()
        self.warmed = 0
        self.warm_total = 0

    def get(self, text: str, lang: str) -> np.ndarray:
        """int16 16 kHz audio for text, generating and caching it if needed."""
        key = cache_key(text, lang, self.voice_id(lang))
        with self._lock:
            if key in self._mem:
                return self._mem[key]
        path = self.dir / f"{key}.wav"
        if path.exists():
            audio, rate = read_wav(path.read_bytes())
            if rate != OUTPUT_RATE:
                path.unlink(missing_ok=True)
                return self.get(text, lang)
        else:
            audio = self.synth.synthesize(text, lang)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(wav_bytes(audio, OUTPUT_RATE))
            tmp.replace(path)
        with self._lock:
            if len(self._mem) >= self._memory_items:
                self._mem.pop(next(iter(self._mem)))
            self._mem[key] = audio
        return audio

    def warm(self, langs: tuple[str, ...] = LANGS) -> None:
        """Pre-generate every fixed sentence (runs in a background thread at startup)."""
        jobs = [(s, lang) for lang in langs for s in static_sentences(lang)]
        self.warm_total = len(jobs)
        for text, lang in jobs:
            try:
                self.get(text, lang)
            except Exception as exc:
                log.warning("TTS warm-up failed for %r (%s): %s", text, lang, exc)
            self.warmed += 1
        log.info("TTS cache warm: %d phrases", self.warmed)
