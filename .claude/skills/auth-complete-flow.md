---
name: auth-complete-flow
description: >-
  Next.js (App Router) / Supabase / TypeScript
  プロジェクトにおける認証フロー全般の実装・修復・監査・デバッグを行う包括的スキル。 Google OAuth・GitHub
  OAuth・Email/Magic Link・パスワードリセット・NextAuth v5 / Supabase Auth の両対応。
  「ログインしても未認証」「セッションが保持されない」「OAuthコールバック失敗」「本番HTTPS環境でのリダイレクトループ」
  「メールリンクが機能しない」「権限チェック漏れ」など認証全般の問題発生時に起動する。
category: auth
version: 3
tags:
  - nextjs
  - supabase
  - nextauth
  - oauth
  - jwt
  - magic-link
  - typescript
sourceSkillIds:
  - 2f74dbd8
  - 1d57d2e4
  - 66bd76e5
  - fae179bc
  - 2012789c
  - ec487531
  - 785232c6
  - 74925ad6
  - 34f57810
  - b5913cce
  - a2254dbd
  - 9ef22ce0
  - 348a3298
  - 21e3a772
  - 1247dc38
  - 8fe1b0a7
  - 0c7a5fc9
  - 2c84c48b
  - cb2f47b7
  - 7c767995
  - da99bb38
  - adc68264
  - 8af5b12b
  - c0eac1f9
  - 9cabb20f
  - 1fdaf7e3
  - 93f9b78e
  - e23e5149
  - bfc7933f
  - d25849d9
  - 7b586499
  - 5394377b
  - eb90b4bf
  - 59c4daae
  - 07c6c38e
  - 07206c63
  - f1cba622
  - 9a8598b4
  - 30d6d26c
  - b1d03195
generatedAt: '2026-06-17'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-28T12:00:00.000Z'
adoptedFromArchive:
  - archive/skills/medlearn-auth-session.md
  - archive/skills/auth-complete-flow.md
  - archive/skills/auth-email-flow.md
  - archive/skills/auth-system.md
  - archive/skills/auth-verify.md
  - archive/skills/design-login-page.md
  - archive/skills/email-auth-links.md
  - archive/skills/github-pat-integration.md
  - archive/skills/integration-oauth.md
  - archive/skills/new-api-route.md
---

# auth-complete-flow — 認証フロー完全実装スキル

Next.js (App Router) + Supabase + TypeScript における認証フロー全般を扱う包括的スキルです。
**新規実装・既存バグ修正・セキュリティ監査・本番デプロイ前チェック** の 4 用途をカバーします。

---

## 0. 起動判定チェックリスト

以下のいずれかに該当する場合、このスキルを使用してください。

| 症状 / 作業 | 該当セクション |
|---|---|
| 認証プロバイダーを新規追加したい | §1 アーキテクチャ選定 |
| ログインしても未認証状態になる | §4 デバッグ手順 |
| セッションが保持されない | §4-B セッション診断 |
| OAuth コールバックが失敗する | §3-A OAuth 実装, §4-C |
| メールリンクが届かない / 機能しない | §3-B メールリンク実装 |
| 本番 HTTPS でリダイレクトループが起きる | §5 HTTPS 本番バグ |
| パスワードリセットを実装したい | §3-B |
| middleware の権限チェックを実装したい | §2-C Middleware |
| デプロイ前に認証フローを静的検証したい | §6 静的検証チェックリスト |
| GitHub PAT 連携でプライベートリポジトリが取れない | §3-C GitHub PAT |

---

## 1. アーキテクチャ選定

### 1-A. 認証ライブラリの選択基準

```
要件を確認する順序:
1. Supabase を既に使っているか？
   → YES: Supabase Auth を第一候補とする（SSR クライアント + Server Actions）
   → NO:  NextAuth v5 (Auth.js) を使う

2. 複数の OAuth プロバイダーが必要か？
   → YES & Supabase: Supabase Auth の Social Login 機能を使う
   → YES & NextAuth: providers 配列に追加

3. JWT をカスタマイズしたいか？
   → Supabase: RLS ポリシーで代替 / JWT claim カスタムは Edge Function が必要
   → NextAuth: callbacks.jwt / callbacks.session で自由に拡張可能
```

### 1-B. 対応プロバイダー一覧

| プロバイダー | Supabase Auth | NextAuth v5 | 実装セクション |
|---|---|---|---|
| Google OAuth | ✅ | ✅ | §3-A |
| GitHub OAuth | ✅ | ✅ | §3-A |
| Email Magic Link | ✅ | ✅ | §3-B |
| Email + Password | ✅ | Credentials | §3-B |
| Password Reset | ✅ | カスタム実装 | §3-B |
| GitHub PAT（外部連携） | — | — | §3-C |
| freee / Stripe / Meta Ads | — | — | §3-D |

---

## 2. ファイル構成

### 2-A. Supabase Auth 構成（推奨）

```
app/
├── (auth)/
│   ├── login/
│   │   ├── page.tsx          # サーバーコンポーネント（レイアウト）
│   │   └── login-form.tsx    # クライアントコンポーネント（フォーム操作）
│   ├── register/
│   │   ├── page.tsx
│   │   └── register-form.tsx
│   ├── forgot-password/
│   │   └── page.tsx
│   └── reset-password/
│       └── page.tsx
├── auth/
│   └── callback/
│       └── route.ts          # OAuth / Magic Link コールバック処理
lib/
├── supabase/
│   ├── client.ts             # ブラウザ用クライアント（シングルトン）
│   ├── server.ts             # Server Component / Actions 用クライアント
│   └── middleware.ts         # middleware 用クライアント
middleware.ts                 # ルート保護
```

### 2-B. NextAuth v5 構成

```
app/
├── (auth)/
│   ├── login/page.tsx
│   └── register/page.tsx
├── api/
│   └── auth/
│       └── [...nextauth]/
│           └── route.ts      # NextAuth ハンドラー
lib/
└── auth.ts                   # NextAuth 設定（providers, callbacks, pages）
auth.config.ts                # Edge 互換設定（middleware 用）
middleware.ts                 # NextAuth ミドルウェア
```

### 2-C. Middleware（共通パターン）

```typescript
// middleware.ts
import { NextRequest, NextResponse } from 'next/server'

// Supabase Auth パターン
import { createServerClient } from '@supabase/ssr'

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return request.cookies.getAll() },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          )
          supabaseResponse = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          )
        },
      },
    }
  )

  // ⚠️ 重要: getUser() を必ず呼ぶ（セッションリフレッシュのため）
  const { data: { user } } = await supabase.auth.getUser()

  const isAuthPage = request.nextUrl.pathname.startsWith('/login') ||
                     request.nextUrl.pathname.startsWith('/register')
  const isProtectedRoute = request.nextUrl.pathname.startsWith('/dashboard') ||
                            request.nextUrl.pathname.startsWith('/app')

  if (!user
