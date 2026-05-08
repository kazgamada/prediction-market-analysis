"""Telegram notifier. Falls back to logging when no token is set."""

from __future__ import annotations

import logging

import httpx

from copytrader.config import get_settings

log = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self):
        s = get_settings()
        self._token = s.telegram_bot_token
        self._chat_id = s.telegram_chat_id
        self._client = httpx.Client(timeout=10.0)

    @property
    def enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    def send(self, text: str) -> None:
        if not self.enabled:
            log.info("[notifier] %s", text)
            return
        try:
            self._client.post(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                json={"chat_id": self._chat_id, "text": text, "parse_mode": "Markdown"},
            )
        except Exception as e:
            log.warning("telegram send failed: %s", e)
