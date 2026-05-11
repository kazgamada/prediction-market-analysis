---
category: security
sourceSkillIds:
  - d4182b48
  - f74e42a4
  - '60724619'
  - 8dccdfd5
  - 86844c6c
  - c2e259b3
  - c0fe524b
  - 72f8c951
  - 842f585e
  - 1a51c1ed
  - 4c9135cd
  - bcd96325
  - 988462cc
  - cda747b6
  - '785e3460'
  - 056c5810
  - 63ca3004
  - ab17e3f5
  - b5d28376
  - f789f626
  - 871a9182
  - 49682a71
  - e2242131
  - 46c447b2
  - 58257c07
generatedAt: '2026-05-11'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-10T19:11:30+00:00'
adoptedFromArchive:
  - archive/prediction-market-analysis/.claude/skills/security-best-practices.md
  - archive/aegis-market-os/.claude/skills/security-rate-limit.md
  - archive/AISaaS/.claude/skills/add-audit-log.md
  - archive/AISaaS/.claude/skills/add-encrypted-field.md
  - archive/AISaaS/.claude/skills/add-rate-limit.md
  - archive/AISaaS/.claude/skills/incident-response.md
  - archive/AISaaS/.claude/skills/rotate-secret.md
  - archive/task-matrix/.claude/skills/security-review.md
---
```yaml
---
name: security-best-practices
description: >-
  Next.js/Supabase/TypeScriptプロジェクトにおけるセキュリティのベストプラクティス。
  認証・認可、レート制限、AES-256-GCM暗号化、監査ログ、インシデント対応、シークレット管理、
  セキュリティレビューチェックリストを網羅した包括的なセキュリティガイド。
category: security
---
```

# Security Best Practices

Next.js / Supabase / TypeScript プロジェクト向けの包括的セキュリティガイド。

> **このSkillの使い方**
> - 新機能実装時 → 各セクションのチェックリストを確認
> - インシデント発生時 → §6「インシデント対応」を開いて上から実行
> - コードレビュー時 → §7「セキュリティレビューチェックリスト」を活用
> - PII追加時 → §3「暗号化」を参照
> - シークレット変更時 → §5「シークレット管理」を必ず確認

---

## §1 認証・認可

### 1.1 Supabase Auth の基本設定

```typescript
// lib/supabase/server.ts
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export function createClient() {
  const cookieStore = cookies()
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        get(name: string) { return cookieStore.get(name)?.value },
        set(name: string, value: string, options: CookieOptions) {
          cookieStore.set({ name, value, ...options })
        },
        remove(name: string, options: CookieOptions) {
          cookieStore.set({ name, value: '', ...options })
        },
      },
    }
  )
}
```

### 1.2 Cookie セキュリティ設定

```typescript
// Cookie は常に以下の設定を使うこと
const SECURE_COOKIE_OPTIONS = {
  httpOnly: true,          // XSS からの保護
  sameSite: 'lax' as const, // CSRF 保護（OAuth を壊さない）
  secure: process.env.NODE_ENV === 'production', // 本番は HTTPS のみ
  path: '/',
  maxAge: 60 * 60 * 24 * 30, // 30日（要件に応じて調整）
}
```

### 1.3 tRPC / API ルートでの認可パターン

```typescript
// server/trpc/middleware.ts

/** 認証済みユーザー必須 */
export const protectedProcedure = t.procedure.use(async ({ ctx, next }) => {
  if (!ctx.user) throw new TRPCError({ code: 'UNAUTHORIZED' })
  return next({ ctx: { ...ctx, user: ctx.user } })
})

/** 管理者専用 */
export const adminProcedure = protectedProcedure.use(async ({ ctx, next }) => {
  if (ctx.user.role !== 'admin') throw new TRPCError({ code: 'FORBIDDEN' })
  return next()
})

// ✅ 正しい例: ctx.user.id でスコープを絞る
export const getUserPosts = protectedProcedure
  .query(async ({ ctx }) => {
    return db.posts.findMany({
      where: { userId: ctx.user.id }, // 自分のデータのみ
    })
  })

// ❌ 誤った例: 全ユーザーのデータを返す
export const getAllPosts = protectedProcedure
  .query(async () => {
    return db.posts.findMany() // IDOR 脆弱性
  })
```

### 1.4 Next.js Middleware での認証ガード

```typescript
// middleware.ts
import { createMiddlewareClient } from '@supabase/auth-helpers-nextjs'
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export async function middleware(req: NextRequest) {
  const res = NextResponse.next()
  const supabase = createMiddlewareClient({ req, res })
  const { data: { session } } = await supabase.auth.getSession()

  const isProtectedRoute = req.nextUrl.pathname.startsWith('/dashboard')
  if (isProtectedRoute && !session) {
    const redirectUrl = new URL('/login', req.url)
    redirectUrl.searchParams.set('redirectTo', req.nextUrl.pathname)
    return NextResponse.redirect(redirectUrl)
  }
  return res
}

export const config = {
  matcher: ['/dashboard/:path*', '/api/protected/:path*'],
}
```

---

## §2 レート制限

### 2.1 汎用 rateLimit ユーティリティ

```typescript
// lib/rate-limit.ts
import { LRUCache } from 'lru-cache'
import type { NextRequest } from 'next/server'

interface RateLimitOptions {
  /** 時間窓（ミリ秒）*/
  windowMs: number
  /** 上限リクエスト数 */
  max: number
  /** キーの生成関数（デフォルト: IP アドレス）*/
  keyGenerator?: (req: NextRequest) => string
}

const caches = new Map<string, LRUCache<string, number[]>>()

export function rateLimit(options: RateLimitOptions) {
  const { windowMs, max, keyGenerator } = options
  const cacheKey = `${windowMs}:${max}`

  if (!caches.has(cacheKey)) {
    caches.set(cacheKey, new LRUCache<string, number[]>({
      max: 10_000,
      ttl: windowMs,
    }))
  }
  const cache = caches.get(cacheKey)!

  return {
    check(req: NextRequest): { success: boolean; remaining: number; reset: number } {
      const key = keyGenerator?.(req) ??
        req.headers.get('x-forwarded-for')?.split(',')[0].trim() ??
        req.headers.get('x-real-ip') ??
        'unknown'

      const now = Date.now()
      const timestamps = (cache.get(key) ?? []).filter(t => now - t < windowMs)
      const success = timestamps.length < max

      if (success) {
        timestamps.push(now)
        cache.set(key, timestamps)
      }

      return {
        success,
        remaining: Math.max(0, max - timestamps.length),
        reset: Math.ceil((timestamps[0] ?? now) + windowMs),
      }
    },
  }
}

// レート制限違反レスポンス生成
export function rateLimitResponse(reset: number) {
  return new Response('Too Many Requests', {
    status: 429,
    headers: {
      'Retry-After': String(Math.ceil((reset - Date.now()) / 1000)),
      'X-RateLimit-Reset': String(reset),
    },
  })
}
```

### 2.2 用途別推奨設定

| エンドポイント | 推奨制限 | 理由
