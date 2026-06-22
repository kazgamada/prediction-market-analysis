from __future__ import annotations

import streamlit as st

_SIDEBAR_CSS = """
<style>
[data-testid="stSidebar"] {
    background: #000 !important;
}
[data-testid="stSidebar"] * {
    color: #fff !important;
}
[data-testid="stSidebar"] .stMarkdown a {
    color: #7dd3fc !important;
}
</style>
"""


def render_sidebar() -> None:
    """左サイドバーを描画する（黒背景 + 2階層ナビ + 管理者メニュー下端）。"""
    from copytrader.web.auth import current_user
    from copytrader.web.navigation import ADMIN_NAVIGATION, NAVIGATION

    st.markdown(_SIDEBAR_CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("## CopyTrader")
        st.markdown("---")
        for item in NAVIGATION:
            st.markdown(f"{item['icon']} **{item['label']}**")

        user = current_user()
        if user and getattr(user, "role", None) == "admin":
            st.markdown("---")
            st.markdown("### 管理者メニュー")
            for item in ADMIN_NAVIGATION:
                st.markdown(f"{item['icon']} {item['label']}")
