"""
limes_outpost.config
~~~~~~~~~~~~~~~~
Single source of truth for all environment variables.
Uses pydantic-settings — add `pydantic-settings` to requirements.txt.

Usage anywhere in the package:
    from limes_outpost.config import settings

    api_key = settings.cerebras_api_key
    db_host = settings.db_host
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── API Keys ──────────────────────────────────────────
    openai_api_key:       str = ""
    cerebras_api_key:     str = ""
    elevenlabs_api_key:   str = ""
    elevenlabs_voice_id:  str = ""
    creatomate_api_key:   str = ""
    kling_access_key:     str = ""
    kling_secret_key:     str = ""
    newsdata_api_key:     str = ""
    discord_webhook_url:  str = ""

    # ── Database ──────────────────────────────────────────
    db_host:     str = "localhost"
    db_name:     str = "limes_outpost_db"
    db_user:     str = "limes_outpost_user"
    db_password: str = "limes_outpost_password"
    db_port:     int = 5432

    # ── System ────────────────────────────────────────────
    dry_run: bool = True
    ventures_root: str = ""  # absolute path to ventures/ dir; auto-resolved if empty

    @property
    def ventures_dir(self) -> Path:
        """Always returns an absolute Path to ventures/, regardless of CWD."""
        if self.ventures_root:
            return Path(self.ventures_root).resolve()
        # Auto-resolve: walk up from this file to repo root
        return Path(__file__).parent.parent / "ventures"

    # ── Redis (Phase 3) ───────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── JWT (Phase 4) ─────────────────────────────────────
    jwt_secret:     str = "change-me-before-production"
    jwt_algorithm:  str = "HS256"
    jwt_expire_min: int = 60


# Module-level singleton — import this everywhere
settings = Settings()