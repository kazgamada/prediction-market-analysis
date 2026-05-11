---
name: auth-complete-flow
description: >-
  Next.js (App Router) / Supabase / TypeScript
  プロジェクトにおける認証フロー全般（OAuth・メール確認・マジックリンク・パスワードリセット・NextAuth v5
  カスタムエラー）の実装・修復・監査・デバッグを行う包括的スキル。認証追加・セッション不具合・権限チェック漏れ・HTTPS本番バグ・環境変数確認が必要なときに起動する。
category: auth
sourceSkillIds:
  - 2f74dbd8
  - 1d57d2e4
  - 66bd76e5
  - fae179bc
  - 2012789c
  - ec487531
  - 785232c6
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
  - 1e5aa1a3
  - 07206c63
  - f1cba622
  - 9a8598b4
  - 30d6d26c
  - b1d03195
generatedAt: '2026-05-11'
---

# auth-complete-flow — 認証フロー完全実装スキル

## いつこのスキルを使うか

| トリガー | 例 |
|----------|----|
| 認証機能の新規追加 | OAuth / Magic Link / メール確認 / パスワードリセット を追加したい |
| セッション・リダイレクト不具合 | ログイン後に 404、無限リダイレクト、クッキーが消える |
| 権限チェック漏れ | middleware / layout で未認証ユーザーを通してしまう |
| 本番だけ壊れる | HTTPS 環境で `__Secure-` クッキーが読めない |
| 環境変数疑い | `.env.local` と Vercel 設定の不一致 |
| NextAuth カスタムエラー | `email-not-verified` / `account-locked` を UI に出したい |

---

## Part 1 — Supabase 認証フロー

### 1-1. Supabase クライアント 3 種の役割分担

```
lib/supabase/
  server.ts      # Server Components / Route Handlers / Server Actions 用
  client.ts      # Client Components 用（ブラウザ）
  middleware.ts  # Edge Middleware 専用（セッション更新）
```

#### `lib/supabase/server.ts`

```typescript
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import type { Database } from "@/types/database";

export function createClient() {
  const cookieStore = cookies();
  return createServerClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => cookieStore.getAll(),
        setAll: (cookiesToSet) => {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            );
          } catch {
            // Server Component から呼ばれた場合は書き込み不可 — 無視してよい
          }
        },
      },
    }
  );
}
```

#### `lib/supabase/client.ts`

```typescript
import { createBrowserClient } from "@supabase/ssr";
import type { Database } from "@/types/database";

export function createClient() {
  return createBrowserClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}
```

#### `middleware.ts`（プロジェクトルート）

```typescript
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (cookiesToSet) => {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  // ⚠️ 重要: getUser() を必ず呼ぶ（セッション更新のため）
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // 保護ルートへの未認証アクセスをリダイレクト
  const protectedPaths = ["/dashboard", "/settings", "/api/protected"];
  const isProtected = protectedPaths.some((p) =>
    request.nextUrl.pathname.startsWith(p)
  );

  if (isProtected && !user) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("redirectTo", request.nextUrl.pathname);
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
```

---

### 1-2. OTP / トークンハッシュ方式のメール認証

Supabase はメールリンクに `token_hash` を付与する。  
**`/auth/confirm` ルートでのみ処理し、他のページで OTP を直接検証しない。**

```typescript
// app/auth/confirm/route.ts
import { createClient } from "@/lib/supabase/server";
import { type EmailOtpType } from "@supabase/supabase-js";
import { type NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const token_hash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  const next = searchParams.get("next") ?? "/dashboard";

  if (token_hash && type) {
    const supabase = createClient();
    const { error } = await supabase.auth.verifyOtp({ type, token_hash });

    if (!error) {
      return NextResponse.redirect(new URL(next, request.url));
    }
  }

  // エラー時は dedicated エラーページへ
  return NextResponse.redirect(new URL("/auth/auth-code-error", request.url));
}
```

#### メール種別ごとのフロー

| type 値 | 用途 | 送信トリガー |
|---------|------|-------------|
| `signup` | メールアドレス確認 | `signUp()` |
| `recovery` | パスワードリセット | `resetPasswordForEmail()` |
| `magiclink` | Magic Link ログイン | `signInWithOtp({ email })` |
| `email_change` | メール変更確認 | `updateUser({ email })` |

#### Magic Link ログイン（クライアント側）

```typescript
const { error } = await supabase.auth.signInWithOtp({
  email,
  options: {
    emailRedirectTo: `${location.origin}/auth/confirm?next=/dashboard`,
  },
});
```

#### パスワードリセット

```typescript
// Step 1:
