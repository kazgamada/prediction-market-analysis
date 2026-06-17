"""Telegram bot for notifications + remote commands.

Fail-soft: if TELEGRAM_BOT_TOKEN is unset, notify functions become no-ops.
"""
from copytrader.telegram.notifier import (
    notify,
    notify_daily_summary,
    notify_halt,
    notify_kill_switch,
    notify_large_fill,
    notify_resume,
)

__all__ = [
    "notify",
    "notify_daily_summary",
    "notify_halt",
    "notify_kill_switch",
    "notify_large_fill",
    "notify_resume",
]
