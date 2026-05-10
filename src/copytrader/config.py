from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_db_url(url: str) -> str:
    """Rewrite ``postgres://`` / ``postgresql://`` to ``postgresql+psycopg://``.

    Fly.io's Postgres attach sets DATABASE_URL as ``postgres://...``; SQLAlchemy
    2.x + psycopg3 require an explicit driver suffix.
    """
    if not url:
        return url
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    polygon_rpc_http: str = Field(default="")
    polygon_rpc_ws: str = Field(default="")

    database_url: str = Field(
        default="postgresql+psycopg://copytrader:copytrader@localhost:5432/copytrader"
    )

    polymarket_api_key: str = Field(default="")
    polymarket_api_secret: str = Field(default="")
    polymarket_api_passphrase: str = Field(default="")
    polymarket_clob_url: str = Field(default="https://clob.polymarket.com")
    polymarket_gamma_url: str = Field(default="https://gamma-api.polymarket.com")

    wallet_private_key: str = Field(default="")
    wallet_proxy_address: str = Field(default="")

    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")

    polymarket_start_block: int = Field(default=33605403)

    # auto-catchup backfill のスキップ閾値。head - (この日数 × Polygon の 1日ブロック数)
    # より古いブロックは monitor の自動 catchup では取り込まずスキップする。
    # 完全履歴が必要なら Actions ページから明示的に from_block を指定して手動実行する。
    backfill_recent_days: int = Field(default=60)

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return _normalize_db_url(v)


@lru_cache
def get_settings() -> Settings:
    return Settings()
