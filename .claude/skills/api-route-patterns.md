---
category: api-router
sourceSkillIds:
  - 3b8b6f3f
  - 054208d0
  - fd774bbd
  - '17e52886'
  - fe4fd046
  - '79047663'
  - eb5b5790
  - bb56451a
  - 8c491bd3
  - 4c1e226f
  - 8c38bbfc
  - e79eb2df
  - e3dcdb7e
  - 630f0c79
  - ce339f24
  - a6ff5932
generatedAt: '2026-05-11'
---
```yaml
---
name: api-route-patterns
description: >-
  Next.js App Router APIルートの実装パターン集。認証ガード・Zodバリデーション・
  エラーハンドリング・レスポンス型の標準化を一括で提供する。新規APIルート作成・
  既存ルートのリファクタ・保護レベルの設定変更時に参照する。
  トリガー：「API追加」「ルート作成」「認証ガード」「バリデーション」「エラーハンドリング」
category: api-router
---
```

# API Route Patterns — Next.js App Router

## 概要

Next.js App Router（`app/api/**`）における**認証ガード・Zodバリデーション・エラーハンドリング・レスポンス型の標準化**を一元管理するパターン集。

新規ルート作成時は必ず**保護レベル分類フローチャート**で位置づけを確認してから実装する。

---

## 1. 保護レベル分類フローチャート

```
新しい API ルート
   │
   ├─ Webhook（Stripe / 外部サービスから）?
   │     → プロバイダ署名検証を最初に配置（セッション不要）
   │
   ├─ Cron / スケジューラから呼ばれる?
   │     → CRON_SECRET ヘッダ検証のみ
   │
   ├─ 管理者専用（admin パネル等）?
   │     → requireAdmin() ガード
   │
   ├─ 認証済みユーザー全員が使える?
   │     → requireAuth() ガード
   │
   ├─ テナント/プラン制限が必要?
   │     → requireAuth() + enforcePlanLimit()
   │
   └─ パブリック（認証不要）?
         → ガードなし（レート制限は別途検討）
```

> **迷ったら「認証済みユーザー全員」を選ぶ。後から緩めるより絞める方が安全。**

---

## 2. 標準ユーティリティ (`lib/api-helpers.ts`)

プロジェクトに合わせて実装・配置する共通ヘルパー群。

```typescript
// lib/api-helpers.ts
import { NextRequest, NextResponse } from "next/server";
import { z, ZodSchema } from "zod";

/** 成功レスポンス */
export function ok<T>(data: T, status = 200) {
  return NextResponse.json({ success: true, data }, { status });
}

/** エラーレスポンス */
export function err(message: string, status = 400, details?: unknown) {
  return NextResponse.json(
    { success: false, error: message, ...(details ? { details } : {}) },
    { status }
  );
}

/** Zod バリデーション — 失敗時は 422 を返す */
export function validateBody<T>(
  schema: ZodSchema<T>,
  body: unknown
): { data: T; error: null } | { data: null; error: NextResponse } {
  const result = schema.safeParse(body);
  if (!result.success) {
    return {
      data: null,
      error: err("Validation failed", 422, result.error.flatten()),
    };
  }
  return { data: result.data, error: null };
}

/** クエリパラメータのバリデーション */
export function validateQuery<T>(
  schema: ZodSchema<T>,
  searchParams: URLSearchParams
): { data: T; error: null } | { data: null; error: NextResponse } {
  const raw = Object.fromEntries(searchParams.entries());
  return validateBody(schema, raw);
}

/** 統一エラーハンドラ */
export function handleError(error: unknown): NextResponse {
  console.error("[API Error]", error);
  if (error instanceof z.ZodError) {
    return err("Validation error", 422, error.flatten());
  }
  if (error instanceof Error) {
    // 本番環境では内部メッセージを隠す
    const message =
      process.env.NODE_ENV === "production"
        ? "Internal server error"
        : error.message;
    return err(message, 500);
  }
  return err("Internal server error", 500);
}
```

---

## 3. 認証ガード (`lib/api-guard.ts`)

```typescript
// lib/api-guard.ts
import { auth } from "@/lib/auth"; // NextAuth / Clerk / 独自認証に差し替え
import { err } from "./api-helpers";
import { NextRequest, NextResponse } from "next/server";

type Session = { user: { id: string; role: string; tenantId?: string } };

/** 認証済みユーザーが必要なルートに使う */
export async function requireAuth(
  req: NextRequest,
  handler: (req: NextRequest, session: Session) => Promise<NextResponse>
): Promise<NextResponse> {
  const session = await auth();
  if (!session?.user) return err("Unauthorized", 401);
  return handler(req, session as Session);
}

/** 管理者専用ルート */
export async function requireAdmin(
  req: NextRequest,
  handler: (req: NextRequest, session: Session) => Promise<NextResponse>
): Promise<NextResponse> {
  const session = await auth();
  if (!session?.user) return err("Unauthorized", 401);
  if (session.user.role !== "admin") return err("Forbidden", 403);
  return handler(req, session as Session);
}

/** Cron ジョブ（CRON_SECRET ヘッダ検証） */
export function requireCron(
  handler: () => Promise<NextResponse>
): () => Promise<NextResponse> {
  return async () => {
    const secret = process.env.CRON_SECRET;
    // Note: 実際のリクエストオブジェクトが必要な場合は引数で受け取る
    if (!secret) return err("CRON_SECRET not configured", 500);
    // ヘッダ検証は呼び出し元で行う（Vercel Cron は Authorization ヘッダを付与）
    return handler();
  };
}
```

---

## 4. 実装パターン集

### 4-A. パブリック GET（クエリバリデーション付き）

```typescript
// app/api/posts/route.ts
import { NextRequest } from "next/server";
import { z } from "zod";
import { ok, err, validateQuery, handleError } from "@/lib/api-helpers";

const QuerySchema = z.object({
  page: z.coerce.number().int().positive().default(1),
  limit: z.coerce.number().int().min(1).max(100).default(20),
  search: z.string().optional(),
});

export async function GET(req: NextRequest) {
  try {
    const { data: query, error } = validateQuery(
      QuerySchema,
      req.nextUrl.searchParams
    );
    if (error) return error;

    const posts = await db.post.findMany({
      where: query.search
        ? { title: { contains: query.search, mode: "insensitive" } }
        : undefined,
      skip: (query.page - 1) * query
