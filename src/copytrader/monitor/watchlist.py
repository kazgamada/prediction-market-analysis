"""Manage the wallet watchlist."""

from __future__ import annotations

from sqlalchemy import select, update

from copytrader.db import session_scope
from copytrader.models import Wallet


def get_watchlist() -> list[str]:
    with session_scope() as session:
        rows = session.execute(
            select(Wallet.address).where(Wallet.watchlisted.is_(True))
        ).all()
        return [r[0].lower() for r in rows]


def add(address: str, note: str | None = None) -> None:
    address = address.lower()
    with session_scope() as session:
        existing = session.get(Wallet, address)
        if existing:
            existing.watchlisted = True
            if note:
                existing.notes = note
        else:
            session.add(
                Wallet(address=address, watchlisted=True, notes=note, n_trades=0)
            )


def remove(address: str) -> None:
    address = address.lower()
    with session_scope() as session:
        session.execute(
            update(Wallet).where(Wallet.address == address).values(watchlisted=False)
        )
