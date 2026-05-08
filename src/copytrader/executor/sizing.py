"""Compute desired USD size for a copy signal."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CopyConfig:
    """How much to copy a source signal."""

    fixed_usd: float = 5.0
    follow_pct: float = 0.0  # if >0, copy `follow_pct` of source notional capped by fixed
    max_usd: float = 50.0


def desired_usd(source_size_tokens: float, source_price: float, cfg: CopyConfig) -> float:
    if cfg.follow_pct > 0:
        source_notional = source_size_tokens * source_price
        usd = source_notional * cfg.follow_pct
    else:
        usd = cfg.fixed_usd
    return min(usd, cfg.max_usd)
