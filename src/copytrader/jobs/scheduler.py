"""DB-backed cron scheduler.

Polls `scheduled_jobs` once per minute. For each row with
`next_run_at <= now() AND enabled = true`:
  1. enqueue a job of kind=job_kind with params=job_params
  2. update last_run_at, compute next_run_at from cron_expr
  3. set the row's enqueue idempotency_key so a missed cycle won't duplicate

cron_expr uses standard 5-field POSIX cron via croniter. If croniter is
unavailable we fall back to interval mode where cron_expr is parsed as
"every N minutes" via the @every:<n>m form.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from copytrader.db.engine import get_session
from copytrader.db.models import ScheduledJob
from copytrader.jobs.queue import enqueue

log = logging.getLogger("jobs.scheduler")


def _next_run(cron_expr: str, base: datetime) -> datetime:
    """Compute next run time from a cron expression.

    Supports:
    - Standard 5-field cron (via croniter if installed)
    - "@every:<N>m" / "@every:<N>h" / "@every:<N>s" interval shorthand
    """
    if cron_expr.startswith("@every:"):
        spec = cron_expr[len("@every:"):]
        unit = spec[-1]
        n = int(spec[:-1])
        if unit == "s":
            return base + timedelta(seconds=n)
        if unit == "m":
            return base + timedelta(minutes=n)
        if unit == "h":
            return base + timedelta(hours=n)
        if unit == "d":
            return base + timedelta(days=n)
        raise ValueError(f"unknown @every unit: {unit}")

    try:
        from croniter import croniter
    except ImportError:
        # Fallback: every hour at minute 0
        log.warning(
            "croniter not installed; treating cron_expr=%r as @every:1h",
            cron_expr,
        )
        return base + timedelta(hours=1)
    itr = croniter(cron_expr, base)
    return itr.get_next(datetime)


def _due_jobs(session) -> list[ScheduledJob]:
    now = datetime.now(UTC)
    return list(session.execute(
        select(ScheduledJob)
        .where(ScheduledJob.enabled.is_(True))
        .where(ScheduledJob.next_run_at <= now)
    ).scalars())


def _process_due_once() -> int:
    """Process all due scheduled_jobs. Returns number enqueued."""
    enqueued = 0
    with get_session() as s:
        due = _due_jobs(s)
        for job in due:
            try:
                idem = f"sched:{job.name}:{job.next_run_at.isoformat()}"
                jid = enqueue(job.job_kind, job.job_params or {},
                              idempotency_key=idem)
                log.info("scheduler: enqueued %s (job_id=%s) for %s",
                         job.name, jid, job.next_run_at)
                job.last_run_at = job.next_run_at
                job.next_run_at = _next_run(job.cron_expr, datetime.now(UTC))
                enqueued += 1
            except Exception as e:  # noqa: BLE001
                log.exception("scheduler failed to enqueue %s: %s",
                              job.name, e)
    return enqueued


_DEAD_LETTER_ALERT_THRESHOLD = 100
_prev_dead_letter_alerted = False


def _check_dead_letter_overflow() -> None:
    """dead-letter が閾値を超えたら Telegram 通知（状態変化時のみ）。"""
    global _prev_dead_letter_alerted
    try:
        from sqlalchemy import func, select

        from copytrader.db.models import RpcDeadLetter
        with get_session() as s:
            count = s.execute(
                select(func.count()).select_from(RpcDeadLetter)
            ).scalar_one()
            if count >= _DEAD_LETTER_ALERT_THRESHOLD and not _prev_dead_letter_alerted:
                oldest_row = s.execute(
                    select(RpcDeadLetter.error_text).order_by(
                        RpcDeadLetter.created_at.asc()
                    ).limit(1)
                ).scalar_one_or_none()
                from copytrader.telegram.notifier import notify_dead_letter_overflow
                notify_dead_letter_overflow(
                    count=count,
                    oldest_error=str(oldest_row or "unknown"),
                )
                _prev_dead_letter_alerted = True
            elif count < _DEAD_LETTER_ALERT_THRESHOLD:
                _prev_dead_letter_alerted = False
    except Exception as e:  # noqa: BLE001
        log.warning("dead_letter check failed: %s", e)


async def run_scheduler(*, interval_seconds: int = 60) -> None:
    """Long-running coroutine: poll scheduled_jobs every interval_seconds."""
    log.info("scheduler: starting, interval=%ds", interval_seconds)
    while True:
        try:
            _process_due_once()
        except Exception as e:  # noqa: BLE001
            log.exception("scheduler tick failed: %s", e)
        try:
            _check_dead_letter_overflow()
        except Exception as e:  # noqa: BLE001
            log.warning("dead_letter check tick error: %s", e)
        await asyncio.sleep(interval_seconds)


def seed_default_schedule() -> None:
    """Insert built-in scheduled jobs if not already present.

    Called once at worker boot. Idempotent.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    now = datetime.now(UTC)
    # Only seed jobs whose handler is already implemented. The list will
    # grow as PRs #10 (watchlist_rotate) etc. land.
    defaults = [
        ("nightly_phase0", "0 18 * * *", "phase0",
         {"window": 30, "watchlist_top": 10, "delays": [30, 60, 120],
          "copy_usd_per_trade": 50},
         now + timedelta(hours=1)),
        ("gamma_resolve_fetch", "@every:60m", "gamma_resolve_fetch",
         {}, now + timedelta(minutes=5)),
        ("watchlist_rotate", "0 19 * * *", "watchlist_rotate",
         {}, now + timedelta(hours=2)),
        ("daily_summary_telegram", "0 0 * * *", "daily_summary_telegram",
         {}, now + timedelta(hours=3)),
        # Refresh on-chain USDC/MATIC balances for the risk floors. Fail-soft
        # when TRADER_ADDRESS / RPC are unset, so safe to always schedule.
        ("balance_refresh", "@every:10m", "balance_refresh",
         {}, now + timedelta(minutes=2)),
    ]
    with get_session() as s:
        for name, cron_expr, kind, params, next_run in defaults:
            stmt = pg_insert(ScheduledJob).values(
                name=name, cron_expr=cron_expr, job_kind=kind,
                job_params=params, next_run_at=next_run, enabled=True,
            ).on_conflict_do_nothing(index_elements=[ScheduledJob.name])
            s.execute(stmt)
    log.info("scheduler: default jobs seeded")
