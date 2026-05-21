"""Password gate (無効化済み).

頻繁な再認証要求を避けるため、`require_password()` は no-op に変更。
再導入する場合は git 履歴から復元する。
"""
from __future__ import annotations


def require_password() -> None:
    return
