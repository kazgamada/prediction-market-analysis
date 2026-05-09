"""Streamlit ヘルパー: 長時間ジョブのライブログ表示。

3 秒以上かかった処理は、`copytrader.*` ロガーの出力を画面に流して
進捗を可視化する。短時間で終わる処理ではログ枠を出さずスピナのみ。
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

    - 3 秒以内に終わる場合はスピナーだけ。
    - 超えると `st.code` ブロックに `copytrader.*` の INFO 以上のログを流し続ける。
    - 処理完了後は経過時間付きで最終ログを残す。
    - 例外は呼び出し側に再送出する (元のスタックトレースは保持しない簡略版)。
    """
    log_queue: "queue.Queue[str]" = queue.Queue(maxsize=10_000)
    handler = _QueueHandler(log_queue)
    attached: list[logging.Logger] = []
    for name in logger_names:
        lg = logging.getLogger(name)
        if lg.level == logging.NOTSET or lg.level > logging.INFO:
            lg.setLevel(logging.INFO)
        lg.addHandler(handler)
        attached.append(lg)

    result_box: dict[str, Any] = {}

    def _runner() -> None:
        try:
            result_box["value"] = fn(*args, **kwargs)
        except BaseException as e:  # noqa: BLE001 - re-raised by caller
            result_box["error"] = e

    worker = threading.Thread(target=_runner, name=f"live-logs:{label}", daemon=True)
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx

        add_script_run_ctx(worker)
    except Exception:
        # ctx 連携できなくても実行自体は可能。
        pass

    spinner_ctx = st.spinner(label)
    spinner_ctx.__enter__()
    placeholder = st.empty()
    log_lines: list[str] = []
    started = time.monotonic()
    showing_logs = False
    try:
        worker.start()
        while worker.is_alive():
            _drain(log_queue, log_lines)
            elapsed = time.monotonic() - started
            if not showing_logs and elapsed >= threshold_seconds:
                showing_logs = True
            if showing_logs:
                _render(placeholder, label, elapsed, log_lines, done=False)
            time.sleep(0.2)
        worker.join(timeout=1.0)
        _drain(log_queue, log_lines)
        elapsed = time.monotonic() - started
        if showing_logs or elapsed >= threshold_seconds:
            _render(placeholder, label, elapsed, log_lines, done=True)
    finally:
        spinner_ctx.__exit__(None, None, None)
        for lg in attached:
            lg.removeHandler(handler)

    if "error" in result_box:
        raise result_box["error"]
    return result_box["value"]


def _drain(q: "queue.Queue[str]", sink: list[str]) -> None:
    try:
        while True:
            sink.append(q.get_nowait())
    except queue.Empty:
        return


def _render(
    placeholder: Any,
    label: str,
    elapsed: float,
    lines: list[str],
    *,
    done: bool,
) -> None:
    head = (
        f"[{label}] done in {elapsed:0.1f}s"
        if done
        else f"[{label}] running… {elapsed:0.1f}s"
    )
    body = "\n".join(lines[-_MAX_VISIBLE_LINES:]) if lines else "(待機中: ログ未出力)"
    placeholder.code(f"{head}\n{body}", language="log")
