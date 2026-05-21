"""Gamma API response dataclasses."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class MarketInfo:
    """Minimal subset of /markets fields we use."""
    condition_id: bytes               # 0x... hex decoded to bytes (32 bytes)
    slug: str
    question: str
    closed: bool
    resolved: bool
    end_date: datetime | None
    volume_24h: Decimal
    liquidity: Decimal


@dataclass(frozen=True)
class MarketResolution:
    condition_id: bytes
    outcome: int                      # 0=No, 1=Yes (or index into outcomes for multi)
    payout_per_share: Decimal         # typically 1 or 0
    resolved_at: datetime
