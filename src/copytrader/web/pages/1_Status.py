"""Live status: signals, positions, recent risk events."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from copytrader.web.cache import (
    chain_head as cached_chain_head,
)
from copytrader.web.cache import (
    force_refresh,
    status_snapshot,
)
from copytrader.web.nav import render_sidebar_menu_help

render_sidebar_menu_help()
st.title("Status")
st.caption(
    "現在の運用状態スナップショット。インデックス済み trade 数、検出済みシグナル、発注、ウォッチリスト、最新の取り込み時刻、"
    "オープンポジションと直近のリスクイベントを一覧で確認できます。"
)

_auto = st.toggle(
    "Auto refresh (5 秒)",
    value=False,
    help="ON にすると 5 秒ごとにこのページを再読込し、Backfill 等の進捗をリアルタイムで追えます。",
)

snap = status_snapshot()
chain_info = cached_chain_head()
_chain_head: int | None = chain_info.get("head")
_chain_err: str | None = chain_info.get("error")

n_trades = snap["n_trades"]
n_signals = snap["n_signals"]
n_orders = snap["n_orders"]
n_watch = snap["n_watch"]
last_trade_ts = snap["last_trade_ts"]
last_trade_block = snap["last_trade_block"]
cursor_rows = snap["cursor_rows"]
sig_rows = snap["sig_rows"]
pos_rows = snap["pos_rows"]
order_rows = snap["order_rows"]
risk_rows = snap["risk_rows"]

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

st.subheader("Backfill progress")
st.caption(
    "indexer のチェックポイント (`ingest_cursor`) からバックフィルの進捗を表示します。"
    "Streamlit UI / CLI / Fly machine のどこで backfill を走らせていても DB を見るので進捗が分かります。"
)

if not cursor_rows:
    st.info("backfill 用の cursor がまだありません。Actions ページか CLI で `copytrader backfill` を 1 度走らせてください。")
else:
    if _chain_head:
        st.caption(f"chain head: block **{_chain_head:,}**")
    elif _chain_err:
        st.caption(f"chain head 取得失敗: `{_chain_err[:140]}` (POLYGON_RPC_HTTP 未設定の可能性)")

    for row in cursor_rows:
        block = row["block_number"]
        ts = row["updated_at"]
        age_str = ""
        if ts:
            age_s = (datetime.now(timezone.utc) - ts).total_seconds()
            age_str = (
                f" — last update {int(age_s)}s ago"
                if age_s < 120
                else f" — last update {int(age_s // 60)}m ago"
            )
        col_l, col_r = st.columns([3, 2])
        if _chain_head and _chain_head > 0:
            ratio = max(0.0, min(1.0, block / _chain_head))
            col_l.progress(ratio, text=f"**{row['source']}**: block {block:,} / {_chain_head:,} ({ratio*100:.2f}%)")
        else:
            col_l.markdown(f"**{row['source']}**: block {block:,}")
        remaining = (_chain_head - block) if _chain_head else None
        col_r.markdown(
            f"残り blocks: **{remaining:,}**{age_str}" if remaining is not None and remaining >= 0
            else f"&nbsp;{age_str}"
        )

if last_trade_block:
    st.caption(f"latest indexed trade: block **{int(last_trade_block):,}**")

st.subheader("Open positions")
st.dataframe(pd.DataFrame(pos_rows) if pos_rows else pd.DataFrame(), use_container_width=True)

st.subheader("Recent signals")
st.dataframe(pd.DataFrame(sig_rows) if sig_rows else pd.DataFrame(), use_container_width=True)

st.subheader("Recent orders")
st.dataframe(pd.DataFrame(order_rows) if order_rows else pd.DataFrame(), use_container_width=True)

st.subheader("Recent risk events")
st.dataframe(pd.DataFrame(risk_rows) if risk_rows else pd.DataFrame(), use_container_width=True)

if st.button("Refresh", help="DB から最新の値を取り直してこのページを再描画します。"):
    force_refresh()
    st.rerun()

if _auto:
    import time as _time

    _time.sleep(5)
    st.rerun()
