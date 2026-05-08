---
name: auth-complete-flow
description: >-
  Next.js/Supabase/TypeScriptプロジェクトにおける認証フロー（OAuth・メール・マジックリンク・パスワードリセット）の実装・修復・監査・デバッグを行う包括的スキル。認証追加・セッション不具合・権限チェック漏れ・環境変数確認が必要なときに起動する。
category: auth
sourceSkillIds:
  - '906407e9'
  - '43560110'
  - 7f195b18
  - 5906a766
  - 7c03fba4
  - 5597d0ff
  - d0840991
  - 3c592d1d
  - 65b4cfb1
  - a2614101
  - ce004062
  - 74d839c6
  - 3d525e31
  - c1afe582
  - 7434c525
  - b013114c
  - 48d14926
  - 1e07217a
  - 2d0f80c2
  - 0fee0014
  - e2309e2d
  - d7fe2e18
  - eace4dd7
  - 9c8cafea
  - 9b4fb8af
  - a1ca0bbd
  - f743a005
  - 86ba9955
  - ac0d86a6
  - 3364fc72
  - 81a169be
  - f8796576
  - 1395b5d2
  - b29ac157
  - dff81e26
  - c15ad940
  - 0a98865c
  - 3cb1943a
  - 8f170407
  - d5df728f
  - e4e7c55a
  - e4f99eac
  - 25376c0a
  - ff8f258a
  - fa1bba76
  - c6d21246
  - 71a155ef
  - eb5ed6c2
  - 886b4e87
  - 5f4a44af
  - a23cda31
  - b4db4a06
  - 7a6209ea
  - 6dd2891e
  - b93def46
  - 02e6f9d3
  - d50886b7
  - 1d615646
  - 69eee762
  - 3fbb2eee
  - 91e27bd5
  - 79c298d8
  - 1b3424e1
  - d46525eb
  - ca67e5e7
  - 8a752d94
  - 15f4d701
  - 2b626550
  - bbd46a26
  - be8b2fb2
generatedAt: '2026-05-08'
---

# auth-complete-flow

## 概要

Next.js + Supabase + TypeScript スタックにおける認証フロー全体を実装・修復・監査・デバッグするスキル。OAuth（Google/GitHub等）・メール/パスワード・マジックリンク・パスワードリセットの各フローを統一的に扱う。

### このスキルを起動すべき状況

- 新規認証フロー（OAuth・メール・マジックリンク）を追加するとき
- ログイン後にセッションが取れない・ループするなどの不具合があるとき
- ミドルウェアやサーバーコンポーネントで認証チェック漏れが疑われるとき
- 環境変数の設定ミスやコールバック URL の不一致が疑われるとき
- 認証まわりのセキュリティ監査・コードレビューを行うとき

---

## 1. アーキテクチャ全体像

```
┌─────────────────────────────────────────────────────────┐
│                    Next.js App Router                    │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                  │
│  │ middleware.ts │    │ Route Handler│                  │
│  │ (Edge)        │    │ /auth/callback│                 │
│  └──────┬───────┘    └──────┬───────┘                  │
│         │                   │                           │
│  ┌──────▼───────────────────▼───────┐                  │
│  │     Supabase SSR Client          │                  │
│  │  createServerClient / cookies()  │                  │
│  └──────────────────────────────────┘                  │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                  │
│  │ Server Comp. │    │ Client Comp. │                  │
│  │ createClient │    │ createClient │                  │
│  │ (server)     │    │ (browser)    │                  │
│  └──────────────┘    └──────────────┘                  │
└─────────────────────────────────────────────────────────┘
                         │
                    Supabase Auth
                         │
              ┌──────────┴──────────┐
              │                     │
          OAuth Provider      Email / OTP
         (Google, GitHub)    (Magic Link)
```

---

## 2. 必須ファイル構成

```
src/
├── lib/
│   └── supabase/
│       ├── client.ts        # ブラウザ用クライアント（シングルトン）
│       ├── server.ts        # サーバー用クライアント（cookies）
│       └── middleware.ts    # ミドルウェア用クライアント
├── app/
│   ├── auth/
│   │   ├── callback/
│   │   │   └── route.ts     # OAuthコールバック・マジックリンク処理
│   │   ├── login/
│   │   │   └── page.tsx
│   │   └── error/
│   │       └── page.tsx
│   └── middleware.ts        # ルートガード
└── types/
    └── auth.ts              # 認証関連型定義
```

---

## 3. Supabase クライアント実装

### 3-1. ブラウザ用（`src/lib/supabase/client.ts`）

```typescript
import { createBrowserClient } from '@supabase/ssr'
import type { Database } from '@/types/database'

// シングルトンパターン（React 18 の StrictMode 対策）
let client: ReturnType<typeof createBrowserClient<Database>> | undefined

export function createClient() {
  if (client) return client
  client = createBrowserClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
  return client
}
```

### 3-2. サーバー用（`src/lib/supabase/server.ts`）

```typescript
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'
import type { Database } from '@/types/database'

export async function createClient() {
  const cookieStore = await cookies()

  return createServerClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll()
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            )
          } catch {
            // Server Componentから呼ばれた場合は無視（読み取り専用）
          }
        },
      },
    }
  )
}
```

### 3-3. ミドルウェア用（`src/lib/supabase/middleware.ts`）

```typescript
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import type { Database } from '@/types/database'

export async function createMiddlewareClient(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })

  const supabase = createServerClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
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

  return { supabase, supabaseResponse }
}
```

---

## 4. ミドルウェア（ルートガード）

```typescript
// src/middleware.ts
import { NextRequest, NextResponse } from 'next/server'
import { createMiddlewareClient } from '@/lib/supabase/middleware'

// 認証不要のパス
const PUBLIC_PATHS = [
  '/auth/login',
  '/auth/signup',
  '/auth/callback',
  '/auth/error',
  '/',           // ランディングページ（必要に応じて除外）
]

export async function middleware(request: NextRequest) {
  const { supabase, supabaseResponse }
