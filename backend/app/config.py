from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg2://wa_app:wa_app_password@localhost:5432/whatsapp_orders"
    jwt_secret: str = "change-this-to-a-long-random-string"
    token_minutes: int = 720
    cors_origins: str = "http://localhost:4300,http://127.0.0.1:4300"

    ai_enabled: bool = True
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:1.5b"
    ollama_timeout_seconds: int = 60

    business_utc_offset_minutes: int = 330

    # AI voice-call payment reminders (see docs/PAYMENT_REMINDERS.md)
    business_name: str = "Order Desk"
    reminders_enabled: bool = False  # turns on the automatic scheduler; manual/test calls work either way
    reminder_max_attempts: int = 3
    reminder_gap_hours: int = 24
    reminder_first_after_hours: int = 24
    reminder_window_start: int = 10  # business-time hour, inclusive
    reminder_window_end: int = 19  # business-time hour, exclusive
    reminder_check_minutes: int = 30
    reminder_calls_per_cycle: int = 10  # calls run one after another, ~2 min each
    voice_agent_url: str = "http://127.0.0.1:8100"
    voice_agent_ws_url: str = "ws://127.0.0.1:8100"  # as reached from the staff browser
    voice_agent_secret: str = "change-this-voice-agent-secret"
    reminder_test_calls_apply: bool = False  # demo: browser test calls update the order like real calls
    reminder_recordings_dir: str = str(Path(__file__).resolve().parent.parent / "recordings")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def business_tz(self) -> timezone:
        return timezone(timedelta(minutes=self.business_utc_offset_minutes))

    def business_now(self) -> datetime:
        return datetime.now(self.business_tz)


@lru_cache
def get_settings() -> Settings:
    return Settings()
