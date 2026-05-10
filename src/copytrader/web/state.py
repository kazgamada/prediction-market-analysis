"""UI 状態のクロスセッション永続化。

`ui_state` テーブルに `(key, value: jsonb)` で任意の JSON 値を保存する。
セッションをまたいでも (ブラウザリロード / 再訪問でも) 同じ値を引き出せる。

使い方:

    state.hydrate("status.auto_refresh", default=False)
    auto = st.toggle("Auto refresh", key="status.auto_refresh",
                     on_change=state.remember, args=("status.auto_refresh",))

    # 完了したジョブの記録
    state.set("actions.last_backfill", {"saved": 123, "log": "..."})
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import streamlit as st
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from copytrader.db import session_scope
from copytrader.models import UiState


def get(key: str, default: Any = None) -> Any:
    """DB から値を取り出す。無ければ default。"""
    try:
        with session_scope() as session:
            row = session.execute(
                select(UiState.value).where(UiState.key == key)
            ).first()
        if row is None:
            return default
        return row[0]
    except Exception:
        return default


def set(key: str, value: Any) -> None:  # noqa: A001 - intentional API name
    """DB に upsert (key, value) を書き込む。"""
    payload = json.loads(json.dumps(value, default=_json_fallback))
    try:
        with session_scope() as session:
            stmt = pg_insert(UiState).values(
                key=key,
                value=payload,
                updated_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["key"],
                set_={"value": payload, "updated_at": datetime.now(timezone.utc)},
            )
            session.execute(stmt)
    except Exception:
        pass


def hydrate(key: str, default: Any = None) -> Any:
    """`st.session_state[key]` が未設定なら DB から読み込んでセット。"""
    if key not in st.session_state:
        st.session_state[key] = get(key, default)
    return st.session_state[key]


def remember(key: str) -> None:
    """`st.session_state[key]` の現在値を DB に保存 (on_change コールバック向け)。"""
    if key in st.session_state:
        set(key, st.session_state[key])


def _json_fallback(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"not JSON-serializable: {type(o).__name__}")
