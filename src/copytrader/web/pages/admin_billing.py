"""管理者 > Billing 管理。"""
from __future__ import annotations

import datetime as _dt
import os

import pandas as pd
import streamlit as st
from sqlalchemy import select

from copytrader.db.engine import get_session
from copytrader.db.models import AdminAuditLog, User
from copytrader.web.auth import current_user, require_admin
from copytrader.web.sidebar import render_sidebar

st.set_page_config(page_title="Admin Billing", layout="wide",
                   initial_sidebar_state="expanded")
require_admin()
render_sidebar()

st.markdown("""
<style>
.stApp { background: #000 !important; color: #fff !important; }
</style>""", unsafe_allow_html=True)

st.markdown("## 💳 Billing 管理")

_stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
if not _stripe_key:
    st.warning("STRIPE_SECRET_KEY が設定されていません。Billing 機能は無効です。")
    st.stop()

import stripe  # noqa: E402

stripe.api_key = _stripe_key

with get_session() as s:
    users = s.execute(
        select(User).where(User.stripe_customer_id.is_not(None))
    ).scalars().all()

rows = [
    {
        "メール": u.email,
        "ステータス": u.subscription_status or "—",
        "期限": str(u.subscription_period_end)[:10] if u.subscription_period_end else "—",
    }
    for u in users
]

event = st.dataframe(
    pd.DataFrame(rows),
    use_container_width=True,
    on_select="rerun",
    selection_mode="single-row",
)

if event.selection.rows:
    u = users[event.selection.rows[0]]
    with st.expander(f"📋 {u.email} の支払履歴", expanded=True):
        try:
            invoices = stripe.Invoice.list(customer=u.stripe_customer_id, limit=10)
            for inv in invoices.auto_paging_iter():
                c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                c1.write(_dt.datetime.fromtimestamp(inv.created).strftime("%Y-%m-%d"))
                c2.write(f"¥{inv.amount_paid:,}")
                c3.write(inv.status)
                if inv.invoice_pdf:
                    c4.markdown(f"[PDF]({inv.invoice_pdf})")
        except stripe.error.StripeError as e:
            st.error(f"Stripe エラー: {e}")

        st.markdown("---")
        charge_id = st.text_input("返金対象の Charge ID", key=f"charge_{u.id}")
        amount = st.number_input("返金額（円）", min_value=1, key=f"amount_{u.id}")
        if st.button("⚠️ 返金実行", type="secondary", key=f"refund_{u.id}"):
            if st.session_state.get(f"_refund_confirmed_{u.id}"):
                try:
                    stripe.Refund.create(charge=charge_id, amount=int(amount))
                    with get_session() as s:
                        s.add(AdminAuditLog(
                            actor_id=current_user().id,
                            action="refund",
                            target_type="charge",
                            target_id=charge_id,
                            detail={"amount": amount},
                        ))
                    st.success("返金しました")
                    st.session_state.pop(f"_refund_confirmed_{u.id}", None)
                except stripe.error.StripeError as e:
                    st.error(f"返金エラー: {e}")
            else:
                st.warning(f"¥{amount:,} を返金します。もう一度押して確定してください。")
                st.session_state[f"_refund_confirmed_{u.id}"] = True
