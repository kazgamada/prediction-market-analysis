"""One-shot operations: backfill, sync markets, reconcile, poll."""

from __future__ import annotations

import streamlit as st

from copytrader.config import get_settings
from copytrader.web.logs import run_with_live_logs
from copytrader.web.nav import render_sidebar_menu_help

render_sidebar_menu_help()
st.title("Actions")
st.caption("One-shot maintenance operations. Long jobs run in this process; "
           "for production-scale backfills, run the corresponding CLI on a worker.")

s = get_settings()
if not s.polygon_rpc_http:
    st.error("POLYGON_RPC_HTTP is not set; chain operations will fail.")

st.subheader("Indexer")
c1, c2 = st.columns(2)
with c1:
    chunk_size = st.number_input(
        "Chunk size",
        value=2000,
        min_value=100,
        max_value=5000,
        help="1 回の eth_getLogs で取りに行くブロック数。Alchemy 無料枠は 10 まで、PAYG なら 2000 推奨。大きいほど高速だがプラン上限に注意。",
    )
    max_workers = st.number_input(
        "Max workers",
        value=10,
        min_value=1,
        max_value=30,
        help="同時並列で投げる RPC リクエスト数。多いほど速いがレート制限に当たりやすい。PAYG なら 10〜20 が目安。",
    )
    commit_every = st.number_input(
        "Commit every (chunks)",
        value=5,
        min_value=1,
        max_value=50,
        help="DB に書き込む単位。N 個のチャンクをまとめて 1 トランザクションで commit。大きいほど DB 負荷が下がる。",
    )
    from_block_in = st.text_input(
        "From block (blank = resume from cursor)",
        value="",
        help="開始ブロック番号 (10進)。空欄なら ingest_cursor の続きから (なければ初期ブロックから) 再開します。",
    )
    to_block_in = st.text_input(
        "To block (blank = head)",
        value="",
        help="終了ブロック番号 (10進)。空欄ならチェーンの最新ヘッドまで取得します。",
    )
    if st.button(
        "Run backfill",
        help="OrderFilled ログを DB に取り込みます。途中で止めても cursor から再開可能。",
    ):
        from copytrader.indexer.backfill import backfill

        try:
            fb = int(from_block_in) if from_block_in else None
            tb = int(to_block_in) if to_block_in else None
            saved = run_with_live_logs(
                "backfill (this can take hours for full history)",
                backfill,
                from_block=fb,
                to_block=tb,
                chunk_size=int(chunk_size),
                max_workers=int(max_workers),
                commit_every=int(commit_every),
            )
            st.success(f"saved {saved} new trades")
        except Exception as e:
            st.error(str(e))

with c2:
    max_pages = st.number_input(
        "Max pages (0 = all)",
        value=0,
        min_value=0,
        help="Gamma API から取得するページ数の上限。0 で全件。動作確認だけなら 1〜2 で十分。",
    )
    if st.button(
        "Sync markets (Gamma API)",
        help="Polymarket の市場メタデータ (タイトル、token id 等) を取得し markets テーブルに保存します。",
    ):
        from copytrader.markets.gamma import sync_markets

        try:
            mp = int(max_pages) if max_pages > 0 else None
            saved = run_with_live_logs(
                "fetching market metadata from Gamma API",
                sync_markets,
                max_pages=mp,
            )
            st.success(f"saved {saved} markets")
        except Exception as e:
            st.error(str(e))

st.divider()

st.subheader("Live mode maintenance")
st.caption("These require WALLET creds and CLOB API to be set.")
c3, c4 = st.columns(2)
with c3:
    no_trip = st.checkbox(
        "Don't trip killswitch on mismatch",
        value=False,
        help="ON にすると、不整合があってもキルスイッチを発動しません。診断用途で使用、本番では通常 OFF。",
    )
    if st.button(
        "Reconcile on-chain",
        help="DB に記録されたポジションとオンチェーンの実残高を突合し、ズレがあれば一覧表示します。",
    ):
        from copytrader.executor.reconciler import reconcile_live
        from copytrader.risk.limits import RiskState

        try:
            state = RiskState()
            diffs = run_with_live_logs(
                "reconciling DB positions vs on-chain balances",
                reconcile_live,
                state=state,
                trip_on_mismatch=not no_trip,
            )
            if not diffs:
                st.success("all live positions match on-chain")
            else:
                st.warning(f"{len(diffs)} mismatches; killswitch={state.halted}")
                st.dataframe(
                    [
                        {
                            "token_id": d.token_id,
                            "expected": float(d.expected),
                            "actual": float(d.actual),
                            "diff": float(d.diff),
                        }
                        for d in diffs
                    ]
                )
        except Exception as e:
            st.error(str(e))

with c4:
    if st.button(
        "Poll open orders",
        help="CLOB API でオープン中の自注文の状態を取得し、約定 / キャンセルを DB に反映します。",
    ):
        from copytrader.executor.poller import poll_open_orders

        try:
            n = run_with_live_logs(
                "polling open orders via CLOB API",
                poll_open_orders,
            )
            st.success(f"updated {n} orders")
        except Exception as e:
            st.error(str(e))
