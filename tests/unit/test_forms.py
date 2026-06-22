"""フォーム保存ガード try_save の挙動（Streamlit をスタブ化して検証）。"""
from __future__ import annotations

import sys
import types


def _install_streamlit_stub() -> dict:
    """st.error / st.success / st.toast の呼び出しを記録するスタブを注入。"""
    calls: dict = {"error": [], "success": [], "toast": []}
    stub = types.ModuleType("streamlit")
    stub.error = lambda msg: calls["error"].append(msg)
    stub.success = lambda msg: calls["success"].append(msg)
    stub.toast = lambda msg, icon=None: calls["toast"].append(msg)
    sys.modules["streamlit"] = stub
    return calls


def test_try_save_success_shows_green() -> None:
    calls = _install_streamlit_stub()
    from copytrader.web.forms import try_save

    ok = try_save(lambda: None, "保存しました")
    assert ok is True
    assert calls["success"] == ["保存しました"]
    assert calls["error"] == []


def test_try_save_success_toast() -> None:
    calls = _install_streamlit_stub()
    from copytrader.web.forms import try_save

    ok = try_save(lambda: None, "保存しました", toast=True)
    assert ok is True
    assert calls["toast"] == ["保存しました"]
    assert calls["success"] == []


def test_try_save_failure_surfaces_real_error() -> None:
    calls = _install_streamlit_stub()
    from copytrader.web.forms import try_save

    def boom() -> None:
        raise ValueError("relation app_settings does not exist")

    ok = try_save(boom, "保存しました")
    assert ok is False
    # 成功色は出さず、失敗を1件だけ赤で表示
    assert calls["success"] == []
    assert len(calls["error"]) == 1
    # 実際の例外型とメッセージを隠さず含める
    assert "ValueError" in calls["error"][0]
    assert "relation app_settings does not exist" in calls["error"][0]
