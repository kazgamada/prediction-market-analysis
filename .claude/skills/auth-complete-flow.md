---
name: auth-complete-flow
description: >-
  Next.js (App Router) / Supabase / TypeScript プロジェクトにおける認証フロー全般
  （OAuth・メール確認・マジックリンク・パスワードリセット・NextAuth v5 カスタムエラー・セッション検証・HTTPS本番バグ）
  の実装・修復・監査・デバッグを行う包括的スキル。
  認証追加・セッション不具合・権限チェック漏れ・HTTPS本番バグ・環境変数確認・OAuthコールバック失敗が必要なときに起動する。
category: auth
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
---

# auth-complete-flow

Next.js App Router + Supabase + TypeScript における認証フロー全般を実装・修復・監査する包括的スキル。

## 🗺️ 認証方式マップ

| 方式 | 主なユースケース | トリガーワード |
|------|----------------|--------------|
| **Supabase OAuth** | Google / GitHub ソーシャルログイン | "OAuthを追加" "Googleログイン" |
| **Magic Link** | パスワードレスメール認証 | "マジックリンク" "メールでログイン" |
| **Email OTP / Token Hash** | メール確認・パスワードリセット | "メール確認" "パスワードリセット" |
| **NextAuth v5 Credentials** | メール+パスワード (DB照合) | "ログインフォーム" "カスタム認証" |
| **NextAuth v5 OAuth** | 外部IdP + NextAuth セッション | "NextAuth Google" |
| **JWT セッション検証** | SSRでのセッション確認 | "セッションが保持されない" "未認証状態" |

---

## 📁 必須ファイル構成

```
src/
├── app/
│   ├── auth/
│   │   ├── callback/route.ts          # Supabase OAuth/Magic Link コールバック
│   │   ├── confirm/route.ts           # OTP token-hash 確認
│   │   └── error/page.tsx             # 認証エラー表示
│   ├── (auth)/
│   │   ├── login/page.tsx
│   │   └── signup/page.tsx
│   └── api/auth/[...nextauth]/route.ts # NextAuth v5 (使用時)
├── lib/
│   ├── supabase/
│   │   ├── server.ts                  # createServerClient (cookies())
│   │   ├── client.ts                  # createBrowserClient
│   │   └── middleware.ts              # createServerClient (request/response)
│   ├── auth.ts                        # NextAuth v5 config (使用時)
│   └── session.ts                     # verifySession / getSession ヘルパー
├── middleware.ts                       # セッションリフレッシュ + ルート保護
└── types/
    └── auth.ts                        # 認証関連型定義
```

---

## 🔧 実装パターン集

### 1. Supabase クライアント 3種セットアップ

```typescript
// lib/supabase/server.ts
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'
import type { Database } from '@/types/database'

export function createClient() {
  const cookieStore = cookies()
  return createServerClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return cookieStore.getAll() },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            )
          } catch {} // Server Component では無視
        },
      },
    }
  )
}
```

```typescript
// lib/supabase/client.ts
import { createBrowserClient } from '@supabase/ssr'
import type { Database } from '@/types/database'

export function createClient() {
  return createBrowserClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}
```

```typescript
// lib/supabase/middleware.ts
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function updateSession(request: NextRequest) {
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
  // セッションリフレッシュ（必須）
  const { data: { user } } = await supabase.auth.getUser()

  // ルート保護
  const isProtected = request.nextUrl.pathname.startsWith('/dashboard')
  if (!user && isProtected) {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  return supabaseResponse
}
```

---

### 2. OAuth フロー

```typescript
// app/(auth)/login/page.tsx — OAuth ボタン
'use client'
import { createClient } from '@/lib/supabase/client'

export default function LoginPage() {
  const supabase = createClient()

  const handleOAuth = async (provider: 'google' | 'github') => {
    await supabase.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: `${location.origin}/auth/callback`,
        scopes: provider === 'google' ? 'openid email profile' : undefined,
      },
    })
  }

  return (
    <button onClick={() => handleOAuth('google')}>
      Google でログイン
    </button>
  )
}
```

```typescript
// app/auth/callback/route.ts
import { createClient } from '@/lib/supabase/server'
import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')
  const next = searchParams.get('next') ?? '/dashboard'

  if (code) {
    const supabase = createClient()
    const { error } = await supabase.auth.exchangeCodeForSession(code)
    if (!error) {
      // ✅ HTTPS本番対応: origin をそのまま使う（hardcode しない）
      return NextResponse.redirect(`${origin}${next}`)
    }
  }

  return NextResponse.redirect(`${origin}/auth/error?error=callback_failed`)
}
```

---

### 3. Email
