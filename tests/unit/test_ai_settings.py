"""AI / OpenRouter ヘルパーの単体テスト（DB 不要・純粋ロジックのみ）。"""
from __future__ import annotations

from decimal import Decimal

import pytest

from copytrader.ai.app_settings import mask_secret
from copytrader.ai.openrouter import parse_models
from copytrader.ai.resolve_model import (
    ANTHROPIC_BASE_URL,
    OPENROUTER_BASE_URL,
    resolve_api_key,
    resolve_model,
)
from copytrader.ai.usage import estimate_cost

# --- マスク表示 ---------------------------------------------------------------

def test_mask_secret_empty_shows_unset() -> None:
    assert mask_secret(None) == "未設定"
    assert mask_secret("") == "未設定"


def test_mask_secret_keeps_prefix_and_tail() -> None:
    masked = mask_secret("sk-or-v1-abcdef1234567890abcd")
    assert masked.startswith("sk-or-v1-")
    assert masked.endswith("abcd")
    assert "•" in masked
    # 中央の生値は露出しない
    assert "abcdef12" not in masked


def test_mask_secret_short_value_fully_masked() -> None:
    masked = mask_secret("short")
    assert masked == "•" * 8


# --- モデルパース -------------------------------------------------------------

def test_parse_models_extracts_fields_and_sorts() -> None:
    payload = {
        "data": [
            {
                "id": "z/model-b",
                "name": "Zebra Model",
                "context_length": 8000,
                "pricing": {"prompt": "0.000003", "completion": "0.000015"},
            },
            {
                "id": "a/model-a",
                "name": "Alpha Model",
                "context_length": 200000,
                "pricing": {"prompt": "0.0000005", "completion": "0.0000025"},
            },
        ]
    }
    models = parse_models(payload)
    assert [m.name for m in models] == ["Alpha Model", "Zebra Model"]
    alpha = models[0]
    assert alpha.model_id == "a/model-a"
    assert alpha.context_length == 200000
    assert alpha.prompt_price == Decimal("0.0000005")
    assert alpha.completion_price == Decimal("0.0000025")


def test_parse_models_skips_blank_ids_and_handles_missing_pricing() -> None:
    payload = {"data": [{"id": "", "name": "x"}, {"id": "ok/model", "name": "OK"}]}
    models = parse_models(payload)
    assert len(models) == 1
    assert models[0].model_id == "ok/model"
    assert models[0].prompt_price is None
    assert models[0].context_length is None


# --- コスト推定 ---------------------------------------------------------------

def test_estimate_cost_basic() -> None:
    cost = estimate_cost(1000, 500, Decimal("0.000003"), Decimal("0.000015"))
    # 1000*3e-6 + 500*15e-6 = 0.003 + 0.0075 = 0.0105
    assert cost == Decimal("0.0105000")


def test_estimate_cost_handles_none_prices() -> None:
    assert estimate_cost(100, 100, None, None) == Decimal(0)


# --- API キー / モデル解決のフォールバック順 ----------------------------------

def test_resolve_api_key_prefers_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("copytrader.ai.resolve_model.get_app_setting",
                        lambda *a, **k: "sk-or-db", raising=False)
    from copytrader.config import settings
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-env")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-env")
    assert resolve_api_key() == "sk-or-db"


def test_resolve_api_key_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("copytrader.ai.resolve_model.get_app_setting",
                        lambda *a, **k: None, raising=False)
    from copytrader.config import settings
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-env")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-env")
    assert resolve_api_key() == "sk-or-env"


def test_resolve_api_key_final_fallback_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("copytrader.ai.resolve_model.get_app_setting",
                        lambda *a, **k: None, raising=False)
    from copytrader.config import settings
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-env")
    assert resolve_api_key() == "sk-ant-env"


def test_resolve_model_openrouter_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("copytrader.ai.resolve_model.get_app_setting",
                        lambda *a, **k: "sk-or-db", raising=False)
    from copytrader.config import settings
    monkeypatch.setattr(settings, "openrouter_model", "")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr("copytrader.ai.openrouter.get_selected_config",
                        lambda: None, raising=False)
    rm = resolve_model()
    assert rm.provider == "openrouter"
    assert rm.base_url == OPENROUTER_BASE_URL
    assert rm.api_key == "sk-or-db"


def test_resolve_model_env_model_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("copytrader.ai.resolve_model.get_app_setting",
                        lambda *a, **k: None, raising=False)
    from copytrader.config import settings
    monkeypatch.setattr(settings, "openrouter_model", "forced/model")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant")
    rm = resolve_model()
    # env モデルが最優先で採用される
    assert rm.model_id == "forced/model"
    # キーが OpenRouter 系に無いので Anthropic フォールバック
    assert rm.provider == "anthropic"
    assert rm.base_url == ANTHROPIC_BASE_URL
