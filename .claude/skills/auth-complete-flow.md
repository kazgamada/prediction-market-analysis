---
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
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-10T19:11:30+00:00'
adoptedFromArchive:
  - archive/prediction-market-analysis/.claude/skills/auth-complete-flow.md
  - archive/aegis-market-os/.claude/skills/account-auth-ops.md
  - archive/aegis-market-os/.claude/skills/architecture-overview.md
  - archive/aegis-market-os/.claude/skills/auth-email-password.md
  - archive/aegis-market-os/.claude/skills/auth-tokens-mailer.md
  - archive/aegis-market-os/.claude/skills/dev-server-hook.md
  - archive/aegis-market-os/.claude/skills/trpc-patterns.md
  - archive/ai-company/.claude/skills/auth-email-flow/SKILL.md
  - archive/ai-company/.claude/skills/nextauth-custom-error/SKILL.md
  - archive/ai-company/.claude/skills/resend-diagnostics/SKILL.md
---
```yaml
---
name: auth-complete-flow
description: >-
  Next.js/Supabase/TypeScript プロジェクトにおける認証フロー（OAuth・メール/パスワード・マジックリンク・パスワードリセット・メール変更）の
  実装・修復・監査・デバッグを行う包括的スキル。認証追加・セッション不具合・権限チェック漏れ・環境変数確認・
  メール未着・カスタムエラー表示が必要なときに起動する。
category: auth
---
```

# auth-complete-flow

## いつ起動するか

| トリガー | 例 |
|---|---|
| 新規認証追加 | 「Google ログインを追加したい」「マジックリンクを実装して」 |
| セッション不具合 | 「ログイン後に 401 が返る」「ページ遷移でセッションが切れる」 |
| OAuth エラー | 「Google ログインに失敗しました」だけ出る |
| メール未着 | 「確認メールが届かない」「リセットリンクが来ない」 |
| 権限漏れ | 「未ログインでも API が叩ける」「管理者専用ページに入れた」 |
| カスタムエラー | 「メール未確認・アカウントロックを別メッセージで出したい」 |
| 環境変数疑い | 「本番だけ認証が壊れる」 |

---

## 1. アーキテクチャ選択マップ

```
プロジェクトに Supabase がある？
  YES → Supabase Auth（§2）を使う
  NO  → カスタム Auth（§3）を使う
         ├─ Next.js がある？ → NextAuth v5 Credentials（§3-B）
         └─ Express/tRPC？  → jose + Cookie セッション（§3-C）
```

> **原則**: 認証レイヤーを混在させない。Supabase Auth と NextAuth を同一プロジェクトで同時使用しない。

---

## 2. Supabase Auth パターン

### 2-A. 必須環境変数チェックリスト

```bash
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...          # サーバー専用・フロントに漏らさない
NEXT_PUBLIC_SITE_URL=https://example.com  # OAuth コールバック・メールリンク用
```

> `NEXT_PUBLIC_SITE_URL` が間違うと OAuth コールバック・メールリンクが全滅する。  
> Vercel なら `NEXT_PUBLIC_VERCEL_URL` を fallback で使えるが本番は明示指定を推奨。

### 2-B. クライアント初期化（App Router）

```typescript
// lib/supabase/client.ts  ← ブラウザ用
import { createBrowserClient } from '@supabase/ssr';
export const createClient = () =>
  createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );

// lib/supabase/server.ts  ← Server Component / Route Handler 用
import { createServerClient } from '@supabase/ssr';
import { cookies } from 'next/headers';
export const createClient = () => {
  const cookieStore = cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => cookieStore.getAll(),
        setAll: (pairs) =>
          pairs.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)),
      },
    },
  );
};
```

> **禁止**: `createRouteHandlerClient` など旧 API（`@supabase/auth-helpers-nextjs`）は使わない。  
> `@supabase/ssr` の `createServerClient` / `createBrowserClient` で統一。

### 2-C. Middleware（セッション自動更新）

```typescript
// middleware.ts
import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (pairs) => {
          pairs.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          pairs.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options));
        },
      },
    },
  );

  // セッションを必ずリフレッシュ（トークン更新）
  const { data: { user } } = await supabase.auth.getUser();

  // 保護ルートのガード例
  if (!user && request.nextUrl.pathname.startsWith('/dashboard')) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  return response;
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
```

### 2-D. OAuth（Google / GitHub など）

```typescript
// app/auth/login/route.ts
import { createClient } from '@/lib/supabase/server';
import { redirect } from 'next/navigation';

export async function GET() {
  const supabase = createClient();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: `${process.env.NEXT_PUBLIC_SITE_URL}/auth/callback`,
      // scopes: 'openid email profile',  // 必要なら追加
    },
  });
  if (error || !data.url) return redirect('/login?error=oauth_failed');
  redirect(data.url);
}

// app/auth/callback/route.ts
import { createClient } from '@/lib/supabase/server';
import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get('code');
  if (!code) return NextResponse.redirect(new URL('/login?error=no_code', request.url));

  const supabase = createClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) return NextResponse.redirect(new URL('/login?error=exchange_failed', request.url));

  return NextResponse.redirect(new URL('/dashboard', request.url));
}
```

#### Google OAuth state cookie 消失バグ（頻出地雷）

**症状**: "Google ログインに失敗しました" のみ、
