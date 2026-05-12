"""T7 regression: bulk INSERT must never blow past Postgres bind-param cap."""
from __future__ import annotations

import pytest

from copytrader.db.chunked_insert import MAX_BIND_PARAMS, chunk_count, max_rows_per_chunk


def test_max_rows_simple() -> None:
    # 13 cols => floor(65000/13) = 5000
    assert max_rows_per_chunk(13) == 5000


def test_max_rows_one_col_many_rows() -> None:
    assert max_rows_per_chunk(1) == MAX_BIND_PARAMS


def test_max_rows_huge_row_still_allows_one() -> None:
    # Even 100 columns leaves room for 650 rows.
    assert max_rows_per_chunk(100) == 650


def test_max_rows_rejects_zero_cols() -> None:
    with pytest.raises(ValueError):
        max_rows_per_chunk(0)


def test_max_rows_rejects_negative_cols() -> None:
    with pytest.raises(ValueError):
        max_rows_per_chunk(-1)


def test_max_rows_rejects_too_wide() -> None:
    with pytest.raises(ValueError):
        max_rows_per_chunk(MAX_BIND_PARAMS + 1)


@pytest.mark.parametrize(
    "rows, cols, want",
    [
        (0, 10, 0),
        (1, 10, 1),
        (6500, 10, 1),  # exactly fits one chunk
        (6501, 10, 2),
        (100_000, 17, 27),  # 17 cols => 3823 rows/chunk; 100k/3823 = 27 ceil
    ],
)
def test_chunk_count(rows: int, cols: int, want: int) -> None:
    assert chunk_count(rows, cols) == want


def test_no_chunk_exceeds_limit() -> None:
    for cols in (1, 10, 17, 65, 100, 500, 6500):
        rows = max_rows_per_chunk(cols)
        assert rows * cols <= MAX_BIND_PARAMS, (cols, rows)
