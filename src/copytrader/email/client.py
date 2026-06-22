"""Resend メール送信基盤。RESEND_API_KEY 未設定時はログ警告してスキップ。"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)

FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "noreply@example.com")


@dataclass
class EmailMessage:
    to: str
    subject: str
    html: str


def send_email(msg: EmailMessage) -> None:
    """メール送信。RESEND_API_KEY 未設定時はスキップ（fail-soft）。"""
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        log.warning("RESEND_API_KEY not set; skipping email to %s", msg.to)
        return
    try:
        import resend
        resend.api_key = api_key
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": msg.to,
            "subject": msg.subject,
            "html": msg.html,
        })
    except Exception:  # noqa: BLE001
        log.warning("email send failed to %s", msg.to, exc_info=True)


def send_password_reset(to: str, reset_url: str) -> None:
    """パスワードリセットメール送信。"""
    send_email(EmailMessage(
        to=to,
        subject="パスワードリセット",
        html=(
            f"<p><a href='{reset_url}'>こちらをクリックしてパスワードをリセット</a></p>"
            "<p>このリンクは1時間で無効になります。</p>"
        ),
    ))


def send_subscription_receipt(to: str, amount: int, period: str) -> None:
    """サブスクリプション領収書メール送信。"""
    send_email(EmailMessage(
        to=to,
        subject="お支払いが完了しました",
        html=f"<p>{period} 分の料金 ¥{amount:,} を受領しました。</p>",
    ))
