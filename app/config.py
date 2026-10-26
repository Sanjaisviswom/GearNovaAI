"""
app/config.py
─────────────
Centralised settings loaded from environment variables / .env file.
All other modules import `settings` from here.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # ── Database ───────────────────────────────────────────────────────────────────
    database_url: str = "postgresql+psycopg://spareuser:sparepass@localhost:5432/spareparts"

    # ── WhatsApp Cloud API ────────────────────────────────────
    whatsapp_verify_token: str = "my_verify_token"
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_api_version: str = "v19.0"

    @property
    def whatsapp_api_url(self) -> str:
        return (
            f"https://graph.facebook.com/{self.whatsapp_api_version}"
            f"/{self.whatsapp_phone_number_id}/messages"
        )

    # ── Google Gemini AI ──────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    # ── YouTube Data API v3 ───────────────────────────────────
    youtube_api_key: str = ""
    youtube_max_results: int = 3

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Security ──────────────────────────────────────────────
    secret_key: str = "change-me"
    admin_api_key: str = "change-me-admin-key"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — import and call this everywhere."""
    return Settings()


# Convenience alias used across the codebase
settings = get_settings()
