"""Settings, read from environment variables or voice_agent/.env."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(PACKAGE_DIR / ".env"), extra="ignore")

    # Backend (the FastAPI order app) and the shared secret for X-Agent-Secret.
    backend_url: str = "http://127.0.0.1:8000"
    voice_agent_secret: str = ""

    # This service.
    host: str = "0.0.0.0"
    port: int = 8100
    allowed_origins: str = "http://localhost:4300"  # comma separated, for CORS
    log_level: str = "INFO"
    preload_models: bool = True  # load STT/TTS and warm the phrase cache at startup
    # Languages whose fixed sentences are generated at startup. On a CPU each sentence takes
    # 10-30 s, so list only the languages you use (or prepare them earlier with voice_agent.prepare).
    warm_langs: str = "en,hi,te,ta"

    # Understanding (Ollama). The LLM only classifies; replies are fixed phrases.
    use_llm: bool = True
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_timeout_seconds: float = 20.0

    # Speech to text (faster-whisper).
    whisper_model: str = "large-v3"
    whisper_device: str = "auto"  # auto | cuda | cpu
    whisper_compute_type: str = "auto"  # auto -> float16 on cuda, int8 on cpu

    # Text to speech (AI4Bharat Indic Parler-TTS).
    tts_model: str = "ai4bharat/indic-parler-tts"
    tts_device: str = "auto"
    # {speaker} is replaced by the per-language speaker from tts_speakers.
    tts_voice_description: str = (
        "{speaker}'s voice is clear and friendly, speaking at a moderate pace with a "
        "pleasant tone. The recording is of very high quality with no background noise."
    )
    tts_speakers: str = "en:Mary,hi:Divya,te:Lalitha,ta:Jaya"

    # Voice activity detection.
    vad_backend: str = "auto"  # auto | silero | webrtc | energy
    vad_threshold: float = 0.5

    # Asterisk REST Interface (originating calls).
    ari_url: str = "http://127.0.0.1:8088"
    ari_user: str = "voiceagent"
    ari_password: str = ""
    ari_app: str = "voice-agent"
    asterisk_endpoint_template: str = "Mobile/myphone/{phone}"
    asterisk_context: str = "voice-agent"
    asterisk_extension: str = "s"
    asterisk_caller_id: str = ""
    ring_timeout_seconds: int = 40

    # AudioSocket server that Asterisk connects to once the call is answered.
    audiosocket_host: str = "0.0.0.0"
    audiosocket_port: int = 9092

    # Conversation limits.
    max_call_seconds: int = 120
    silence_timeout_seconds: float = 8.0
    max_customer_turns: int = 4

    # Hugging Face: token for the gated AI4Bharat voice model, and where models are stored
    # (set HF_HOME to a drive with ~5 GB free). Passed on to the Hugging Face libraries.
    hf_token: str = ""
    hf_home: str = ""

    # Local data.
    cache_dir: Path = PACKAGE_DIR / "cache"
    include_recording: bool = True

    @property
    def warm_lang_list(self) -> tuple[str, ...]:
        return tuple(x.strip() for x in self.warm_langs.split(",") if x.strip())

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def speaker_for(self, lang: str) -> str:
        speakers = dict(
            part.split(":", 1) for part in self.tts_speakers.split(",") if ":" in part
        )
        return speakers.get(lang, speakers.get("en", "Mary")).strip()

    def voice_description(self, lang: str) -> str:
        return self.tts_voice_description.replace("{speaker}", self.speaker_for(lang))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Hugging Face libraries read these from the environment, not from our .env file.
    if settings.hf_token and not os.environ.get("HF_TOKEN"):
        os.environ["HF_TOKEN"] = settings.hf_token
    if settings.hf_home and not os.environ.get("HF_HOME"):
        os.environ["HF_HOME"] = settings.hf_home
    return settings
