"""ツールチップ文言の一元管理。"""
from __future__ import annotations

TOOLTIPS: dict[str, dict] = {
    # ナビゲーション
    "nav.home": {
        "title": "Home",
        "body": "12タイルで運用状況を一目で確認できます。",
    },
    "nav.strategy": {
        "title": "Strategy",
        "body": "Phase 0の実行と結果レポートを確認します。",
    },
    "nav.execute": {
        "title": "Execute",
        "body": "執行設定・ウォッチリスト・ジョブ管理を行います。",
    },
    "nav.ops": {
        "title": "Ops",
        "body": "障害対応・設定変更・詳細ログを確認します。",
    },
    # 主要ボタン
    "btn.run_phase0": {
        "title": "Phase 0 実行",
        "body": "過去データでedgeを検証します。本番資金は動きません。",
    },
    "btn.kill_switch": {
        "title": "Kill Switch",
        "body": "ONにすると執行を即時停止します。",
        "shortcut": "即時反映・確認なし",
    },
    # 管理者
    "admin.freeze": {
        "title": "凍結",
        "body": "ユーザーのログインと操作を即時停止します。",
        "shortcut": "監査ログに記録",
    },
}
