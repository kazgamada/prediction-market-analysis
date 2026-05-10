"""Manage the wallet watchlist."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from copytrader.monitor.watchlist import add as wl_add
from copytrader.monitor.watchlist import remove as wl_remove
from copytrader.web.cache import invalidate_watchlist, watchlist_rows
from copytrader.web.logs import render_running_jobs_banner
from copytrader.web.nav import render_sidebar_menu_help

render_sidebar_menu_help()
_any_running = render_running_jobs_banner()
st.title("Watchlist")
st.caption(
    "監視対象ウォレットの管理。ここに追加されたウォレットの取引が monitor によって追跡され、シグナル化されます。"
    "Rank ページから自動投入することもできます。"
)

with st.form("add_form", clear_on_submit=True):
    cols = st.columns([3, 2, 1])
    addr = cols[0].text_input(
        "Wallet address (0x…)",
        help="追加するウォレットのアドレス。0x で始まる 42 文字の hex。チェックサム不要 (内部で小文字化されます)。",
    )
    note = cols[1].text_input(
        "Note",
        placeholder="e.g. top by 30d Sharpe",
        help="任意のメモ (なぜ watchlist 入りさせたか等)。一覧表示と運用ログに使われます。",
    )
    submitted = cols[2].form_submit_button(
        "Add",
        help="このアドレスを watchlist に追加します。既存の場合は note のみ更新。",
    )
    if submitted:
        if not addr or not addr.startswith("0x") or len(addr) != 42:
            st.error("address must be 42-char 0x… hex")
        else:
            wl_add(addr, note or None)
            invalidate_watchlist()
            st.success(f"watchlisted {addr.lower()}")
            st.rerun()

table = pd.DataFrame(watchlist_rows())

st.subheader(f"Currently watchlisted: {len(table)}")
st.dataframe(table, use_container_width=True)

if not table.empty:
    target = st.selectbox(
        "Remove address",
        options=[""] + list(table["address"]),
        help="watchlist から外したいアドレスを選択。空欄のままなら削除はされません。",
    )
    if target and st.button(
        "Remove",
        type="primary",
        help="選択したアドレスを watchlist から外します。trade 履歴自体は DB に残ります。",
    ):
        wl_remove(target)
        invalidate_watchlist()
        st.success(f"removed {target}")
        st.rerun()

if _any_running:
    import time as _time

    _time.sleep(3)
    st.rerun()
