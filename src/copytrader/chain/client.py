"""Polygon RPC client wrapper."""

from __future__ import annotations

import concurrent.futures
import logging
from collections.abc import Generator
from typing import Optional

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from copytrader.chain.contracts import (
    EXCHANGES,
    ORDER_FILLED_ABI,
    ORDER_FILLED_TOPIC,
)
from copytrader.chain.errors import wrap_rpc_errors
from copytrader.config import get_settings

log = logging.getLogger(__name__)


class PolygonClient:
    def __init__(self, rpc_url: Optional[str] = None):
        self.rpc_url = rpc_url or get_settings().polygon_rpc_http
        if not self.rpc_url:
            raise RuntimeError("POLYGON_RPC_HTTP is required")
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 15}))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self._contracts = {
            name: self.w3.eth.contract(
                address=Web3.to_checksum_address(addr),
                abi=[ORDER_FILLED_ABI],
            )
            for name, addr in EXCHANGES.items()
        }

    @wrap_rpc_errors
    def block_number(self) -> int:
        return self.w3.eth.block_number

    @wrap_rpc_errors
    def block_timestamp(self, block_number: int) -> int:
        return self.w3.eth.get_block(block_number)["timestamp"]

    @wrap_rpc_errors
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
        chunk_size: int = 2000,
        max_workers: int = 10,
    ) -> Generator[tuple[list[dict], int, int], None, None]:
        """Yield (logs, start, end) per chunk. **個別 chunk の失敗は呑む**:

        - "too large" は半分に分割して再試行
        - その他の例外は logging.warning だけして空 list を yield
        - これで 1 チャンクの RPC ハング/エラーで backfill 全体が止まらない
        """
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
                msg = str(e).lower()
                if "too large" in msg and end > start:
                    mid = (start + end) // 2
                    a, _, _ = _fetch(start, mid)
                    b, _, _ = _fetch(mid + 1, end)
                    return a + b, start, end
                log.warning(
                    "iter_logs: chunk failed exchange=%s start=%s end=%s err=%s",
                    exchange, start, end, str(e)[:200],
                )
                # 失敗チャンクは空として継続。次の catchup iteration で再取得される。
                return [], start, end

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            for batch_idx in range(0, len(ranges), max_workers):
                batch = ranges[batch_idx : batch_idx + max_workers]
                futs = {ex.submit(_fetch, s, e): (s, e) for s, e in batch}
                results: dict[tuple[int, int], list[dict]] = {}
                for fut in concurrent.futures.as_completed(futs):
                    try:
                        logs, s, e = fut.result()
                        results[(s, e)] = logs
                    except Exception as e:
                        s, ee = futs[fut]
                        log.warning(
                            "iter_logs: future raised exchange=%s start=%s end=%s err=%s",
                            exchange, s, ee, str(e)[:200],
                        )
                        results[(s, ee)] = []
                for s, e in batch:
                    yield results.get((s, e), []), s, e
