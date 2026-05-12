"""Job queue backed by Postgres.

Design rules:
  * `enqueue(kind, params, idempotency_key=...)` returns the existing job id
    if `idempotency_key` already exists. This is how we prevent double-click
    of the "Run Phase 0" button creating two jobs (D4).
  * `claim()` uses `SELECT ... FOR UPDATE SKIP LOCKED` so multiple workers
    are race-free without an external lock service.
  * Logs go to `job_logs` so the UI can `polling SELECT` them.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from copytrader.db.engine import get_session
from copytrader.db.models import Job, JobLog

log = logging.getLogger(__name__)


def enqueue(
    kind: str,
    params: dict[str, Any],
    *,
    idempotency_key: str | None = None,
    parent_job_id: int | None = None,
) -> int:
    """Insert a PENDING job. If `idempotency_key` matches existing, return that id."""
    with get_session() as s:
        if idempotency_key:
            existing = s.execute(
                select(Job).where(Job.idempotency_key == idempotency_key)
            ).scalar_one_or_none()
            if existing:
                return existing.id
        job = Job(
            kind=kind,
            params=params,
            idempotency_key=idempotency_key,
            parent_job_id=parent_job_id,
        )
        s.add(job)
        s.flush()
        return job.id


def get_job(job_id: int) -> Job | None:
    with get_session() as s:
        row = s.get(Job, job_id)
        if row:
            s.expunge(row)
        return row


def append_log(job_id: int, message: str, level: int = 20) -> None:
    with get_session() as s:
        s.add(JobLog(job_id=job_id, message=message, level=level))


def set_progress(job_id: int, progress: dict[str, Any]) -> None:
    with get_session() as s:
        s.execute(update(Job).where(Job.id == job_id).values(progress=progress))


def set_result(job_id: int, result: dict[str, Any]) -> None:
    with get_session() as s:
        s.execute(update(Job).where(Job.id == job_id).values(result=result))


@contextmanager
def claim(worker_id: str) -> Iterator[Job | None]:
    """Claim one PENDING job, mark it RUNNING, yield it.

    On success: status=SUCCEEDED, finished_at set.
    On exception: status=FAILED, error_text recorded.
    """
    with get_session() as s:
        job = _claim_one(s, worker_id)
        if job is None:
            yield None
            return

        # Manually commit the claim so the row is visible to others as RUNNING.
        s.commit()
        try:
            yield job
        except Exception as e:
            log.exception("job %d failed", job.id)
            s.execute(
                update(Job)
                .where(Job.id == job.id)
                .values(
                    status="FAILED",
                    error_text=f"{type(e).__name__}: {e}",
                    finished_at=datetime.now(UTC),
                )
            )
            # commit the FAILED status before re-raising so callers see it
            s.commit()
            raise
        else:
            s.execute(
                update(Job)
                .where(Job.id == job.id)
                .values(status="SUCCEEDED", finished_at=datetime.now(UTC))
            )


def _claim_one(s: Session, worker_id: str) -> Job | None:
    """SELECT FOR UPDATE SKIP LOCKED a pending job and flip it to RUNNING."""
    row = s.execute(
        text(
            "SELECT id FROM jobs WHERE status = 'PENDING' "
            "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
    ).first()
    if row is None:
        return None
    job_id = row[0]
    s.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(
            status="RUNNING",
            started_at=datetime.now(UTC),
            worker_id=worker_id,
        )
    )
    s.flush()
    job = s.get(Job, job_id)
    return job


def wait_for(job_id: int, *, poll_s: float = 1.0, timeout_s: float | None = None) -> Job:
    """Poll until job reaches a terminal state. Raises on FAILED."""
    import time as _time
    start = _time.time()
    while True:
        j = get_job(job_id)
        if j is None:
            raise RuntimeError(f"job {job_id} disappeared")
        if j.status in ("SUCCEEDED", "FAILED", "CANCELLED"):
            if j.status != "SUCCEEDED":
                raise RuntimeError(f"job {job_id} {j.status}: {j.error_text}")
            return j
        if timeout_s and _time.time() - start > timeout_s:
            raise TimeoutError(f"job {job_id} did not finish in {timeout_s}s")
        _time.sleep(poll_s)


# Convenience handle used inside handlers.

class JobHandle:
    """Sugar handed to handler functions."""

    def __init__(self, job: Job):
        self.id = job.id
        self.kind = job.kind
        self.params = dict(job.params or {})

    def log(self, msg: str, level: int = 20) -> None:
        append_log(self.id, msg, level=level)
        log.info("[job %d] %s", self.id, msg)

    def progress(self, p: dict[str, Any]) -> None:
        set_progress(self.id, p)

    def result(self, r: dict[str, Any]) -> None:
        set_result(self.id, r)
