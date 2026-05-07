"""Calibration-fade strategy.

Trades on the gap between contract price and empirical win rate at that price,
using a user-supplied calibration curve (typically derived from the
``win_rate_by_price`` analysis). Buys when the curve says the contract is
underpriced by at least ``min_edge``, and sells held positions when it is
overpriced by the same margin.

The calibration is supplied as an explicit list of ``(price, actual_win_rate)``
points. There is no built-in default — running without one would amount to
silently mis-calibrated trading.
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy, StrategyConfig

from src.trading.risk import RiskManager


def interpolate_actual(price: float, points: tuple[tuple[float, float], ...]) -> float:
    """Linearly interpolate the actual win rate at ``price`` from sorted points.

    ``points`` must be sorted ascending by price. Outside the range, the
    nearest endpoint value is used (no extrapolation).
    """
    if not points:
        raise ValueError("calibration_points is empty")
    if price <= points[0][0]:
        return points[0][1]
    if price >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= price <= x1:
            if x1 == x0:
                return y0
            t = (price - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return points[-1][1]


class CalibrationFadeConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    calibration_points: tuple[tuple[float, float], ...]
    min_edge: float = 0.05


class CalibrationFadeStrategy(Strategy):
    def __init__(self, config: CalibrationFadeConfig, risk: RiskManager) -> None:
        if not config.calibration_points:
            raise ValueError("calibration_points must contain at least one point")
        if config.min_edge <= 0:
            raise ValueError("min_edge must be positive")
        sorted_points = tuple(sorted(config.calibration_points, key=lambda p: p[0]))
        for x, y in sorted_points:
            if not (0.0 <= x <= 1.0) or not (0.0 <= y <= 1.0):
                raise ValueError(f"calibration point out of [0,1]: ({x}, {y})")
        super().__init__(config)
        self._points = sorted_points
        self.risk = risk
        self.instrument = None

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        self.subscribe_trade_ticks(self.config.instrument_id)

    def on_trade_tick(self, tick: TradeTick) -> None:
        price = float(tick.price)
        actual = interpolate_actual(price, self._points)
        edge = actual - price

        positions = self.cache.positions_open(instrument_id=self.config.instrument_id)
        equity = float(
            self.portfolio.account(self.instrument.venue).balance_total(self.instrument.quote_currency)
        )

        has_position = bool(positions)

        if not has_position and edge >= self.config.min_edge:
            size = self.risk.order_size(equity, price)
            if size <= 0:
                return
            qty = self.instrument.make_qty(Decimal(str(size)))
            if qty.as_double() <= 0:
                return
            order = self.order_factory.market(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.BUY,
                quantity=qty,
                time_in_force=TimeInForce.IOC,
            )
            self.submit_order(order)
        elif has_position and edge <= -self.config.min_edge:
            for pos in positions:
                qty = Quantity.from_str(str(pos.quantity))
                order = self.order_factory.market(
                    instrument_id=self.config.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=qty,
                    time_in_force=TimeInForce.IOC,
                )
                self.submit_order(order)
