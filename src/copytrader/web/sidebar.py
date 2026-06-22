"""サイドバーレンダラ（黒背景・グループ分けナビ）。

Streamlit 標準のページ自動ナビ（pages/ をファイル名で並べるもの）は
hide_default_page_nav() で隠し、このカスタムナビ 1 本に統一する。
"""
from __future__ import annotations

import streamlit as st

from copytrader.web.auth import current_user
from copytrader.web.navigation import NAV_SECTIONS, NavItem

# 標準ページナビを隠すための CSS（ログイン前画面でも効くよう auth 側でも適用）
HIDE_DEFAULT_NAV_CSS = """
<style>
[data-testid="stSidebarNav"] { display: none !important; }
</style>
"""

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
.nav-section-title {
    color: #7a8499 !important;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    margin: 1rem 0 0.25rem;
}
</style>
"""


def hide_default_page_nav() -> None:
    """Streamlit 標準のページ自動ナビを非表示にする。"""
    st.markdown(HIDE_DEFAULT_NAV_CSS, unsafe_allow_html=True)


def render_sidebar() -> None:
    """全ページ共通サイドバー。require_login() の直後に呼ぶ。"""
    hide_default_page_nav()
    st.markdown(_SIDEBAR_CSS, unsafe_allow_html=True)
    user = current_user()
    is_admin = bool(user and user.role == "admin")

    with st.sidebar:
        st.markdown("### 📊 Copytrader")
        for section in NAV_SECTIONS:
            # 管理者専用セクションは admin にだけ表示
            if section.admin_only and not is_admin:
                continue
            st.markdown(
                f'<div class="nav-section-title">{section.title}</div>',
                unsafe_allow_html=True,
            )
            _render_nav_items(section.items)

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
