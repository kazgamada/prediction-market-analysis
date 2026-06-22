from __future__ import annotations

import os

import streamlit as st

st.markdown("""
<style>
.stApp, .stApp > div { background: #000 !important; color: #fff !important; }
[data-testid="stHeader"] { background: #000 !important; }
</style>""", unsafe_allow_html=True)


def main() -> None:
    from copytrader.web.auth import require_admin
    from copytrader.web.sidebar import render_sidebar

    require_admin()
    render_sidebar()

    st.title("💳 Billing 管理")

    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        st.info("STRIPE_SECRET_KEY が未設定です。モック表示モードです。")
        _mock_billing_view()
        return

    try:
        import stripe  # type: ignore[import-untyped]

        stripe.api_key = stripe_key
        _stripe_billing_view(stripe)
    except Exception as e:  # noqa: BLE001
        st.error(f"Stripe エラー: {e}")
        _mock_billing_view()


def _mock_billing_view() -> None:
    from sqlalchemy import select

    from copytrader.db.engine import get_session
    from copytrader.db.models import User

    st.subheader("ユーザー一覧（モック）")
    try:
        with get_session() as s:
            users = s.execute(select(User)).scalars().all()
        for u in users:
            st.write(f"- {u.email}: plan={getattr(u, 'plan', 'free')}")
    except Exception as e:  # noqa: BLE001
        st.warning(f"DB 読み込み失敗: {e}")


def _stripe_billing_view(stripe: object) -> None:  # type: ignore[type-arg]
    st.subheader("Stripe カスタマー一覧")
    st.info("Stripe 連携実装中...")


main()
