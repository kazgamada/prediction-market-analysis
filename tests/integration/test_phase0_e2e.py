"""Phase 0 end-to-end with seeded trades (no RPC).

Seeds the trades table by hand, runs rank + replay handlers directly,
and asserts that the result is well-formed. Skips the backfill step
because that requires real RPC; the indexer process is what fills
trades in production.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from copytrader.db.engine import get_session
from copytrader.db.models import Trade


def _seed_trade(
    s, *, ts: datetime, taker: bytes, token_id: int, side: int,
    price: Decimal, shares: Decimal, idx: int,
) -> None:
    s.add(Trade(
        tx_hash=b"\xaa" * 32, log_index=idx, block_number=1_000 + idx, ts=ts,
        exchange="ctf",
        order_hash=b"\xbb" * 32,
        maker=b"\x11" * 20,
        taker=taker,
        side=side,
        maker_asset_id=0 if side == 0 else token_id,
        taker_asset_id=token_id if side == 0 else 0,
        maker_amount_filled=int(price * shares * 10**6) if side == 0 else int(shares * 10**6),
        taker_amount_filled=int(shares * 10**6) if side == 0 else int(price * shares * 10**6),
        token_id=token_id,
        price=price,
        size_shares=shares,
        size_usdc=price * shares,
    ))


def _seed_winning_wallet(fresh_db) -> bytes:
    """Seed one wallet with a profitable trade pattern + plenty of follow-on
    market activity so replay has reference prices to fill at.
    """
    smart = b"\x42" * 20
    base = datetime.now(UTC) - timedelta(days=3)
    with get_session() as s:
        idx = 0
        for token in range(1, 50):  # 49 different markets, 49+ trades
            # Smart money buys at 0.40
            _seed_trade(
                s, ts=base + timedelta(seconds=idx),
                taker=smart, token_id=token, side=0,
                price=Decimal("0.40"), shares=Decimal("250"), idx=idx,
            )
            idx += 1
            # Other taker provides a fill 60s later at 0.41 (reference price)
            _seed_trade(
                s, ts=base + timedelta(seconds=idx + 60),
                taker=b"\x77" * 20, token_id=token, side=0,
                price=Decimal("0.41"), shares=Decimal("100"), idx=idx,
            )
            idx += 1
            # Smart money sells at 0.60 a day later
            _seed_trade(
                s, ts=base + timedelta(days=1, seconds=idx),
                taker=smart, token_id=token, side=1,
                price=Decimal("0.60"), shares=Decimal("250"), idx=idx,
            )
            idx += 1
            # Reference fill 60s later at 0.59
            _seed_trade(
                s, ts=base + timedelta(days=1, seconds=idx + 60),
                taker=b"\x78" * 20, token_id=token, side=1,
                price=Decimal("0.59"), shares=Decimal("100"), idx=idx,
            )
            idx += 1
    return smart


def test_rank_finds_winning_wallet(fresh_db) -> None:
    smart = _seed_winning_wallet(fresh_db)
    from copytrader.analysis.rank import rank_wallets
    rows = rank_wallets(window_days=7, min_trades=30, min_volume_usdc=1000, top_n=10)
    addrs = [r.address for r in rows]
    assert "0x" + smart.hex() in addrs
    smart_row = next(r for r in rows if r.address == "0x" + smart.hex())
    assert smart_row.realized_pnl_usdc > 0


def test_replay_profitable_copy(fresh_db) -> None:
    smart = _seed_winning_wallet(fresh_db)
    from copytrader.analysis.replay import replay_copytrade
    r = replay_copytrade(
        window_days=7,
        top_wallets=["0x" + smart.hex()],
        delay_seconds=30,
        copy_usd_per_trade=50,
    )
    assert r.signals_total == 98  # 49 buys + 49 sells from smart wallet
    assert r.signals_executed > 0
    # Following a winning wallet (buys at 0.41, sells at 0.59) should profit.
    assert r.realized_pnl_usdc > 0
    assert r.roi_pct > 0


@pytest.mark.parametrize("delay", [30, 60, 120])
def test_replay_handles_various_delays(fresh_db, delay) -> None:
    smart = _seed_winning_wallet(fresh_db)
    from copytrader.analysis.replay import replay_copytrade
    r = replay_copytrade(
        window_days=7,
        top_wallets=["0x" + smart.hex()],
        delay_seconds=delay,
        copy_usd_per_trade=50,
    )
    assert r.delay_seconds == delay
    assert r.signals_total > 0


def test_phase0_handler_end_to_end(fresh_db, monkeypatch) -> None:
    smart = _seed_winning_wallet(fresh_db)
    # Stub the backfill step (requires real RPC); phase0 catches & continues.
    from copytrader.jobs import handlers as H
    monkeypatch.setattr(H, "handle_backfill", lambda h: h.log("backfill skipped"))

    from copytrader.jobs.queue import claim, enqueue
    jid = enqueue("phase0", {
        "window": 7, "watchlist_top": 5, "delays": [30],
        "copy_usd_per_trade": 50,
    })
    with claim("test-worker") as job:
        assert job is not None
        from copytrader.jobs.queue import JobHandle
        from copytrader.jobs.handlers import HANDLERS
        HANDLERS["phase0"](JobHandle(job))

    from copytrader.jobs.queue import get_job
    final = get_job(jid)
    assert final.status == "SUCCEEDED"
    assert "0x" + smart.hex() in (final.result or {}).get("top_wallets", [])
    replay_per_delay = (final.result or {}).get("replay", {}).get("per_delay", [])
    assert len(replay_per_delay) == 1
    assert int(replay_per_delay[0]["signals_executed"]) > 0
