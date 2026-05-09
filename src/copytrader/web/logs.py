"""Streamlit ヘルパー: 長時間ジョブのライブログ表示。

3 秒以内に終わる処理は通常のスピナーだけ。
3 秒を超えた段階で `st.status` ブロックを開き、`copytrader.*` ロガーの
INFO 以上のメッセージを `st.code` に流し続ける。

Streamlit 1.36+ の `st.status` を使用。`add_script_run_ctx` でワーカー
スレッドに script run コンテキストを連結する公式パターンに沿っている。
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

import streamlit as st

T = TypeVar("T")

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_DEFAULT_LOGGERS = ("copytrader",)
_MAX_VISIBLE_LINES = 400
_POLL_INTERVAL = 0.3


class _QueueHandler(logging.Handler):
    def __init__(self, q: "queue.Queue[str]") -> None:
        super().__init__(level=logging.INFO)
        self.q = q
        self.setFormatter(logging.Formatter(_LOG_FORMAT, "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.q.put_nowait(self.format(record))
        except queue.Full:
            pass


def run_with_live_logs(
    label: str,
    fn: Callable[..., T],
    *args: Any,
    threshold_seconds: float = 3.0,
    logger_names: tuple[str, ...] = _DEFAULT_LOGGERS,
    **kwargs: Any,
) -> T:
    """`fn(*args, **kwargs)` を実行し、`threshold_seconds` を超えたら詳細ログを表示。

    - 3 秒以内に終了: スピナーのみ。元の挙動と互換。
    - 3 秒超過: `st.status` を開き、進行中ログを `st.code` で更新し続ける。
    - 例外は呼び出し側に再送出する (元の traceback を保持)。
    """
    log_queue: "queue.Queue[str]" = queue.Queue(maxsize=10_000)
    handler = _QueueHandler(log_queue)
    attached: list[logging.Logger] = _attach_handler(handler, logger_names)

    result_box: dict[str, Any] = {}

    def _runner() -> None:
        try:
            result_box["value"] = fn(*args, **kwargs)
        except BaseException as e:  # noqa: BLE001 - re-raised below
            result_box["error"] = e

    worker = threading.Thread(target=_runner, name=f"live-logs:{label}", daemon=True)
    _attach_script_ctx(worker)

    started = time.monotonic()
    try:
        with st.spinner(label):
            worker.start()
            worker.join(timeout=threshold_seconds)
            if worker.is_alive():
                _stream_until_done(label, worker, log_queue, started, result_box)
            else:
                _drain(log_queue, [])
    finally:
        _detach_handler(handler, attached)

    if "error" in result_box:
        raise result_box["error"]
    return result_box["value"]


def _stream_until_done(
    label: str,
    worker: threading.Thread,
    log_queue: "queue.Queue[str]",
    started: float,
    result_box: dict[str, Any],
) -> None:
    log_lines: list[str] = []
    elapsed = time.monotonic() - started
    status = st.status(
        f"{label} — running… {elapsed:0.1f}s", expanded=True, state="running"
    )
    with status:
        placeholder = st.empty()
        while worker.is_alive():
            _drain(log_queue, log_lines)
            elapsed = time.monotonic() - started
            placeholder.code(_body(log_lines), language="log")
            status.update(label=f"{label} — running… {elapsed:0.1f}s")
            time.sleep(_POLL_INTERVAL)
        worker.join(timeout=1.0)
        _drain(log_queue, log_lines)
        elapsed = time.monotonic() - started
        placeholder.code(_body(log_lines), language="log")
    final_state = "error" if "error" in result_box else "complete"
    status.update(
        label=f"{label} — done in {elapsed:0.1f}s",
        state=final_state,
        expanded=True,
    )


def _attach_handler(
    handler: logging.Handler, names: tuple[str, ...]
) -> list[logging.Logger]:
    attached: list[logging.Logger] = []
    for name in names:
        lg = logging.getLogger(name)
        if lg.level == logging.NOTSET or lg.level > logging.INFO:
            lg.setLevel(logging.INFO)
        lg.addHandler(handler)
        attached.append(lg)
    return attached


def _detach_handler(
    handler: logging.Handler, loggers: list[logging.Logger]
) -> None:
    for lg in loggers:
        try:
            lg.removeHandler(handler)
        except Exception:
            pass


def _attach_script_ctx(thread: threading.Thread) -> None:
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx

        add_script_run_ctx(thread)
    except Exception:
        # script ctx を連結できなくても処理自体は走らせる。
        pass


def _drain(q: "queue.Queue[str]", sink: list[str]) -> None:
    try:
        while True:
            sink.append(q.get_nowait())
    except queue.Empty:
        return


def _body(lines: list[str]) -> str:
    if not lines:
        return "(ログ出力待機中…)"
    return "\n".join(lines[-_MAX_VISIBLE_LINES:])
