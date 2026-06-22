from __future__ import annotations

import streamlit as st

st.markdown("""
<style>
.stApp, .stApp > div { background: #000 !important; color: #fff !important; }
[data-testid="stHeader"] { background: #000 !important; }
</style>""", unsafe_allow_html=True)


def main() -> None:
    from sqlalchemy import select

    from copytrader.db.engine import get_session
    from copytrader.db.models import User
    from copytrader.web.auth import require_admin
    from copytrader.web.sidebar import render_sidebar

    require_admin()
    render_sidebar()

    st.title("👥 ユーザー管理")

    try:
        with get_session() as s:
            users = s.execute(select(User)).scalars().all()
    except Exception as e:  # noqa: BLE001
        st.error(f"DB エラー: {e}")
        return

    if not users:
        st.info("ユーザーが存在しません。")
        return

    for u in users:
        with st.expander(f"{u.email} ({u.role})"):
            col1, col2 = st.columns(2)
            with col1:
                new_role = st.selectbox(
                    "ロール",
                    ["user", "admin"],
                    index=0 if u.role == "user" else 1,
                    key=f"role_{u.id}",
                )
                if st.button("ロール変更", key=f"role_btn_{u.id}"):
                    try:
                        with get_session() as s:
                            user = s.get(User, u.id)
                            if user:
                                user.role = new_role
                        st.success("変更しました")
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"エラー: {e}")
            with col2:
                active = u.is_active
                label = "有効化" if not active else "無効化"
                if st.button(label, key=f"active_btn_{u.id}"):
                    try:
                        with get_session() as s:
                            user = s.get(User, u.id)
                            if user:
                                user.is_active = not active
                        st.success("変更しました")
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"エラー: {e}")


main()
