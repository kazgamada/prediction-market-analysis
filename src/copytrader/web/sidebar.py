"""サイドバーレンダラ（黒背景・2階層ナビ）。"""
from __future__ import annotations

import streamlit as st

from copytrader.web.auth import current_user
from copytrader.web.navigation import ADMIN_NAVIGATION, NAVIGATION, NavItem

_SIDEBAR_CSS = """
<style>
[data-testid="stSidebar"] {
    background-color: #000 !important;
    color: #fff !important;
}
[data-testid="stSidebar"] a,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span {
    color: #fff !important;
}
.admin-divider {
    border-top: 1px solid #333;
    margin: 1rem 0 0.5rem;
}
</style>
"""


def render_sidebar() -> None:
    """全ページ共通サイドバー。require_login() の直後に呼ぶ。"""
    st.markdown(_SIDEBAR_CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("### 📊 Copytrader")
        _render_nav_items(NAVIGATION)

        user = current_user()
        if user and user.role == "admin":
            st.markdown('<div class="admin-divider"></div>', unsafe_allow_html=True)
            st.markdown("**管理者**")
            _render_nav_items(ADMIN_NAVIGATION)

        st.markdown("---")
        if user:
            st.caption(f"👤 {user.email}")
            if st.button("ログアウト", use_container_width=True, key="_sidebar_logout"):
                from copytrader.web.auth import logout
                logout()


def _render_nav_items(items: list[NavItem]) -> None:
    for item in items:
        if item.children:
            with st.expander(item.label, expanded=False):
                for child in item.children:
                    st.page_link(child.page, label=child.label)
        else:
            st.page_link(item.page, label=item.label)
