"""Rollout promotion criteria evaluator.

Evaluates whether the current phase is ready to promote to the next
(A→B→C→D). Returns a structured result that can be displayed in the
Execute page and used by the meta-autonomy scheduler.

条件 (7件, すべて満たせば昇格可):
  1. elapsed_days    >= rollout_phase_duration_days (Phase A: 28d)
  2. roi_pct         >= rollout_promote_roi_pct     (default: +3%)
  3. drawdown_pct    <= rollout_promote_max_dd_pct  (default: 8%)
  4. win_rate_pct    >= rollout_promote_min_wr_pct  (default: 52%)
  5. divergence_pct  <= rollout_promote_max_div_pct (default: 20%)
  6. avg_latency_ms  <= rollout_promote_max_lat_ms  (default: 3000)
  7. kill_switch_test_days_ago <= rollout_promote_ks_test_within_days (default: 7)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from copytrader.db import settings_table
from copytrader.db.engine import get_session
from copytrader.db.models import AuditLog, Execution, TradePnl


def _get(key: str, default):
    try:
        v = settings_table.get(key)
    except Exception:  # noqa: BLE001
        return default
    return v if v is not None else default


@dataclass
class PromotionCriterion:
    label: str
    ok: bool
    current_value: str


@dataclass
class PromotionResult:
    phase: str
    elapsed_days: int
    can_promote: bool
    criteria: list[PromotionCriterion] = field(default_factory=list)


def _elapsed_days() -> int:
    raw = _get("rollout_started_at", None)
    if not raw:
        return 0
    try:
        if isinstance(raw, (int, float)):
            started = datetime.fromtimestamp(float(raw), tz=UTC)
        else:
            s = str(raw).rstrip("Z")
            started = datetime.fromisoformat(s).replace(tzinfo=UTC)
        return max(0, (datetime.now(UTC) - started).days)
    except Exception:  # noqa: BLE001
        return 0


def _roi_and_wr(since: datetime) -> tuple[float, float]:
    """Return (roi_pct, win_rate_pct) since the given timestamp."""
    try:
        with get_session() as s:
            rows = s.execute(
                select(TradePnl.realized_usdc).where(TradePnl.ts >= since)
            ).scalars().all()
        if not rows:
            return 0.0, 0.0
        total = sum(float(r) for r in rows)
        wins = sum(1 for r in rows if float(r) > 0)
        usdc_balance = float(_get("usdc_balance_cache", 0) or 0)
        roi = (total / usdc_balance * 100) if usdc_balance > 0 else 0.0
        wr = (wins / len(rows) * 100) if rows else 0.0
        return roi, wr
    except Exception:  # noqa: BLE001
        return 0.0, 0.0


def _max_drawdown_pct(since: datetime) -> float:
    """Compute max drawdown as % of peak cumulative PnL since timestamp."""
    try:
        with get_session() as s:
            rows = s.execute(
                select(TradePnl.realized_usdc, TradePnl.ts)
                .where(TradePnl.ts >= since)
                .order_by(TradePnl.ts)
            ).all()
        if not rows:
            return 0.0
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for r_usdc, _ in rows:
            cum += float(r_usdc)
            if cum > peak:
                peak = cum
            if peak > 0:
                dd = (peak - cum) / peak * 100
                if dd > max_dd:
                    max_dd = dd
        return max_dd
    except Exception:  # noqa: BLE001
        return 0.0


def _avg_latency_ms() -> float:
    """Average signal-to-place latency over last 100 executions."""
    try:
        with get_session() as s:
            val = s.execute(
                select(func.avg(Execution.signal_to_place_ms))
                .where(Execution.signal_to_place_ms.isnot(None))
                .order_by(Execution.placed_at.desc())
                .limit(100)
            ).scalar_one_or_none()
        return float(val) if val is not None else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def _kill_switch_test_days_ago() -> int | None:
    """Days since last kill switch test (actor=web or telegram, action=kill_switch_on→off).
    Returns None if no test found.
    """
    try:
        with get_session() as s:
            row = s.execute(
                select(AuditLog.ts)
                .where(AuditLog.action == "kill_switch_off")
                .order_by(AuditLog.ts.desc())
                .limit(1)
            ).scalar_one_or_none()
        if row is None:
            return None
        return (datetime.now(UTC) - row).days
    except Exception:  # noqa: BLE001
        return None


def _backtest_divergence_pct() -> float:
    """Estimate divergence between phase0 expected ROI and actual ROI.
    Returns 0.0 if not enough data.
    """
    try:
        from sqlalchemy import desc

        from copytrader.db.models import Job
        with get_session() as s:
            row = s.execute(
                select(Job)
                .where(Job.kind == "phase0")
                .where(Job.status == "SUCCEEDED")
                .order_by(desc(Job.finished_at))
                .limit(1)
            ).scalar_one_or_none()
        if not row or not row.result:
            return 0.0
        result = dict(row.result)
        agg = result.get("aggregate") or {}
        expected_roi = float(agg.get("median_roi") or 0)
        if expected_roi == 0:
            return 0.0
        # 実績 ROI: 直近 30d
        since = datetime.now(UTC) - timedelta(days=30)
        actual_roi, _ = _roi_and_wr(since)
        if expected_roi != 0:
            return abs((actual_roi - expected_roi) / abs(expected_roi) * 100)
        return 0.0
    except Exception:  # noqa: BLE001
        return 0.0


# フェーズごとの期間定義（日数）
_PHASE_DURATIONS = {"A": 28, "B": 28, "C": 56, "D": 9999}


def evaluate_promotion_criteria() -> PromotionResult:
    """昇格条件を評価して PromotionResult を返す。

    フェーズが 'D' の場合は昇格不要なので can_promote=False。
    """
    phase = str(_get("rollout_phase", "A") or "A")
    elapsed = _elapsed_days()
    phase_dur = _PHASE_DURATIONS.get(phase, 28)
    since = datetime.now(UTC) - timedelta(days=phase_dur)

    roi, wr = _roi_and_wr(since)
    dd = _max_drawdown_pct(since)
    lat = _avg_latency_ms()
    ks_days = _kill_switch_test_days_ago()

    # 閾値
    req_roi = float(_get("rollout_promote_roi_pct", 3.0))
    max_dd = float(_get("rollout_promote_max_dd_pct", 8.0))
    min_wr = float(_get("rollout_promote_min_wr_pct", 52.0))
    max_div = float(_get("rollout_promote_max_div_pct", 20.0))
    max_lat = float(_get("rollout_promote_max_lat_ms", 3000.0))
    ks_within = int(_get("rollout_promote_ks_test_within_days", 7))
    div = _backtest_divergence_pct()

    criteria = [
        PromotionCriterion(
            f"経過 ≥ {phase_dur}d",
            elapsed >= phase_dur,
            f"{elapsed}日",
        ),
        PromotionCriterion(
            f"ROI ≥ +{req_roi:.0f}%",
            roi >= req_roi,
            f"{roi:+.1f}%",
        ),
        PromotionCriterion(
            f"DD ≤ {max_dd:.0f}%",
            dd <= max_dd,
            f"-{dd:.1f}%",
        ),
        PromotionCriterion(
            f"勝率 ≥ {min_wr:.0f}%",
            wr >= min_wr,
            f"{wr:.1f}%",
        ),
        PromotionCriterion(
            f"乖離 ≤ {max_div:.0f}%",
            div <= max_div,
            f"{div:.1f}%",
        ),
        PromotionCriterion(
            f"Latency ≤ {max_lat:.0f}ms",
            lat <= max_lat if lat > 0 else True,
            f"{lat:.0f}ms" if lat > 0 else "N/A",
        ),
        PromotionCriterion(
            f"kill switch テスト ≤ {ks_within}d",
            ks_days is not None and ks_days <= ks_within,
            f"{ks_days}日前" if ks_days is not None else "未実施",
        ),
    ]

    can_promote = phase != "D" and all(c.ok for c in criteria)
    return PromotionResult(
        phase=phase,
        elapsed_days=elapsed,
        can_promote=can_promote,
        criteria=criteria,
    )
