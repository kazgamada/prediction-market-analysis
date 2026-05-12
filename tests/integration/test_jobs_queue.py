"""Job queue: enqueue, idempotency, claim, success/failure transitions."""
from __future__ import annotations

import pytest

from copytrader.jobs.queue import (
    JobHandle,
    append_log,
    claim,
    enqueue,
    get_job,
    set_progress,
    set_result,
    wait_for,
)


def test_enqueue_returns_id(fresh_db) -> None:
    jid = enqueue("rank", {"window": 30})
    j = get_job(jid)
    assert j is not None
    assert j.kind == "rank"
    assert j.status == "PENDING"
    assert j.params == {"window": 30}


def test_idempotency_returns_same_id(fresh_db) -> None:
    a = enqueue("phase0", {"window": 30}, idempotency_key="phase0:2026-05-12")
    b = enqueue("phase0", {"window": 30}, idempotency_key="phase0:2026-05-12")
    assert a == b


def test_claim_marks_running_then_succeeded(fresh_db) -> None:
    jid = enqueue("rank", {"window": 7})
    with claim("test-worker") as job:
        assert job is not None
        assert job.id == jid
        assert job.status == "RUNNING"
        set_progress(job.id, {"phase": "halfway"})
        set_result(job.id, {"ok": True})
    final = get_job(jid)
    assert final.status == "SUCCEEDED"
    assert final.result == {"ok": True}
    assert final.progress == {"phase": "halfway"}


def test_claim_exception_marks_failed(fresh_db) -> None:
    jid = enqueue("rank", {})
    with pytest.raises(RuntimeError):
        with claim("test-worker") as job:
            assert job is not None
            raise RuntimeError("boom")
    final = get_job(jid)
    assert final.status == "FAILED"
    assert "boom" in (final.error_text or "")


def test_claim_returns_none_when_empty(fresh_db) -> None:
    with claim("idle") as job:
        assert job is None


def test_claim_skip_locked_runs_one_at_a_time(fresh_db) -> None:
    """Two `claim()` blocks in sequence should each pick a different job."""
    a = enqueue("rank", {"n": 1})
    b = enqueue("rank", {"n": 2})

    seen = []
    with claim("w1") as j1:
        seen.append(j1.id)
        # Re-entering inside the open transaction with a fresh session
        # should still find the *other* pending job.
        with claim("w2") as j2:
            assert j2 is not None
            seen.append(j2.id)
    assert sorted(seen) == sorted([a, b])


def test_append_log_visible(fresh_db) -> None:
    jid = enqueue("rank", {})
    append_log(jid, "hello", level=20)
    append_log(jid, "world", level=30)

    from sqlalchemy import select

    from copytrader.db.engine import get_session
    from copytrader.db.models import JobLog
    with get_session() as s:
        rows = s.execute(
            select(JobLog).where(JobLog.job_id == jid).order_by(JobLog.id)
        ).scalars().all()
        assert [r.message for r in rows] == ["hello", "world"]


def test_job_handle_helpers(fresh_db) -> None:
    jid = enqueue("rank", {"x": 1})
    with claim("test") as job:
        h = JobHandle(job)
        assert h.params == {"x": 1}
        h.log("step a")
        h.progress({"done": 0.5})
        h.result({"answer": 42})
    final = get_job(jid)
    assert final.result == {"answer": 42}
    assert final.progress == {"done": 0.5}


def test_wait_for_succeeded(fresh_db) -> None:
    import threading
    jid = enqueue("rank", {})

    def worker() -> None:
        with claim("bg") as job:
            assert job is not None
            JobHandle(job).result({"ok": True})

    t = threading.Thread(target=worker)
    t.start()
    j = wait_for(jid, poll_s=0.1, timeout_s=5)
    t.join()
    assert j.status == "SUCCEEDED"


def test_wait_for_raises_on_failure(fresh_db) -> None:
    import threading
    jid = enqueue("rank", {})

    def worker() -> None:
        try:
            with claim("bg") as job:
                assert job is not None
                raise ValueError("bad")
        except ValueError:
            pass

    t = threading.Thread(target=worker)
    t.start()
    with pytest.raises(RuntimeError, match="FAILED"):
        wait_for(jid, poll_s=0.1, timeout_s=5)
    t.join()
