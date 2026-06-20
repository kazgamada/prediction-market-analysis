"""Test job queue idempotency, claim, progress, FAILED handling."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from copytrader.db.models import Job

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(
    job_id: int = 1,
    kind: str = "backfill",
    status: str = "PENDING",
    idempotency_key: str | None = None,
) -> Job:
    j = Job(
        kind=kind,
        params={"window": 7},
        idempotency_key=idempotency_key,
    )
    j.id = job_id
    j.status = status
    j.created_at = datetime.now(UTC)
    j.progress = {}
    return j


def _session_ctx(sess: Any) -> Any:
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=sess)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# enqueue idempotency (D4)
# ---------------------------------------------------------------------------

class TestEnqueueIdempotency:
    """Duplicate idempotency_key must return the existing job id."""

    def test_idempotency_returns_existing_id(self) -> None:
        existing = _make_job(job_id=42, idempotency_key="phase0:2026-06-01")
        sess = MagicMock()
        sess.execute.return_value.scalar_one_or_none.return_value = existing
        sess.flush.return_value = None

        with patch("copytrader.jobs.queue.get_session", return_value=_session_ctx(sess)):
            from copytrader.jobs import queue as q
            result = q.enqueue("phase0", {}, idempotency_key="phase0:2026-06-01")
        assert result == 42

    def test_no_idempotency_key_creates_new(self) -> None:
        sess = MagicMock()
        sess.flush.return_value = None
        # add() is called; job.id is set after flush
        added_jobs: list[Job] = []

        def _add(obj: Any) -> None:
            obj.id = 99
            added_jobs.append(obj)

        sess.add.side_effect = _add

        with patch("copytrader.jobs.queue.get_session", return_value=_session_ctx(sess)):
            from copytrader.jobs import queue as q
            result = q.enqueue("backfill", {"window": 7})
        assert result == 99
        assert len(added_jobs) == 1

    def test_different_key_creates_new(self) -> None:
        """A non-matching idempotency key should create a new job."""
        sess = MagicMock()
        # No existing job for the key
        sess.execute.return_value.scalar_one_or_none.return_value = None

        def _add(obj: Any) -> None:
            obj.id = 77

        sess.add.side_effect = _add

        with patch("copytrader.jobs.queue.get_session", return_value=_session_ctx(sess)):
            from copytrader.jobs import queue as q
            result = q.enqueue("phase0", {}, idempotency_key="phase0:2026-06-02")
        assert result == 77


# ---------------------------------------------------------------------------
# append_log
# ---------------------------------------------------------------------------

class TestAppendLog:
    def test_append_log_adds_job_log(self) -> None:
        sess = MagicMock()
        added: list = []
        sess.add.side_effect = lambda obj: added.append(obj)

        with patch("copytrader.jobs.queue.get_session", return_value=_session_ctx(sess)):
            from copytrader.jobs import queue as q
            q.append_log(job_id=5, message="hello", level=20)

        assert len(added) == 1
        from copytrader.db.models import JobLog
        assert isinstance(added[0], JobLog)
        assert added[0].job_id == 5
        assert added[0].message == "hello"
        assert added[0].level == 20


# ---------------------------------------------------------------------------
# set_progress / set_result
# ---------------------------------------------------------------------------

class TestSetProgressResult:
    def test_set_progress_calls_update(self) -> None:
        sess = MagicMock()

        with patch("copytrader.jobs.queue.get_session", return_value=_session_ctx(sess)):
            from copytrader.jobs import queue as q
            q.set_progress(job_id=3, progress={"pct": 50})

        sess.execute.assert_called_once()

    def test_set_result_calls_update(self) -> None:
        sess = MagicMock()

        with patch("copytrader.jobs.queue.get_session", return_value=_session_ctx(sess)):
            from copytrader.jobs import queue as q
            q.set_result(job_id=3, result={"roi": 1.5})

        sess.execute.assert_called_once()


# ---------------------------------------------------------------------------
# get_job
# ---------------------------------------------------------------------------

class TestGetJob:
    def test_get_job_returns_job(self) -> None:
        job = _make_job(job_id=10)
        sess = MagicMock()
        sess.get.return_value = job
        sess.expunge.return_value = None

        with patch("copytrader.jobs.queue.get_session", return_value=_session_ctx(sess)):
            from copytrader.jobs import queue as q
            result = q.get_job(10)
        assert result is job

    def test_get_job_returns_none_for_missing(self) -> None:
        sess = MagicMock()
        sess.get.return_value = None

        with patch("copytrader.jobs.queue.get_session", return_value=_session_ctx(sess)):
            from copytrader.jobs import queue as q
            result = q.get_job(999)
        assert result is None


# ---------------------------------------------------------------------------
# JobHandle proxy
# ---------------------------------------------------------------------------

class TestJobHandle:
    def test_job_handle_log_delegates(self) -> None:
        sess = MagicMock()
        added: list = []
        sess.add.side_effect = lambda obj: added.append(obj)

        with patch("copytrader.jobs.queue.get_session", return_value=_session_ctx(sess)):
            from copytrader.jobs.queue import JobHandle
            job = _make_job(job_id=7)
            handle = JobHandle(job)
            handle.log("test message", level=30)

        from copytrader.db.models import JobLog
        assert len(added) == 1
        assert isinstance(added[0], JobLog)
        assert added[0].message == "test message"
        assert added[0].level == 30

    def test_job_handle_progress_delegates(self) -> None:
        sess = MagicMock()

        with patch("copytrader.jobs.queue.get_session", return_value=_session_ctx(sess)):
            from copytrader.jobs.queue import JobHandle
            job = _make_job(job_id=8)
            handle = JobHandle(job)
            handle.progress({"done": 5, "total": 10})

        sess.execute.assert_called_once()

    def test_job_handle_result_delegates(self) -> None:
        sess = MagicMock()

        with patch("copytrader.jobs.queue.get_session", return_value=_session_ctx(sess)):
            from copytrader.jobs.queue import JobHandle
            job = _make_job(job_id=9)
            handle = JobHandle(job)
            handle.result({"replay_roi": 2.3})

        sess.execute.assert_called_once()


# ---------------------------------------------------------------------------
# claim context manager — FAILED case (T10 prevention)
# ---------------------------------------------------------------------------

class TestClaimFailed:
    """A job that raises inside the claim() block must be marked FAILED."""

    def test_exception_inside_claim_marks_failed(self) -> None:
        job = _make_job(job_id=20, status="PENDING")
        sess = MagicMock()
        sess.commit.return_value = None

        executed_stmts: list = []
        sess.execute.side_effect = lambda stmt, *a, **kw: executed_stmts.append(stmt)

        with patch("copytrader.jobs.queue.get_session", return_value=_session_ctx(sess)):
            with patch("copytrader.jobs.queue._claim_one", return_value=job):
                from copytrader.jobs import queue as q
                with pytest.raises(ValueError, match="simulated failure"):
                    with q.claim("worker-1") as claimed_job:
                        assert claimed_job is job
                        raise ValueError("simulated failure")

        # At least one execute call must have been made (the FAILED update).
        # SQLAlchemy bound values — look for the :status param containing "FAILED".
        assert len(executed_stmts) >= 1, "Expected at least one UPDATE to run"
        # Compile the stmt with literal_binds to check the value.
        from sqlalchemy.dialects import postgresql
        compiled_sqls = []
        for stmt in executed_stmts:
            try:
                compiled = stmt.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
                compiled_sqls.append(str(compiled))
            except Exception:
                compiled_sqls.append(str(stmt))
        found_failed = any("FAILED" in s for s in compiled_sqls)
        assert found_failed, (
            "Expected at least one UPDATE setting status=FAILED; "
            f"compiled stmts: {compiled_sqls}"
        )

    def test_no_job_available_yields_none(self) -> None:
        sess = MagicMock()

        with patch("copytrader.jobs.queue.get_session", return_value=_session_ctx(sess)):
            with patch("copytrader.jobs.queue._claim_one", return_value=None):
                from copytrader.jobs import queue as q
                with q.claim("worker-1") as claimed_job:
                    assert claimed_job is None
