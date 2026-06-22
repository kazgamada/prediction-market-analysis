"""ナビゲーション定義（一元管理）。

サイドバーを 3 グループに明確分離する:
  📊 ツール運用    — 毎日の閲覧・分析・運用（全ユーザー）
  ⚙️ ユーザー設定  — 自分の通知・課金などの設定（全ユーザー）
  🔧 管理者メニュー — システム運営者向け（admin ロールのみ表示）
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NavItem:
    label: str
    page: str
    icon: str = ""
    admin_only: bool = False
    children: list[NavItem] = field(default_factory=list)


@dataclass
class NavSection:
    title: str
    items: list[NavItem]
    admin_only: bool = False


NAV_SECTIONS: list[NavSection] = [
    NavSection("📊 ツール運用", [
        NavItem("🏠 ホーム", "app.py"),
        NavItem("📈 Strategy（戦略分析）", "pages/1_Strategy.py"),
        NavItem("⚡ Execute（執行）", "pages/2_Execute.py"),
        NavItem("🔧 Ops（運用・保守）", "pages/3_Ops.py"),
        NavItem("❓ Help（マニュアル）", "pages/4_Help.py"),
    ]),
    NavSection("⚙️ ユーザー設定", [
        NavItem("🔔 通知設定", "pages/settings_notifications.py"),
        NavItem("💳 課金・プラン", "pages/settings_billing.py"),
    ]),
    NavSection("🔧 管理者メニュー", [
        NavItem("🤖 AI設定", "pages/admin_ai_settings.py", admin_only=True),
        NavItem("👥 ユーザー管理", "pages/admin_users.py", admin_only=True),
        NavItem("💳 Billing 管理", "pages/admin_billing.py", admin_only=True),
        NavItem("📧 メール送信", "pages/admin_email.py", admin_only=True),
    ], admin_only=True),
]


# 後方互換（既存 import 対策）
NAVIGATION: list[NavItem] = NAV_SECTIONS[0].items + NAV_SECTIONS[1].items
ADMIN_NAVIGATION: list[NavItem] = NAV_SECTIONS[2].items
