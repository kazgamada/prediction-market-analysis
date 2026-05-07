"""Trivial threshold strategy: buy when price <= buy_below, sell when >= sell_above.

Acts as a smoke-test strategy for the framework. Real strategies derived from
the existing analyses (calibration fade, longshot fade) live in sibling files
and follow the same Strategy / RiskManager wiring.
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy, StrategyConfig

from src.trading.risk import RiskManager


class ThresholdConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    buy_below: float
    sell_above: float


class ThresholdStrategy(Strategy):
    def __init__(self, config: ThresholdConfig, risk: RiskManager) -> None:
        super().__init__(config)
        self.risk = risk
        self.instrument = None

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        self.subscribe_trade_ticks(self.config.instrument_id)

    def on_trade_tick(self, tick: TradeTick) -> None:
        price = float(tick.price)
        position = self.cache.positions_open(instrument_id=self.config.instrument_id)
        equity = float(self.portfolio.account(self.instrument.venue).balance_total(self.instrument.quote_currency))

        has_position = bool(position)

        if not has_position and price <= self.config.buy_below:
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
        elif has_position and price >= self.config.sell_above:
            for pos in position:
                qty = Quantity.from_str(str(pos.quantity))
                order = self.order_factory.market(
                    instrument_id=self.config.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=qty,
                    time_in_force=TimeInForce.IOC,
                )
                self.submit_order(order)
