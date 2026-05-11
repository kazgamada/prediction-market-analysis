---
name: security-best-practices
description: >-
  Next.js/Supabase/TypeScriptプロジェクトにおける包括的なセキュリティガイド。認証・認可、レート制限、CSRF保護、暗号化、監査ログ、インシデント対応、シークレット管理を網羅し、コードパターンと原則のバランスを取った実装指針を提供する。
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
---

# Security Best Practices

Next.js / Supabase / TypeScript プロジェクト向けセキュリティ実装ガイド。

---

## 1. 認証・認可

### 1-1. Supabase Auth の基本設定

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
        getAll: () => cookieStore.getAll(),
        setAll: (cookiesToSet) => {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          )
        },
      },
    }
  )
}
```

### 1-2. ミドルウェアによるセッション保護

```typescript
// middleware.ts
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

const PUBLIC_PATHS = ['/', '/auth/login', '/auth/signup', '/api/webhooks']

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (cookiesToSet) => {
          cookiesToSet.forEach(({ name, value, options }) => {
            request.cookies.set(name, value)
            response.cookies.set(name, value, options)
          })
        },
      },
    }
  )

  const { data: { user } } = await supabase.auth.getUser()
  const isPublic = PUBLIC_PATHS.some(p => request.nextUrl.pathname.startsWith(p))

  if (!user && !isPublic) {
    return NextResponse.redirect(new URL('/auth/login', request.url))
  }

  return response
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
```

### 1-3. ロールベースアクセス制御（RBAC）

```typescript
// lib/auth/rbac.ts
type Role = 'admin' | 'member' | 'viewer'

const ROLE_HIERARCHY: Record<Role, number> = {
  admin: 3,
  member: 2,
  viewer: 1,
}

export function hasRole(userRole: Role, requiredRole: Role): boolean {
  return ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[requiredRole]
}

// Server Action / API Route での使用例
export async function requireRole(requiredRole: Role) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) throw new Error('UNAUTHORIZED')

  const { data: profile } = await supabase
    .from('profiles')
    .select('role')
    .eq('id', user.id)
    .single()

  if (!profile || !hasRole(profile.role as Role, requiredRole)) {
    throw new Error('FORBIDDEN')
  }

  return user
}
```

### 1-4. Supabase RLS ポリシー

```sql
-- 自分のデータのみ読み取り可能
create policy "Users can read own data"
  on profiles for select
  using (auth.uid() = user_id);

-- 管理者のみ全件読み取り可能
create policy "Admins can read all"
  on profiles for select
  using (
    exists (
      select 1 from profiles
      where id = auth.uid() and role = 'admin'
    )
  );

-- サービスロールはRLSをバイパス（サーバーサイドのみで使用）
-- SUPABASE_SERVICE_ROLE_KEY は絶対にクライアントに渡さない
```

---

## 2. API セキュリティ

### 2-1. レート制限

```typescript
// lib/rate-limit.ts
import { Redis } from '@upstash/redis'
import { Ratelimit } from '@upstash/ratelimit'

const redis = new Redis({
  url: process.env.UPSTASH_REDIS_URL!,
  token: process.env.UPSTASH_REDIS_TOKEN!,
})

// 用途別にリミッターを分ける
export const rateLimiters = {
  api: new Ratelimit({
    redis,
    limiter: Ratelimit.slidingWindow(60, '1 m'),   // 60req/min
    prefix: 'rl:api',
  }),
  auth: new Ratelimit({
    redis,
    limiter: Ratelimit.slidingWindow(5, '15 m'),   // 5req/15min（ログイン試行）
    prefix: 'rl:auth',
  }),
  expensive: new Ratelimit({
    redis,
    limiter: Ratelimit.slidingWindow(10, '1 h'),   // 10req/hour（AI生成など）
    prefix: 'rl:expensive',
  }),
}

// API Route / Server Action での使用
export async function checkRateLimit(
  limiter: keyof typeof rateLimiters,
  identifier: string // user ID or IP
) {
  const { success, remaining, reset } = await rateLimiters[limiter].limit(identifier)

  if (!success) {
    throw Object.assign(new Error('RATE_LIMIT_EXCEEDED'), {
      remaining,
      resetAt: new Date(reset),
    })
  }

  return { remaining }
}
```

### 2-2. 入力バリデーション（Zod）

```typescript
// lib/validation/schemas.ts
import { z } from 'zod'

// 共通ルール
const safeString = z.string().trim().max(1000)
const safeText = z.string().trim().max(10000)
const safeId = z.string().uuid()

// エンティティごとのスキーマ定義例
export const CreatePostSchema = z.object({
  title: safeString.min(1).max(200),
  content: safeText,
  tags: z.array(safeString).max(10).optional(),
})

// API Route でのバリデーション
export async function POST(request: Request) {
  const body = await request.json()
  const result = CreatePostSchema.safeParse(body)

  if (!result.success) {
    return Response.json(
      { error: 'VALIDATION_ERROR', issues: result.error.issues },
      { status: 400 }
    )
  }

  // result.data は型安全かつサニタイズ済み
}
```

### 
