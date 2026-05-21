"""Telegram notification helpers — fail-soft.

If TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are unset, all functions become
no-ops (log the message and return). This lets us deploy without secrets
and turn on later.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

log = logging.getLogger("telegram.notifier")


def _enabled() -> bool:
    return bool(
        os.environ.get("TELEGRAM_BOT_TOKEN")
        and os.environ.get("TELEGRAM_CHAT_ID")
    )


def notify(text: str, *, severity: str = "info",
           parse_mode: str | None = "Markdown") -> bool:
    """Send a message. Returns True if delivered, False if disabled / failed.

    severity: info / warn / alert — added as a prefix emoji.
    """
    prefix = {
        "info": "ℹ️", "warn": "⚠️", "alert": "🚨",
    }.get(severity, "")
    full_text = f"{prefix} {text}" if prefix else text
    if not _enabled():
        log.info("telegram(disabled, would send): %s", full_text)
        return False
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": full_text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("telegram send failed: %s", e)
        return False


def notify_kill_switch(on: bool, *, reason: str = "manual") -> None:
    state = "🛑 KILL SWITCH ON" if on else "✅ Kill switch OFF (resume)"
    notify(f"*{state}*\nreason: {reason}", severity="alert")


def notify_halt(conditions: list[str], metrics: dict) -> None:
    notify(
        f"*🛑 Halt triggered*\nconditions: `{', '.join(conditions)}`\n"
        f"metrics: `{metrics}`",
        severity="alert",
    )


def notify_resume() -> None:
    notify("*Resumed* — auto-trading is LIVE again.", severity="info")


def notify_large_fill(
    *, market: str, side: str, size_usdc: float, fill_price: float,
) -> None:
    notify(
        f"*Fill* {market}\n{side} ${size_usdc:.0f} @ {fill_price:.3f}",
        severity="info",
    )


def notify_daily_summary(
    *, phase: str, day_in_phase: int, phase_pnl: float,
    today_pnl: float, open_positions: int, usdc: float, matic: float,
    status: str,
) -> None:
    text = (
        "*📊 Daily Summary*\n"
        f"Phase: `{phase}` (Day {day_in_phase})\n"
        f"Today PnL: `${today_pnl:+.2f}`\n"
        f"Phase total: `${phase_pnl:+.2f}`\n"
        f"Open positions: `{open_positions}`\n"
        f"USDC: `${usdc:,.0f}` / MATIC: `{matic:.1f}`\n"
        f"Status: {status}"
    )
    notify(text, severity="info")
