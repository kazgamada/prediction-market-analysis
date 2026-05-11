"""ページ表示を 0.1 秒目標で高速化するためのプロセス内キャッシュとバックグラウンド warmer。

各ページが毎回叩いていた DB クエリ / RPC 呼び出しの結果を `_LATEST` に保持し、
別スレッド (warmer) が一定間隔で再評価することで、ユーザーが画面を開いた瞬間は
常にメモリ上のキャッシュから返すことを狙う。

書き込み系 (watchlist の追加・削除など) では `invalidate_*` を呼んで該当キーを破棄する。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from sqlalchemy import func, select

from copytrader.db import session_scope
from copytrader.models import (
    IngestCursor,
    Order,
    Position,
    RiskEvent,
    Signal,
    Trade,
    Wallet,
)

log = logging.getLogger(__name__)

_LATEST: dict[str, Any] = {}
_LOCK = threading.RLock()

_WARM_INTERVAL_SEC = 5.0


def _compute_status() -> dict[str, Any]:
    with session_scope() as session:
        n_trades = session.execute(select(func.count()).select_from(Trade)).scalar() or 0
        n_signals = session.execute(select(func.count()).select_from(Signal)).scalar() or 0
        n_orders = session.execute(select(func.count()).select_from(Order)).scalar() or 0
        n_watch = (
            session.execute(
                select(func.count()).select_from(Wallet).where(Wallet.watchlisted.is_(True))
            ).scalar()
            or 0
        )
        last_trade_ts = session.execute(select(func.max(Trade.block_timestamp))).scalar()
        last_trade_block = session.execute(select(func.max(Trade.block_number))).scalar()

        cursors = (
            session.execute(select(IngestCursor).where(IngestCursor.name.like("backfill%")))
            .scalars()
            .all()
        )
        cursor_rows = [
            {
                "source": c.name,
                "block_number": int(c.block_number) if c.block_number else 0,
                "updated_at": c.updated_at,
            }
            for c in cursors
        ]

        recent_signals = (
            session.execute(select(Signal).order_by(Signal.detected_at.desc()).limit(50))
            .scalars()
            .all()
        )
        sig_rows = [
            {
                "when": s.detected_at.strftime("%m-%d %H:%M:%S") if s.detected_at else "",
                "wallet": s.source_wallet,
                "side": s.side,
                "token": s.token_id[:14] + "…",
                "src_price": float(s.source_price),
                "src_size": float(s.source_size),
                "status": s.status,
                "notes": (s.notes or "")[:60],
            }
            for s in recent_signals
        ]

        open_pos = (
            session.execute(select(Position).where(Position.closed_at.is_(None))).scalars().all()
        )
        pos_rows = [
            {
                "mode": p.mode,
                "token": p.token_id[:14] + "…",
                "size": float(p.size or 0),
                "avg_entry": float(p.avg_entry_price or 0),
                "realized_pnl": float(p.realized_pnl or 0),
                "opened_at": p.opened_at.strftime("%m-%d %H:%M") if p.opened_at else "",
            }
            for p in open_pos
        ]

        recent_orders = (
            session.execute(select(Order).order_by(Order.placed_at.desc()).limit(20))
            .scalars()
            .all()
        )
        order_rows = [
            {
                "when": o.placed_at.strftime("%m-%d %H:%M:%S") if o.placed_at else "",
                "mode": o.mode,
                "side": o.side,
                "token": o.token_id[:14] + "…",
                "size": float(o.size or 0),
                "limit": float(o.limit_price or 0),
                "filled": float(o.filled_size or 0),
                "avg_fill": float(o.avg_fill_price or 0) if o.avg_fill_price else None,
                "status": o.status,
            }
            for o in recent_orders
        ]

        risk = (
            session.execute(select(RiskEvent).order_by(RiskEvent.occurred_at.desc()).limit(20))
            .scalars()
            .all()
        )
        risk_rows = [
            {
                "when": r.occurred_at.strftime("%m-%d %H:%M:%S"),
                "kind": r.kind,
                "halted": "Y" if r.halted else "",
                "detail": (r.detail or "")[:160],
            }
            for r in risk
        ]

    return {
        "n_trades": n_trades,
        "n_signals": n_signals,
        "n_orders": n_orders,
        "n_watch": n_watch,
        "last_trade_ts": last_trade_ts,
        "last_trade_block": last_trade_block,
        "cursor_rows": cursor_rows,
        "sig_rows": sig_rows,
        "pos_rows": pos_rows,
        "order_rows": order_rows,
        "risk_rows": risk_rows,
    }


def _compute_chain_head() -> dict[str, Any]:
    try:
        from copytrader.chain.client import PolygonClient

        return {"head": PolygonClient().block_number(), "error": None}
    except Exception as e:
        return {"head": None, "error": str(e)}


def _compute_watchlist() -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = (
            session.execute(
                select(Wallet)
                .where(Wallet.watchlisted.is_(True))
                .order_by(Wallet.score.desc().nullslast())
            )
            .scalars()
            .all()
        )
        return [
            {
                "address": w.address,
                "score": float(w.score) if w.score else 0.0,
                "pnl_usd": float(w.realized_pnl_usd or 0),
                "volume_usd": float(w.total_volume_usd or 0),
                "n_trades": w.n_trades or 0,
                "notes": w.notes or "",
            }
            for w in rows
        ]


def _compute_replay_candidates() -> list[tuple[str, float]]:
    with session_scope() as session:
        rows = session.execute(
            select(Wallet.address, Wallet.score)
            .order_by(Wallet.score.desc().nullslast())
            .limit(200)
        ).all()
        return [(a, float(s) if s else 0.0) for a, s in rows]


_REGISTRY: dict[str, Callable[[], Any]] = {
    "status": _compute_status,
    "chain_head": _compute_chain_head,
    "watchlist": _compute_watchlist,
    "replay_candidates": _compute_replay_candidates,
}


def _get(key: str) -> Any:
    with _LOCK:
        if key in _LATEST:
            return _LATEST[key]
    val = _REGISTRY[key]()
    with _LOCK:
        _LATEST[key] = val
    return val


def status_snapshot() -> dict[str, Any]:
    return _get("status")


def chain_head() -> dict[str, Any]:
    return _get("chain_head")


def watchlist_rows() -> list[dict[str, Any]]:
    return _get("watchlist")


def replay_candidates() -> list[tuple[str, float]]:
    return _get("replay_candidates")


def invalidate_watchlist() -> None:
    with _LOCK:
        _LATEST.pop("watchlist", None)
        _LATEST.pop("status", None)


def invalidate_all() -> None:
    with _LOCK:
        _LATEST.clear()


def force_refresh() -> None:
    """ユーザーが明示的に Refresh を押したときの即時再計算。"""
    for key, fn in _REGISTRY.items():
        try:
            val = fn()
            with _LOCK:
                _LATEST[key] = val
        except Exception:
            log.exception("force_refresh: failed key=%s", key)


_warmer_started = False
_warmer_start_lock = threading.Lock()


def _warm_loop() -> None:
    while True:
        for key, fn in _REGISTRY.items():
            try:
                val = fn()
                with _LOCK:
                    _LATEST[key] = val
            except Exception:
                log.exception("page-cache-warmer: failed key=%s", key)
        time.sleep(_WARM_INTERVAL_SEC)


def start_background_warmer() -> None:
    """プロセス内に 1 つだけ daemon スレッドを起動する。複数回呼ばれても無視。"""
    global _warmer_started
    with _warmer_start_lock:
        if _warmer_started:
            return
        threading.Thread(
            target=_warm_loop, name="page-cache-warmer", daemon=True
        ).start()
        _warmer_started = True


_catchup_started = False
_catchup_start_lock = threading.Lock()
_CATCHUP_INTERVAL_SEC = 300.0


def _bump_cursors_to_recent_floor() -> None:
    """cursor が `head - backfill_recent_days * 43200` より古い場合、
    その値まで前進させて古い履歴をスキップする。

    catchup ループが動かなくても、Streamlit が起動した瞬間に cursor が
    直近 N 日相当の位置に書き換わるので、UI 上の進捗もすぐ更新される。
    trade テーブルへの insert は別途 catchup / WS で進めるので、cursor の
    先行は無害 (idempotent insert + max-cursor 保護)。
    """
    from datetime import datetime, timezone

    from copytrader.chain.client import PolygonClient
    from copytrader.config import get_settings
    from copytrader.db import session_scope
    from copytrader.models import IngestCursor

    recent_days = get_settings().backfill_recent_days
    if not recent_days or recent_days <= 0:
        return

    try:
        head = PolygonClient().block_number()
    except Exception:
        log.exception("bump_cursors: chain head fetch failed")
        return

    POLYGON_BLOCKS_PER_DAY = 43_200
    recent_floor = max(0, head - recent_days * POLYGON_BLOCKS_PER_DAY)

    now = datetime.now(timezone.utc)
    with session_scope() as session:
        for exchange in ("ctf", "negrisk"):
            name = f"backfill_{exchange}"
            cur = session.get(IngestCursor, name)
            if cur is None:
                session.add(IngestCursor(name=name, block_number=recent_floor, updated_at=now))
                log.info("bump_cursors: created %s at recent_floor=%s", name, recent_floor)
            elif (cur.block_number or 0) < recent_floor:
                old = cur.block_number
                cur.block_number = recent_floor
                cur.updated_at = now
                log.info("bump_cursors: %s %s -> %s (recent_floor)", name, old, recent_floor)


def _catchup_loop() -> None:
    """web プロセス内で動く保険的 catchup loop。

    monitor プロセスが死んでいても backfill が止まらないよう、
    web (Streamlit) プロセスでも同じ catchup を回す。
    settings.backfill_recent_days の窓だけを対象にする。
    backfill 自体が冪等 (ON CONFLICT DO NOTHING + 単調増加 cursor) なので
    monitor と並走しても安全。
    """
    from copytrader.config import get_settings
    from copytrader.indexer.backfill import backfill as do_backfill

    log.info("web-catchup: thread started")
    backoff = 1.0
    while True:
        try:
            recent_days = get_settings().backfill_recent_days
            do_backfill(chunk_size=1000, max_workers=5, recent_days=recent_days)
            backoff = 1.0
        except Exception:
            log.exception("web-catchup: backfill failed; retrying in %.1fs", backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
            continue
        time.sleep(_CATCHUP_INTERVAL_SEC)


def start_background_catchup() -> None:
    """プロセス内に 1 つだけ daemon catchup スレッドを起動する。

    起動直後に同期で `_bump_cursors_to_recent_floor()` を呼ぶ。これで
    Streamlit が最初にロードされた瞬間に cursor が直近 60 日相当に
    ジャンプし、UI 上の進捗もすぐ反映される。
    """
    global _catchup_started
    with _catchup_start_lock:
        if _catchup_started:
            return
        try:
            _bump_cursors_to_recent_floor()
        except Exception:
            log.exception("start_background_catchup: bump failed")
        threading.Thread(
            target=_catchup_loop, name="web-catchup", daemon=True
        ).start()
        _catchup_started = True
        log.info("start_background_catchup: launched daemon thread")
