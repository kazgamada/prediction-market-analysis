---
name: api-route-patterns
description: >-
  Next.js App Router の API ルート実装パターン集。認証・認可ガード、Zod バリデーション、エラーハンドリング、
  プラン制限、Webhook 署名検証、tRPC 型安全、バックグラウンドジョブ（Inngest）、AI プロバイダー抽象化まで網羅。 新規 API
  ルート追加・既存ルート修正・型エラー解消・スケジュールジョブ追加・プラン制限実装時にトリガー。
category: api-router
sourceSkillIds:
  - 3b8b6f3f
  - 054208d0
  - 31e942d4
  - fd774bbd
  - '17e52886'
  - fe4fd046
  - '79047663'
  - eb5b5790
  - bb56451a
  - 4119be00
  - 8c491bd3
  - 4c1e226f
  - 8c38bbfc
  - e79eb2df
  - e3dcdb7e
  - 630f0c79
  - ce339f24
  - a6ff5932
  - 1e5aa1a3
  - 4b1ba739
  - 203130a7
generatedAt: '2026-06-17'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-06-17T23:01:56+09:00'
adoptedFromArchive:
  - archive/skills/api-route-patterns.md
  - archive/skills/claude-api-spec-gen.md
  - archive/skills/add-email-template.md
  - archive/skills/calendar.md
  - archive/skills/deploy.md
  - archive/skills/gmail-auto-sync.md
  - archive/skills/inngest-scheduled-function.md
  - archive/skills/plan-limits-enforcement.md
  - archive/skills/ai-integration.md
  - archive/skills/api-bundle-rebuild.md
---

# api-route-patterns — Next.js / TypeScript / Zod 汎用 API パターン集

## 0. 適用判断フローチャート

```
新規 API エンドポイント追加
  ├─ App Router Route Handler？  → § 1
  ├─ tRPC procedure？            → § 2
  ├─ Webhook 受信？              → § 3
  ├─ プラン制限が必要？          → § 4
  ├─ バックグラウンドジョブ？    → § 5
  └─ AI プロバイダー呼び出し？  → § 6
```

---

## 1. Route Handler 基本骨格

### 1-1. GET（クエリパラメータ + 認証）

```typescript
// app/api/items/route.ts
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getServerSession } from "@/lib/auth"; // プロジェクト共通ヘルパー

const querySchema = z.object({
  page:   z.coerce.number().int().min(1).default(1),
  limit:  z.coerce.number().int().min(1).max(100).default(20),
  status: z.enum(["active", "archived"]).optional(),
});

export async function GET(req: NextRequest) {
  // 1. 認証
  const session = await getServerSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // 2. バリデーション
  const parsed = querySchema.safeParse(
    Object.fromEntries(req.nextUrl.searchParams)
  );
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid query", details: parsed.error.flatten() },
      { status: 400 }
    );
  }
  const { page, limit, status } = parsed.data;

  // 3. ビジネスロジック
  try {
    const items = await db.item.findMany({
      where: { tenantId: session.tenantId, ...(status && { status }) },
      skip: (page - 1) * limit,
      take: limit,
    });
    return NextResponse.json({ items, page, limit });
  } catch (err) {
    console.error("[GET /api/items]", err);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
```

### 1-2. POST（ボディバリデーション + 認可）

```typescript
// app/api/items/route.ts（続き）
const createSchema = z.object({
  title:       z.string().min(1).max(255),
  description: z.string().max(1000).optional(),
  tags:        z.array(z.string()).max(10).default([]),
});

export async function POST(req: NextRequest) {
  const session = await getServerSession();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  // 権限チェック（ロールベース）
  if (!session.permissions.includes("item:create")) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const body = await req.json().catch(() => null);
  const parsed = createSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten() },
      { status: 422 }
    );
  }

  try {
    const item = await db.item.create({
      data: { ...parsed.data, tenantId: session.tenantId },
    });
    return NextResponse.json(item, { status: 201 });
  } catch (err) {
    console.error("[POST /api/items]", err);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
```

### 1-3. 共通エラーハンドラーラッパー

繰り返しを減らすためのユーティリティ：

```typescript
// lib/api/handler.ts
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "@/lib/auth";

type Handler = (req: NextRequest, session: Session) => Promise<NextResponse>;

export function withAuth(handler: Handler) {
  return async (req: NextRequest) => {
    try {
      const session = await getServerSession();
      if (!session) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
      }
      return await handler(req, session);
    } catch (err) {
      console.error("[API Error]", err);
      return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
    }
  };
}

// 使用例
// export const GET = withAuth(async (req, session) => { ... });
```

---

## 2. tRPC — 型安全 Router パターン

### 2-1. 基本 procedure

```typescript
// server/routers/item.ts
import { z } from "zod";
import { router, protectedProcedure, publicProcedure } from "@/server/trpc";
import { TRPCError } from "@trpc/server";

export const itemRouter = router({
  list: protectedProcedure
    .input(z.object({
      cursor: z.string().optional(),
      limit:  z.number().min(1).max(100).default(20),
    }))
    .query(async ({ ctx, input }) => {
      const items = await ctx.db.item.findMany({
        where:   { tenantId: ctx.session.tenantId },
        take:    input.limit + 1,
        cursor:  input.cursor ? { id: input.cursor } : undefined,
        orderBy: { createdAt: "desc" },
      });

      const hasMore = items.length > input.limit;
      return {
        items:      hasMore ? items.slice(0, -1) : items,
        nextCursor: hasMore ? items[items.length - 2].id : undefined,
      };
    }),

  create: protectedProcedure
    .input(z.object({
      title:       z.string().min(1).max(255),
      description: z.string().max(1000).optional(),
    }))
    .mutation(async ({ ctx, input }) => {
      // プラン制限チェック（§4 参照）
      await enforcePlanLimit(ctx.session.tenantId, "items");

      return ctx.db.item.create({
        data: { ...input, tenantId: ctx.session.tenantId },
      });
    }),

  delete: protectedProcedure
    .input(z.object({ id: z.string().cuid() }))
    .mutation(
