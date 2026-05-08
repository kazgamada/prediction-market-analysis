"""Hard caps applied before every order. Same instance is used in paper and live."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone


@dataclass(frozen=True)
class RiskLimits:
    """All caps in USD unless noted. Percentages are 0-1."""

    max_order_usd: float
    max_position_usd_per_token: float
    max_total_exposure_usd: float
    max_daily_loss_usd: float
    max_concurrent_orders: int = 5
    max_orders_per_minute: int = 30

    def __post_init__(self) -> None:
        for name in (
            "max_order_usd",
            "max_position_usd_per_token",
            "max_total_exposure_usd",
            "max_daily_loss_usd",
        ):
            v = getattr(self, name)
            if v <= 0:
                raise ValueError(f"{name} must be > 0, got {v}")
        if self.max_order_usd > self.max_position_usd_per_token:
            raise ValueError("max_order_usd cannot exceed max_position_usd_per_token")


@dataclass
class RiskState:
    """Mutable counters; reset_daily() at UTC midnight."""

    daily_loss_usd: float = 0.0
    open_orders: int = 0
    realized_pnl_usd: float = 0.0
    halted: bool = False
    halt_reason: str | None = None
    today: date = datetime.now(timezone.utc).date()

    def maybe_roll_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self.today:
            self.today = today
            self.daily_loss_usd = 0.0


@dataclass
class SizingDecision:
    allowed: bool
    size_tokens: float
    reason: str


def decide_size(
    *,
    side: str,
    fill_price_estimate: float,
    desired_usd: float,
    current_position_usd: float,
    total_exposure_usd: float,
    limits: RiskLimits,
    state: RiskState,
) -> SizingDecision:
    """Compute the actual order size in tokens given desired USD and caps.

    Returns SizingDecision; if allowed=False, size_tokens is 0 and reason
    explains which cap blocked the order.
    """
    state.maybe_roll_day()
    if state.halted:
        return SizingDecision(False, 0.0, f"halted: {state.halt_reason}")
    if state.open_orders >= limits.max_concurrent_orders:
        return SizingDecision(False, 0.0, "max_concurrent_orders")
    if state.daily_loss_usd >= limits.max_daily_loss_usd:
        return SizingDecision(False, 0.0, "max_daily_loss_usd")
    if fill_price_estimate <= 0 or fill_price_estimate >= 1:
        return SizingDecision(False, 0.0, f"invalid price {fill_price_estimate}")

    # Cap by per-order USD
    capped_usd = min(desired_usd, limits.max_order_usd)

    # Cap by per-token position (only for BUY; SELL reduces position)
    if side.upper() == "BUY":
        room_in_token = max(0.0, limits.max_position_usd_per_token - current_position_usd)
        capped_usd = min(capped_usd, room_in_token)
        room_total = max(0.0, limits.max_total_exposure_usd - total_exposure_usd)
        capped_usd = min(capped_usd, room_total)

    if capped_usd <= 0:
        return SizingDecision(False, 0.0, "no headroom under caps")

    size_tokens = capped_usd / fill_price_estimate
    return SizingDecision(True, size_tokens, "ok")
