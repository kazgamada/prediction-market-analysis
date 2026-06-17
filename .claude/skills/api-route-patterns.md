---
name: api-route-patterns
description: >-
  Next.js App Router の API ルート実装パターン。認証・認可ガード、Zod
  バリデーション、エラーハンドリング、フィルタ共有、プラン制限、Webhook 署名検証、tRPC 型安全まで網羅。新規 API
  ルート追加・既存ルート修正・型エラー解消時にトリガー。
category: api-router
sourceSkillIds:
  - 3b8b6f3f
  - 31e942d4
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
  - 4b1ba739
  - 203130a7
generatedAt: '2026-05-23'
---

# API Route Patterns — Next.js / TypeScript / Zod

## 0. 思想・原則

| 原則 | 内容 |
|------|------|
| **Guard First** | 認証・認可は関数の冒頭で完結させ、ビジネスロジックと混在させない |
| **Single Source of Filter** | 一覧 GET と一括 DELETE はフィルタ述語を共有し、「表示件数 ≠ 削除件数」事故を防ぐ |
| **Zod at the Boundary** | 外部入力（Request body / query / env）は必ず Zod でパース。型は `z.infer` から生成 |
| **Consistent Error Shape** | 全ルートで同一の `{ error, code, details? }` JSON を返す |
| **Plan Gate Before Write** | リソース作成系エンドポイントはプラン上限チェックを書き込みより前に実行 |

---

## 1. ルート分類フローチャート

```
新しい API ルートを追加する
        │
        ├─ 外部 Webhook（Stripe / GitHub 等）?
        │       → §2-A: 署名検証ガード
        │
        ├─ Cron / バックグラウンドジョブ?
        │       → §2-B: Cron Secret ガード
        │
        ├─ 管理者専用?
        │       → §2-C: Admin ガード（session + role）
        │
        ├─ テナント/組織スコープの書き込み?
        │       → §2-D: 認証 + プラン制限ガード
        │
        ├─ 認証済みユーザーの読み取り?
        │       → §2-E: Session ガード のみ
        │
        └─ Public（認証不要）?
                → §2-F: レート制限のみ推奨
```

---

## 2. ガードパターン実装

### 2-A. Webhook 署名検証

```typescript
// app/api/webhooks/stripe/route.ts
import { headers } from "next/headers";
import Stripe from "stripe";

export async function POST(req: Request) {
  const body = await req.text(); // JSON.parse 前に取得
  const sig = headers().get("stripe-signature") ?? "";

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, sig, process.env.STRIPE_WEBHOOK_SECRET!);
  } catch {
    return NextResponse.json({ error: "Invalid signature" }, { status: 400 });
  }

  switch (event.type) {
    case "customer.subscription.updated":
      await handleSubscriptionUpdate(event.data.object);
      break;
    // ...
  }
  return NextResponse.json({ received: true });
}
```

### 2-B. Cron Secret ガード

```typescript
// app/api/cron/daily-report/route.ts
export async function GET(req: Request) {
  const auth = req.headers.get("authorization");
  if (auth !== `Bearer ${process.env.CRON_SECRET}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  // --- ジョブ本体 ---
}
```

> **Inngest を使う場合**: `inngest.createFunction` でラップし、
> `lib/inngest-functions.ts` にまとめる（cron/event-driven 両対応）。

```typescript
// lib/inngest-functions.ts
import { inngest } from "./inngest";

export const dailyReport = inngest.createFunction(
  { id: "daily-report", name: "Daily Report" },
  { cron: "0 9 * * *" },
  async ({ step }) => {
    await step.run("generate", async () => { /* ... */ });
  }
);
```

### 2-C. Admin ガード

```typescript
// lib/api-guard.ts
import { auth } from "@/lib/auth";
import { NextResponse } from "next/server";

export async function requireAdmin() {
  const session = await auth();
  if (!session?.user) {
    return { error: NextResponse.json({ error: "Unauthenticated", code: "AUTH_REQUIRED" }, { status: 401 }) };
  }
  if (session.user.role !== "admin") {
    return { error: NextResponse.json({ error: "Forbidden", code: "INSUFFICIENT_ROLE" }, { status: 403 }) };
  }
  return { session };
}

// 使用例
export async function DELETE(req: Request) {
  const guard = await requireAdmin();
  if ("error" in guard) return guard.error;
  const { session } = guard;
  // ...
}
```

### 2-D. 認証 + プラン制限ガード（書き込み系）

```typescript
// app/api/employees/route.ts
import { requireSession } from "@/lib/api-guard";
import { checkPlanLimit } from "@/lib/plan-limits";

export async function POST(req: Request) {
  // 1. 認証
  const guard = await requireSession();
  if ("error" in guard) return guard.error;
  const { session } = guard;

  // 2. プラン制限（書き込み前に必ず実行）
  const limitCheck = await checkPlanLimit(session.user.tenantId, "aiEmployees");
  if (!limitCheck.allowed) {
    return NextResponse.json(
      { error: "Plan limit reached", code: "PLAN_LIMIT_EXCEEDED", limit: limitCheck.limit },
      { status: 402 }
    );
  }

  // 3. バリデーション
  const body = EmployeeCreateSchema.safeParse(await req.json());
  if (!body.success) {
    return NextResponse.json({ error: "Validation failed", details: body.error.flatten() }, { status: 422 });
  }

  // 4. ビジネスロジック
  // ...
}
```

---

## 3. Zod バリデーションパターン

### 3-A. Request Body

```typescript
import { z } from "zod";

const CreateItemSchema = z.object({
  name:      z.string().min(1).max(100),
  price:     z.number().positive(),
  category:  z.enum(["food", "drink", "other"]).optional(),
  tags:      z.array(z.string()).default([]),
});
type CreateItemInput = z.infer<typeof CreateItemSchema>;

// ルート内
const parsed = CreateItemSchema.safeParse(await req.json());
if (!parsed.success) {
  return NextResponse.json(
    { error: "Validation failed", code: "INVALID_INPUT", details: parsed.error.flatten() },
    { status: 422 }
  );
}
const data: CreateItemInput = parsed.data;
```

### 3-B. Query Parameters

```typescript
const ListQuerySchema
