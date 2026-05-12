"""Wallet ranking by realized PnL within the window."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from copytrader.analysis.pnl import compute_wallet_pnl, load_trades


@dataclass
class RankedWallet:
    address: str  # hex 0x...
    trades: int
    volume_usdc: Decimal
    realized_pnl_usdc: Decimal
    win_rate: Decimal | None


def rank_wallets(
    *,
    window_days: int,
    min_trades: int = 30,
    min_volume_usdc: float = 5_000.0,
    top_n: int = 50,
) -> list[RankedWallet]:
    trades = load_trades(window_days)
    wallets = compute_wallet_pnl(trades)
    out: list[RankedWallet] = []
    for addr, wp in wallets.items():
        if wp.trades < min_trades:
            continue
        if wp.volume_usdc < Decimal(str(min_volume_usdc)):
            continue
        out.append(RankedWallet(
            address="0x" + addr.hex(),
            trades=wp.trades,
            volume_usdc=wp.volume_usdc,
            realized_pnl_usdc=wp.realized_pnl_usdc,
            win_rate=wp.win_rate,
        ))
    out.sort(key=lambda r: r.realized_pnl_usdc, reverse=True)
    return out[:top_n]
