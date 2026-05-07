"""Build a nautilus BinaryOption instrument from local Polymarket market data.

Polymarket binary option markets trade outcome tokens between 0 and 1 USDC.
For backtesting we don't need API-fetched fee schedules — both maker and taker
fees default to zero (configurable per-backtest if needed). Tick size is set
to 0.01 by default which matches Polymarket's coarsest tick; markets with
finer ticks can be overridden by passing tick_size explicitly.
"""

from __future__ import annotations

import time
from decimal import Decimal

import pandas as pd

from nautilus_trader.adapters.polymarket.common.constants import POLYMARKET_VENUE  # noqa: F401
from nautilus_trader.adapters.polymarket.common.parsing import (
    get_polymarket_instrument_id,
    get_polymarket_token_id,
    pUSD,
)
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.instruments import BinaryOption
from nautilus_trader.model.objects import Price, Quantity


def build_binary_option(
    condition_id: str,
    token_id: str,
    question: str,
    outcome: str = "YES",
    end_date_iso: str | None = None,
    tick_size: str = "0.01",
    maker_fee: float = 0.0,
    taker_fee: float = 0.0,
) -> BinaryOption:
    """Construct a BinaryOption instrument without hitting the Polymarket API."""
    instrument_id = get_polymarket_instrument_id(condition_id, token_id)
    raw_symbol = Symbol(get_polymarket_token_id(instrument_id))

    price_increment = Price.from_str(tick_size)
    size_increment = Quantity.from_str("0.000001")

    if end_date_iso:
        expiration_ns = pd.Timestamp(end_date_iso).value
    else:
        expiration_ns = (pd.Timestamp.now(tz="UTC") + pd.DateOffset(years=10)).value

    ts_init = time.time_ns()

    return BinaryOption(
        instrument_id=instrument_id,
        raw_symbol=raw_symbol,
        outcome=outcome,
        description=question,
        asset_class=AssetClass.ALTERNATIVE,
        currency=pUSD,
        price_increment=price_increment,
        price_precision=price_increment.precision,
        size_increment=size_increment,
        size_precision=size_increment.precision,
        activation_ns=0,
        expiration_ns=expiration_ns,
        max_quantity=None,
        min_quantity=None,
        maker_fee=Decimal(str(maker_fee)),
        taker_fee=Decimal(str(taker_fee)),
        ts_event=ts_init,
        ts_init=ts_init,
        info={"condition_id": condition_id, "token_id": token_id},
    )
