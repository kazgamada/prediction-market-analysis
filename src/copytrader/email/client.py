from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    from_email: str | None = None,
) -> bool:
    """メールを送信する。失敗時は False を返す（例外を上げない）。"""
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        log.warning("RESEND_API_KEY not set — email not sent to %s", to)
        return False
    try:
        import resend  # type: ignore[import-untyped]

        resend.api_key = api_key
        sender = from_email or os.environ.get("EMAIL_FROM", "noreply@example.com")
        resend.Emails.send({
            "from": sender,
            "to": to,
            "subject": subject,
            "html": html,
        })
        log.info("Email sent to %s: %s", to, subject)
        return True
    except Exception:  # noqa: BLE001
        log.exception("Failed to send email to %s", to)
        return False
