"""
Centralized configuration loaded from environment variables / .env file.
All values are read once at startup and exposed as a singleton `settings`.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env if present (local dev). On Railway, env vars are injected directly.
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """Bot configuration. All fields can be overridden via environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Telegram ---
    bot_token: str = Field(
        default="",
        description="Telegram Bot Token from @BotFather (e.g. 123456:ABC-DEF...)",
        validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "BOT_TOKEN"),
    )
    admin_ids: str = Field(
        default="",
        description="Comma-separated Telegram user IDs who can use admin commands",
        validation_alias=AliasChoices("ADMIN_IDS", "TELEGRAM_ADMIN_IDS"),
    )

    # --- IVASMS ---
    # Default IVASMS credentials — used as fallback when a user hasn't set their own.
    # Per-user credentials take priority (multi-user mode).
    ivasms_default_email: str = Field(default="", description="Optional shared IVASMS email")
    ivasms_default_password: str = Field(default="", description="Optional shared IVASMS password")
    ivasms_default_cookies_json: str = Field(
        default="",
        description="Optional shared IVASMS cookies JSON string (alternative to email/password)",
    )

    # --- Polling ---
    otp_poll_interval_seconds: int = Field(
        default=10,
        description="Seconds between OTP polls when auto-poll is active",
    )
    otp_poll_timeout_seconds: int = Field(
        default=300,
        description="Auto-poll session lifetime (5 min default) before it stops",
    )

    # --- Rate limiting ---
    user_cooldown_seconds: int = Field(
        default=5,
        description="Per-user cooldown between API calls to prevent IVASMS bans",
    )

    # --- Database ---
    database_path: str = Field(
        default=str(DATA_DIR / "ivasms_bot.db"),
        description="SQLite database file path",
    )

    # --- Health server ---
    health_port: int = Field(default=8080, description="Port for Railway health-check HTTP server")
    health_host: str = Field(default="0.0.0.0", description="Health server bind host")

    # --- Misc ---
    log_level: str = Field(default="INFO", description="Loguru log level (DEBUG/INFO/WARNING/ERROR)")

    @property
    def admin_id_list(self) -> list[int]:
        """Parse comma-separated admin IDs into a list of ints."""
        if not self.admin_ids:
            return []
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip().isdigit()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


# Singleton used across the codebase
settings = get_settings()


def is_admin(user_id: int) -> bool:
    """Check whether a Telegram user ID is in the admin list."""
    return user_id in settings.admin_id_list
