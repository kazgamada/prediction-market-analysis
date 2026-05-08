"""Polygon RPC client wrapper."""

from __future__ import annotations

import concurrent.futures
from collections.abc import Generator
from typing import Optional

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from copytrader.chain.contracts import (
    EXCHANGES,
    ORDER_FILLED_ABI,
    ORDER_FILLED_TOPIC,
)
from copytrader.config import get_settings


class PolygonClient:
    def __init__(self, rpc_url: Optional[str] = None):
        self.rpc_url = rpc_url or get_settings().polygon_rpc_http
        if not self.rpc_url:
            raise RuntimeError("POLYGON_RPC_HTTP is required")
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 30}))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self._contracts = {
            name: self.w3.eth.contract(
                address=Web3.to_checksum_address(addr),
                abi=[ORDER_FILLED_ABI],
            )
            for name, addr in EXCHANGES.items()
        }

    def block_number(self) -> int:
        return self.w3.eth.block_number

    def block_timestamp(self, block_number: int) -> int:
        return self.w3.eth.get_block(block_number)["timestamp"]

    def get_order_filled_logs(
        self,
        from_block: int,
        to_block: int,
        exchange: str,
    ) -> list[dict]:
        addr = EXCHANGES[exchange]
        return list(
            self.w3.eth.get_logs(
                {
                    "address": Web3.to_checksum_address(addr),
                    "topics": [ORDER_FILLED_TOPIC],
                    "fromBlock": from_block,
                    "toBlock": to_block,
                }
            )
        )

    def decode_log(self, log: dict, exchange: str) -> dict:
        contract = self._contracts[exchange]
        decoded = contract.events.OrderFilled().process_log(log)
        return dict(decoded["args"])

    def iter_logs(
        self,
        from_block: int,
        to_block: int,
        exchange: str,
        chunk_size: int = 1000,
        max_workers: int = 5,
    ) -> Generator[tuple[list[dict], int, int], None, None]:
        ranges: list[tuple[int, int]] = []
        cur = from_block
        while cur <= to_block:
            end = min(cur + chunk_size - 1, to_block)
            ranges.append((cur, end))
            cur = end + 1

        def _fetch(start: int, end: int) -> tuple[list[dict], int, int]:
            try:
                return self.get_order_filled_logs(start, end, exchange), start, end
            except Exception as e:
                if "too large" in str(e).lower() and end > start:
                    mid = (start + end) // 2
                    a, _, _ = _fetch(start, mid)
                    b, _, _ = _fetch(mid + 1, end)
                    return a + b, start, end
                raise

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            for batch_idx in range(0, len(ranges), max_workers):
                batch = ranges[batch_idx : batch_idx + max_workers]
                futs = {ex.submit(_fetch, s, e): (s, e) for s, e in batch}
                results: dict[tuple[int, int], list[dict]] = {}
                for fut in concurrent.futures.as_completed(futs):
                    logs, s, e = fut.result()
                    results[(s, e)] = logs
                for s, e in batch:
                    yield results[(s, e)], s, e
