---
name: security-best-practices
description: >-
  Next.js/Supabase/TypeScriptプロジェクトにおけるセキュリティのベストプラクティス。認証・認可、レート制限、暗号化、監査ログ、インシデント対応、シークレット管理を網羅した包括的なセキュリティガイド。
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
  - b5d28376
  - f789f626
  - 871a9182
  - 49682a71
  - e2242131
  - 46c447b2
  - 58257c07
generatedAt: '2026-05-08'
---

# Security Best Practices

Next.js / Supabase / TypeScript プロジェクト向けの包括的なセキュリティガイド。

---

## 1. 認証・認可（Authentication & Authorization）

### 1.1 Supabase Auth の基本設定

すべての保護リソースへのアクセスはサーバーサイドで認証を検証する。クライアント側の認証状態のみに依存しない。

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

// Server Action / Route Handler での認証確認
export async function requireAuth() {
  const supabase = createClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error || !user) {
    throw new Error('Unauthorized')
  }
  return user
}
```

### 1.2 ロールベースアクセス制御（RBAC）

```typescript
// lib/auth/rbac.ts
type Role = 'admin' | 'member' | 'viewer'

const ROLE_HIERARCHY: Record<Role, number> = {
  admin: 3,
  member: 2,
  viewer: 1,
}

export async function requireRole(minimumRole: Role) {
  const user = await requireAuth()
  const supabase = createClient()

  const { data: profile } = await supabase
    .from('profiles')
    .select('role')
    .eq('id', user.id)
    .single()

  const userRole = profile?.role as Role
  if (!userRole || ROLE_HIERARCHY[userRole] < ROLE_HIERARCHY[minimumRole]) {
    throw new Error(`Forbidden: requires ${minimumRole} role`)
  }

  return { user, role: userRole }
}

// 使用例
export async function adminAction() {
  const { user } = await requireRole('admin')
  // admin専用処理
}
```

### 1.3 Middleware による保護

```typescript
// middleware.ts
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

const PROTECTED_PATHS = ['/dashboard', '/admin', '/api/protected']
const ADMIN_PATHS = ['/admin']

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // 保護対象パスの確認
  const isProtected = PROTECTED_PATHS.some(p => pathname.startsWith(p))
  if (!isProtected) return NextResponse.next()

  const response = NextResponse.next()
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { /* cookie handlers */ } }
  )

  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    const loginUrl = new URL('/login', request.url)
    loginUrl.searchParams.set('redirectTo', pathname)
    return NextResponse.redirect(loginUrl)
  }

  // 管理者パスの追加チェック
  if (ADMIN_PATHS.some(p => pathname.startsWith(p))) {
    const { data: profile } = await supabase
      .from('profiles')
      .select('role')
      .eq('id', user.id)
      .single()

    if (profile?.role !== 'admin') {
      return NextResponse.redirect(new URL('/403', request.url))
    }
  }

  return response
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
```

---

## 2. Row Level Security（RLS）

Supabase のすべてのテーブルで RLS を有効化する。「デフォルト拒否」原則を徹底する。

```sql
-- すべてのテーブルで RLS を有効化
ALTER TABLE public.items ENABLE ROW LEVEL SECURITY;

-- ❌ 危険: 全件アクセス許可
-- CREATE POLICY "allow_all" ON items FOR ALL USING (true);

-- ✅ 安全: 所有者のみアクセス
CREATE POLICY "owner_select" ON public.items
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "owner_insert" ON public.items
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "owner_update" ON public.items
  FOR UPDATE USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "owner_delete" ON public.items
  FOR DELETE USING (auth.uid() = user_id);

-- チームベースのアクセス制御
CREATE POLICY "team_member_select" ON public.team_items
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM team_members
      WHERE team_id = team_items.team_id
        AND user_id = auth.uid()
        AND status = 'active'
    )
  );

-- 管理者は全件参照可能
CREATE POLICY "admin_full_access" ON public.items
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND role = 'admin'
    )
  );
```

### RLS チェックリスト

- [ ] 全テーブルで `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` を実行
- [ ] `service_role` キーはサーバーサイドのみ使用（クライアントに露出しない）
- [ ] `anon` キーで意図しないデータが取得できないか確認
- [ ] INSERT の `WITH CHECK` と UPDATE の `USING` / `WITH CHECK` を両方定義

---

## 3. レート制限（Rate Limiting）

### 3.1 In-Memory レート制限（小規模向け）

```typescript
// lib/security/rate-limit.ts
interface RateLimitEntry {
  count: number
  resetAt: number
}

const store = new Map<string, RateLimitEntry>()

interface RateLimitOptions {
  maxRequests: number
  windowMs: number
  identifier?: string
}

export function rateLimit(options: RateLimitOptions) {
  return {
    check: (key: string): { success: boolean; remaining: number; resetAt: number } => {
      const now = Date.now()
      const entry = store.get(key)

      if
