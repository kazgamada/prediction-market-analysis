"""Test cursor monotonic update and ensure_floor (T6, T9 prevention)."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Unit tests that don't require a live database — patch get_session.
# ---------------------------------------------------------------------------

def _make_session_mock(initial_block: int | None = None):
    """Return a mock Session and the Cursor row it will serve."""
    from copytrader.db.models import Cursor

    if initial_block is not None:
        row = Cursor(name="test", last_block=initial_block)
    else:
        row = None

    sess = MagicMock()
    sess.get.return_value = row
    sess.flush.return_value = None
    sess.execute.return_value = None

    # After flush, sess.get should return the updated row. We simulate this
    # by capturing the value written via execute and updating our row object.
    return sess, row


class TestMaxRowsPerChunk:
    """Sanity-check chunked_insert helper referenced by cursor tests."""

    def test_max_rows_per_chunk_basic(self) -> None:
        from copytrader.db.chunked_insert import max_rows_per_chunk

        assert max_rows_per_chunk(1) == 65000
        assert max_rows_per_chunk(10) == 6500

    def test_max_rows_per_chunk_zero_raises(self) -> None:
        from copytrader.db.chunked_insert import max_rows_per_chunk

        with pytest.raises(ValueError):
            max_rows_per_chunk(0)


# ---------------------------------------------------------------------------
# Tests for ensure_floor logic (T9 prevention)
# ---------------------------------------------------------------------------

class TestEnsureFloor:
    """ensure_floor should move cursor to floor when current < floor."""

    def test_ensure_floor_snaps_up(self) -> None:
        """Cursor below floor must be snapped to floor."""
        from copytrader.db.models import Cursor

        cursor_row = Cursor(name="test_snap", last_block=100)
        sess = MagicMock()
        sess.get.return_value = cursor_row

        # _advance_in_session will re-read the row; after execute+flush
        # return the updated row.
        updated_row = Cursor(name="test_snap", last_block=500)

        def _get_side_effect(model, key):
            if sess.get.call_count > 1:
                return updated_row
            return cursor_row

        sess.get.side_effect = _get_side_effect

        import contextlib
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=sess)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch("copytrader.indexer.cursor.get_session", return_value=ctx):
            from copytrader.indexer import cursor
            result = cursor.ensure_floor("test_snap", 500)
        assert result == 500

    def test_ensure_floor_no_op_when_above(self) -> None:
        """Cursor above floor must NOT be moved down."""
        from copytrader.db.models import Cursor

        cursor_row = Cursor(name="test_nop", last_block=1000)
        sess = MagicMock()
        sess.get.return_value = cursor_row

        import contextlib
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=sess)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch("copytrader.indexer.cursor.get_session", return_value=ctx):
            from copytrader.indexer import cursor as cursor_mod
            result = cursor_mod.ensure_floor("test_nop", 500)
        assert result == 1000

    def test_ensure_floor_creates_when_missing(self) -> None:
        """ensure_floor with no existing cursor should create one at floor."""
        sess = MagicMock()
        sess.get.return_value = None  # no cursor row

        from copytrader.db.models import Cursor
        new_row = Cursor(name="new_cur", last_block=300)
        # After _advance_in_session, row should be available
        sess.get.side_effect = [None, new_row]

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=sess)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch("copytrader.indexer.cursor.get_session", return_value=ctx):
            from copytrader.indexer import cursor as cursor_mod
            result = cursor_mod.ensure_floor("new_cur", 300)
        assert result == 300


# ---------------------------------------------------------------------------
# Tests for advance monotonic invariant (T6 prevention)
# ---------------------------------------------------------------------------

class TestAdvanceMonotonic:
    """advance should use GREATEST, never move cursor backwards."""

    def test_advance_forward_succeeds(self) -> None:
        from copytrader.db.models import Cursor

        after_row = Cursor(name="fwd", last_block=200)
        sess = MagicMock()
        sess.get.return_value = after_row  # after flush

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=sess)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch("copytrader.indexer.cursor.get_session", return_value=ctx):
            from copytrader.indexer import cursor as cursor_mod
            result = cursor_mod.advance("fwd", 200)
        assert result == 200
        # execute was called (the UPSERT statement)
        sess.execute.assert_called_once()

    def test_advance_uses_greatest_sql(self) -> None:
        """The stmt generated must contain GREATEST."""
        from copytrader.db.models import Cursor

        after_row = Cursor(name="mono", last_block=100)
        sess = MagicMock()
        sess.get.return_value = after_row

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=sess)
        ctx.__exit__ = MagicMock(return_value=False)

        captured_stmts: list = []

        def capture_execute(stmt, *args, **kwargs):  # noqa: ARG001
            captured_stmts.append(stmt)

        sess.execute.side_effect = capture_execute

        with patch("copytrader.indexer.cursor.get_session", return_value=ctx):
            from copytrader.indexer import cursor as cursor_mod
            cursor_mod.advance("mono", 100)

        # The SQL text inside the statement must reference GREATEST.
        assert len(captured_stmts) == 1
        stmt_str = str(captured_stmts[0])
        assert "GREATEST" in stmt_str, f"Expected GREATEST in SQL, got:\n{stmt_str}"
