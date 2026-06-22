"""フォーム保存の信頼性・エラー可視化ヘルパー（AUDIT.md 共通機能要件）。

「保存に失敗したのに固定文言で原因が隠れる」「失敗が成功色のまま」を構造的に
排除する。保存ハンドラは `try_save()` を通すことで、失敗時に**実際の例外内容を
赤**で表示し、成功時のみ**緑/トースト**を出す。無言の握りつぶしを禁止する。
"""
from __future__ import annotations

from collections.abc import Callable


def try_save(
    fn: Callable[[], object],
    success_msg: str,
    *,
    toast: bool = False,
) -> bool:
    """保存処理 `fn` を実行し、成否を画面に出し分ける。成功なら True。

    - 失敗: `st.error` で**実際の例外型とメッセージ**を赤表示（原因を隠さない）
    - 成功: `toast=True` ならトースト、そうでなければ `st.success`（緑）
    """
    import streamlit as st

    try:
        fn()
    except Exception as e:  # noqa: BLE001
        st.error(f"保存に失敗しました（{type(e).__name__}）: {e}")
        return False
    if toast:
        st.toast(success_msg, icon="✅")
    else:
        st.success(success_msg)
    return True
