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
    from copytrader.email.client import send_email
    from copytrader.web.auth import require_admin
    from copytrader.web.sidebar import render_sidebar

    require_admin()
    render_sidebar()

    st.title("📧 メール送信（管理者）")

    try:
        with get_session() as s:
            users = s.execute(select(User)).scalars().all()
        emails = [u.email for u in users]
    except Exception as e:  # noqa: BLE001
        st.error(f"DB エラー: {e}")
        return

    recipient = st.selectbox("送信先", ["全員"] + emails)
    subject = st.text_input("件名", value="CopyTrader からのお知らせ")
    body = st.text_area("本文 (HTML)", height=200)

    if st.button("送信"):
        targets = emails if recipient == "全員" else [recipient]
        success = 0
        for email in targets:
            if send_email(to=email, subject=subject, html=body):
                success += 1
        st.success(f"{success}/{len(targets)} 件送信しました")


main()
