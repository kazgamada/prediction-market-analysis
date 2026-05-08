from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
