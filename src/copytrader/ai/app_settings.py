"""`app_settings` テーブルアクセサ（管理者 UI から入力する設定の永続化）。

AUDIT.md A-1 / F に対応。API キーのようなセンシティブ値を管理者画面から
入力・保存し、表示時はマスクする。読み書きの認可はアプリ層（呼び出し元の
`require_admin()`）で担保する想定で、本モジュール自体は認可判定を持たない。
"""
from __future__ import annotations

import uuid as _uuid_mod

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from copytrader.db.engine import get_session
from copytrader.db.models import AppSetting

# 管理者画面で扱う設定キー
OPENROUTER_API_KEY = "openrouter_api_key"


def get_app_setting(key: str, default: str | None = None) -> str | None:
    """`app_settings` から生の文字列値を返す server-only ヘルパー（AUDIT.md A-1）。

    値が空文字の場合は未設定扱いで `default` を返す。
    """
    with get_session() as s:
        row = s.execute(
            select(AppSetting).where(AppSetting.key == key)
        ).scalar_one_or_none()
        if row is None or not row.value:
            return default
        return row.value


def set_app_setting(
    key: str,
    value: str | None,
    *,
    updated_by: _uuid_mod.UUID | None = None,
    description: str | None = None,
) -> None:
    """`app_settings` を upsert する。`value=""`/`None` は「削除（env フォールバックへ）」。

    `updated_by` に操作者の user_id を記録し、監査ログを兼ねる。
    """
    normalized = (value or "").strip() or None
    with get_session() as s:
        stmt = pg_insert(AppSetting).values(
            key=key,
            value=normalized,
            description=description,
            updated_by=updated_by,
        )
        set_: dict = {
            "value": stmt.excluded.value,
            "updated_by": stmt.excluded.updated_by,
            "updated_at": stmt.excluded.updated_at,
        }
        if description is not None:
            set_["description"] = stmt.excluded.description
        stmt = stmt.on_conflict_do_update(index_elements=[AppSetting.key], set_=set_)
        s.execute(stmt)


def mask_secret(value: str | None) -> str:
    """秘密値をマスク表示用文字列に変換（例: `sk-or-v1-••••••••4abc`）。

    空なら「未設定」。短すぎる値は全マスク。
    """
    if not value:
        return "未設定"
    visible_prefix = ""
    for sep in ("sk-or-v1-", "sk-or-", "sk-ant-", "sk-"):
        if value.startswith(sep):
            visible_prefix = sep
            break
    tail = value[-4:] if len(value) > 8 else ""
    return f"{visible_prefix}{'•' * 8}{tail}"


def masked_view(key: str) -> dict:
    """API 応答相当の安全なビュー。生の `value` は返さず maskedValue/isEmpty のみ。

    AUDIT.md A-1 の「GET は value を送らず maskedValue と isEmpty のみ」に対応。
    """
    raw = get_app_setting(key)
    return {"key": key, "maskedValue": mask_secret(raw), "isEmpty": raw is None}
