---
name: auth-complete-flow
description: >-
  Next.js/Supabase/TypeScriptプロジェクトにおける認証フロー（OAuth・メール・マジックリンク・パスワードリセット）の実装・修復・監査・デバッグを行う包括的スキル。認証追加・セッション不具合・権限チェック漏れ・環境変数確認が必要なときに起動する。
category: auth
sourceSkillIds:
  - '906407e9'
  - d718c6c5
  - '43560110'
  - 7f195b18
  - 5906a766
  - 7c03fba4
  - 5597d0ff
  - d0840991
  - bcb9645b
  - 3c592d1d
  - 65b4cfb1
  - a2614101
  - 6cb76b9b
  - 0f60149e
  - ce004062
  - 74d839c6
  - 3d525e31
  - bbe9913d
  - c1afe582
  - 631cc480
  - 7434c525
  - b013114c
  - 48d14926
  - 1e07217a
  - 2d0f80c2
  - 0fee0014
  - e2309e2d
  - d7fe2e18
  - eace4dd7
  - 39a955fa
  - '28651465'
  - 9c8cafea
  - 9ace2330
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
  - b80db551
  - 8f170407
  - d5df728f
  - e4e7c55a
  - e4f99eac
  - 949da0ce
  - 4332fd57
  - 25376c0a
  - ff8f258a
  - fa1bba76
  - c6d21246
  - 71a155ef
  - eb5ed6c2
  - df9e6eac
  - 6ad27777
  - 886b4e87
  - d5a86c2b
  - 42b870e9
  - 5f4a44af
  - 692e843b
  - e1bd946c
  - a23cda31
  - 2ecdd695
  - 374faec4
  - 8b5881ba
  - b4db4a06
  - 7a6209ea
  - 6dd2891e
  - 10e5b740
  - '89408744'
  - b93def46
  - 02e6f9d3
  - d50886b7
  - 1d615646
  - 69eee762
  - 7aa48f05
  - 5216f037
  - 3fbb2eee
  - 91e27bd5
  - 79c298d8
  - b7cca168
  - 655ec61e
  - 1b3424e1
  - 463e51f9
  - 4f3f9e40
  - d46525eb
  - 5340bf4c
  - ca67e5e7
  - 8a752d94
  - 15f4d701
  - 2b626550
  - bbd46a26
  - 9847ce03
  - be8b2fb2
  - 24b61d7c
  - 46e3a279
generatedAt: '2026-05-11'
---

# auth-complete-flow

## このSkillが対応するシナリオ

- 新規プロジェクトへの認証フロー追加（OAuth / メール / マジックリンク / パスワードリセット）
- セッションが維持されない・ログアウトできない・リダイレクトループが発生する
- RLSポリシーで権限チェックが漏れている
- 環境変数の設定ミスによる認証エラー
- 認証フロー全体のセキュリティ監査

---

## 1. 必須環境変数チェックリスト

認証関連の不具合の約60%は環境変数の設定ミスに起因する。最初に確認する。

```bash
# .env.local（Next.js開発環境）
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...

# サーバーサイドのみ（クライアントに露出させない）
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# OAuth使用時（Supabaseダッシュボードにも同じ値を設定）
# Google: Authentication > Providers > Google
# GitHub: Authentication > Providers > GitHub
```

**確認コマンド**:
```bash
# 環境変数が正しくロードされているか確認
node -e "require('dotenv').config({path:'.env.local'}); console.log(process.env.NEXT_PUBLIC_SUPABASE_URL)"
```

---

## 2. Supabaseクライアントの正しい初期化パターン

### 2-1. ブラウザ用クライアント（Client Components）

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

### 2-2. サーバー用クライアント（Server Components / Route Handlers）

```typescript
// lib/supabase/server.ts
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
            // Server Componentからの呼び出しでは書き込み不可（無視して良い）
          }
        },
      },
    }
  )
}
```

### 2-3. Middleware用クライアント

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

  // セッションのリフレッシュ（必須）
  const { data: { user } } = await supabase.auth.getUser()

  // 未認証ユーザーの保護ルートへのアクセスをリダイレクト
  const protectedPaths = ['/dashboard', '/settings', '/profile']
  const isProtected = protectedPaths.some(path =>
    request.nextUrl.pathname.startsWith(path)
  )

  if (!user && isProtected) {
    const redirectUrl = request.nextUrl.clone()
    redirectUrl.pathname = '/login'
    redirectUrl.searchParams.set('redirectTo', request.nextUrl.pathname)
    return NextResponse.redirect(redirectUrl)
  }

  return supabaseResponse
}
```

```typescript
// middleware.ts（プロジェクトルート）
import { type NextRequest } from 'next/server'
import { updateSession } from '@/lib/supabase/middleware'

export async function middleware(request: NextRequest) {
  return await updateSession(request)
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
}
```

---

## 3. 認証フローの実装

### 3-1. メール＋パスワード認証

```typescript
// app/auth/actions.ts
'use server'

import { revalidatePath } from 'next/cache'
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

export async function signUp(formData: FormData) {
  const supabase = await createClient()

  const { error } = await supabase.auth.signUp({
    email: formData.get('email') as string,
    password: formData.get('password') as string,
    options: {
      emailRedirectTo: `${process.env.NEXT_PUBLIC_SITE_URL}/auth/callback`,
    },
  })

  if (error) {
    return { error: error.message }
  }

  return { message: '確認メールを送信しました。メールをご確認ください。' }
}

export async function signIn(formData: FormData) {
  const supabase = await createClient()

  const { error } = await supabase.auth.signInWithPassword({
    email: formData.get('email') as string,
    password: formData.get('password') as string,
  })

  if (error) {
    return { error: error.message }
  }

  revalidatePath('/', 'layout')
  redirect('/dashboard')
}

export async function signOut() {
  const supabase = await createClient()
  await supabase.auth.signOut()
  revalidat
