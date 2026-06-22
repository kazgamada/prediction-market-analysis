from __future__ import annotations

import os

import streamlit as st


def main() -> None:
    from copytrader.web.auth import current_user, require_login
    from copytrader.web.sidebar import render_sidebar

    require_login()
    render_sidebar()

    st.title("💳 Billing 設定")

    user = current_user()
    if user is None:
        st.warning("ログインしてください")
        return

    st.write(f"メール: {user.email}")
    plan = getattr(user, "plan", "free")
    st.write(f"プラン: {plan}")

    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        st.info("Stripe 未設定のため、プラン変更は現在ご利用できません。")
        return

    if st.button("プロプランにアップグレード"):
        st.info("Stripe チェックアウト連携は実装中です。")


main()
