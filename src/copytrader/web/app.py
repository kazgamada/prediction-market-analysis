"""Streamlit entry point for the polymarket-copytrader admin UI.

Run locally:
    streamlit run src/copytrader/web/app.py

The UI is read/write for analytical operations (rank, replay, inspect, watchlist).
Secrets stay in env (Fly secrets or .env); the UI only displays whether each
secret is configured, never the value itself.
"""

from __future__ import annotations

import os

import streamlit as st

from copytrader.config import get_settings

st.set_page_config(
    page_title="polymarket-copytrader",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)


def _gate() -> bool:
    """Optional shared-secret gate when WEB_PASSWORD is set."""
    expected = os.getenv("WEB_PASSWORD") or ""
    if not expected:
        return True
    if st.session_state.get("auth_ok"):
        return True
    with st.sidebar:
        pw = st.text_input("Password", type="password")
        if st.button("Enter"):
            if pw == expected:
                st.session_state["auth_ok"] = True
                st.rerun()
            else:
                st.error("wrong password")
    st.stop()
    return False


def main() -> None:
    _gate()

    st.title(":chart_with_upwards_trend: polymarket-copytrader")
    st.caption(
        "Smart-money copy-trade research and operations console. "
        "Pick a page from the sidebar."
    )

    s = get_settings()
    cols = st.columns(4)
    cols[0].metric(
        "Polygon HTTP",
        "set" if s.polygon_rpc_http else "missing",
        help="Polygon の HTTP RPC エンドポイント (POLYGON_RPC_HTTP)。eth_getLogs などのオンチェーン読み取りに使用。",
    )
    cols[1].metric(
        "Polygon WS",
        "set" if s.polygon_rpc_ws else "missing",
        help="Polygon の WebSocket RPC (POLYGON_RPC_WS)。ライブモードのリアルタイム購読に使用。",
    )
    cols[2].metric(
        "CLOB API",
        "set" if s.polymarket_api_key else "missing",
        help="Polymarket CLOB API キー。ライブ発注に必要。リサーチだけなら未設定でよい。",
    )
    cols[3].metric(
        "Wallet",
        "EOA"
        if s.wallet_private_key and not s.wallet_proxy_address
        else ("proxy" if s.wallet_proxy_address else "missing"),
        help="発注ウォレット種別。EOA=直の秘密鍵 / proxy=Safe等のプロキシ。ライブモードで必要。",
    )

    st.markdown(
        """
        ### Phase guide

        - **Phase 0** (offline): run `Backfill`, then `Rank`, then `Replay` to confirm edge.
        - **Phase 1**: pick a watchlist on the `Rank` page (top N → Watchlist).
        - **Phase 2-3**: run the `monitor` or `paper` worker on Fly. Use this UI to
          watch signals come in (`Status` page).
        - **Phase 4+**: run the `live` worker; use `Reconcile` and `Poll` actions
          to verify before trusting fills.
        """
    )


if __name__ == "__main__":
    main()
