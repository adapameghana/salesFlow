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
