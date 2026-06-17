"""Periodically pull resolved markets from Gamma API into market_resolutions.

Designed to be called from a job handler (scheduled via `scheduled_jobs`).
Idempotent: existing condition_ids are not overwritten unless payout changes.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from copytrader.db.engine import get_session
from copytrader.db.models import MarketResolution as MR
from copytrader.gamma.client import GammaClient

log = logging.getLogger("gamma.resolver")


async def fetch_and_persist_resolutions(
    *,
    base_url: str = "https://gamma-api.polymarket.com",
    lookback_days: int = 90,
    max_pages: int = 50,
) -> dict:
    """Fetch resolved markets since the latest stored row (or lookback_days
    if empty), insert new ones. Returns a summary dict for the job result.
    """
    since: datetime | None = None
    with get_session() as s:
        latest = s.execute(
            select(MR.resolved_at).order_by(MR.resolved_at.desc()).limit(1)
        ).scalar_one_or_none()
        if latest:
            # Re-fetch a small overlap to catch late-resolved markets
            since = latest - timedelta(hours=12)
        else:
            since = datetime.now(UTC) - timedelta(days=lookback_days)

    log.info("gamma.resolver: fetching resolved markets since %s", since)

    inserted = 0
    updated = 0
    seen = 0
    async with GammaClient(base_url=base_url) as client:
        async for resolution in client.iter_resolved_markets(
            since=since, max_pages=max_pages,
        ):
            seen += 1
            with get_session() as s:
                stmt = pg_insert(MR).values(
                    condition_id=resolution.condition_id,
                    outcome=resolution.outcome,
                    payout_per_share=resolution.payout_per_share,
                    resolved_at=resolution.resolved_at,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[MR.condition_id],
                    set_={
                        "outcome": stmt.excluded.outcome,
                        "payout_per_share": stmt.excluded.payout_per_share,
                        "resolved_at": stmt.excluded.resolved_at,
                        "fetched_at": datetime.now(UTC),
                    },
                    where=(
                        (MR.outcome != stmt.excluded.outcome)
                        | (MR.payout_per_share != stmt.excluded.payout_per_share)
                    ),
                )
                result = s.execute(stmt)
                if result.rowcount > 0:
                    # rowcount counts both inserts and updates
                    existing = s.execute(
                        select(MR).where(MR.condition_id == resolution.condition_id)
                    ).scalar_one_or_none()
                    if existing and existing.fetched_at < datetime.now(UTC) - timedelta(seconds=1):
                        updated += 1
                    else:
                        inserted += 1

    summary = {
        "seen": seen,
        "inserted": inserted,
        "updated": updated,
        "since": since.isoformat() if since else None,
    }
    log.info("gamma.resolver: done %s", summary)
    return summary


def run_gamma_resolve_fetch_job(params: dict) -> dict:
    """Entry point invoked by job_runner for kind='gamma_resolve_fetch'."""
    base_url = params.get("base_url", "https://gamma-api.polymarket.com")
    lookback_days = int(params.get("lookback_days", 90))
    max_pages = int(params.get("max_pages", 50))
    return asyncio.run(
        fetch_and_persist_resolutions(
            base_url=base_url,
            lookback_days=lookback_days,
            max_pages=max_pages,
        )
    )
