"""One-shot operations: backfill, sync markets, reconcile, poll."""

from __future__ import annotations

import streamlit as st

from copytrader.config import get_settings

st.title("Actions")
st.caption("One-shot maintenance operations. Long jobs run in this process; "
           "for production-scale backfills, run the corresponding CLI on a worker.")

s = get_settings()
if not s.polygon_rpc_http:
    st.error("POLYGON_RPC_HTTP is not set; chain operations will fail.")

st.subheader("Indexer")
c1, c2 = st.columns(2)
with c1:
    chunk_size = st.number_input("Chunk size", value=1000, min_value=100, max_value=5000)
    from_block_in = st.text_input("From block (blank = resume from cursor)", value="")
    to_block_in = st.text_input("To block (blank = head)", value="")
    if st.button("Run backfill"):
        from copytrader.indexer.backfill import backfill

        with st.spinner("running backfill (this can take hours for full history)…"):
            try:
                fb = int(from_block_in) if from_block_in else None
                tb = int(to_block_in) if to_block_in else None
                saved = backfill(from_block=fb, to_block=tb, chunk_size=int(chunk_size))
                st.success(f"saved {saved} new trades")
            except Exception as e:
                st.error(str(e))

with c2:
    max_pages = st.number_input("Max pages (0 = all)", value=0, min_value=0)
    if st.button("Sync markets (Gamma API)"):
        from copytrader.markets.gamma import sync_markets

        with st.spinner("fetching market metadata…"):
            try:
                mp = int(max_pages) if max_pages > 0 else None
                saved = sync_markets(max_pages=mp)
                st.success(f"saved {saved} markets")
            except Exception as e:
                st.error(str(e))

st.divider()

st.subheader("Live mode maintenance")
st.caption("These require WALLET creds and CLOB API to be set.")
c3, c4 = st.columns(2)
with c3:
    no_trip = st.checkbox("Don't trip killswitch on mismatch", value=False)
    if st.button("Reconcile on-chain"):
        from copytrader.executor.reconciler import reconcile_live
        from copytrader.risk.limits import RiskState

        try:
            state = RiskState()
            diffs = reconcile_live(state=state, trip_on_mismatch=not no_trip)
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
    if st.button("Poll open orders"):
        from copytrader.executor.poller import poll_open_orders

        try:
            n = poll_open_orders()
            st.success(f"updated {n} orders")
        except Exception as e:
            st.error(str(e))
