"""OpenRouter API 連携（モデル一覧取得・選択モデルの保存/取得）。

AUDIT.md A-2 / C / D に対応。
- `fetch_models()`: 全モデル一覧を取得し 1 時間キャッシュ（C: models GET）
- `get_selected_config()` / `save_selected_config()`: 選択モデルの取得・保存（C: config）
"""
from __future__ import annotations

import logging
import time
import uuid as _uuid_mod
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select, update

from copytrader.ai.resolve_model import resolve_api_key
from copytrader.db.engine import get_session
from copytrader.db.models import OpenRouterConfig

log = logging.getLogger(__name__)

MODELS_URL = "https://openrouter.ai/api/v1/models"
_CACHE_TTL_SECONDS = 3600  # 1 時間（AUDIT.md A-2）

# プロセス内キャッシュ: (取得時刻, モデルリスト)
_models_cache: tuple[float, list[Model]] | None = None


@dataclass(frozen=True)
class Model:
    """OpenRouter のモデル 1 件（トークン単価は USD/token）。"""
    model_id: str
    name: str
    context_length: int | None
    prompt_price: Decimal | None
    completion_price: Decimal | None


# OpenRouter へ到達できない場合（ネットワーク制限・障害時）の最小フォールバック。
# ライブ取得に成功すれば常にそちらで上書きされる。単価は概算（USD/token）。
FALLBACK_MODELS: list[Model] = [
    Model("anthropic/claude-3.5-sonnet", "Anthropic: Claude 3.5 Sonnet",
          200000, Decimal("0.000003"), Decimal("0.000015")),
    Model("anthropic/claude-3.5-haiku", "Anthropic: Claude 3.5 Haiku",
          200000, Decimal("0.0000008"), Decimal("0.000004")),
    Model("openai/gpt-4o", "OpenAI: GPT-4o",
          128000, Decimal("0.0000025"), Decimal("0.00001")),
    Model("openai/gpt-4o-mini", "OpenAI: GPT-4o mini",
          128000, Decimal("0.00000015"), Decimal("0.0000006")),
    Model("google/gemini-2.0-flash-001", "Google: Gemini 2.0 Flash",
          1000000, Decimal("0.0000001"), Decimal("0.0000004")),
    Model("meta-llama/llama-3.3-70b-instruct", "Meta: Llama 3.3 70B Instruct",
          131072, Decimal("0.00000012"), Decimal("0.0000003")),
]


def _to_decimal(raw: object) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def parse_models(payload: dict) -> list[Model]:
    """OpenRouter `/models` レスポンス JSON を Model のリストへ変換。"""
    out: list[Model] = []
    for item in payload.get("data", []):
        pricing = item.get("pricing") or {}
        out.append(Model(
            model_id=item.get("id", ""),
            name=item.get("name") or item.get("id", ""),
            context_length=item.get("context_length"),
            prompt_price=_to_decimal(pricing.get("prompt")),
            completion_price=_to_decimal(pricing.get("completion")),
        ))
    out.sort(key=lambda m: m.name.lower())
    return [m for m in out if m.model_id]


def fetch_models(*, force: bool = False) -> list[Model]:
    """OpenRouter の全モデル一覧を取得（1 時間キャッシュ）。

    API キーは任意（models エンドポイントは未認証でも取得可）。失敗時は
    例外を送出せず空リストを返し、呼び出し側でハンドリングする。
    """
    global _models_cache
    now = time.monotonic()
    if not force and _models_cache is not None:
        fetched_at, models = _models_cache
        if now - fetched_at < _CACHE_TTL_SECONDS:
            return models

    headers = {}
    api_key = resolve_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = httpx.get(MODELS_URL, headers=headers, timeout=20.0)
        resp.raise_for_status()
        models = parse_models(resp.json())
    except Exception:  # noqa: BLE001
        log.warning("OpenRouter モデル一覧の取得に失敗", exc_info=True)
        # 取得失敗時は古いキャッシュがあればそれを返す
        return _models_cache[1] if _models_cache else []

    _models_cache = (now, models)
    return models


def get_selected_config() -> OpenRouterConfig | None:
    """選択中（is_selected=true）のモデル設定を返す。無ければ None。"""
    with get_session() as s:
        return s.execute(
            select(OpenRouterConfig).where(OpenRouterConfig.is_selected.is_(True))
        ).scalar_one_or_none()


def save_selected_config(model: Model, *, updated_by: _uuid_mod.UUID | None = None) -> None:
    """選択モデルを保存し、`is_selected` が常に 1 件になるよう既存を解除する。"""
    with get_session() as s:
        s.execute(
            update(OpenRouterConfig)
            .where(OpenRouterConfig.is_selected.is_(True))
            .values(is_selected=False)
        )
        s.flush()
        existing = s.execute(
            select(OpenRouterConfig).where(OpenRouterConfig.model_id == model.model_id)
        ).scalar_one_or_none()
        if existing is not None:
            existing.model_name = model.name
            existing.context_length = model.context_length
            existing.prompt_price_per_token = model.prompt_price
            existing.completion_price_per_token = model.completion_price
            existing.is_selected = True
            existing.updated_by = updated_by
        else:
            s.add(OpenRouterConfig(
                model_id=model.model_id,
                model_name=model.name,
                context_length=model.context_length,
                prompt_price_per_token=model.prompt_price,
                completion_price_per_token=model.completion_price,
                is_selected=True,
                updated_by=updated_by,
            ))
