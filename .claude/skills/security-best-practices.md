---
name: security-best-practices
description: >-
  Next.js/Supabase/TypeScriptプロジェクトにおけるセキュリティのベストプラクティス。
  認証・認可、レート制限、PII暗号化、監査ログ、インシデント対応、シークレット管理を網羅した包括的なセキュリティガイド。
category: security
sourceSkillIds:
  - d1d927c6
  - b5f82bc0
  - 550a948c
  - 75f78551
  - 2e1f3893
  - df5813f3
  - 0f81e61b
  - dba5acfd
generatedAt: '2026-05-11'
---

# セキュリティ ベストプラクティス

Next.js / Supabase / TypeScript プロジェクト全体に適用される、セキュリティ設計・実装・運用の標準ガイド。
**新機能を実装するとき・レビューするとき・インシデントが起きたとき**、このSkillを起点にする。

---

## 目次

1. [ミドルウェアと HTTP セキュリティヘッダー](#1-ミドルウェアと-http-セキュリティヘッダー)
2. [認証・認可チェックリスト](#2-認証認可チェックリスト)
3. [レート制限](#3-レート制限)
4. [PII 暗号化（AES-256-GCM）](#4-pii-暗号化aes-256-gcm)
5. [監査ログ](#5-監査ログ)
6. [シークレット管理とローテーション](#6-シークレット管理とローテーション)
7. [セキュリティレビュー手順](#7-セキュリティレビュー手順)
8. [インシデント対応プレイブック](#8-インシデント対応プレイブック)

---

## 1. ミドルウェアと HTTP セキュリティヘッダー

### 標準ミドルウェア適用順序

```typescript
// lib/security-middleware.ts
import helmet from 'helmet';
import cors from 'cors';

export function applySecurityMiddleware(app: Express) {
  // 1. helmet — CSP / HSTS / X-Frame-Options / X-Content-Type-Options
  app.use(helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        scriptSrc: ["'self'", "'strict-dynamic'"],
        styleSrc: ["'self'", "'unsafe-inline'"],   // 必要最小限に絞ること
        imgSrc: ["'self'", "data:", "https:"],
        connectSrc: ["'self'", process.env.NEXT_PUBLIC_SUPABASE_URL!],
        frameSrc: ["'none'"],
      },
    },
    hsts: { maxAge: 31536000, includeSubDomains: true, preload: true },
  }));

  // 2. CORS — 本番環境は許可オリジンを明示的に絞る
  app.use(cors({
    origin: process.env.NODE_ENV === 'production'
      ? [process.env.APP_URL!]           // TODO: 追加オリジンが必要な場合はここに列挙
      : true,
    credentials: true,
  }));

  // 3. trust proxy — Vercel / Railway の X-Forwarded-For を有効化
  app.set('trust proxy', 1);
}
```

### Next.js の場合（`middleware.ts`）

```typescript
// middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const response = NextResponse.next();

  // セキュリティヘッダーを追加
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  response.headers.set(
    'Permissions-Policy',
    'camera=(), microphone=(), geolocation=()'
  );

  return response;
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
```

---

## 2. 認証・認可チェックリスト

新しいAPI/ページを実装する際、以下を必ず確認する。

### tRPC の場合

```typescript
// ✅ protectedProcedure — 認証済みユーザーのデータアクセス
export const getMyItems = protectedProcedure
  .query(async ({ ctx }) => {
    return db.item.findMany({
      where: { userId: ctx.user.id },  // ← ctx.user.id で必ずフィルタ
    });
  });

// ✅ adminProcedure — 管理者専用操作
export const deleteUser = adminProcedure
  .input(z.object({ targetUserId: z.string() }))
  .mutation(async ({ ctx, input }) => {
    // ctx.user.role === 'admin' はミドルウェア層で保証済み
  });

// ⚠️ publicProcedure — 認証不要だが公開範囲を最小限に
export const getPublicStats = publicProcedure
  .query(async () => {
    return { total: await db.item.count() }; // 個人情報を含まない値のみ
  });
```

### チェックリスト

```
認証・認可
- [ ] 全 protectedProcedure で ctx.user.id によるデータアクセス制限があるか
- [ ] publicProcedure が不要なデータを公開していないか
- [ ] adminProcedure が適切に使われているか
- [ ] セッション有効期限が適切か（推奨: 30日以内）
- [ ] Cookie 設定: httpOnly: true, sameSite: "lax", secure: true（本番）

Supabase RLS
- [ ] すべてのテーブルで RLS が有効か（auth.uid() = user_id パターン）
- [ ] Service Role Key をクライアントサイドで使用していないか
- [ ] anon キーの権限が最小権限原則を満たしているか
```

### Supabase RLS ポリシーのひな形

```sql
-- users テーブルの基本パターン
ALTER TABLE items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users can read own items"
  ON items FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "users can insert own items"
  ON items FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- 管理者は全件参照可（service role は RLS をバイパスするため、
-- アプリ層でも role チェックを行うこと）
CREATE POLICY "admins can read all items"
  ON items FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE profiles.id = auth.uid()
        AND profiles.role = 'admin'
    )
  );
```

---

## 3. レート制限

### 推奨制限値

| エンドポイント種別 | 推奨制限 | 理由 |
|---|---|---|
| 公開 POST API（フォーム投稿等） | 10 req/min/IP | スパム・DoS 防止 |
| メール送
