"""Tests for the indexer.backfill helpers (param-limit batching, monotonic cursor)."""

from __future__ import annotations

from copytrader.indexer.backfill import POLYGON_BLOCKS_PER_DAY


def test_polygon_blocks_per_day_constant():
    # 約 2 秒/block × 86400 sec/day = 43200 blocks/day。Polygon の実測に近い値。
    assert POLYGON_BLOCKS_PER_DAY == 43_200


def test_flush_batches_below_pg_param_limit(monkeypatch):
    """_flush は 1 INSERT あたり <= 60000 パラメータに分割する (PG 制限 65535)。"""
    from copytrader.indexer import backfill as bf

    captured_batch_sizes: list[int] = []

    class FakeStmt:
        def on_conflict_do_nothing(self, **_kw):
            return self

    class FakeSession:
        def execute(self, _stmt) -> None: ...
        def get(self, _model, _name): return None
        def add(self, _row) -> None: ...

    class FakeCtx:
        def __enter__(self): return FakeSession()
        def __exit__(self, *exc): return False

    def fake_session_scope():
        return FakeCtx()

    def fake_insert(_model):
        class _Builder:
            def values(self, batch):
                captured_batch_sizes.append(len(batch))
                return FakeStmt()
        return _Builder()

    monkeypatch.setattr(bf, "session_scope", fake_session_scope)
    monkeypatch.setattr(bf, "insert", fake_insert)

    # 18 列 / 行を想定 (Trade の実カラム数と一致)
    rows = [{f"c{i}": i for i in range(18)} for _ in range(10_000)]
    n = bf._flush(rows, "test_cursor", 12345)

    assert n == len(rows)
    assert captured_batch_sizes, "INSERT が 1 回も発行されていない"
    assert max(captured_batch_sizes) * 18 <= 60_000, (
        f"バッチサイズが上限超え: max={max(captured_batch_sizes)} cols=18"
    )
    assert sum(captured_batch_sizes) == len(rows)


def test_flush_cursor_is_monotonic(monkeypatch):
    """既存 cursor より小さい block_number が来ても巻き戻さない。"""
    from copytrader.indexer import backfill as bf

    class FakeCursor:
        def __init__(self, block):
            self.block_number = block
            self.updated_at = None

    fake_cur = FakeCursor(58_680_401)

    class FakeSession:
        def execute(self, _stmt) -> None: ...
        def get(self, _model, _name): return fake_cur
        def add(self, _row) -> None: ...

    class FakeCtx:
        def __enter__(self): return FakeSession()
        def __exit__(self, *exc): return False

    monkeypatch.setattr(bf, "session_scope", lambda: FakeCtx())

    bf._flush([], "backfill_ctf", 100)
    assert fake_cur.block_number == 58_680_401, "小さい値で上書きされてしまった"

    bf._flush([], "backfill_ctf", 84_109_448)
    assert fake_cur.block_number == 84_109_448, "大きい値で前進していない"
