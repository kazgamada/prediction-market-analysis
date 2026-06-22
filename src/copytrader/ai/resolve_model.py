"""モデル / API キー解決ヘルパー（AUDIT.md F）。

API キーの優先順位:
  DB(`app_settings.openrouter_api_key`) → env `OPENROUTER_API_KEY`
  → env `ANTHROPIC_API_KEY`

モデルの優先順位:
  env `OPENROUTER_MODEL`（強制上書き） → DB の選択モデル → None

DB が空のときは env、それも空なら Anthropic SDK 直叩き用に provider を
`anthropic` として返す（AUDIT.md F の最終フォールバック）。
"""
from __future__ import annotations

from dataclasses import dataclass

from copytrader.ai.app_settings import OPENROUTER_API_KEY, get_app_setting
from copytrader.config import settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"


@dataclass(frozen=True)
class ResolvedModel:
    provider: str          # "openrouter" | "anthropic"
    api_key: str           # 空文字なら未設定
    base_url: str
    model_id: str | None   # 未選択なら None


def resolve_api_key() -> str:
    """API キーを DB → env(OPENROUTER) → env(ANTHROPIC) の順で解決する。

    DB アクセス不可の場合は env にフォールバックする（UI 以外からの利用でも
    壊れないようにするため）。
    """
    try:
        db_value = get_app_setting(OPENROUTER_API_KEY)
    except Exception:  # noqa: BLE001
        db_value = None
    if db_value:
        return db_value
    if settings.openrouter_api_key:
        return settings.openrouter_api_key
    return settings.anthropic_api_key or ""


def resolve_model() -> ResolvedModel:
    """利用すべきモデルと API キー・ベース URL を解決する。"""
    # モデル ID: env 強制上書き → DB 選択モデル
    model_id: str | None = settings.openrouter_model or None
    if model_id is None:
        try:
            from copytrader.ai.openrouter import get_selected_config
            cfg = get_selected_config()
            model_id = cfg.model_id if cfg else None
        except Exception:  # noqa: BLE001
            model_id = None

    # API キー解決と provider 判定
    try:
        db_key = get_app_setting(OPENROUTER_API_KEY)
    except Exception:  # noqa: BLE001
        db_key = None

    if db_key or settings.openrouter_api_key:
        return ResolvedModel(
            provider="openrouter",
            api_key=db_key or settings.openrouter_api_key,
            base_url=OPENROUTER_BASE_URL,
            model_id=model_id,
        )

    # 最終フォールバック: Anthropic 直叩き
    return ResolvedModel(
        provider="anthropic",
        api_key=settings.anthropic_api_key or "",
        base_url=ANTHROPIC_BASE_URL,
        model_id=model_id,
    )
