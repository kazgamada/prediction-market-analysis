"""Display helpers for Streamlit pages."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal


def short_addr(addr: bytes | str) -> str:
    if isinstance(addr, bytes):
        h = "0x" + addr.hex()
    else:
        h = addr if addr.startswith("0x") else "0x" + addr
    return h[:6] + "…" + h[-4:]


def fmt_usd(v: Decimal | float | int | str | None) -> str:
    if v is None:
        return "—"
    d = Decimal(str(v))
    return f"${d:,.2f}"


def fmt_pct(v: Decimal | float | str | None) -> str:
    if v is None:
        return "—"
    return f"{Decimal(str(v)):.2f}%"


def fmt_ago(ts: datetime | None) -> str:
    if ts is None:
        return "—"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - ts
    s = int(delta.total_seconds())
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"
