"""Lease expiry measures staleness from heartbeat, not started_at (E-9)."""
from __future__ import annotations

from sqlalchemy import text

from copytrader.db.engine import get_session
from copytrader.jobs.queue import claim, enqueue, get_job, heartbeat


def test_long_job_with_recent_heartbeat_not_expired(fresh_db) -> None:
    jid = enqueue("backfill", {"window": 90})
    with get_session() as s:
        s.execute(text(
            "UPDATE jobs SET status='RUNNING', "
            "started_at = NOW() - INTERVAL '2 hours', "
            "heartbeat_at = NOW(), worker_id='alive' WHERE id=:id"
        ), {"id": jid})

    with claim("other") as job:
        assert job is None  # nothing PENDING to claim
    # Old started_at but fresh heartbeat → must NOT be expired.
    assert get_job(jid).status == "RUNNING"


def test_old_heartbeat_is_expired(fresh_db) -> None:
    jid = enqueue("backfill", {})
    with get_session() as s:
        s.execute(text(
            "UPDATE jobs SET status='RUNNING', "
            "started_at = NOW() - INTERVAL '2 hours', "
            "heartbeat_at = NOW() - INTERVAL '1 hour', worker_id='dead' WHERE id=:id"
        ), {"id": jid})

    with claim("other") as job:
        assert job is None
    final = get_job(jid)
    assert final.status == "FAILED"
    assert "lease expired" in (final.error_text or "")


def test_heartbeat_bumps_timestamp(fresh_db) -> None:
    jid = enqueue("backfill", {})
    with get_session() as s:
        s.execute(text(
            "UPDATE jobs SET status='RUNNING', "
            "started_at = NOW() - INTERVAL '2 hours', "
            "heartbeat_at = NOW() - INTERVAL '2 hours', worker_id='w' WHERE id=:id"
        ), {"id": jid})
    heartbeat(jid)  # operator/handler beat refreshes liveness
    with claim("other") as job:
        assert job is None
    assert get_job(jid).status == "RUNNING"
