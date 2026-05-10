"""進捗 / ETA 計算ヘルパー。`run_with_live_logs` の `progress_fn` に渡す。

DB の `ingest_cursor` をポーリングし、観測した進行レートからチェーン
ヘッドまでの ETA を Markdown 文字列で返す。`backfill_progress_fn()` は
クロージャでサンプル履歴を保持するので、毎回 fresh な closure を作る。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Optional

from sqlalchemy import select

from copytrader.db import session_scope
from copytrader.models import IngestCursor

_HEAD_REFRESH_SEC = 30.0
_MAX_SAMPLES = 12


def backfill_progress_fn() -> Callable[[], Optional[str]]:
    """backfill 用の progress closure を作る。

    呼ぶたびに最新の cursor と (キャッシュ済みの) chain head を比較し、
    各 exchange の進捗 (block / head / %) と、観測レートから計算した
    ETA を Markdown 文字列で返す。失敗時は None を返す。
    """
    state = {
        "head": None,  # type: ignore[var-annotated]
        "head_at": 0.0,
        "samples": [],  # list[tuple[float monotonic, int max_block]]
    }

    def _refresh_head() -> None:
        now = time.monotonic()
        if state["head"] is not None and (now - state["head_at"]) < _HEAD_REFRESH_SEC:
            return
        try:
            from copytrader.chain.client import PolygonClient

            state["head"] = PolygonClient().block_number()
            state["head_at"] = now
        except Exception:
            pass

    def _impl() -> Optional[str]:
        _refresh_head()
        head = state["head"]

        with session_scope() as session:
            cursors = (
                session.execute(
                    select(IngestCursor).where(IngestCursor.name.like("backfill%"))
                )
                .scalars()
                .all()
            )

        if not cursors:
            return "_(ingest_cursor が未作成。最初の commit を待っています…)_"

        per_exchange_lines: list[str] = []
        max_block = 0
        for c in cursors:
            block = int(c.block_number or 0)
            max_block = max(max_block, block)
            if head and head > 0:
                pct = block / head * 100
                per_exchange_lines.append(
                    f"- `{c.name}`: block **{block:,}** / {head:,} (**{pct:.2f}%**)"
                )
            else:
                per_exchange_lines.append(f"- `{c.name}`: block **{block:,}**")

        now = time.monotonic()
        samples: list[tuple[float, int]] = state["samples"]
        if not samples or samples[-1][1] != max_block:
            samples.append((now, max_block))
            if len(samples) > _MAX_SAMPLES:
                del samples[: len(samples) - _MAX_SAMPLES]
            state["samples"] = samples

        eta_line = ""
        if head and len(samples) >= 2:
            t0, b0 = samples[0]
            tn, bn = samples[-1]
            dt = tn - t0
            db = bn - b0
            if dt > 0 and db > 0:
                rate = db / dt
                remaining = max(0, head - max_block)
                eta_s = remaining / rate if rate > 0 else 0
                eta_line = (
                    f"\n\n**ETA** ≈ {_fmt_duration(eta_s)} "
                    f"(rate {rate:,.0f} blocks/s, remaining {remaining:,} blocks)"
                )
            elif db == 0 and dt > 5:
                eta_line = "\n\n_(進捗停滞中: 直近サンプル間で block_number が動いていません)_"

        head_line = f"chain head: **{head:,}**\n\n" if head else ""
        return head_line + "\n".join(per_exchange_lines) + eta_line

    return _impl


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m"
