"""Live status: signals, positions, recent risk events."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import func, select

from copytrader.db import session_scope
from copytrader.models import Order, Position, RiskEvent, Signal, Trade, Wallet
from copytrader.web.nav import render_sidebar_menu_help

render_sidebar_menu_help()
st.title("Status")
st.caption(
    "現在の運用状態スナップショット。インデックス済み trade 数、検出済みシグナル、発注、ウォッチリスト、最新の取り込み時刻、"
    "オープンポジションと直近のリスクイベントを一覧で確認できます。"
)

with session_scope() as session:
    n_trades = session.execute(select(func.count()).select_from(Trade)).scalar() or 0
    n_signals = session.execute(select(func.count()).select_from(Signal)).scalar() or 0
    n_orders = session.execute(select(func.count()).select_from(Order)).scalar() or 0
    n_watch = session.execute(
        select(func.count()).select_from(Wallet).where(Wallet.watchlisted.is_(True))
    ).scalar() or 0

    last_trade_ts = session.execute(select(func.max(Trade.block_timestamp))).scalar()

    recent_signals = session.execute(
        select(Signal).order_by(Signal.detected_at.desc()).limit(50)
    ).scalars().all()
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

    open_pos = session.execute(
        select(Position).where(Position.closed_at.is_(None))
    ).scalars().all()
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

    recent_orders = session.execute(
        select(Order).order_by(Order.placed_at.desc()).limit(20)
    ).scalars().all()
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

    risk = session.execute(
        select(RiskEvent).order_by(RiskEvent.occurred_at.desc()).limit(20)
    ).scalars().all()
    risk_rows = [
        {
            "when": r.occurred_at.strftime("%m-%d %H:%M:%S"),
            "kind": r.kind,
            "halted": "Y" if r.halted else "",
            "detail": (r.detail or "")[:160],
        }
        for r in risk
    ]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(
    "Trades indexed",
    f"{n_trades:,}",
    help="trades テーブルに保存済みの OrderFilled イベント件数。Backfill / 監視で増加します。",
)
c2.metric(
    "Signals",
    f"{n_signals:,}",
    help="ウォッチリスト対象ウォレットの取引から生成された累計シグナル数。",
)
c3.metric(
    "Orders",
    f"{n_orders:,}",
    help="ペーパーまたはライブモードでこのアプリが発注した累計注文数。",
)
c4.metric(
    "Watchlisted",
    f"{n_watch:,}",
    help="現在ウォッチリスト登録中のウォレット数。Rank / Watchlist ページで増減できます。",
)
if last_trade_ts:
    age = datetime.now(timezone.utc) - last_trade_ts
    c5.metric(
        "Last trade",
        f"{int(age.total_seconds()//60)}m ago",
        help="最新の取り込み済み trade の経過時間。古すぎる場合は monitor が止まっている可能性。",
    )
else:
    c5.metric(
        "Last trade",
        "never",
        help="まだ trade を 1 件も取り込んでいません。Actions ページで Backfill を実行してください。",
    )

st.subheader("Open positions")
st.dataframe(pd.DataFrame(pos_rows) if pos_rows else pd.DataFrame(), use_container_width=True)

st.subheader("Recent signals")
st.dataframe(pd.DataFrame(sig_rows) if sig_rows else pd.DataFrame(), use_container_width=True)

st.subheader("Recent orders")
st.dataframe(pd.DataFrame(order_rows) if order_rows else pd.DataFrame(), use_container_width=True)

st.subheader("Recent risk events")
st.dataframe(pd.DataFrame(risk_rows) if risk_rows else pd.DataFrame(), use_container_width=True)

if st.button("Refresh", help="DB から最新の値を取り直してこのページを再描画します。"):
    st.rerun()
