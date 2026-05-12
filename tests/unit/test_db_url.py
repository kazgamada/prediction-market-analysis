"""T17 regression: postgres:// must be normalized to psycopg3 form."""
from __future__ import annotations

import pytest

from copytrader.db.engine import normalize_db_url


@pytest.mark.parametrize(
    "raw, want",
    [
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("", ""),
    ],
)
def test_normalize(raw: str, want: str) -> None:
    assert normalize_db_url(raw) == want


def test_normalize_idempotent() -> None:
    url = "postgres://u:p@h:5432/db?sslmode=require"
    once = normalize_db_url(url)
    twice = normalize_db_url(once)
    assert once == twice
