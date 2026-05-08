---
name: api-route-patterns
description: >-
  Next.js App Router
  APIルートの実装パターン集。認証ガード・Zodバリデーション・エラーハンドリング・レスポンス型の標準化を一括で提供する。新規APIルート作成・既存ルートのリファクタ・保護レベルの設定変更時に参照する。
category: api-router
sourceSkillIds:
  - ecef156f
  - ecabd2b9
  - a0402a83
  - 9821a84e
  - 449f44fc
  - 9b7f45d1
  - f01a2f3a
  - 7e61dd01
  - 3805819e
  - eac9a44c
  - '33105718'
  - dd713770
  - a8f1324b
  - 8d57af27
  - b7d584f7
  - 9efafb63
  - 8457e2a3
  - e82475fd
  - 99caa9f1
  - 83bf7503
  - 65e9a904
  - fcebede9
  - 2c7ceffc
  - bdda532f
  - b7298831
  - a2cfa62a
  - be507bc2
  - 3ae522f8
  - 6438920a
  - 8b4c241d
  - d38769fd
  - bac81196
  - 0ec93b1e
  - 16f7bcc7
  - 4688b569
  - 5f56b6f6
  - d80d20fa
  - 5a5aa68d
  - c4cff93f
  - cfef4151
  - b2119b1e
  - b821f3f2
  - 6712b59d
  - ba4a2881
  - '49243085'
  - 454fb33a
  - a5314778
  - 30f43ecb
generatedAt: '2026-05-08'
---

# Next.js App Router — APIルート実装パターン集

新規APIルートを追加・変更するときは、このSkillを最初に参照する。
認証ガード・バリデーション・エラーハンドリング・レスポンス型の**4軸**を必ず揃えること。

---

## 1. 保護レベルの分類フローチャート

```
新しい API ルート
   │
   ├─ Webhook（Stripe・LINE など外部サービスから）?
   │     → [A] 署名検証ガード
   │
   ├─ Vercel Cron / 内部スケジューラから呼ばれる?
   │     → [B] Cronシークレットガード
   │
   ├─ サインイン不要の公開エンドポイント?
   │     → [C] 公開（レート制限のみ推奨）
   │
   ├─ サインイン必須（一般ユーザー）?
   │     → [D] セッション認証ガード
   │
   ├─ 管理者・特権ロール必須?
   │     → [E] ロールガード（D の上位）
   │
   └─ サービス間 API（M2M）?
         → [F] APIキー / JWT Bearer ガード
```

ルートを実装する前に必ずこのフローで分類し、**対応するガードパターンを冒頭に配置**する。

---

## 2. 標準レスポンス型

すべてのAPIルートは以下の型に準拠したレスポンスを返す。

```typescript
// types/api.ts
export type ApiSuccess<T> = {
  success: true;
  data: T;
};

export type ApiError = {
  success: false;
  error: {
    code: string;      // 機械可読コード（例: "VALIDATION_ERROR"）
    message: string;   // 人間向けメッセージ
    details?: unknown; // Zodエラーなど追加情報（開発時のみ）
  };
};

export type ApiResponse<T> = ApiSuccess<T> | ApiError;
```

```typescript
// lib/api-response.ts
import { NextResponse } from "next/server";
import type { ApiResponse } from "@/types/api";

export function ok<T>(data: T, status = 200) {
  return NextResponse.json<ApiResponse<T>>(
    { success: true, data },
    { status }
  );
}

export function err(
  code: string,
  message: string,
  status: number,
  details?: unknown
) {
  return NextResponse.json<ApiResponse<never>>(
    { success: false, error: { code, message, details } },
    { status }
  );
}
```

---

## 3. ガードパターン実装例

### [A] Webhook署名検証ガード（例: Stripe）

```typescript
// app/api/webhooks/stripe/route.ts
import { headers } from "next/headers";
import Stripe from "stripe";
import { err, ok } from "@/lib/api-response";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

export async function POST(req: Request) {
  const body = await req.text();
  const sig = headers().get("stripe-signature") ?? "";

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(
      body,
      sig,
      process.env.STRIPE_WEBHOOK_SECRET!
    );
  } catch {
    return err("INVALID_SIGNATURE", "Webhook signature verification failed", 400);
  }

  // イベントハンドリング
  switch (event.type) {
    case "checkout.session.completed":
      // ...
      break;
  }

  return ok({ received: true });
}
```

### [B] Cron シークレットガード

```typescript
// app/api/cron/daily-report/route.ts
import { err, ok } from "@/lib/api-response";

export async function GET(req: Request) {
  const authHeader = req.headers.get("authorization");
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return err("UNAUTHORIZED", "Invalid cron secret", 401);
  }

  // バッチ処理
  return ok({ processed: true });
}
```

### [C] 公開エンドポイント（バリデーション + レート制限推奨）

```typescript
// app/api/public/search/route.ts
import { z } from "zod";
import { err, ok } from "@/lib/api-response";

const QuerySchema = z.object({
  q: z.string().min(1).max(100),
  limit: z.coerce.number().int().min(1).max(50).default(20),
});

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const parsed = QuerySchema.safeParse(Object.fromEntries(searchParams));

  if (!parsed.success) {
    return err("VALIDATION_ERROR", "Invalid query parameters", 400, parsed.error.flatten());
  }

  const { q, limit } = parsed.data;
  // 検索処理
  return ok({ results: [], query: q, limit });
}
```

### [D] セッション認証ガード

```typescript
// app/api/user/profile/route.ts
import { auth } from "@/lib/auth"; // NextAuth / Clerk / 独自実装を抽象化
import { z } from "zod";
import { err, ok } from "@/lib/api-response";

const UpdateProfileSchema = z.object({
  displayName: z.string().min(1).max(50),
  bio: z.string().max(200).optional(),
});

export async function PATCH(req: Request) {
  // 認証チェック
  const session = await auth();
  if (!session?.user) {
    return err("UNAUTHORIZED", "Authentication required", 401);
  }

  // ボディバリデーション
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return err("INVALID_JSON", "Request body must be valid JSON", 400);
  }

  const parsed = UpdateProfileSchema.safeParse(body);
  if (!parsed.success) {
    return err("VALIDATION_ERROR", "Invalid request body", 400, parsed.error.flatten());
  }

  // ビジネスロジック
  const updated = await updateUserProfile(session.user.id, parsed.data);
  return ok(updated);
}
```

### [E] ロールガード（管理者専用）

```typescript
// app/api/admin/users/route.ts
import { auth } from "@/lib/auth";
import { err, ok } from "@/lib/api-response";

export async function GET() {
  const session = await auth();

  if (!session?.user) {
    return err("UNAUTHORIZED", "Authentication required", 401);
  }
  if (session.user.role !== "admin") {
    
