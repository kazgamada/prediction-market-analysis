"""管理者 > ユーザー管理。"""
from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from copytrader.db.engine import get_session
from copytrader.db.models import AdminAuditLog, User
from copytrader.web.auth import current_user, require_admin
from copytrader.web.forms import try_save
from copytrader.web.sidebar import render_sidebar

st.set_page_config(page_title="ユーザー管理", layout="wide",
                   initial_sidebar_state="expanded")
require_admin()
render_sidebar()

# 管理者ページ: 全面黒背景
st.markdown("""
<style>
.stApp { background: #000 !important; color: #fff !important; }
</style>""", unsafe_allow_html=True)

st.markdown("## 👥 ユーザー管理")

col1, col2 = st.columns([3, 1])
search = col1.text_input("メール検索")
status_filter = col2.selectbox("ステータス", ["全て", "active", "canceled", "past_due"])

with get_session() as s:
    q = select(User)
    if search:
        q = q.where(User.email.ilike(f"%{search}%"))
    if status_filter != "全て":
        q = q.where(User.subscription_status == status_filter)
    users = s.execute(q).scalars().all()

rows = [
    {
        "メール": u.email,
        "ロール": u.role,
        "サブスク": u.subscription_status or "—",
        "期限": str(u.subscription_period_end)[:10] if u.subscription_period_end else "—",
        "登録日": str(u.created_at)[:10],
        "有効": "✅" if u.is_active else "❌",
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
    with st.expander(f"👤 {u.email} の詳細", expanded=True):
        col1, col2, col3 = st.columns(3)
        col1.metric("ロール", u.role)
        col2.metric("ステータス", u.subscription_status or "—")
        col3.metric("有効", "✅" if u.is_active else "❌")

        with st.form(f"user_edit_{u.id}"):
            new_role = st.selectbox(
                "ロール変更", ["user", "admin"],
                index=0 if u.role == "user" else 1,
            )
            is_active = st.checkbox("有効", value=u.is_active)
            if st.form_submit_button("保存"):
                def _do_update() -> None:
                    with get_session() as s:
                        user_obj = s.get(User, u.id)
                        if user_obj:
                            user_obj.role = new_role
                            user_obj.is_active = is_active
                    with get_session() as s:
                        s.add(AdminAuditLog(
                            actor_id=current_user().id,
                            action="update_user",
                            target_type="user",
                            target_id=str(u.id),
                            detail={"role": new_role, "is_active": is_active},
                        ))
                if try_save(_do_update, "保存しました"):
                    st.rerun()

        if st.button("🚫 アカウントを凍結", type="secondary", key=f"freeze_{u.id}"):
            def _do_freeze() -> None:
                with get_session() as s:
                    user_obj = s.get(User, u.id)
                    if user_obj:
                        user_obj.is_active = False
                with get_session() as s:
                    s.add(AdminAuditLog(
                        actor_id=current_user().id,
                        action="freeze_user",
                        target_type="user",
                        target_id=str(u.id),
                        detail={},
                    ))
            if try_save(_do_freeze, f"{u.email} を凍結しました"):
                st.rerun()
