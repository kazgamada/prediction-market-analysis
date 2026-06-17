"""Telegram command handlers (/halt /resume /status /balance /positions).

Polls Telegram getUpdates API in a loop. If a command is received from an
admin user_id, executes the action and replies.

Fail-soft: if TELEGRAM_BOT_TOKEN unset, the runner exits immediately.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select

from copytrader.db import settings_table
from copytrader.db.engine import get_session
from copytrader.db.models import AuditLog, Position, TradePnl

log = logging.getLogger("telegram.commands")


def _admin_ids() -> set[int]:
    raw = os.environ.get("TELEGRAM_ADMIN_USER_IDS", "")
    out = set()
    for tok in raw.split(","):
        tok = tok.strip()
        if tok.isdigit():
            out.add(int(tok))
    return out


def _enabled() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN"))


async def _get_updates(client: httpx.AsyncClient, token: str,
                       offset: int) -> list[dict]:
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        resp = await client.get(
            url,
            params={"offset": offset, "timeout": 25,
                    "allowed_updates": '["message"]'},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", []) if data.get("ok") else []
    except Exception as e:  # noqa: BLE001
        log.warning("getUpdates failed: %s", e)
        return []


def _handle_status() -> str:
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = datetime.now(UTC) - timedelta(days=7)
    with get_session() as s:
        today = s.execute(
            select(func.coalesce(func.sum(TradePnl.realized_usdc), 0))
            .where(TradePnl.ts >= midnight)
        ).scalar_one()
        week = s.execute(
            select(func.coalesce(func.sum(TradePnl.realized_usdc), 0))
            .where(TradePnl.ts >= week_ago)
        ).scalar_one()
        positions = int(s.execute(
            select(func.count()).select_from(Position)
            .where(Position.open_size_shares > 0)
        ).scalar_one())
    kill = bool(settings_table.get("kill_switch_on") or False)
    paper = not bool(settings_table.get("execution_enabled") or False)
    return (
        f"*Status*\n"
        f"Today PnL: `${float(today):+.2f}`\n"
        f"7d PnL: `${float(week):+.2f}`\n"
        f"Positions: `{positions}`\n"
        f"Kill switch: {'🛑 ON' if kill else '🟢 OFF'}\n"
        f"Mode: {'📝 paper' if paper else '💰 live'}"
    )


def _handle_halt(user_id: int) -> str:
    settings_table.set_("kill_switch_on", True)
    with get_session() as s:
        s.add(AuditLog(actor=f"telegram:{user_id}",
                       action="kill_switch_on", details={"via": "telegram"}))
    return "🛑 *Kill switch ON.* No new orders will be placed."


def _handle_resume(user_id: int) -> str:
    settings_table.set_("kill_switch_on", False)
    with get_session() as s:
        s.add(AuditLog(actor=f"telegram:{user_id}",
                       action="kill_switch_off", details={"via": "telegram"}))
    return "✅ *Kill switch OFF.* Auto-trading resumed."


def _handle_balance() -> str:
    usdc = float(settings_table.get("usdc_balance_cache") or 0.0)
    matic = float(settings_table.get("matic_balance_cache") or 0.0)
    return f"*Balance*\nUSDC: `${usdc:,.2f}`\nMATIC: `{matic:.2f}`"


def _handle_positions() -> str:
    with get_session() as s:
        rows = s.execute(
            select(Position).where(Position.open_size_shares > 0)
            .order_by(Position.open_size_usdc.desc()).limit(5)
        ).scalars().all()
    if not rows:
        return "*Positions*\n(none open)"
    lines = ["*Top 5 Positions*"]
    for p in rows:
        side = "B" if int(p.side) == 0 else "S"
        lines.append(
            f"• `{p.market_label or str(p.token_id)[:12]}` "
            f"{side} ${float(p.open_size_usdc):.0f} @ {float(p.avg_price):.3f}"
        )
    return "\n".join(lines)


def _handle_pnl(arg: str) -> str:
    days = 7
    if arg.endswith("d"):
        try:
            days = int(arg[:-1])
        except ValueError:
            pass
    since = datetime.now(UTC) - timedelta(days=days)
    with get_session() as s:
        total = float(s.execute(
            select(func.coalesce(func.sum(TradePnl.realized_usdc), 0))
            .where(TradePnl.ts >= since)
        ).scalar_one())
    return f"*PnL ({days}d):* `${total:+.2f}`"


def _dispatch(text: str, user_id: int) -> str | None:
    text = text.strip()
    if not text.startswith("/"):
        return None
    cmd, *rest = text.split(maxsplit=1)
    arg = rest[0] if rest else ""
    cmd = cmd.lower().split("@")[0]

    if cmd == "/status":
        return _handle_status()
    if cmd == "/balance":
        return _handle_balance()
    if cmd == "/positions":
        return _handle_positions()
    if cmd == "/pnl":
        return _handle_pnl(arg or "7d")

    # Admin-only
    if user_id not in _admin_ids():
        return "⚠️ Unauthorized."
    if cmd == "/halt":
        return _handle_halt(user_id)
    if cmd == "/resume":
        return _handle_resume(user_id)
    return f"Unknown command: `{cmd}`"


async def _send_reply(client: httpx.AsyncClient, token: str,
                      chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        await client.post(
            url,
            json={"chat_id": chat_id, "text": text,
                  "parse_mode": "Markdown"},
            timeout=10.0,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("send reply failed: %s", e)


async def run_telegram_commands() -> None:
    """Long-running coroutine: long-poll Telegram and dispatch."""
    if not _enabled():
        log.info("telegram.commands: TELEGRAM_BOT_TOKEN unset; exiting")
        return
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    offset = 0
    log.info("telegram.commands: starting long-poll")
    async with httpx.AsyncClient() as client:
        await _send_reply(
            client, token,
            int(os.environ.get("TELEGRAM_CHAT_ID", "0") or 0),
            "🤖 Copytrader bot online. Commands: /status /balance /positions "
            "/pnl 7d /halt /resume",
        )
        while True:
            updates = await _get_updates(client, token, offset)
            for upd in updates:
                offset = max(offset, int(upd.get("update_id", 0)) + 1)
                msg = upd.get("message") or {}
                text = msg.get("text") or ""
                from_user = msg.get("from") or {}
                user_id = int(from_user.get("id", 0))
                chat = msg.get("chat") or {}
                chat_id = int(chat.get("id", 0))
                if not text or not chat_id:
                    continue
                reply = _dispatch(text, user_id)
                if reply:
                    await _send_reply(client, token, chat_id, reply)
            await asyncio.sleep(1)
