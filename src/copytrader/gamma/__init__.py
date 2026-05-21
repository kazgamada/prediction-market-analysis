"""Polymarket Gamma API client.

Public read-only API (no auth required). Used to fetch market resolutions
(payouts) so we can compute resolve-aware PnL beyond Phase 0's closed-trade
accounting.

API docs: https://docs.polymarket.com/#gamma-api
"""
from copytrader.gamma.client import GammaClient
from copytrader.gamma.models import MarketInfo, MarketResolution

__all__ = ["GammaClient", "MarketInfo", "MarketResolution"]
