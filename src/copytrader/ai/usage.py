"""AI 使用量ログの記録とコスト集計（AUDIT.md E / F）。

- `log_usage()`: 各 AI 呼び出し後にトークン数・推定コストを記録
- `cost_summary()`: 過去 N 日の合計コスト・トークン・モデル別内訳を返す
"""
from __future__ import annotations

import logging
import uuid as _uuid_mod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from copytrader.db.engine import get_session
from copytrader.db.models import AiUsageLog

log = logging.getLogger(__name__)


def estimate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    prompt_price: Decimal | None,
    completion_price: Decimal | None,
) -> Decimal:
    """トークン単価（USD/token）からコスト（USD）を推定する。"""
    pp = prompt_price or Decimal(0)
    cp = completion_price or Decimal(0)
    return pp * Decimal(prompt_tokens) + cp * Decimal(completion_tokens)


def log_usage(
    *,
    model_id: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    estimated_cost_usd: Decimal | None = None,
    user_id: _uuid_mod.UUID | None = None,
    endpoint: str | None = None,
    success: bool = True,
) -> None:
    """1 回の AI 呼び出しを `ai_usage_log` に記録する。失敗しても例外を投げない。"""
    try:
        with get_session() as s:
            s.add(AiUsageLog(
                user_id=user_id,
                model_id=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                estimated_cost_usd=estimated_cost_usd,
                endpoint=endpoint,
                success=success,
            ))
    except Exception:  # noqa: BLE001
        log.warning("ai_usage_log への記録に失敗", exc_info=True)


@dataclass
class CostSummary:
    days: int
    total_cost_usd: Decimal
    total_tokens: int
    by_model: list[dict]  # [{model_id, cost_usd, tokens, calls}]


def cost_summary(days: int = 30) -> CostSummary:
    """過去 N 日の合計コスト・トークンとモデル別内訳を返す（AUDIT.md E）。"""
    since = datetime.now(UTC) - timedelta(days=days)
    with get_session() as s:
        total_cost = s.execute(
            select(func.coalesce(func.sum(AiUsageLog.estimated_cost_usd), 0))
            .where(AiUsageLog.created_at >= since)
        ).scalar_one()
        total_tokens = s.execute(
            select(func.coalesce(func.sum(AiUsageLog.total_tokens), 0))
            .where(AiUsageLog.created_at >= since)
        ).scalar_one()
        rows = s.execute(
            select(
                AiUsageLog.model_id,
                func.coalesce(func.sum(AiUsageLog.estimated_cost_usd), 0).label("cost"),
                func.coalesce(func.sum(AiUsageLog.total_tokens), 0).label("tokens"),
                func.count().label("calls"),
            )
            .where(AiUsageLog.created_at >= since)
            .group_by(AiUsageLog.model_id)
            .order_by(func.coalesce(func.sum(AiUsageLog.estimated_cost_usd), 0).desc())
        ).all()
    by_model = [
        {
            "model_id": r.model_id,
            "cost_usd": Decimal(str(r.cost)),
            "tokens": int(r.tokens),
            "calls": int(r.calls),
        }
        for r in rows
    ]
    return CostSummary(
        days=days,
        total_cost_usd=Decimal(str(total_cost)),
        total_tokens=int(total_tokens),
        by_model=by_model,
    )
