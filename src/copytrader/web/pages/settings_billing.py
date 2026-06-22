"""設定 > Billing — 支払履歴・領収書。"""
from __future__ import annotations

import datetime
import os

import pandas as pd
import streamlit as st

from copytrader.web.auth import current_user, require_login
from copytrader.web.sidebar import render_sidebar

st.set_page_config(page_title="Billing", layout="wide",
                   initial_sidebar_state="expanded")
require_login()
render_sidebar()

st.markdown("## 💳 Billing")

user = current_user()
if not user or not user.stripe_customer_id:
    st.info("まだお支払い情報がありません。")
    st.stop()

_stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
if not _stripe_key:
    st.warning("Billing 機能は現在利用できません。")
    st.stop()

import stripe  # noqa: E402

stripe.api_key = _stripe_key

try:
    if user.stripe_subscription_id:
        sub = stripe.Subscription.retrieve(user.stripe_subscription_id)
        col1, col2 = st.columns(2)
        col1.metric("ステータス", sub.status)
        col2.metric(
            "次回請求日",
            datetime.datetime.fromtimestamp(sub.current_period_end).strftime("%Y-%m-%d"),
        )

    st.markdown("### 支払履歴")
    invoices = stripe.Invoice.list(customer=user.stripe_customer_id, limit=20)
    rows = []
    for inv in invoices.auto_paging_iter():
        rows.append({
            "日付": datetime.datetime.fromtimestamp(inv.created).strftime("%Y-%m-%d"),
            "金額": f"¥{inv.amount_paid:,}",
            "ステータス": inv.status,
            "領収書": inv.hosted_invoice_url or "",
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("支払履歴がありません。")

    if st.button("支払い方法を変更"):
        portal = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=os.environ.get("APP_BASE_URL", "http://localhost:8501") + "/settings_billing",
        )
        st.markdown(f'<meta http-equiv="refresh" content="0; url={portal.url}">',
                    unsafe_allow_html=True)
except stripe.error.StripeError as e:
    st.error(f"Stripe エラー: {e}")
