# polymarket-copytrader — AUDIT.md 完全実装 作業マニュアル

> 作成日: 2026-06-21  
> 根拠: `AUDIT.md` 全文（共通UIデザイン規約 / 共通機能要件 Billing / 共通UX規約 / 共通機能要件 メール/通知 / フェーズ1 Step1〜4）  
> 対象スタック: Python 3.12 / Streamlit / SQLAlchemy + Alembic / Postgres / Fly.io

---

## 0. 前提整理：AUDIT.md と本ツールのスタック差異

AUDIT.md は **Next.js 14 / TypeScript / Supabase / Stripe** を共通前提に書かれている。  
本ツールは **Python 3.12 / Streamlit / SQLAlchemy / Postgres** であるため、以下の読み替えを行う。

| AUDIT.md の概念 | 本ツールでの対応方針 |
|---|---|
| Supabase Auth（signup/login/email確認） | DB 管理の独自マルチユーザー認証（`users` テーブル + bcrypt + JWT セッション） |
| Supabase RLS | SQLAlchemy クエリレベルのユーザーフィルタ（`WHERE user_id = :me`） |
| Next.js App Router + layout.tsx | Streamlit multipage + `st.session_state` + `st.sidebar` |
| Tailwind CSS / CSS変数 | `theme.py` の Python 定数 + Streamlit カスタム CSS（`st.markdown` inject） |
| React コンポーネント（Sidebar, NavGroup, etc.） | Streamlit `st.sidebar` + Python ヘルパ関数 |
| `/admin/**` ルート | Streamlit admin ページ（`pages/admin_*.py`）+ ロール検証デコレータ |
| Stripe Billing | Stripe Python SDK（`stripe` パッケージ） |
| Resend メール | `resend` Python SDK または `sendgrid` |
| `@radix-ui/react-tooltip`（HelpTooltip） | Streamlit `st.markdown` + CSS/JS inject の hover tooltip（既実装の `help_icon()` を拡張） |
| Playwright E2E | `playwright` Python（`pytest-playwright`） |

---

## 1. 実装項目の全体マップと優先度

| # | カテゴリ | 項目 | 優先度 | 概算工数 | 現状 |
|---|---|---|---|---|---|
| A-1 | 認証 | マルチユーザー認証（signup/login/logout/PW reset） | **P0** | 3d | 単一PWゲートのみ |
| A-2 | 認証 | ロール管理（user/admin）+ admin保護 | **P0** | 1d | なし |
| A-3 | 認証 | セッション管理（JWT or DB セッション） | **P0** | 1d | session_state のみ |
| B-1 | UI構造 | 左カラム固定サイドバー（黒背景/白文字） | P1 | 1d | なし（collapsed） |
| B-2 | UI構造 | 管理者メニュー（サイドバー下端固定） | P1 | 0.5d | なし |
| B-3 | UI構造 | 2階層ナビ（アコーディオン、現在地ハイライト） | P1 | 1d | フラットなページリスト |
| B-4 | UI構造 | ページ内タブ廃止・独立ページ化 | P2 | 1d | Strategy/Execute に暗黙タブあり |
| B-5 | UI構造 | `config/navigation.py` 一元管理 | P2 | 0.5d | なし |
| B-6 | UI構造 | 管理者ページ全面黒背景 | P2 | 0.5d | なし |
| B-7 | UI構造 | モバイル対応（サイドバードロワー化） | P3 | 1d | なし |
| C-1 | Billing | ユーザー Billing ページ（/settings/billing） | P1 | 2d | なし |
| C-2 | Billing | 管理者 Billing ページ（/admin/billing） | P1 | 2d | なし |
| C-3 | Billing | Stripe Webhook（署名検証付き） | P1 | 1d | なし |
| C-4 | Billing | DB スキーマ（stripe_customer_id 等） | P1 | 0.5d | なし |
| D-1 | メール | Resend 送信基盤 | P1 | 1d | Telegram のみ |
| D-2 | メール | 通知設定 ON/OFF 永続化 | P2 | 1d | なし |
| D-3 | メール | 管理者→ユーザー一斉送信 | P2 | 1d | なし |
| D-4 | メール | 通知テンプレート編集 UI | P3 | 1.5d | なし |
| E-1 | UX | 管理者ユーザー一覧（/admin/users） | P1 | 1d | なし |
| E-2 | UX | ユーザー詳細（ダブルクリック/詳細パネル） | P1 | 0.5d | なし |
| E-3 | UX | 初回ユーザー動線（オンボーディング） | P2 | 1d | なし |
| E-4 | UX | エラーメッセージ改善（全 catch 節レビュー） | P2 | 0.5d | 一部のみ |
| F-1 | Tooltip | `help_icon()` 拡張（350ms 遅延/mousedown キャンセル） | P2 | 0.5d | 基本実装あり |
| F-2 | Tooltip | `config/tooltips.py` 一元管理 | P2 | 0.5d | インライン記述 |
| G-1 | E2E | Playwright テスト（5シナリオ） | P2 | 2d | なし |

---

## 2. A：認証システム（マルチユーザー）

### 現状
`web/auth.py` の `require_password()` は単一の `WEB_PASSWORD` 環境変数でゲートするだけ。  
AUDIT.md が求めるマルチユーザー認証（signup/login/logout/PW reset/メール確認）は未実装。

### 判断ポイント（実装前に確認必須）
> **このツールをマルチユーザー SaaS として提供するか？**  
> - Yes → 以下の A-1〜A-3 をすべて実装する  
> - No（個人利用ツールのまま） → 現状の `WEB_PASSWORD` で十分。A-1〜A-3 はスコープ外

---

### A-1: DB マルチユーザー認証の実装

#### migration: `alembic/versions/0006_auth_users.py`
```sql
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    pw_hash     TEXT NOT NULL,               -- bcrypt
    role        TEXT NOT NULL DEFAULT 'user', -- 'user' | 'admin'
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    email_verified_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT UNIQUE NOT NULL,        -- SHA-256(random token)
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX sessions_token_hash_idx ON sessions(token_hash);
CREATE INDEX sessions_user_id_idx ON sessions(user_id);

CREATE TABLE pw_reset_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT UNIQUE NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ
);
```

#### `src/copytrader/web/auth.py` 全面書き換え
```python
"""マルチユーザー認証ゲート。"""
import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import streamlit as st
from sqlalchemy import select

from copytrader.db.engine import get_session
from copytrader.db.models import Session as DbSession, User

SESSION_COOKIE = "_session_token"
SESSION_TTL = timedelta(days=7)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with get_session() as s:
        s.add(DbSession(
            user_id=user_id,
            token_hash=_hash_token(token),
            expires_at=datetime.now(UTC) + SESSION_TTL,
        ))
    return token


def _resolve_session(token: str) -> User | None:
    h = _hash_token(token)
    with get_session() as s:
        row = s.execute(
            select(DbSession).where(
                DbSession.token_hash == h,
                DbSession.expires_at > datetime.now(UTC),
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return s.get(User, row.user_id)


def current_user() -> User | None:
    """session_state にキャッシュ済みユーザーを返す。未認証なら None。"""
    return st.session_state.get("_current_user")


def require_login() -> None:
    """未認証ならログインフォームを表示してページ描画を停止する。"""
    if current_user() is not None:
        return

    token = st.session_state.get(SESSION_COOKIE)
    if token:
        user = _resolve_session(token)
        if user and user.is_active:
            st.session_state["_current_user"] = user
            return
        st.session_state.pop(SESSION_COOKIE, None)

    _show_login_form()
    st.stop()


def require_admin() -> None:
    """管理者ロール以外はアクセス拒否（403相当）。"""
    require_login()
    if current_user().role != "admin":
        st.error("⛔ 管理者専用ページです。")
        st.stop()


def _show_login_form() -> None:
    st.markdown("## 🔒 ログイン")
    with st.form("login_form"):
        email = st.text_input("メールアドレス")
        pw = st.text_input("パスワード", type="password")
        col1, col2 = st.columns(2)
        submitted = col1.form_submit_button("ログイン")
        reset_link = col2.form_submit_button("パスワードを忘れた")

    if submitted:
        _handle_login(email, pw)
    if reset_link:
        st.session_state["_show_reset"] = True
        st.rerun()

    if st.session_state.get("_show_reset"):
        _show_pw_reset_form()


def _handle_login(email: str, pw: str) -> None:
    with get_session() as s:
        user = s.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
    if user is None or not bcrypt.checkpw(pw.encode(), user.pw_hash.encode()):
        st.error("メールアドレスまたはパスワードが違います")
        return
    if not user.is_active:
        st.error("このアカウントは無効化されています")
        return
    token = _create_session(str(user.id))
    st.session_state[SESSION_COOKIE] = token
    st.session_state["_current_user"] = user
    st.rerun()


def logout() -> None:
    st.session_state.pop(SESSION_COOKIE, None)
    st.session_state.pop("_current_user", None)
    st.rerun()
```

#### `src/copytrader/web/pages/login.py`（サインアップ画面）
```python
"""サインアップ（新規ユーザー登録）。"""
import bcrypt
import streamlit as st
from sqlalchemy import select
from copytrader.db.engine import get_session
from copytrader.db.models import User

st.set_page_config(page_title="サインアップ", layout="centered")

st.markdown("## 📝 新規登録")
with st.form("signup_form"):
    email = st.text_input("メールアドレス")
    pw = st.text_input("パスワード（8文字以上）", type="password")
    pw2 = st.text_input("パスワード（確認）", type="password")
    submitted = st.form_submit_button("登録")

if submitted:
    if len(pw) < 8:
        st.error("パスワードは8文字以上にしてください")
    elif pw != pw2:
        st.error("パスワードが一致しません")
    else:
        with get_session() as s:
            exists = s.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if exists:
                st.error("このメールアドレスはすでに登録されています")
            else:
                pw_hash = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
                s.add(User(email=email, pw_hash=pw_hash))
        st.success("登録しました。ログインしてください。")
        st.page_link("pages/login.py", label="ログインへ")
```

#### パスワードリセット（概要のみ）
1. `pw_reset_tokens` にトークンを INSERT → Resend（D-1）でリセットメールを送信
2. ユーザーがリンクを踏む → トークン検証 → 新パスワード入力フォーム → `users.pw_hash` 更新

---

### A-2: ロール管理と管理者保護

全ページ先頭の `require_password()` を `require_login()` に置き換える。  
管理者専用ページ（`pages/admin_*.py`）は `require_admin()` を呼ぶ。

```python
# 全 web/pages/*.py の先頭を変更
# Before:
require_password()
# After (一般ページ):
require_login()
# After (管理者ページ):
require_admin()
```

---

## 3. B：共通UIデザイン規約（サイドバー構造）

### 現状 GAP 分析

| 規約項目 | 現状 | 判定 | 改修内容 | 工数 |
|---|---|---|---|---|
| 左カラム固定（黒背景・白文字） | `initial_sidebar_state="collapsed"` で折りたたみ | ❌ | `expanded` に変更 + CSS で黒背景化 | 0.5d |
| ユーザーメニュー上部・管理者メニュー下端 | メニュー構造なし | ❌ | `navigation.py` + サイドバーレンダラ | 1d |
| 2階層ナビ（アコーディオン開閉） | Streamlit の自動ページリスト | ❌ | カスタムサイドバーで実装 | 1d |
| 現在地ハイライト | なし | ❌ | `st.query_params` で判定 | 0.5d |
| ページ内タブの廃止 | `st.tabs()` 使用なし（確認済） | ✅ | 対応不要 | — |
| カラー規約（左:黒/右:白） | 全面ダークテーマ | ⚠️ | 一般ページの右カラムを白に変更 | 0.5d |
| 管理者ページ全面黒 | 管理者ページ自体がない | ❌ | admin ページ作成時に適用 | 0.5d |
| モバイルドロワー | なし | ❌ | Streamlit ネイティブのハンバーガーで対応可 | P3 |

### B-1〜B-5: 実装手順

#### Step 1: `src/copytrader/web/navigation.py` 作成
```python
"""ナビゲーション定義（一元管理）。"""
from dataclasses import dataclass, field

@dataclass
class NavItem:
    label: str
    page: str          # Streamlit page path (e.g. "pages/1_Strategy.py")
    icon: str = ""
    admin_only: bool = False
    children: list["NavItem"] = field(default_factory=list)


NAVIGATION: list[NavItem] = [
    NavItem("🏠 Home",       "app.py"),
    NavItem("📈 Strategy",   "pages/1_Strategy.py"),
    NavItem("⚡ Execute",    "pages/2_Execute.py", children=[
        NavItem("ウォッチリスト", "pages/2a_Watchlist.py"),
        NavItem("ジョブ",       "pages/2b_Jobs.py"),
        NavItem("ロールアウト",  "pages/2c_Rollout.py"),
    ]),
    NavItem("🔧 Ops",        "pages/3_Ops.py"),
]

ADMIN_NAVIGATION: list[NavItem] = [
    NavItem("👥 ユーザー管理",    "pages/admin_users.py",   admin_only=True),
    NavItem("💳 Billing 管理",   "pages/admin_billing.py", admin_only=True),
    NavItem("📧 メール送信",      "pages/admin_email.py",   admin_only=True),
]
```

#### Step 2: `src/copytrader/web/sidebar.py` 作成
```python
"""サイドバーレンダラ（黒背景・2階層ナビ）。"""
import streamlit as st
from copytrader.web.auth import current_user
from copytrader.web.navigation import ADMIN_NAVIGATION, NAVIGATION, NavItem

_SIDEBAR_CSS = """
<style>
[data-testid="stSidebar"] {
    background-color: #000 !important;
    color: #fff !important;
}
[data-testid="stSidebar"] a, [data-testid="stSidebar"] p,
[data-testid="stSidebar"] label, [data-testid="stSidebar"] span {
    color: #fff !important;
}
[data-testid="stSidebar"] .nav-item-active {
    background: #1a1a1a;
    border-radius: 6px;
}
.admin-divider { border-top: 1px solid #333; margin: 1rem 0 0.5rem; }
</style>
"""

def render_sidebar() -> None:
    """全ページ共通サイドバー。app.py 等の先頭で呼ぶ。"""
    st.markdown(_SIDEBAR_CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("### 📊 Copytrader")
        _render_nav_items(NAVIGATION)

        user = current_user()
        if user and user.role == "admin":
            st.markdown('<div class="admin-divider"></div>', unsafe_allow_html=True)
            st.markdown("**管理者**", help="管理者メニュー")
            _render_nav_items(ADMIN_NAVIGATION)

        st.markdown("---")
        if user:
            st.caption(f"👤 {user.email}")
            if st.button("ログアウト", use_container_width=True):
                from copytrader.web.auth import logout
                logout()


def _render_nav_items(items: list[NavItem]) -> None:
    for item in items:
        if item.children:
            with st.expander(item.label, expanded=_is_active_group(item)):
                for child in item.children:
                    st.page_link(child.page, label=child.label, icon=child.icon)
        else:
            st.page_link(item.page, label=item.label, icon=item.icon)


def _is_active_group(item: NavItem) -> bool:
    """現在のページが子ページならグループを自動展開。"""
    # Streamlit does not expose current page path directly;
    # use st.query_params or __file__ inspection per page.
    return False  # 各ページで session_state["_active_group"] をセットして拡張
```

#### Step 3: 全ページに `render_sidebar()` を追加
```python
# 各 pages/*.py の先頭（set_page_config の直後）に追加
from copytrader.web.sidebar import render_sidebar
# ...
st.set_page_config(..., initial_sidebar_state="expanded")  # collapsed → expanded
require_login()
render_sidebar()
```

---

## 4. C：Billing（Stripe 連携）

### 判断ポイント（実装前に確認必須）
> **このツールを課金制 SaaS として提供するか？**  
> - Yes → C-1〜C-4 を実装する  
> - No（個人利用）→ Billing 不要。スコープ外として docs/requirements.md に明記すること

### C-4: DB スキーマ（先行実装必須）

#### migration: `alembic/versions/0007_billing.py`
```sql
ALTER TABLE users
    ADD COLUMN stripe_customer_id TEXT,
    ADD COLUMN stripe_subscription_id TEXT,
    ADD COLUMN subscription_status TEXT,       -- 'active' | 'trialing' | 'past_due' | 'canceled'
    ADD COLUMN subscription_period_end TIMESTAMPTZ,
    ADD COLUMN price_id TEXT;

CREATE TABLE admin_audit_log (
    id          BIGSERIAL PRIMARY KEY,
    actor_id    UUID NOT NULL REFERENCES users(id),
    action      TEXT NOT NULL,                 -- 'refund' | 'cancel_subscription' | 'send_email'
    target_type TEXT NOT NULL,                 -- 'user' | 'invoice'
    target_id   TEXT NOT NULL,
    detail      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### C-1: ユーザー Billing ページ（`pages/settings_billing.py`）

```python
"""設定 > Billing — 支払履歴・領収書。"""
import stripe
import streamlit as st
from copytrader.web.auth import current_user, require_login
from copytrader.web.sidebar import render_sidebar

st.set_page_config(page_title="Billing", layout="wide",
                   initial_sidebar_state="expanded")
require_login()
render_sidebar()

st.markdown("## 💳 Billing")

user = current_user()
if not user.stripe_customer_id:
    st.info("まだお支払い情報がありません。")
    st.stop()

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

# --- サブスク状態表示 ---
sub = stripe.Subscription.retrieve(user.stripe_subscription_id)
st.metric("ステータス", sub.status)
st.metric("次回請求日", _fmt_ts(sub.current_period_end))

# --- 支払履歴一覧 ---
invoices = stripe.Invoice.list(customer=user.stripe_customer_id, limit=20)
rows = []
for inv in invoices.auto_paging_iter():
    rows.append({
        "日付": _fmt_ts(inv.created),
        "金額": f"¥{inv.amount_paid:,}",
        "ステータス": inv.status,
        "領収書": inv.hosted_invoice_url or "",
    })
df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True)

# カード変更は Stripe Customer Portal へ
if st.button("支払い方法を変更"):
    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=st.get_option("server.baseUrlPath") + "/settings_billing",
    )
    st.markdown(f'<meta http-equiv="refresh" content="0; url={session.url}">',
                unsafe_allow_html=True)
```

### C-2: 管理者 Billing ページ（`pages/admin_billing.py`）

```python
"""管理者 > Billing 管理。"""
import stripe, os
import pandas as pd
import streamlit as st
from copytrader.web.auth import require_admin, current_user
from copytrader.web.sidebar import render_sidebar
from copytrader.db.engine import get_session
from copytrader.db.models import User, AdminAuditLog

st.set_page_config(page_title="Admin Billing", layout="wide",
                   initial_sidebar_state="expanded")
require_admin()
render_sidebar()

# 管理者ページ: 全面黒背景
st.markdown("""
<style>
.stApp { background: #000 !important; color: #fff !important; }
</style>""", unsafe_allow_html=True)

st.markdown("## 👥 Billing 管理")
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

# --- ユーザー一覧 ---
with get_session() as s:
    users = s.execute(select(User).where(User.stripe_customer_id != None)).scalars().all()

rows = [{"email": u.email, "status": u.subscription_status,
         "period_end": u.subscription_period_end} for u in users]
df = pd.DataFrame(rows)

# dataframe_events でダブルクリック検知
event = st.dataframe(df, use_container_width=True, on_select="rerun",
                     selection_mode="single-row")

selected = event.selection.rows
if selected:
    user = users[selected[0]]
    with st.expander(f"📋 {user.email} の支払履歴", expanded=True):
        invoices = stripe.Invoice.list(customer=user.stripe_customer_id, limit=10)
        for inv in invoices.auto_paging_iter():
            c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
            c1.write(_fmt_ts(inv.created))
            c2.write(f"¥{inv.amount_paid:,}")
            c3.write(inv.status)
            if inv.invoice_pdf:
                c4.markdown(f"[PDF]({inv.invoice_pdf})")
        
        # 返金操作
        st.markdown("---")
        charge_id = st.text_input("返金対象の Charge ID")
        amount = st.number_input("返金額（円）", min_value=1)
        if st.button("⚠️ 返金実行", type="secondary"):
            if st.session_state.get("_refund_confirmed"):
                stripe.Refund.create(charge=charge_id, amount=int(amount))
                _log_audit(current_user().id, "refund", "charge", charge_id,
                           {"amount": amount})
                st.success("返金しました")
                st.session_state.pop("_refund_confirmed")
            else:
                st.warning(f"¥{amount:,} を返金します。もう一度押して確定してください。")
                st.session_state["_refund_confirmed"] = True
```

### C-3: Stripe Webhook（`pages/api/stripe_webhook.py`）

Streamlit は API ルートを持たないため、**別途 FastAPI エンドポイント**か  
Fly.io の `web` プロセスに `aiohttp` ルートを追加する方式を推奨。

```python
# health/server.py に追加（既存の aiohttp サーバーを流用）
import stripe, os
from aiohttp import web

async def stripe_webhook(request: web.Request) -> web.Response:
    payload = await request.read()
    sig = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig, os.environ["STRIPE_WEBHOOK_SECRET"]
        )
    except stripe.error.SignatureVerificationError:
        return web.Response(status=400, text="invalid signature")

    if event["type"] == "invoice.paid":
        _handle_invoice_paid(event["data"]["object"])
    elif event["type"] == "customer.subscription.updated":
        _handle_subscription_updated(event["data"]["object"])
    elif event["type"] == "charge.refunded":
        _handle_refund(event["data"]["object"])
    return web.Response(status=200, text="ok")

def _handle_invoice_paid(invoice: dict) -> None:
    customer_id = invoice["customer"]
    with get_session() as s:
        user = s.execute(select(User).where(
            User.stripe_customer_id == customer_id
        )).scalar_one_or_none()
        if user:
            user.subscription_status = "active"
```

---

## 5. D：メール/通知（Resend）

### D-1: 送信基盤 `src/copytrader/email/client.py`

```python
"""Resend メール送信基盤。"""
import os
import resend
from dataclasses import dataclass

resend.api_key = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "noreply@example.com")

@dataclass
class EmailMessage:
    to: str
    subject: str
    html: str

def send_email(msg: EmailMessage) -> None:
    if not resend.api_key:
        return  # dev 環境ではスキップ
    resend.Emails.send({
        "from": FROM_EMAIL,
        "to": msg.to,
        "subject": msg.subject,
        "html": msg.html,
    })

def send_password_reset(to: str, reset_url: str) -> None:
    send_email(EmailMessage(
        to=to,
        subject="パスワードリセット",
        html=f"<p><a href='{reset_url}'>こちらをクリックしてパスワードをリセット</a></p>"
             f"<p>このリンクは1時間で無効になります。</p>",
    ))

def send_subscription_receipt(to: str, amount: int, period: str) -> None:
    send_email(EmailMessage(
        to=to,
        subject="お支払いが完了しました",
        html=f"<p>{period} 分の料金 ¥{amount:,} を受領しました。</p>",
    ))
```

### D-2: 通知設定テーブル

```sql
-- migration 0008_notification_prefs.py
CREATE TABLE notification_prefs (
    user_id      UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    invoice_paid BOOLEAN NOT NULL DEFAULT TRUE,
    risk_halt    BOOLEAN NOT NULL DEFAULT TRUE,
    daily_summary BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### D-3: 管理者→ユーザー送信（`pages/admin_email.py`）

```python
"""管理者 > メール送信。"""
import streamlit as st
from copytrader.web.auth import require_admin
from copytrader.web.sidebar import render_sidebar
from copytrader.email.client import send_email, EmailMessage
from copytrader.db.engine import get_session
from copytrader.db.models import User

st.set_page_config(page_title="メール送信", layout="wide")
require_admin()
render_sidebar()

st.markdown("## 📧 ユーザーへのメール送信")

target = st.radio("送信対象", ["全ユーザー", "絞り込み（ステータス別）", "個別指定"])
subject = st.text_input("件名")
body = st.text_area("本文（HTML可）")

if st.button("送信", type="primary"):
    with st.spinner("送信中..."):
        with get_session() as s:
            users = _resolve_targets(s, target)
        for u in users:
            send_email(EmailMessage(to=u.email, subject=subject, html=body))
        _log_audit(current_user().id, "send_email", "users", target,
                   {"subject": subject, "count": len(users)})
    st.success(f"{len(users)} 件送信しました")
```

---

## 6. E：管理者ユーザー一覧（`pages/admin_users.py`）

```python
"""管理者 > ユーザー管理。"""
import streamlit as st
import pandas as pd
from sqlalchemy import select
from copytrader.web.auth import require_admin, current_user
from copytrader.web.sidebar import render_sidebar
from copytrader.db.engine import get_session
from copytrader.db.models import User, AdminAuditLog

st.set_page_config(page_title="ユーザー管理", layout="wide")
require_admin()
render_sidebar()

st.markdown("## 👥 ユーザー一覧")

# 検索・絞り込み
col1, col2 = st.columns([3, 1])
search = col1.text_input("メール検索")
status_filter = col2.selectbox("ステータス", ["全て", "active", "canceled", "past_due"])

with get_session() as s:
    q = select(User)
    if search:
        q = q.where(User.email.ilike(f"%{search}%"))
    if status_filter != "全て":
        q = q.where(User.subscription_status == status_filter)
    users = s.execute(q).scalars().all()

rows = [{
    "メール": u.email,
    "ロール": u.role,
    "サブスク": u.subscription_status or "—",
    "期限": str(u.subscription_period_end)[:10] if u.subscription_period_end else "—",
    "登録日": str(u.created_at)[:10],
    "有効": "✅" if u.is_active else "❌",
} for u in users]

event = st.dataframe(pd.DataFrame(rows), use_container_width=True,
                     on_select="rerun", selection_mode="single-row")

# ダブルクリック相当（行選択→詳細パネル）
if event.selection.rows:
    u = users[event.selection.rows[0]]
    with st.expander(f"👤 {u.email} の詳細", expanded=True):
        col1, col2, col3 = st.columns(3)
        col1.metric("ロール", u.role)
        col2.metric("ステータス", u.subscription_status or "—")

        with st.form(f"user_edit_{u.id}"):
            new_role = st.selectbox("ロール変更", ["user", "admin"],
                                    index=0 if u.role == "user" else 1)
            is_active = st.checkbox("有効", value=u.is_active)
            if st.form_submit_button("保存"):
                with get_session() as s:
                    user = s.get(User, u.id)
                    user.role = new_role
                    user.is_active = is_active
                _log_audit(current_user().id, "update_user", "user", str(u.id),
                           {"role": new_role, "is_active": is_active})
                st.success("保存しました")
                st.rerun()

        if st.button("🚫 アカウントを凍結", type="secondary"):
            with get_session() as s:
                s.get(User, u.id).is_active = False
            _log_audit(current_user().id, "freeze_user", "user", str(u.id), {})
            st.warning(f"{u.email} を凍結しました")
            st.rerun()
```

---

## 7. F：HelpTooltip（コンテキストヘルプ）改善

### 現状
`help_icon()` は `title` 属性を使ったネイティブブラウザ tooltip。  
AUDIT.md 規約: 350ms 遅延・mousedown キャンセル・pointer-events:none が必要。

### 改修方針

Streamlit では React コンポーネントを直接扱えないため、  
**`st.components.v1.html()` + カスタム JS** で実装する。

```python
# src/copytrader/web/tooltip.py
import streamlit.components.v1 as components

_TOOLTIP_JS = """
<script>
document.querySelectorAll('.help-tip-icon').forEach(el => {
  let timer = null;
  let tip = null;

  el.addEventListener('mouseenter', () => {
    timer = setTimeout(() => {
      tip = document.createElement('div');
      tip.className = 'help-tooltip';
      tip.style.cssText = `
        position: fixed; z-index: 9999; pointer-events: none;
        background: #1a1a1a; color: #fff; border-radius: 8px;
        padding: 8px 12px; max-width: 220px; font-size: 12px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.5);
      `;
      tip.textContent = el.getAttribute('data-tip');
      document.body.appendChild(tip);
      const r = el.getBoundingClientRect();
      tip.style.left = (r.right + 8) + 'px';
      tip.style.top = r.top + 'px';
    }, 350);
  });

  el.addEventListener('mouseleave', () => {
    clearTimeout(timer);
    if (tip) { tip.remove(); tip = null; }
  });

  el.addEventListener('mousedown', () => {
    clearTimeout(timer);
    if (tip) { tip.remove(); tip = null; }
  });
});
</script>
"""

def inject_tooltip_js() -> None:
    """各ページの inject_theme() 内で一度だけ呼ぶ。"""
    components.html(_TOOLTIP_JS, height=0)
```

### `config/tooltips.py` 作成（一元管理）

```python
# src/copytrader/web/config/tooltips.py
TOOLTIPS: dict[str, dict] = {
    # ナビゲーション
    "nav.home":       {"title": "Home",         "body": "12タイルで運用状況を一目で確認できます。"},
    "nav.strategy":   {"title": "Strategy",     "body": "Phase 0の実行と結果レポートを確認します。"},
    "nav.execute":    {"title": "Execute",      "body": "執行設定・ウォッチリスト・ジョブ管理を行います。"},
    "nav.ops":        {"title": "Ops",          "body": "障害対応・設定変更・詳細ログを確認します。"},
    # 主要ボタン
    "btn.run_phase0": {"title": "Phase 0 実行", "body": "過去データでedgeを検証します。本番資金は動きません。"},
    "btn.kill_switch":{"title": "Kill Switch",  "body": "ONにすると執行を即時停止します。",
                       "shortcut": "即時反映・確認なし"},
    # 管理者
    "admin.freeze":   {"title": "凍結",         "body": "ユーザーのログインと操作を即時停止します。",
                       "shortcut": "監査ログに記録"},
}
```

---

## 8. G：E2E テスト（Playwright）

AUDIT.md Step 2.5 で必須とされる5シナリオをローカル Postgres 上で実行する。

### セットアップ
```bash
pip install pytest-playwright
playwright install chromium
docker compose up -d   # Postgres + web + worker
```

### `e2e/test_auth.py`（シナリオ1: 認証フロー）
```python
import pytest
from playwright.sync_api import Page

BASE = "http://localhost:8501"

def test_signup_login_logout(page: Page):
    # サインアップ
    page.goto(f"{BASE}/login")
    page.fill("[data-testid='stTextInput']:nth-of-type(1)", "test@example.com")
    page.fill("[data-testid='stTextInput']:nth-of-type(2)", "password123")
    page.fill("[data-testid='stTextInput']:nth-of-type(3)", "password123")
    page.click("button:has-text('登録')")
    page.wait_for_selector("text=登録しました")

    # ログイン
    page.goto(BASE)
    page.fill("[data-testid='stTextInput']:nth-of-type(1)", "test@example.com")
    page.fill("[data-testid='stTextInput']:nth-of-type(2)", "password123")
    page.click("button:has-text('ログイン')")
    page.wait_for_selector("text=Home")

    # ログアウト
    page.click("button:has-text('ログアウト')")
    page.wait_for_selector("text=ログイン")
```

### `e2e/test_admin.py`（シナリオ3: 管理者フロー）
```python
def test_admin_user_list(page: Page, admin_user):
    _login(page, admin_user.email, "adminpass")
    page.goto(f"{BASE}/admin_users")
    page.wait_for_selector("text=ユーザー一覧")
    # 一般ユーザーが管理者ページにアクセスできないことを確認
    _login(page, "user@example.com", "userpass")
    page.goto(f"{BASE}/admin_users")
    page.wait_for_selector("text=管理者専用ページです")
```

---

## 9. 実装順序（推奨ロードマップ）

### Week 1（P0・認証基盤）
1. **マルチユーザー要否の意思決定**（Yes/No を確定してから進む）
2. migration 0006（users/sessions テーブル）
3. `web/auth.py` 全面書き換え（require_login / require_admin）
4. 全ページの `require_password()` → `require_login()` 置き換え
5. 初期管理者ユーザーの seed（`python -m copytrader.cli.create_admin`）

### Week 2（P1・UI構造 + 管理者ページ）
6. `navigation.py` + `sidebar.py` 作成
7. 全ページに `render_sidebar()` + `initial_sidebar_state="expanded"` 追加
8. `pages/admin_users.py` 作成
9. `pages/admin_billing.py` の骨格（Stripe 未接続でもユーザー一覧を表示）

### Week 3（P1・Billing）
10. migration 0007（stripe_customer_id 等）
11. `pip install stripe` + `pages/settings_billing.py`
12. Webhook ハンドラを `health/server.py` に追加
13. Stripe テストモードで E2E 検証

### Week 4（P1〜P2・メール + UX）
14. `pip install resend` + `email/client.py`
15. migration 0008（notification_prefs）
16. パスワードリセットメール実装
17. `pages/admin_email.py`
18. Playwright E2E 5シナリオ作成

### Week 5（P2〜P3・UX改善）
19. tooltip.py 改善（350ms 遅延・mousedown キャンセル）
20. `config/tooltips.py` 一元化
21. エラーメッセージ全件レビュー
22. 初回ユーザーオンボーディング画面

---

## 10. 環境変数追加リスト

| 変数 | 用途 | 必須度 |
|---|---|---|
| `STRIPE_SECRET_KEY` | Stripe API（サーバー側） | Billing 実装時必須 |
| `STRIPE_WEBHOOK_SECRET` | Webhook 署名検証 | Billing 実装時必須 |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | Stripe フロント（本ツールでは不要） | — |
| `RESEND_API_KEY` | メール送信 | メール実装時必須 |
| `RESEND_FROM_EMAIL` | 送信元アドレス | メール実装時必須 |
| `JWT_SECRET` または `SESSION_SECRET` | セッショントークン署名 | 認証実装時必須 |
| `ADMIN_INITIAL_EMAIL` | 初期管理者アカウント | 認証実装時必須 |
| `ADMIN_INITIAL_PASSWORD` | 初期管理者PW（初回起動後に変更） | 認証実装時必須 |

---

## 11. スコープ外（このツールには不要と判断した項目）

| AUDIT.md 項目 | 理由 |
|---|---|
| Supabase RLS | Postgres + SQLAlchemy 直接アクセス。RLS の代替はクエリレベルの `WHERE user_id = :me` |
| Next.js middleware / layout.tsx | Streamlit には該当なし |
| `@supabase/ssr` セッション管理 | 独自 sessions テーブルで代替 |
| `@radix-ui/react-tooltip` | Python/Streamlit ではカスタム JS で代替 |
| Tailwind CSS テーマトークン | Streamlit の CSS 変数（`theme.py` 定数）で代替 |
| OAuth（Google等）ログイン | 要否は個別判断。追加コスト 2d |
| ユーザー→顧客へのメール送信 | このツールに「顧客」概念は存在しない |

---

## 12. 実装チェックリスト

```
認証
[ ] migration 0006 (users / sessions / pw_reset_tokens)
[ ] web/auth.py: require_login / require_admin / logout
[ ] pages/login.py: サインアップ・ログインフォーム
[ ] パスワードリセットフロー（DB + Resend メール）
[ ] 全ページの require_password → require_login 置き換え
[ ] 管理者ページへの require_admin 追加
[ ] 初期管理者 seed スクリプト

UI構造
[ ] navigation.py（NAVIGATION / ADMIN_NAVIGATION 定義）
[ ] sidebar.py（黒背景 CSS + render_sidebar 関数）
[ ] 全ページ: render_sidebar() + expanded サイドバー

管理者ページ
[ ] pages/admin_users.py（一覧・絞り込み・詳細・凍結）
[ ] pages/admin_billing.py（支払履歴・返金・サブスク変更）
[ ] pages/admin_email.py（一斉・個別送信）

Billing
[ ] migration 0007 (stripe_customer_id 等 + admin_audit_log)
[ ] pip install stripe
[ ] pages/settings_billing.py（履歴・領収書・Portal）
[ ] health/server.py: Stripe Webhook ルート追加（署名検証必須）
[ ] Webhook ハンドラ: invoice.paid / subscription.updated / charge.refunded

メール
[ ] pip install resend
[ ] email/client.py (send_email / send_password_reset / send_receipt)
[ ] migration 0008 (notification_prefs)
[ ] 通知設定 ON/OFF 永続化（Ops > 設定ページに追加）

Tooltip
[ ] tooltip.py: 350ms 遅延 + mousedown キャンセル JS
[ ] config/tooltips.py: 全メニュー・ボタンの文言一元管理

E2E
[ ] pip install pytest-playwright && playwright install chromium
[ ] e2e/test_auth.py（signup/login/logout）
[ ] e2e/test_crud.py（Phase 0 実行フロー）
[ ] e2e/test_admin.py（管理者フロー + 権限境界）
[ ] e2e/test_billing.py（Stripe テストモード）
[ ] e2e/test_edge_cases.py（異常系）
```
