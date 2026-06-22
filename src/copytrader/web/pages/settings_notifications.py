from __future__ import annotations

import streamlit as st


def main() -> None:
    from sqlalchemy import select

    from copytrader.db.engine import get_session
    from copytrader.db.models import NotificationPref
    from copytrader.web.auth import current_user, require_login
    from copytrader.web.sidebar import render_sidebar

    require_login()
    render_sidebar()

    st.title("🔔 通知設定")

    user = current_user()
    if user is None:
        st.warning("ログインしてください")
        return

    try:
        with get_session() as s:
            pref = s.execute(
                select(NotificationPref).where(NotificationPref.user_id == user.id)
            ).scalar_one_or_none()
    except Exception as e:  # noqa: BLE001
        st.error(f"DB エラー: {e}")
        return

    invoice_paid = pref.invoice_paid if pref else True
    risk_halt = pref.risk_halt if pref else True
    daily_summary = pref.daily_summary if pref else False

    new_invoice_paid = st.checkbox("請求完了メールを受け取る", value=invoice_paid)
    new_risk_halt = st.checkbox("リスク停止アラートを受け取る", value=risk_halt)
    new_daily_summary = st.checkbox("日次サマリーメールを受け取る", value=daily_summary)

    if st.button("保存"):
        try:
            with get_session() as s:
                existing = s.execute(
                    select(NotificationPref).where(NotificationPref.user_id == user.id)
                ).scalar_one_or_none()
                if existing:
                    existing.invoice_paid = new_invoice_paid
                    existing.risk_halt = new_risk_halt
                    existing.daily_summary = new_daily_summary
                else:
                    s.add(NotificationPref(
                        user_id=user.id,
                        invoice_paid=new_invoice_paid,
                        risk_halt=new_risk_halt,
                        daily_summary=new_daily_summary,
                    ))
            st.success("保存しました")
        except Exception as e:  # noqa: BLE001
            st.error(f"保存失敗: {e}")


main()
