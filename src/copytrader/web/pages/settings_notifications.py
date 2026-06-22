"""設定 > 通知設定。"""
from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from copytrader.db.engine import get_session
from copytrader.db.models import NotificationPref
from copytrader.web.auth import current_user, require_login
from copytrader.web.forms import try_save
from copytrader.web.sidebar import render_sidebar

st.set_page_config(page_title="通知設定", layout="wide",
                   initial_sidebar_state="expanded")
require_login()
render_sidebar()

st.markdown("## 🔔 通知設定")

user = current_user()
if not user:
    st.stop()

with get_session() as s:
    pref = s.execute(
        select(NotificationPref).where(NotificationPref.user_id == user.id)
    ).scalar_one_or_none()

with st.form("notification_prefs_form"):
    invoice_paid = st.checkbox(
        "支払い完了通知",
        value=pref.invoice_paid if pref else True,
    )
    risk_halt = st.checkbox(
        "リスク停止通知",
        value=pref.risk_halt if pref else True,
    )
    daily_summary = st.checkbox(
        "日次サマリー",
        value=pref.daily_summary if pref else False,
    )
    if st.form_submit_button("保存"):
        def _do_save() -> None:
            with get_session() as s:
                existing = s.execute(
                    select(NotificationPref).where(NotificationPref.user_id == user.id)
                ).scalar_one_or_none()
                if existing:
                    existing.invoice_paid = invoice_paid
                    existing.risk_halt = risk_halt
                    existing.daily_summary = daily_summary
                else:
                    s.add(NotificationPref(
                        user_id=user.id,
                        invoice_paid=invoice_paid,
                        risk_halt=risk_halt,
                        daily_summary=daily_summary,
                    ))
        if try_save(_do_save, "設定を保存しました"):
            st.rerun()
