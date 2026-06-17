"""Async httpx-based wrapper around Polymarket Gamma API.

Defensive: every request has a timeout, the client logs all errors but does
NOT raise on transient failures (caller decides). Resolutions are written
to `market_resolutions` table by `gamma.resolver`.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from copytrader.gamma.models import MarketInfo, MarketResolution

log = logging.getLogger("gamma.client")

DEFAULT_BASE = "https://gamma-api.polymarket.com"
DEFAULT_TIMEOUT = 10.0


def _hex_to_bytes(hex_str: str) -> bytes:
    s = hex_str.removeprefix("0x")
    return bytes.fromhex(s)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # Gamma returns ISO 8601 (e.g. "2024-11-05T00:00:00Z")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class GammaClient:
    def __init__(self, base_url: str = DEFAULT_BASE,
                 timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._http = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "GammaClient":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    async def _get(self, path: str, **params: Any) -> Any:
        url = f"{self.base_url}{path}"
        resp = await self._http.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def iter_resolved_markets(
        self,
        *,
        since: datetime | None = None,
        limit_per_page: int = 100,
        max_pages: int = 50,
    ) -> AsyncIterator[MarketResolution]:
        """Paginated iterator over resolved markets, newest first.

        Stops paginating when `since` is older than the cursor (since arg
        prevents re-fetching the entire history).
        """
        offset = 0
        for _ in range(max_pages):
            try:
                rows = await self._get(
                    "/markets",
                    closed="true",
                    limit=limit_per_page,
                    offset=offset,
                    order="endDate",
                    ascending="false",
                )
            except httpx.HTTPError as e:  # noqa: BLE001
                log.warning("gamma /markets failed: %s", e)
                return
            if not rows:
                return
            for row in rows:
                resolution = self._row_to_resolution(row)
                if resolution is None:
                    continue
                if since and resolution.resolved_at < since:
                    return
                yield resolution
            offset += limit_per_page

    def _row_to_resolution(self, row: dict) -> MarketResolution | None:
        """Convert one /markets row to a MarketResolution.

        Skips rows that aren't actually resolved (no umaResolutionStatus or
        still pending). Polymarket /markets rows have:
          condition_id, closed, resolved, umaResolutionStatuses,
          tokens (with outcome + winner), endDate.
        """
        if not row.get("resolved") or row.get("umaResolutionStatuses") is None:
            return None
        cond_hex = row.get("conditionId") or row.get("condition_id")
        if not cond_hex:
            return None
        try:
            condition_id = _hex_to_bytes(cond_hex)
        except ValueError:
            return None
        # Find winning outcome
        tokens = row.get("tokens") or []
        winner_idx = -1
        payout = Decimal(0)
        for idx, t in enumerate(tokens):
            if t.get("winner"):
                winner_idx = idx
                payout = Decimal("1.0")
                break
        if winner_idx < 0:
            return None
        end = _parse_dt(row.get("endDate") or row.get("end_date"))
        if end is None:
            end = datetime.utcnow()
        return MarketResolution(
            condition_id=condition_id,
            outcome=winner_idx,
            payout_per_share=payout,
            resolved_at=end,
        )

    async def get_market(self, slug: str) -> MarketInfo | None:
        try:
            row = await self._get("/markets", slug=slug)
        except httpx.HTTPError as e:  # noqa: BLE001
            log.warning("gamma /markets?slug=%s failed: %s", slug, e)
            return None
        if isinstance(row, list):
            if not row:
                return None
            row = row[0]
        try:
            return MarketInfo(
                condition_id=_hex_to_bytes(row["conditionId"]),
                slug=row.get("slug", slug),
                question=row.get("question", ""),
                closed=bool(row.get("closed")),
                resolved=bool(row.get("resolved")),
                end_date=_parse_dt(row.get("endDate")),
                volume_24h=Decimal(str(row.get("volume24hr") or "0")),
                liquidity=Decimal(str(row.get("liquidity") or "0")),
            )
        except (KeyError, ValueError) as e:
            log.warning("gamma row parse failed for %s: %s", slug, e)
            return None
