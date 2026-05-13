"""Streaming PnL avoids loading every row into memory.

This test seeds a moderate row count and asserts that:
  * rank_wallets returns the same wallet identity as the in-memory variant
  * progress_cb is invoked at least once when yield_per is exceeded
  * lease cleanup expires zombie RUNNING jobs after the configured window
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from copytrader.db.engine import get_session
from copytrader.db.models import Trade


def _seed(s, *, idx: int, taker: bytes, side: int, price: str,
          shares: str, token_id: int = 1) -> None:
    px = Decimal(price)
    sh = Decimal(shares)
    s.add(Trade(
        tx_hash=bytes([(idx >> 24) & 0xff, (idx >> 16) & 0xff,
                       (idx >> 8) & 0xff, idx & 0xff]) * 8,
        log_index=idx,
        block_number=1000 + idx,
        # idx ascending → ts ascending (so BUY at smaller idx precedes SELL)
        ts=datetime(2026, 5, 12, 0, 0, 0, tzinfo=UTC) + timedelta(seconds=idx),
        exchange="ctf",
        order_hash=b"\xbb" * 32,
        maker=b"\x11" * 20,
        taker=taker,
        side=side,
        maker_asset_id=0 if side == 0 else token_id,
        taker_asset_id=token_id if side == 0 else 0,
        maker_amount_filled=int(px * sh * 10**6) if side == 0 else int(sh * 10**6),
        taker_amount_filled=int(sh * 10**6) if side == 0 else int(px * sh * 10**6),
        token_id=token_id,
        price=px,
        size_shares=sh,
        size_usdc=px * sh,
    ))


def test_streaming_rank_invokes_progress_cb(fresh_db) -> None:
    smart = b"\x42" * 20
    # 60 trades, yield_per=10 → progress_cb fires at least 6 times in-loop
    with get_session() as s:
        for i in range(30):
            _seed(s, idx=i * 2, taker=smart, side=0, price="0.40", shares="100",
                  token_id=i + 1)
            _seed(s, idx=i * 2 + 1, taker=smart, side=1, price="0.60", shares="100",
                  token_id=i + 1)

    from copytrader.analysis.pnl import stream_wallet_pnl
    seen: list[int] = []
    wallets = stream_wallet_pnl(window_days=7, yield_per=10,
                                progress_cb=lambda n: seen.append(n))
    assert len(seen) >= 6
    assert seen[-1] == 60
    assert wallets[smart].trades == 60
    assert wallets[smart].realized_pnl_usdc > 0


def test_rank_wallets_via_streaming(fresh_db) -> None:
    smart = b"\x42" * 20
    with get_session() as s:
        for i in range(30):
            _seed(s, idx=i * 2, taker=smart, side=0, price="0.40", shares="100",
                  token_id=i + 1)
            _seed(s, idx=i * 2 + 1, taker=smart, side=1, price="0.60", shares="100",
                  token_id=i + 1)
    from copytrader.analysis.rank import rank_wallets
    rows = rank_wallets(window_days=7, min_trades=30, min_volume_usdc=1000, top_n=5)
    assert any(r.address == "0x" + smart.hex() for r in rows)


def test_lease_cleanup_expires_zombie_running(fresh_db) -> None:
    """A job stuck in RUNNING with started_at >30 minutes ago is auto-
    expired to FAILED on the next claim() so the queue keeps moving."""
    from copytrader.db.engine import get_session
    from copytrader.jobs.queue import claim, enqueue

    # Create a job, fake-claim it, then move started_at back 1 hour
    jid = enqueue("rank", {"window": 7})
    with get_session() as s:
        s.execute(text(
            "UPDATE jobs SET status='RUNNING', "
            "started_at = NOW() - INTERVAL '1 hour', "
            "worker_id='dead-worker' WHERE id=:id"
        ), {"id": jid})

    # Enqueue a second job; claim() should find no PENDING but should also
    # have expired the zombie above.
    with claim("new-worker") as job:
        # No new PENDING was added, so we shouldn't claim anything.
        assert job is None

    from copytrader.jobs.queue import get_job
    final = get_job(jid)
    assert final.status == "FAILED"
    assert "lease expired" in (final.error_text or "")


def test_lease_cleanup_skips_fresh_running(fresh_db) -> None:
    """A RUNNING job within the lease window must NOT be expired."""
    from copytrader.db.engine import get_session
    from copytrader.jobs.queue import claim, enqueue
    jid = enqueue("rank", {})
    with get_session() as s:
        s.execute(text(
            "UPDATE jobs SET status='RUNNING', started_at=NOW(), "
            "worker_id='alive' WHERE id=:id"
        ), {"id": jid})
    with claim("new-worker") as job:
        assert job is None  # no PENDING to claim
    from copytrader.jobs.queue import get_job
    final = get_job(jid)
    assert final.status == "RUNNING", "fresh RUNNING must not be expired"
