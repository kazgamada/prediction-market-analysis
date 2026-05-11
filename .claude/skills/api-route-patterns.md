---
name: api-route-patterns
description: >-
  Next.js App Router
  APIルートの実装パターン集。認証ガード・Zodバリデーション・エラーハンドリング・レスポンス型の標準化を一括で提供する。新規APIルート作成・既存ルートのリファクタ・保護レベルの設定変更時に参照する。Webhook署名検証・プランリミット強制・バックグラウンドジョブとの連携パターンも含む。
category: api-router
sourceSkillIds:
  - ecef156f
  - '82388022'
  - ecabd2b9
  - a0402a83
  - 9821a84e
  - 449f44fc
  - 9b7f45d1
  - f01a2f3a
  - 7e61dd01
  - c1b9870d
  - 3805819e
  - eac9a44c
  - e6023b03
  - '33105718'
  - dd713770
  - a8f1324b
  - 8d57af27
  - cb10e747
  - b7d584f7
  - 9efafb63
  - 8457e2a3
  - 0d8af390
  - e82475fd
  - 99caa9f1
  - 4dcb8f4d
  - 83bf7503
  - 65e9a904
  - fcebede9
  - 2c7ceffc
  - 8ac9867b
  - bdda532f
  - b7298831
  - a2cfa62a
  - be507bc2
  - 3ae522f8
  - 6438920a
  - a7f1915d
  - 8b4c241d
  - 8482a06c
  - d38769fd
  - ee1049cf
  - 1c3776b3
  - bac81196
  - c26125e4
  - 0ec93b1e
  - 16f7bcc7
  - 4688b569
  - 5f56b6f6
  - cb839737
  - d80d20fa
  - 5a5aa68d
  - c4cff93f
  - '26415849'
  - cfef4151
  - b2119b1e
  - b821f3f2
  - 6712b59d
  - 892c69f5
  - ba4a2881
  - 5f204565
  - '49243085'
  - 454fb33a
  - a5314778
  - 30f43ecb
  - 9e97cfa6
generatedAt: '2026-05-11'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-10T19:11:30+00:00'
adoptedFromArchive:
  - archive/prediction-market-analysis/.claude/skills/api-route-patterns.md
  - archive/aegis-market-os/.claude/skills/ai-integration.md
  - archive/aegis-market-os/.claude/skills/api-bundle-rebuild.md
  - archive/aegis-market-os/.claude/skills/billing-stripe.md
  - archive/aegis-market-os/.claude/skills/discovery-github-content.md
  - archive/aegis-market-os/.claude/skills/discovery-pipeline.md
  - archive/aegis-market-os/.claude/skills/discovery-x-rapidapi.md
  - archive/ai-company/.claude/skills/inngest-scheduled-function/SKILL.md
  - archive/ai-company/.claude/skills/plan-limits-enforcement/SKILL.md
  - archive/AISaaS/.claude/skills/add-protected-api.md
---

# API ルート実装パターン集（Next.js App Router）

新規 API ルートを追加・リファクタするときは、まずこの Skill を参照して実装パターンを選択してください。

---

## 0. ルート分類フローチャート

```
新しい API ルート
   │
   ├─ Webhook（Stripe・外部サービスなど）?
   │     → §1: Webhook ルート（署名検証）
   │
   ├─ Vercel Cron / 内部スケジューラから呼ばれる?
   │     → §2: Cron ルート（CRON_SECRET 検証）
   │
   ├─ 認証不要な公開エンドポイント?
   │     → §3: パブリックルート（Zod バリデーションのみ）
   │
   ├─ 認証済みユーザーのみ?
   │     → §4: 認証必須ルート（セッション検証）
   │
   ├─ リソース作成・消費を伴う?
   │     → §5: プランリミット強制を追加
   │
   └─ 管理者のみ?
         → §6: 管理者専用ルート（role チェック）
```

---

## 1. 共通基盤

### 1-1. 標準レスポンス型

```ts
// lib/api-response.ts
import { NextResponse } from "next/server";

export type ApiSuccess<T> = { success: true; data: T };
export type ApiError   = { success: false; error: string; code?: string };
export type ApiResponse<T> = ApiSuccess<T> | ApiError;

export const ok = <T>(data: T, status = 200) =>
  NextResponse.json<ApiSuccess<T>>({ success: true, data }, { status });

export const err = (error: string, status = 400, code?: string) =>
  NextResponse.json<ApiError>({ success: false, error, code }, { status });
```

### 1-2. 認証ガード基盤（`lib/api-guard.ts`）

```ts
// lib/api-guard.ts
import { auth } from "@/lib/auth";            // 例: NextAuth / Lucia など
import { err } from "@/lib/api-response";
import type { NextRequest } from "next/server";

export type GuardedSession = {
  userId: string;
  orgId:  string;
  role:   "admin" | "member" | "viewer";
};

/** 認証必須ガード。失敗時は 401/403 を返し、成功時は session を返す */
export async function requireAuth(
  req: NextRequest,
): Promise<{ session: GuardedSession } | NextResponse> {
  const session = await auth(req);
  if (!session) return err("Unauthorized", 401, "UNAUTHORIZED");
  return { session };
}

/** 管理者専用ガード */
export async function requireAdmin(
  req: NextRequest,
): Promise<{ session: GuardedSession } | NextResponse> {
  const result = await requireAuth(req);
  if (result instanceof NextResponse) return result;
  if (result.session.role !== "admin")
    return err("Forbidden", 403, "FORBIDDEN");
  return result;
}
```

### 1-3. Zod バリデーションヘルパー

```ts
// lib/validate.ts
import { z, ZodSchema } from "zod";
import { err } from "@/lib/api-response";

export async function validateBody<T>(
  req: Request,
  schema: ZodSchema<T>,
): Promise<{ data: T } | NextResponse> {
  try {
    const json = await req.json();
    const result = schema.safeParse(json);
    if (!result.success)
      return err(result.error.issues.map((i) => i.message).join(", "), 422, "VALIDATION_ERROR");
    return { data: result.data };
  } catch {
    return err("Invalid JSON", 400, "BAD_REQUEST");
  }
}

export function validateQuery<T>(
  searchParams: URLSearchParams,
  schema: ZodSchema<T>,
): { data: T } | NextResponse {
  const raw = Object.fromEntries(searchParams.entries());
  const result = schema.safeParse(raw);
  if (!result.success)
    return err(result.error.issues.map((i) => i.message).join(", "), 422, "VALIDATION_ERROR");
  return { data: result.data };
}
```

### 1-4. 共通エラーハンドラ

```ts
// lib/api-error-handler.ts
import { err } from "@/lib/api-response";

export function handleApiError(e: unknown) {
  console.error("[API Error]", e);
  if (e instanceof Error) return err(e.message, 500, "INTERNAL_ERROR");
  return err("Internal Server Error", 500, "INTERNAL_ERROR");
}
```

---

## 2. §1: Webhook ルート（Stripe など）

> **重要**: `express.raw()` 相当の生バイト処理が必要。`NextRequest.text()` を使う。

```ts
// app/api/webhooks/stripe/route.ts
import { NextRequest } from "next/server";
import Stripe from "stripe";
import { err, ok } from "@/lib/api-response";
import { handleApiError } from "@/lib/api-error-handler";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

export async function POST(req: NextRequest) {
  try {
    const body = await req.text();                         // ← raw body 必須
    const sig  = req.headers.get("stripe-signature") ?? "";

    let event: Stripe.Event;
    try {
      event = stripe.webhooks.constructEvent(
        body, sig, process.env.STRIPE_WEBHOOK_SECRET!,
      );
    } catch {
      return err("Invalid signature", 400, "WEBHOOK_SIGNATURE_ERROR");
    }

    switch (event.type) {
      case "checkout.session.completed":
        await handleCheckoutCompleted(event.data.object);
        break;
      case "customer.subscription.deleted":
        await handleSubscriptionDeleted(event.data.object);
        break;
      // 他のイベント...
    }

    return ok({ received: true });
  } catch (e) {
    return handleApiError(e);
  }
}
```

---

## 3. §2: Cron ルート（Vercel Cron / 内部スケジューラ）

```ts
// app/api/cron/daily-report/route.ts
import { NextRequest } from "next/server";
import { err, ok } from "@/lib/api-response";
import { handleApiError } from "@/lib/api-error-handler";

export async function GET(req: NextRequest) {
  // Vercel Cron は Authorization ヘ
