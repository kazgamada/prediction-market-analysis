"""Status (Home) — F15 / REBUILD §6.4.

このページは「今システムはどこまで取り込めているか」を実データで表示する唯一の場所。
モックデータは一切使わない。
- cursor block / head / lag
- 直近 1h の trade 件数
- dead-letter 件数
- RPC self-test 結果
- 直近の risk events
- 走行中 / 直近 jobs
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import streamlit as st
from sqlalchemy import desc, func, select

from copytrader.chain.errors import redact_url
from copytrader.config import settings
from copytrader.db.engine import get_session
from copytrader.db.engine import ping as db_ping
from copytrader.db.models import Cursor, Job, JobLog, RiskEvent, RpcDeadLetter, Trade
from copytrader.indexer.backfill import CURSOR_NAME
from copytrader.jobs.queue import enqueue
from copytrader.web.auth import require_password
from copytrader.web.format import fmt_ago

st.set_page_config(
    page_title="Status",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)
require_password()

st.markdown("""
<style>
.block-container{padding-top:0.5rem!important;padding-bottom:0.4rem!important;max-width:100%!important}
[data-testid="stMetric"]{padding:0.1rem!important}
[data-testid="stMetricLabel"]{font-size:0.7rem!important}
[data-testid="stMetricValue"]{font-size:1rem!important}
[data-testid="stMetricDelta"]{font-size:0.65rem!important}
h1,h3,h4,h5{padding:0!important;margin:0.2rem 0!important}
h1{font-size:1.2rem!important}
h5{font-size:0.85rem!important}
hr{margin:0.3rem 0!important}
.stDataFrame{font-size:0.72rem!important}
[data-testid="stVerticalBlockBorderWrapper"]{padding:0.3rem 0.5rem!important;border-radius:6px!important}
.stButton button{padding:0.2rem 0.5rem!important;font-size:0.78rem!important}
</style>
""", unsafe_allow_html=True)

st.markdown("# 📡 Status")


# ---------------------------------------------------------------------------
# データ取得 (5 秒 TTL)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=5)
def _snapshot() -> dict:
    try:
        with get_session() as s:
            cur = s.get(Cursor, CURSOR_NAME)
            one_h_ago = datetime.now(UTC) - timedelta(hours=1)
            trades_1h = int(
                s.execute(
                    select(func.count()).select_from(Trade).where(Trade.ts >= one_h_ago)
                ).scalar_one()
            )
            trades_total = int(
                s.execute(select(func.count()).select_from(Trade)).scalar_one()
            )
            dl_pending = int(
                s.execute(
                    select(func.count()).select_from(RpcDeadLetter)
                    .where(RpcDeadLetter.resolved_at.is_(None))
                ).scalar_one()
            )
            running_jobs = int(
                s.execute(
                    select(func.count()).select_from(Job).where(Job.status == "RUNNING")
                ).scalar_one()
            )
            recent_risks = s.execute(
                select(RiskEvent).order_by(desc(RiskEvent.ts)).limit(3)
            ).scalars().all()
            return {
                "cursor_block": cur.last_block if cur else None,
                "cursor_updated_at": cur.updated_at if cur else None,
                "trades_1h": trades_1h,
                "trades_total": trades_total,
                "dl_pending": dl_pending,
                "running_jobs": running_jobs,
                "recent_risks": [
                    {"kind": r.kind, "severity": r.severity, "msg": r.message, "ts": r.ts}
                    for r in recent_risks
                ],
                "db_error": None,
            }
    except Exception as e:  # noqa: BLE001
        return {"db_error": str(e)}


@st.cache_data(ttl=30)
def _rpc_status() -> tuple[bool, str]:
    """RPC の最新ブロック取得を試みる (30 秒 TTL)。"""
    try:
        import asyncio

        from copytrader.chain.client import JsonRpcClient
        if not settings.polygon_rpc_http:
            return False, "POLYGON_RPC_HTTP unset"

        async def _check() -> tuple[bool, str]:
            c = JsonRpcClient(settings.polygon_rpc_http)
            try:
                head = await c.get_block_number()
                return True, f"head={head:,}"
            finally:
                await c.aclose()

        return asyncio.run(_check())
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


snap = _snapshot()
db_ok = db_ping()

# ---------------------------------------------------------------------------
# ステータスバー
# ---------------------------------------------------------------------------
sb = st.columns(6)

if snap.get("db_error"):
    sb[0].error(f"db: {snap['db_error'][:50]}", icon="🔴")
else:
    sb[0].metric(
        "DB",
        "ok" if db_ok else "down",
        help="PostgreSQL 接続状態。down なら Fly.io の Postgres ダッシュボードを確認。",
    )
    sb[1].metric(
        "cursor block",
        f"{snap['cursor_block']:,}" if snap["cursor_block"] else "—",
        fmt_ago(snap["cursor_updated_at"]) if snap["cursor_updated_at"] else "no cursor",
        help="indexer が処理した最新ブロック。更新が 5 分止まっていたら indexer 停止の可能性。",
    )
    sb[2].metric(
        "trades (1h)",
        f"{snap['trades_1h']:,}",
        help="直近 1 時間で取り込んだ trade 件数。0 が続くなら indexer 停止または市場閑散。",
    )
    sb[3].metric(
        "trades (total)",
        f"{snap['trades_total']:,}",
        help="DB に蓄積した全 trade 件数。",
    )
    sb[4].metric(
        "dead-letters",
        snap["dl_pending"],
        delta_color="inverse" if snap["dl_pending"] > 0 else "off",
        help="未解決 RPC エラー chunk 数。10 件超で警戒。",
    )
    sb[5].metric(
        "running jobs",
        snap["running_jobs"],
        help="現在 worker が実行中の job 数。",
    )

# ---------------------------------------------------------------------------
# RPC self-test / Phase 0 ボタン / Risk events
# ---------------------------------------------------------------------------
r1 = st.columns([1, 1.5, 1])

with r1[0], st.container(border=True):
    st.markdown("##### RPC self-test")
    if not settings.polygon_rpc_http:
        st.warning("POLYGON_RPC_HTTP が未設定")
    else:
        rpc_ok, rpc_detail = _rpc_status()
        if rpc_ok:
            st.success(f"✅ OK — {rpc_detail}", icon="✅")
        else:
            st.error(f"🔴 NG — {rpc_detail}")
        st.caption(f"HTTP: {redact_url(settings.polygon_rpc_http) or '(unset)'}")
        st.caption(f"WS: {redact_url(settings.polygon_rpc_ws) or '(unset)'}")

with r1[1], st.container(border=True):
    st.markdown("##### Phase 0 を実行")
    st.caption("バックフィル → ランク → リプレイ を連続実行します。")
    with st.form("phase0_home"):
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1.2])
        w = c1.number_input("window 日", min_value=1, max_value=90, value=30)
        tn = c2.number_input("top N", min_value=1, max_value=200, value=10)
        cu = c3.number_input("copy $", min_value=1, max_value=10000, value=50)
        ds = c4.text_input("delays (秒)", "30,60,120")
        sub = st.form_submit_button("▶ Run Phase 0", type="primary",
                                    use_container_width=True)
        if sub:
            try:
                delays = [int(x.strip()) for x in ds.split(",") if x.strip()]
                idem = f"phase0:{datetime.now(UTC).strftime('%Y%m%d%H%M')}:{int(w)}:{int(tn)}"
                jid = enqueue("phase0", {
                    "window": int(w), "watchlist_top": int(tn),
                    "delays": delays, "copy_usd_per_trade": float(cu),
                }, idempotency_key=idem)
                st.success(f"enqueued job #{jid} — Strategy ページでログを確認")
            except Exception as e:  # noqa: BLE001
                st.error(f"enqueue 失敗: {e}")

with r1[2], st.container(border=True):
    st.markdown("##### Risk Events")
    if not snap.get("db_error"):
        risks = snap.get("recent_risks", [])
        if not risks:
            st.success("記録なし (正常)")
        else:
            sev_label = {1: "info", 2: "warn", 3: "alert"}
            for rv in risks:
                sev = sev_label.get(rv["severity"], str(rv["severity"]))
                fn = st.error if rv["severity"] >= 3 else (st.warning if rv["severity"] == 2 else st.info)
                fn(f"[{sev}] {rv['kind']}: {rv['msg'][:80]} ({fmt_ago(rv['ts'])})")
    else:
        st.error(snap["db_error"][:60])

# ---------------------------------------------------------------------------
# 直近 jobs
# ---------------------------------------------------------------------------
st.markdown("##### 直近 Jobs")

@st.cache_data(ttl=3)
def _recent_jobs() -> list[dict]:
    try:
        with get_session() as s:
            rows = s.execute(
                select(Job).order_by(desc(Job.created_at)).limit(10)
            ).scalars().all()
            return [
                {
                    "id": r.id,
                    "kind": r.kind,
                    "status": r.status,
                    "created": fmt_ago(r.created_at),
                    "finished": fmt_ago(r.finished_at) if r.finished_at else "—",
                    "error": (r.error_text or "")[:60],
                }
                for r in rows
            ]
    except Exception as e:  # noqa: BLE001
        return [{"error": str(e)}]


jobs_data = _recent_jobs()
st.dataframe(jobs_data, use_container_width=True, hide_index=True, height=220)

# ---------------------------------------------------------------------------
# 選択 job のログ (F17: live log with polling)
# ---------------------------------------------------------------------------
st.markdown("##### Job ログ")
col_jid, col_refresh = st.columns([2, 1])
job_id_input = col_jid.number_input(
    "Job ID", min_value=1, step=1,
    value=jobs_data[0]["id"] if jobs_data and "id" in jobs_data[0] else 1,
    key="status_jid",
    label_visibility="collapsed",
)
auto_refresh = col_refresh.checkbox("2 秒おきに更新", value=False, key="status_auto")

@st.cache_data(ttl=2)
def _job_logs(job_id: int) -> tuple[dict | None, list[str]]:
    try:
        with get_session() as s:
            j = s.get(Job, job_id)
            if not j:
                return None, []
            logs = s.execute(
                select(JobLog).where(JobLog.job_id == job_id)
                .order_by(JobLog.ts).limit(200)
            ).scalars().all()
            return (
                {"status": j.status, "progress": j.progress, "result": j.result,
                 "error": j.error_text},
                [f"[{lg.ts.strftime('%H:%M:%S')}] {lg.message}" for lg in logs],
            )
    except Exception as e:  # noqa: BLE001
        return None, [str(e)]


job_meta, job_logs_lines = _job_logs(int(job_id_input))
if job_meta:
    status_color = {"SUCCEEDED": "green", "FAILED": "red", "RUNNING": "orange"}.get(
        job_meta["status"], "gray"
    )
    st.markdown(
        f"<span style='color:{status_color};font-weight:bold'>{job_meta['status']}</span>"
        + (f" — {job_meta['error']}" if job_meta.get("error") else ""),
        unsafe_allow_html=True,
    )
    if job_meta.get("progress"):
        st.json(job_meta["progress"], expanded=False)
    if job_meta.get("result"):
        st.json(job_meta["result"], expanded=True)
    if job_logs_lines:
        st.code("\n".join(job_logs_lines), language=None)
    else:
        st.caption("ログなし")
else:
    st.caption("job が見つかりません")

if auto_refresh:
    import time
    time.sleep(2)
    st.rerun()

# ---------------------------------------------------------------------------
# フッター: Build info
# ---------------------------------------------------------------------------
st.markdown(
    f"<div style='font-size:0.65rem;color:#aaa;margin-top:1rem'>"
    f"git={settings.git_sha} | build={settings.build_time} | "
    f"window={settings.indexer_window_days}d</div>",
    unsafe_allow_html=True,
)
