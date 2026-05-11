---
name: api-route-patterns
description: >-
  Next.js App Router
  APIルートの実装パターン集。認証ガード・Zodバリデーション・エラーハンドリング・レスポンス型の標準化を一括で提供する。新規APIルート作成・既存ルートのリファクタ・保護レベルの設定変更時に参照する。
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
---

# Next.js App Router — APIルート実装パターン集

## 概要

新規APIルートを追加・修正するときは、このSkillを参照し以下の原則に従うこと。

| 関心事 | 対応パターン |
|---|---|
| 認証・認可 | ルート分類フローチャート → ガード関数 |
| 入力検証 | Zodスキーマ → `safeParse` |
| エラー応答 | `apiError` ヘルパー → 統一JSONフォーマット |
| 成功応答 | `apiSuccess` ヘルパー → 統一JSONフォーマット |
| ルート構成 | HTTPメソッドごとに名前付きexport |

---

## 1. ルート分類フローチャート

新しいAPIルートを追加するとき、**必ず**以下の6分類に割り振ってから実装する。

```
新しい API ルート
   │
   ├─ Webhook（Stripe・LINE など外部プロバイダから）?
   │     → プロバイダ署名検証（§2-A）
   │
   ├─ Cron / スケジューラから呼ばれる?
   │     → Cron シークレット検証（§2-B）
   │
   ├─ サービス間内部通信?
   │     → 内部シークレット検証（§2-C）
   │
   ├─ 認証済みユーザー専用?
   │     → セッション検証 → userId 取得（§2-D）
   │
   ├─ 認証済み管理者専用?
   │     → セッション検証 → role === "admin" 確認（§2-E）
   │
   └─ パブリック（認証不要）?
         → ガードなし。レート制限を検討（§2-F）
```

---

## 2. 認証ガードパターン

### 2-A. Webhook署名検証（例: Stripe）

```typescript
// app/api/webhooks/stripe/route.ts
import { headers } from "next/headers";
import Stripe from "stripe";

export async function POST(req: Request) {
  const body = await req.text(); // rawボディが必要
  const sig = headers().get("stripe-signature") ?? "";

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(
      body,
      sig,
      process.env.STRIPE_WEBHOOK_SECRET!
    );
  } catch (err) {
    return apiError("Invalid webhook signature", 400);
  }

  // イベント処理...
  return apiSuccess({ received: true });
}
```

### 2-B. Cron シークレット検証

```typescript
// app/api/cron/daily-batch/route.ts
export async function GET(req: Request) {
  const authHeader = req.headers.get("authorization");
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return apiError("Unauthorized", 401);
  }
  // バッチ処理...
}
```

### 2-C. 内部サービス間通信

```typescript
// app/api/internal/sync/route.ts
export async function POST(req: Request) {
  const secret = req.headers.get("x-internal-secret");
  if (secret !== process.env.INTERNAL_API_SECRET) {
    return apiError("Forbidden", 403);
  }
  // 処理...
}
```

### 2-D. 認証済みユーザー（セッション検証）

```typescript
// app/api/posts/route.ts
import { auth } from "@/lib/auth"; // NextAuth / Clerk / その他

export async function GET(req: Request) {
  const session = await auth();
  if (!session?.user?.id) {
    return apiError("Unauthorized", 401);
  }
  const userId = session.user.id;
  // userId を用いたデータ取得...
}
```

### 2-E. 管理者専用

```typescript
// app/api/admin/users/route.ts
export async function GET(req: Request) {
  const session = await auth();
  if (!session?.user) return apiError("Unauthorized", 401);
  if (session.user.role !== "admin") return apiError("Forbidden", 403);
  // 管理者処理...
}
```

### 2-F. パブリックルート

ガード不要。ただし乱用防止のため **レート制限**（upstash/ratelimit 等）の導入を検討する。

---

## 3. Zodバリデーションパターン

### リクエストボディの検証

```typescript
import { z } from "zod";

const CreatePostSchema = z.object({
  title: z.string().min(1).max(200),
  content: z.string().min(1),
  published: z.boolean().default(false),
});

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user?.id) return apiError("Unauthorized", 401);

  // ─── ① パース ───────────────────────────────────────
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return apiError("Invalid JSON", 400);
  }

  // ─── ② バリデーション ──────────────────────────────
  const parsed = CreatePostSchema.safeParse(body);
  if (!parsed.success) {
    return apiError("Validation failed", 422, parsed.error.flatten());
  }

  const { title, content, published } = parsed.data;
  // DB操作...
}
```

### クエリパラメータの検証

```typescript
const ListQuerySchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  limit: z.coerce.number().int().min(1).max(100).default(20),
  q: z.string().optional(),
});

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const parsed = ListQuerySchema.safeParse(
    Object.fromEntries(searchParams)
  );
  if (!parsed.success) {
    return apiError("Invalid query parameters", 400, parsed.error.flatten());
  }
  const { page, limit, q } = parsed.data;
  // ...
}
```

### 動的ルートパラメータの検証

```typescript
// app/api/posts/[id]/route.ts
const ParamsSchema = z.object({
  id: z.string().cuid(), // または z.string().uuid()
});

export async function GET(
  req: Request,
  { params }: { params: { id: string } }
) {
  const parsed = ParamsSchema.safeParse(params);
  if (!parsed.success) return apiError("Invalid ID", 400);

  const post = await db.post.findUnique({ where: { id: parsed.data.id } });
