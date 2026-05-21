"""Execute — Execution console + Watchlist + Jobs + Rollout phase on single viewport."""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from copytrader.db.engine import get_session
from copytrader.db.models import Job, Watchlist
from copytrader.web.auth import require_password
from copytrader.web.format import fmt_ago, short_addr

st.set_page_config(page_title="Execute", layout="wide",
                   initial_sidebar_state="collapsed")
require_password()

st.markdown("""
<style>
.block-container { padding-top: 0.6rem !important; padding-bottom: 0.4rem !important; max-width: 100% !important; }
[data-testid="stMetric"] { padding: 0.1rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.7rem !important; }
[data-testid="stMetricValue"] { font-size: 1.0rem !important; }
[data-testid="stMetricDelta"] { font-size: 0.65rem !important; }
h1, h3, h4, h5 { padding: 0 !important; margin: 0.2rem 0 !important; }
h1 { font-size: 1.2rem !important; }
h5 { font-size: 0.85rem !important; }
hr { margin: 0.3rem 0 !important; }
.stDataFrame { font-size: 0.72rem !important; }
[data-testid="stVerticalBlockBorderWrapper"] { padding: 0.3rem 0.5rem !important; }
.stProgress > div > div > div { height: 6px !important; }
.stButton button { padding: 0.2rem 0.5rem !important; font-size: 0.78rem !important; }
input, .stNumberInput input { font-size: 0.78rem !important; }
.stTabs [data-baseweb="tab"] { padding: 0.2rem 0.5rem !important; font-size: 0.78rem !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("# Execute　<small style='font-size:0.7rem;color:#888;'>Phase B Micro — 18/28日 / $10 per trade</small>",
            unsafe_allow_html=True)

rng = np.random.default_rng(7)

sb = st.columns([1, 1, 1, 1, 1, 1, 1.2])
sb[0].metric("USDC", "$8,432", "-$120")
sb[1].metric("MATIC", "12.4", "OK")
sb[2].metric("オープン", "7", "$3,210")
sb[3].metric("今日 PnL", "+$184", "+2.2%")
sb[4].metric("Sharpe 30d", "1.42", "+0.08")
sb[5].metric("phase 累計", "+$72", "+$8 (24h)")
with sb[6]:
    kill = st.toggle("Kill Switch", value=False, key="kill_mock")
    if kill:
        st.error("🛑 HALTED")
    else:
        st.success("🟢 LIVE")

r1 = st.columns([1, 1.3, 1.4])

with r1[0], st.container(border=True):
    st.markdown("##### リスク")
    g = go.Figure(go.Indicator(
        mode="gauge+number", value=3.2,
        number={"suffix": "%", "valueformat": ".1f", "font": {"size": 20}},
        title={"text": "今日 DD", "font": {"size": 10}},
        gauge={"axis": {"range": [0, 8], "tickfont": {"size": 8}},
               "bar": {"color": "#d9534f"},
               "steps": [{"range": [0, 4], "color": "#e7f6e7"},
                         {"range": [4, 6.4], "color": "#fff3cd"},
                         {"range": [6.4, 8], "color": "#f8d7da"}],
               "threshold": {"line": {"color": "red", "width": 3},
                             "thickness": 0.75, "value": 8}}))
    g.update_layout(height=140, margin=dict(t=20, b=0, l=10, r=10))
    st.plotly_chart(g, use_container_width=True)
    st.progress(0.43, text="exposure 43/70%")
    st.progress(1.0, text="単一 token 27/25% ⚠")
    st.progress(0.62, text="trades 62/100")
    st.progress(0.38, text="連敗 2/5")

with r1[1], st.container(border=True):
    tab_pos, tab_sig, tab_fill = st.tabs(["ポジション", "シグナル", "fills"])
    with tab_pos:
        pos = pd.DataFrame({
            "market": ["米大統領 — Dem", "FRB 6月 — Yes", "BTC>$150k — Yes",
                       "AI — No", "G7 — Yes", "WC — Brazil", "投票率 — Yes"],
            "side": ["B", "B", "B", "S", "B", "B", "B"],
            "size": [320, 250, 480, 410, 200, 180, 1370],
            "PnL": [22.8, 13.6, 80.0, 12.0, -2.8, -30.0, 90.2],
            "保有": ["2h", "5h", "1d", "3d", "12h", "8h", "30m"],
        })
        st.dataframe(pos, use_container_width=True, hide_index=True, height=235,
                     column_config={
                         "size": st.column_config.NumberColumn(format="$%d"),
                         "PnL": st.column_config.NumberColumn(format="$%+.1f"),
                     })
    with tab_sig:
        now = datetime.now(UTC)
        sig = pd.DataFrame({
            "時刻": [(now - timedelta(seconds=int(s))).strftime("%H:%M:%S")
                     for s in sorted(rng.integers(5, 900, 8))],
            "wallet": [f"0x{rng.integers(0, 16**8):08x}" for _ in range(8)],
            "market": rng.choice(["米大統領", "FRB", "BTC", "AI"], 8),
            "side": rng.choice(["B", "S"], 8).tolist(),
            "price": [round(float(rng.uniform(0.1, 0.9)), 3) for _ in range(8)],
            "状態": rng.choice(["✅", "⏳", "❌", "⏭"], 8, p=[0.5, 0.2, 0.1, 0.2]).tolist(),
        })
        st.dataframe(sig, use_container_width=True, hide_index=True, height=235)
    with tab_fill:
        fills = pd.DataFrame({
            "時刻": [(datetime.now(UTC) - timedelta(seconds=int(s))).strftime("%H:%M:%S")
                     for s in sorted(rng.integers(30, 7200, 8))],
            "market": rng.choice(["米大統領", "FRB", "BTC", "AI", "WC"], 8),
            "side": rng.choice(["B", "S"], 8).tolist(),
            "size": [int(rng.choice([50, 100, 150, 200])) for _ in range(8)],
            "ms": [int(rng.normal(850, 280)) for _ in range(8)],
            "slip%": [round(float(rng.normal(0.4, 0.6)), 2) for _ in range(8)],
            "PnL": [round(float(rng.normal(2, 12)), 2) for _ in range(8)],
        })
        st.dataframe(fills, use_container_width=True, hide_index=True, height=235,
                     column_config={
                         "size": st.column_config.NumberColumn(format="$%d"),
                         "ms": st.column_config.NumberColumn(format="%d"),
                         "slip%": st.column_config.NumberColumn(format="%+.2f"),
                         "PnL": st.column_config.NumberColumn(format="$%+.1f"),
                     })

with r1[2], st.container(border=True):
    tab_wl, tab_jobs, tab_manual = st.tabs(["Watchlist", "Jobs", "手動 order"])
    ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

    def _addr_to_bytes(s: str) -> bytes | None:
        s = s.strip()
        if not ADDR_RE.match(s):
            return None
        return bytes.fromhex(s[2:].lower())

    with tab_wl:
        with st.form("add_wl"):
            ac1, ac2, ac3 = st.columns([3, 2, 1])
            a_str = ac1.text_input("address (0x...)", label_visibility="collapsed",
                                   placeholder="0x...")
            note = ac2.text_input("note", label_visibility="collapsed",
                                  placeholder="note")
            ok = ac3.form_submit_button("Add", type="primary",
                                        use_container_width=True)
            if ok:
                ab = _addr_to_bytes(a_str)
                if ab is None:
                    st.error("invalid address")
                else:
                    try:
                        with get_session() as s:
                            stmt = pg_insert(Watchlist).values(
                                address=ab, note=note or None, active=True,
                            )
                            stmt = stmt.on_conflict_do_update(
                                index_elements=[Watchlist.address],
                                set_={"note": stmt.excluded.note, "active": True},
                            )
                            s.execute(stmt)
                        st.success(f"added {short_addr(ab)}")
                    except Exception as e:  # noqa: BLE001
                        st.error(str(e))
        try:
            with get_session() as s:
                rows = s.execute(
                    select(Watchlist).order_by(Watchlist.added_at.desc()).limit(20)
                ).scalars().all()
                wdata = [
                    {
                        "address": "0x" + r.address.hex()[:16] + "…",
                        "note": r.note,
                        "active": r.active,
                        "added": fmt_ago(r.added_at),
                    }
                    for r in rows
                ]
        except Exception as e:  # noqa: BLE001
            wdata = []
            st.caption(f"db: {e}")
        st.dataframe(wdata, use_container_width=True, hide_index=True, height=180)
    with tab_jobs:
        try:
            with get_session() as s:
                rows = s.execute(
                    select(Job).order_by(desc(Job.created_at)).limit(15)
                ).scalars().all()
                jdata = [
                    {
                        "id": r.id, "kind": r.kind, "status": r.status,
                        "created": fmt_ago(r.created_at),
                        "finished": fmt_ago(r.finished_at) if r.finished_at else "—",
                    }
                    for r in rows
                ]
        except Exception as e:  # noqa: BLE001
            jdata = []
            st.caption(f"db: {e}")
        st.dataframe(jdata, use_container_width=True, hide_index=True, height=235)
    with tab_manual:
        with st.form("manual"):
            mc1, mc2 = st.columns(2)
            mc1.text_input("token_id", "0x1234abcd…", disabled=True)
            mc2.selectbox("side", ["BUY", "SELL"])
            mc1.number_input("size $", min_value=10, max_value=1000, value=50,
                             step=10)
            mc2.number_input("price", min_value=0.01, max_value=0.99, value=0.50,
                             step=0.01, format="%.2f")
            mc1.selectbox("TIF", ["GTC", "IOC", "FOK"])
            confirm = mc2.checkbox("リスク無視")
            st.form_submit_button("発注", type="primary",
                                  use_container_width=True, disabled=not confirm)

r2 = st.columns([1.5, 1, 1])

with r2[0], st.container(border=True):
    st.markdown("##### Rollout 進行 (A→B→C→D)")
    PHASES = [
        ("A", "Paper", 28, 0, "#9aa0a6"),
        ("B", "Micro", 28, 10, "#5b9bd5"),
        ("C", "Small", 56, 50, "#2c7fb8"),
        ("D", "Scale", 9999, 250, "#1a5490"),
    ]
    CUR, DAY = 1, 18
    stp = go.Figure()
    for i, (pid, name, dur, sz, col) in enumerate(PHASES):
        if i < CUR:
            color, op, suf = "#2ca02c", 1.0, " ✓"
        elif i == CUR:
            color, op, suf = col, 1.0, " ●"
        else:
            color, op, suf = "#cccccc", 0.5, ""
        stp.add_shape(type="rect", x0=i + 0.05, x1=i + 0.95, y0=0.35, y1=0.85,
                      fillcolor=color, opacity=op, line=dict(width=0))
        stp.add_annotation(
            x=i + 0.5, y=0.6, showarrow=False,
            text=f"<b>{pid}{suf}</b> {name}　<span style='font-size:8px;color:#eee'>{dur}d/${sz}</span>",
            font=dict(size=10, color="white" if op > 0.7 else "#666"))
        if i < len(PHASES) - 1:
            stp.add_annotation(x=i + 1, y=0.6, showarrow=False, text="→",
                               font=dict(size=14, color="#888"))
    prog = DAY / max(1, PHASES[CUR][2])
    stp.add_shape(type="rect", x0=CUR + 0.05,
                  x1=CUR + 0.05 + 0.9 * min(prog, 1.0),
                  y0=0.27, y1=0.32, fillcolor="#ff8c00", line=dict(width=0))
    stp.update_layout(height=70, margin=dict(t=0, b=0, l=5, r=5),
                      xaxis=dict(visible=False, range=[0, len(PHASES)]),
                      yaxis=dict(visible=False, range=[0, 1]),
                      plot_bgcolor="white")
    st.plotly_chart(stp, use_container_width=True, key="stepper")
    ac = st.columns(4)
    ac[0].button("→ C 昇格", type="primary", use_container_width=True,
                 disabled=True)
    ac[1].button("継続", use_container_width=True)
    ac[2].button("← A 降格", use_container_width=True)
    confirm_h = ac[3].checkbox("HALT")
    st.button("🛑 全停止", use_container_width=True, disabled=not confirm_h)

with r2[1], st.container(border=True):
    st.markdown("##### 昇格条件 (5/7)")
    promo = [
        ("経過 ≥ 28d", False, "18日"),
        ("ROI ≥ +3%", True, "+4.2%"),
        ("DD ≤ 8%", True, "-5.1%"),
        ("勝率 ≥ 52%", True, "56.8%"),
        ("乖離 ≤ 20%", True, "12%"),
        ("Latency ≤ 3000ms", False, "3,420"),
        ("kill switch test", True, "3日前"),
    ]
    pdf = pd.DataFrame([
        {"条件": c, "現在": n, " ": "✅" if ok else "⏳"}
        for c, ok, n in promo
    ])
    st.dataframe(pdf, use_container_width=True, hide_index=True, height=185)

with r2[2], st.container(border=True):
    st.markdown("##### 停止条件 (1 ヒット ⚠)")
    halt = [
        ("日次 PnL < -5%", False, "+0.9%"),
        ("7d PnL < -8%", False, "+2.1%"),
        ("連敗 ≥ 5", False, "2"),
        ("単一 market > 25%", True, "27%"),
        ("indexer lag > 120s", False, "18s"),
        ("USDC < $500", False, "$8,432"),
        ("MATIC < 1.0", False, "12.4"),
    ]
    hdf = pd.DataFrame([
        {"条件": c, "現在": n, " ": "🛑" if t else "🟢"}
        for c, t, n in halt
    ])
    st.dataframe(hdf, use_container_width=True, hide_index=True, height=185)
