"""Application config.

Loads from environment via pydantic-settings. Some values are layered: env
provides the bootstrap value, and the `settings` DB table can override at
runtime (handled by `copytrader.db.settings_table`). This module only owns
the env layer.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://copytrader:copytrader@localhost:5432/copytrader",
    )

    polygon_rpc_http: str = ""
    polygon_rpc_ws: str = ""

    web_password: str = ""

    indexer_window_days: int = 30
    indexer_chunk_size: int = 1000
    indexer_max_parallel: int = 4
    indexer_max_retries: int = 3

    health_port: int = 8080

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    git_sha: str = "dev"
    build_time: str = "dev"


@lru_cache(maxsize=1)
def _cached() -> Settings:
    return Settings()


# Public singleton. Use `settings.x`; tests can monkeypatch fields freely.
settings = _cached()
