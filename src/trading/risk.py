"""Risk caps for trading.

Limits are required (no defaults that could enable trading by accident). The
manager is consulted before every order to size or block it. The same object
is used in backtest, paper, and live modes so behaviour is identical.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimits:
    """Hard caps applied to every order. All percentages are 0-1, not 0-100."""

    max_order_pct: float
    max_position_pct: float
    max_daily_loss_pct: float

    def __post_init__(self) -> None:
        for name in ("max_order_pct", "max_position_pct", "max_daily_loss_pct"):
            v = getattr(self, name)
            if not (0 < v <= 1):
                raise ValueError(f"{name} must be in (0, 1], got {v}")
        if self.max_order_pct > self.max_position_pct:
            raise ValueError("max_order_pct cannot exceed max_position_pct")


class RiskManager:
    def __init__(self, limits: RiskLimits, starting_cash: float) -> None:
        self.limits = limits
        self.starting_cash = float(starting_cash)
        self._daily_loss = 0.0
        self._halted = False

    @property
    def halted(self) -> bool:
        return self._halted

    def order_size(self, equity: float, price: float) -> float:
        """Return the max order size (in tokens) allowed at this price.

        Returns 0 if trading is halted or the cap would round to zero.
        """
        if self._halted or price <= 0:
            return 0.0
        budget = equity * self.limits.max_order_pct
        return budget / price

    def position_cap_size(self, equity: float, price: float) -> float:
        if price <= 0:
            return 0.0
        return (equity * self.limits.max_position_pct) / price

    def record_pnl(self, pnl_delta: float) -> None:
        self._daily_loss += min(pnl_delta, 0.0) * -1.0
        if self._daily_loss / self.starting_cash >= self.limits.max_daily_loss_pct:
            self._halted = True

    def reset_daily(self) -> None:
        self._daily_loss = 0.0
