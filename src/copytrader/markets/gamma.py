"""Polymarket Gamma API client + sync into the market table."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

import httpx
from sqlalchemy.dialects.postgresql import insert

from copytrader.config import get_settings
from copytrader.db import session_scope
from copytrader.models import Market, TokenIndex

log = logging.getLogger(__name__)


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class GammaClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or get_settings().polymarket_gamma_url
        self.client = httpx.Client(timeout=30.0)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()

    def get_markets(self, limit: int = 500, offset: int = 0, **kwargs: Any) -> list[dict]:
        params = {"limit": limit, "offset": offset, **kwargs}
        r = self.client.get(f"{self.base_url}/markets", params=params)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data
        return data.get("markets", [])

    def iter_markets(self, limit: int = 500) -> Iterator[list[dict]]:
        offset = 0
        while True:
            chunk = self.get_markets(limit=limit, offset=offset)
            if not chunk:
                return
            yield chunk
            if len(chunk) < limit:
                return
            offset += len(chunk)


def sync_markets(limit_per_page: int = 500, max_pages: int | None = None) -> int:
    """Iterate Gamma /markets and upsert into market + token_index tables."""
    saved = 0
    now = datetime.now(timezone.utc)
    with GammaClient() as gc:
        for page_idx, chunk in enumerate(gc.iter_markets(limit=limit_per_page)):
            market_rows = []
            token_rows = []
            for m in chunk:
                cid = m.get("conditionId") or ""
                if not cid:
                    continue
                outcomes = m.get("outcomes", "[]")
                token_ids = m.get("clobTokenIds", "[]")
                outcome_prices = m.get("outcomePrices", "[]")
                market_rows.append(
                    dict(
                        condition_id=cid,
                        question=m.get("question"),
                        slug=m.get("slug"),
                        outcomes_json=json.dumps(outcomes) if not isinstance(outcomes, str) else outcomes,
                        clob_token_ids_json=json.dumps(token_ids) if not isinstance(token_ids, str) else token_ids,
                        outcome_prices_json=json.dumps(outcome_prices) if not isinstance(outcome_prices, str) else outcome_prices,
                        end_date=_parse_dt(m.get("endDate")),
                        created_at=_parse_dt(m.get("createdAt")),
                        active=bool(m.get("active", False)),
                        closed=bool(m.get("closed", False)),
                        fetched_at=now,
                    )
                )
                # token_index rows
                try:
                    token_list = json.loads(token_ids) if isinstance(token_ids, str) else token_ids
                except json.JSONDecodeError:
                    token_list = []
                for idx, tid in enumerate(token_list or []):
                    if tid:
                        token_rows.append(
                            dict(token_id=str(tid), condition_id=cid, outcome_index=idx)
                        )

            if market_rows:
                with session_scope() as session:
                    stmt = insert(Market).values(market_rows)
                    upd = {
                        c.name: stmt.excluded[c.name]
                        for c in Market.__table__.columns
                        if c.name != "condition_id"
                    }
                    stmt = stmt.on_conflict_do_update(index_elements=["condition_id"], set_=upd)
                    session.execute(stmt)

                    if token_rows:
                        tstmt = insert(TokenIndex).values(token_rows)
                        tstmt = tstmt.on_conflict_do_update(
                            index_elements=["token_id"],
                            set_={
                                "condition_id": tstmt.excluded.condition_id,
                                "outcome_index": tstmt.excluded.outcome_index,
                            },
                        )
                        session.execute(tstmt)
                saved += len(market_rows)
                log.info("page=%s saved=%s total=%s", page_idx, len(market_rows), saved)

            if max_pages is not None and page_idx + 1 >= max_pages:
                break
    return saved
