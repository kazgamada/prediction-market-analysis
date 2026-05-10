"""Streamlit ヘルパー: 長時間ジョブのライブログ表示 + クロスセッション永続化。

設計:
- worker thread が `fn(*args, **kwargs)` を実行する。
- drainer thread が QueueHandler から logs を吸い上げ、2 秒ごとに
  `ui_state` テーブルに `{status, log_tail, elapsed_s, ...}` を書き込む。
- ページを離れても drainer は daemon thread として走り続け、worker が
  終わるまで DB の更新を続ける → 別ページ / 再訪問からでも進捗を見られる。
- main script 側は `_stream_until_done` で local の log_lines を読んで
  サブセコンドで UI を更新する (ページに留まっている間の体感速度確保)。
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Optional, TypeVar

import streamlit as st

T = TypeVar("T")
ProgressFn = Callable[[], Optional[str]]

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_DEFAULT_LOGGERS = ("copytrader",)
_MAX_VISIBLE_LINES = 400
_POLL_INTERVAL = 0.3
_PERSIST_INTERVAL = 2.0
_RUNNING_STALE_AFTER = 60.0  # seconds without ui_state update => assume dead

TRACKED_JOBS: tuple[str, ...] = (
    "actions.last_backfill",
    "actions.last_sync_markets",
    "actions.last_reconcile",
    "actions.last_poll",
    "rank.last_run",
    "replay.last_run",
    "inspect.last_run",
)


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
    progress_fn: ProgressFn | None = None,
    persist_key: str | None = None,
    **kwargs: Any,
) -> T:
    """`fn(*args, **kwargs)` を実行。3 秒超で詳細ログ表示。

    `persist_key` 指定時は drainer thread が 2 秒ごとに ui_state を更新し、
    ページ離脱後も状態が DB に残り続ける。戻り値は fn の戻り値、例外は再送出。
    """
    log_queue: "queue.Queue[str]" = queue.Queue(maxsize=10_000)
    handler = _QueueHandler(log_queue)
    attached: list[logging.Logger] = _attach_handler(handler, logger_names)

    result_box: dict[str, Any] = {}
    log_lines: list[str] = []
    log_lock = threading.Lock()
    started_wall = datetime.now(timezone.utc)
    started = time.monotonic()

    def _runner() -> None:
        try:
            result_box["value"] = fn(*args, **kwargs)
        except BaseException as e:  # noqa: BLE001 - re-raised below
            result_box["error"] = e

    worker = threading.Thread(target=_runner, name=f"job:{label}", daemon=True)
    _attach_script_ctx(worker)

    drainer_done = threading.Event()
    drainer = threading.Thread(
        target=_drainer_loop,
        name=f"drain:{label}",
        args=(
            persist_key, label, started_wall, started,
            log_queue, log_lines, log_lock, worker, result_box,
            handler, attached, drainer_done,
        ),
        daemon=True,
    )
    _attach_script_ctx(drainer)

    try:
        with st.spinner(label):
            worker.start()
            drainer.start()
            worker.join(timeout=threshold_seconds)
            if worker.is_alive():
                _stream_until_done(
                    label, worker, log_lines, log_lock, started,
                    result_box, progress_fn,
                )
    finally:
        # drainer owns handler detach; do not detach here.
        pass

    # Wait briefly for drainer to write final DB state.
    drainer_done.wait(timeout=3.0)

    if "error" in result_box:
        raise result_box["error"]
    return result_box["value"]


def _drainer_loop(
    persist_key: str | None,
    label: str,
    started_wall: datetime,
    started: float,
    log_queue: "queue.Queue[str]",
    log_lines: list[str],
    log_lock: threading.Lock,
    worker: threading.Thread,
    result_box: dict[str, Any],
    handler: logging.Handler,
    attached: list[logging.Logger],
    done_event: threading.Event,
) -> None:
    last_persist = -1e9
    try:
        while True:
            _drain_into(log_queue, log_lines, log_lock)
            worker_alive = worker.is_alive()
            now = time.monotonic()
            if persist_key and (now - last_persist >= _PERSIST_INTERVAL or not worker_alive):
                last_persist = now
                _write_ui_state(
                    persist_key, label, started_wall, started,
                    log_lines, log_lock, worker_alive, result_box,
                )
            if not worker_alive:
                break
            time.sleep(0.3)
    finally:
        _detach_handler(handler, attached)
        done_event.set()


def _drain_into(
    q: "queue.Queue[str]", sink: list[str], lock: threading.Lock
) -> None:
    new_lines: list[str] = []
    try:
        while True:
            new_lines.append(q.get_nowait())
    except queue.Empty:
        pass
    if not new_lines:
        return
    with lock:
        sink.extend(new_lines)
        # cap memory at 2x visible window
        if len(sink) > _MAX_VISIBLE_LINES * 2:
            del sink[: len(sink) - _MAX_VISIBLE_LINES * 2]


def _write_ui_state(
    persist_key: str,
    label: str,
    started_wall: datetime,
    started: float,
    log_lines: list[str],
    log_lock: threading.Lock,
    worker_alive: bool,
    result_box: dict[str, Any],
) -> None:
    try:
        from copytrader.web import state as ui_state
    except Exception:
        return
    if worker_alive:
        status = "running"
    elif "error" in result_box:
        status = "error"
    else:
        status = "done"
    with log_lock:
        tail = "\n".join(log_lines[-_MAX_VISIBLE_LINES:])
    elapsed_s = round(time.monotonic() - started, 1)
    rec = {
        "label": label,
        "status": status,
        "started_at": started_wall.isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": elapsed_s,
        "log_tail": tail,
        "success": status == "done",
        "result": _safe_repr(result_box.get("value")) if status == "done" else None,
        "error": _safe_repr(result_box.get("error")) if status == "error" else None,
    }
    try:
        ui_state.set(persist_key, rec)
    except Exception:
        pass


def _safe_repr(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return repr(value)[:500]
    except Exception:
        return "(unrepresentable)"


def _stream_until_done(
    label: str,
    worker: threading.Thread,
    log_lines: list[str],
    log_lock: threading.Lock,
    started: float,
    result_box: dict[str, Any],
    progress_fn: ProgressFn | None,
) -> None:
    elapsed = time.monotonic() - started
    status = st.status(
        f"{label} — running… {elapsed:0.1f}s", expanded=True, state="running"
    )
    with status:
        progress_box = st.empty() if progress_fn else None
        placeholder = st.empty()
        last_progress_at = 0.0
        last_progress_text: str | None = None
        while worker.is_alive():
            elapsed = time.monotonic() - started
            with log_lock:
                snapshot = list(log_lines[-_MAX_VISIBLE_LINES:])
            placeholder.code(_body(snapshot), language="log")
            if progress_box is not None and (elapsed - last_progress_at) >= 2.0:
                last_progress_at = elapsed
                try:
                    last_progress_text = progress_fn() if progress_fn else None
                except Exception as e:
                    last_progress_text = f"_(progress 取得失敗: {e})_"
                if last_progress_text:
                    progress_box.markdown(last_progress_text)
            status.update(label=f"{label} — running… {elapsed:0.1f}s")
            time.sleep(_POLL_INTERVAL)
        elapsed = time.monotonic() - started
        with log_lock:
            snapshot = list(log_lines[-_MAX_VISIBLE_LINES:])
        placeholder.code(_body(snapshot), language="log")
    final_state = "error" if "error" in result_box else "complete"
    status.update(
        label=f"{label} — done in {elapsed:0.1f}s",
        state=final_state,
        expanded=True,
    )


def render_live_action(persist_key: str, *, expanded: bool = True) -> bool:
    """ui_state[persist_key] を読んで「実行中」ならステータスブロック、
    終了 / エラーなら expander で再描画する。実行中なら True を返す
    (呼び出し側でページを auto-refresh するための合図)。
    """
    try:
        from copytrader.web import state as ui_state

        rec = ui_state.get(persist_key)
    except Exception:
        return False
    if not isinstance(rec, dict):
        return False

    status = rec.get("status")
    label = rec.get("label", persist_key)
    log_tail = rec.get("log_tail") or "(待機中: ログ未出力)"
    elapsed = rec.get("elapsed_s", 0)
    started_at = rec.get("started_at", "")

    upd_age = _updated_age_seconds(rec.get("updated_at"))
    is_running = status == "running" and (upd_age is not None and upd_age < _RUNNING_STALE_AFTER)
    is_stalled = status == "running" and not is_running

    if is_running:
        sb = st.status(
            f"{label} — running… {elapsed}s (background, last update {int(upd_age or 0)}s ago)",
            expanded=expanded,
            state="running",
        )
        with sb:
            st.code(log_tail, language="log")
        return True

    icon = "✅" if rec.get("success") else ("❌" if rec.get("error") else "⚠️")
    if is_stalled:
        title = (
            f"⚠️ stalled — {label} (last update {int(upd_age or 0)}s ago, "
            "fly machine の auto-stop / 再起動の可能性)"
        )
    else:
        title = f"{icon} 最後の実行: {label} — {started_at} ({elapsed}s)"
    with st.expander(title, expanded=False):
        if rec.get("result"):
            st.markdown(f"**result**: `{rec['result']}`")
        if rec.get("error"):
            st.error(rec["error"])
        st.code(log_tail, language="log")
    return False


# 後方互換: render_last_action は render_live_action に統合済み。
render_last_action = render_live_action


def render_running_jobs_banner(
    persist_keys: tuple[str, ...] | list[str] = TRACKED_JOBS,
) -> bool:
    """全ページ共通: 任意の job が「実行中」なら sidebar に簡易バナーを出す。
    実行中があれば True を返す (auto-refresh 合図)。
    """
    try:
        from copytrader.web import state as ui_state
    except Exception:
        return False
    running: list[str] = []
    for k in persist_keys:
        rec = ui_state.get(k)
        if not isinstance(rec, dict):
            continue
        if rec.get("status") != "running":
            continue
        upd_age = _updated_age_seconds(rec.get("updated_at"))
        if upd_age is None or upd_age >= _RUNNING_STALE_AFTER:
            continue
        running.append(rec.get("label", k))
    if not running:
        return False
    with st.sidebar:
        st.markdown("---")
        st.markdown("**実行中のジョブ**")
        for label in running:
            st.markdown(f"- 🟢 `{label}`")
    return True


def _updated_age_seconds(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        ts = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except Exception:
        return None


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
        pass


def _body(lines: list[str]) -> str:
    if not lines:
        return "(ログ出力待機中…)"
    return "\n".join(lines[-_MAX_VISIBLE_LINES:])
