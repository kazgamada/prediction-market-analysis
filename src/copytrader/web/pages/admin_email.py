"""管理者 > メール送信。"""
from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from copytrader.db.engine import get_session
from copytrader.db.models import AdminAuditLog, User
from copytrader.email.client import EmailMessage, send_email
from copytrader.web.auth import current_user, require_admin
from copytrader.web.sidebar import render_sidebar

st.set_page_config(page_title="メール送信", layout="wide",
                   initial_sidebar_state="expanded")
require_admin()
render_sidebar()

st.markdown("""
<style>
.stApp { background: #000 !important; color: #fff !important; }
</style>""", unsafe_allow_html=True)

st.markdown("## 📧 ユーザーへのメール送信")

target = st.radio("送信対象", ["全ユーザー", "絞り込み（ステータス別）", "個別指定"])
subject = st.text_input("件名")
body = st.text_area("本文（HTML可）")

if target == "絞り込み（ステータス別）":
    status_filter = st.selectbox("サブスクステータス", ["active", "trialing", "past_due", "canceled"])
elif target == "個別指定":
    target_email = st.text_input("送信先メールアドレス")


def _resolve_targets(target_mode: str) -> list[User]:
    with get_session() as s:
        if target_mode == "全ユーザー":
            return s.execute(select(User).where(User.is_active.is_(True))).scalars().all()
        if target_mode == "絞り込み（ステータス別）":
            sf = st.session_state.get("status_filter", "active")
            return s.execute(
                select(User).where(User.subscription_status == sf)
            ).scalars().all()
        # 個別指定
        te = st.session_state.get("target_email", "")
        if not te:
            return []
        result = s.execute(select(User).where(User.email == te)).scalar_one_or_none()
        return [result] if result else []


if st.button("送信", type="primary"):
    if not subject or not body:
        st.error("件名と本文を入力してください")
    else:
        with st.spinner("送信中..."):
            resolved = _resolve_targets(target)
            for u in resolved:
                send_email(EmailMessage(to=u.email, subject=subject, html=body))
            with get_session() as s:
                s.add(AdminAuditLog(
                    actor_id=current_user().id,
                    action="send_email",
                    target_type="users",
                    target_id=target,
                    detail={"subject": subject, "count": len(resolved)},
                ))
        st.success(f"{len(resolved)} 件送信しました")
