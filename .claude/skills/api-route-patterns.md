---
category: api-router
sourceSkillIds:
  - 3b8b6f3f
  - fd774bbd
  - '17e52886'
  - fe4fd046
  - '79047663'
  - eb5b5790
  - bb56451a
  - 8c491bd3
  - 4c1e226f
  - 054208d0
  - 8c38bbfc
  - e79eb2df
  - e3dcdb7e
  - 630f0c79
  - ce339f24
  - a6ff5932
  - 1e5aa1a3
generatedAt: '2026-05-19'
---
```yaml
---
name: api-route-patterns
description: >
  Next.js App Router の API ルート実装パターン集。認可ガード・Zod バリデーション・
  エラーハンドリング・フィルタ共有・プラン制限・セキュリティ監査まで、
  新規 API ルート追加時に参照する包括的ガイド。
  「API を追加する」「ルートを保護する」「バリデーションを追加する」
  「一括削除を実装する」「プラン制限を掛ける」と言及したときにトリガー。
category: API・ルーター
---
```

# API ルートパターン — Next.js / TypeScript / Zod

## 1. 認可ガードの分類と選択

新規 API ルートを追加するときは、必ず以下 **6 分類** のいずれかに割り当て、
対応するガードを **ハンドラ冒頭** に配置する。

```
新しい API ルート
   │
   ├─ Webhook（Stripe など外部から）?
   │     → プロバイダ側の署名検証を実装
   │     → Raw body を必ず読み取ること（json() を先に呼ぶと壊れる）
   │
   ├─ Vercel Cron / Inngest から呼ばれる?
   │     → CRON_SECRET / Inngest の署名を検証
   │
   ├─ 公開エンドポイント（認証不要）?
   │     → Rate-limit のみ適用（例: /api/health, public OGP）
   │
   ├─ 認証済みユーザー全員が使える?
   │     → セッション検証のみ（例: getCurrentUser()）
   │
   ├─ 特定ロール必須（admin / owner）?
   │     → セッション検証 + ロールチェック
   │
   └─ テナント間データ分離が必要?
         → セッション検証 + tenantId フィルタを必ず WHERE 句に含める
```

### 基本ガードの実装例

```ts
// app/api/example/route.ts
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getCurrentUser } from "@/lib/auth";          // セッション取得
import { requireRole } from "@/lib/api-guard";        // ロール検証
import { ApiError, handleApiError } from "@/lib/api-error"; // 統一エラー

export async function GET(req: NextRequest) {
  try {
    // ① 認証
    const user = await getCurrentUser();
    if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    // ② ロール（admin 専用の場合）
    await requireRole(user, "admin"); // 失敗時は ApiError を throw

    // ③ ビジネスロジック
    const data = await fetchSomething(user.tenantId);
    return NextResponse.json(data);
  } catch (err) {
    return handleApiError(err); // ApiError → 適切な status, それ以外 → 500
  }
}
```

---

## 2. Zod バリデーション — リクエスト入力を型安全に検証

### 2-A. Body バリデーション（POST / PUT / PATCH）

```ts
const CreateItemSchema = z.object({
  name:     z.string().min(1).max(100),
  price:    z.number().positive(),
  tags:     z.array(z.string()).max(10).default([]),
  startsAt: z.string().datetime().optional(),
});

export async function POST(req: NextRequest) {
  try {
    const user = await getCurrentUser();
    if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const body = await req.json();
    const parsed = CreateItemSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: "Validation failed", issues: parsed.error.flatten() },
        { status: 400 }
      );
    }
    const { name, price, tags, startsAt } = parsed.data;
    // ... DB 書き込み
  } catch (err) {
    return handleApiError(err);
  }
}
```

### 2-B. SearchParams バリデーション（GET）

```ts
const ListQuerySchema = z.object({
  search:  z.string().optional(),
  page:    z.coerce.number().int().positive().default(1),
  limit:   z.coerce.number().int().min(1).max(100).default(20),
  from:    z.string().date().optional(),
  to:      z.string().date().optional(),
});

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const parsed = ListQuerySchema.safeParse(Object.fromEntries(searchParams));
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid query", issues: parsed.error.flatten() }, { status: 400 });
  }
  const { search, page, limit, from, to } = parsed.data;
  // ...
}
```

---

## 3. フィルタ共有パターン — GET と DELETE で述語を統一

> **なぜ重要か**: 一覧 API と一括削除 API でフィルタ述語がずれると
> 「画面上 4,249 件」→「削除は 4,300 件」という事故が起こる。
> **単一の `applyFilters()` を共有** することで構造的に防ぐ。

```ts
// lib/filters/sales-filters.ts
export interface SalesFilters {
  search?: string;
  product?: string;
  from?: string | null;
  to?: string | null;
}

/** Prisma の where 句に変換する純関数（GroupBy など特殊クエリを除く） */
export function buildSalesWhere(f: SalesFilters): Prisma.SaleWhereInput {
  return {
    ...(f.search  && { OR: [{ id: { contains: f.search } }, { customerName: { contains: f.search } }] }),
    ...(f.product && { productId: f.product }),
    ...(f.from || f.to) && {
      createdAt: {
        ...(f.from && { gte: new Date(f.from) }),
        ...(f.to   && { lte: new Date(f.to)   }),
      },
    },
  };
}
```

```ts
// app/api/admin/sales/route.ts
import { buildSalesWhere, SalesFilters } from "@/lib/filters/sales-filters";

const FilterSchema = z.object({
  search:  z.string().optional(),
  product: z.string().optional(),
  from:    z.string().optional(),
  to:      z.string().optional(),
});

// GET — 一覧
export async function GET(req: NextRequest) {
  const parsed = FilterSchema.safeParse(Object.fromEntries(new URL(req.url).searchParams));
  if (!parsed.success) return NextResponse.json({ error: "Invalid query" }, { status: 400 });

  const where = buildSalesWhere(parsed.data);   // 
