"""ナビゲーション定義（一元管理）。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NavItem:
    label: str
    page: str
    icon: str = ""
    admin_only: bool = False
    children: list[NavItem] = field(default_factory=list)


NAVIGATION: list[NavItem] = [
    NavItem("🏠 Home", "app.py"),
    NavItem("📈 Strategy", "pages/1_Strategy.py"),
    NavItem("⚡ Execute", "pages/2_Execute.py", children=[
        NavItem("ウォッチリスト", "pages/2_Execute.py"),
        NavItem("ジョブ", "pages/2_Execute.py"),
    ]),
    NavItem("🔧 Ops", "pages/3_Ops.py"),
    NavItem("❓ Help", "pages/4_Help.py"),
]

ADMIN_NAVIGATION: list[NavItem] = [
    NavItem("👥 ユーザー管理", "pages/admin_users.py", admin_only=True),
    NavItem("💳 Billing 管理", "pages/admin_billing.py", admin_only=True),
    NavItem("📧 メール送信", "pages/admin_email.py", admin_only=True),
]
