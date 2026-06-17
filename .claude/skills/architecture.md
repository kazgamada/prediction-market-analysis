---
name: architecture
description: >-
  Next.js/TypeScript プロジェクトの汎用アーキテクチャ設計パターン。
  ディレクトリ構成・レイヤー分離・データフロー・型安全性・デプロイ構成の原則を把握する。 新機能追加・バグ調査・技術選定・デプロイ前確認のときに参照する。
category: architecture
version: 1
effectiveTimestamp: '2026-05-28T12:00:00.000Z'
abstractionLevel: 2
targetStack:
  - Next.js
  - TypeScript
sources:
  - medlearn-project-architecture (medical-learning-ai)
sourceSkillIds:
  - 79ee2962
generatedAt: '2026-06-17'
---

# Next.js/TypeScript — 汎用アーキテクチャ設計パターン

## 概要

このSkillは、Next.js + TypeScript を軸としたプロジェクトで繰り返し現れる
アーキテクチャ上の意思決定・構成パターン・設計原則をまとめたものです。
プロジェクト固有の技術スタック（例: tRPC / Drizzle / Supabase）は
「スタック選択肢」として列挙し、原則は汎用的に記述します。

---

## 1. レイヤー構成の原則

```
┌─────────────────────────────────────────┐
│           Presentation Layer            │  ← React Components / Pages
├─────────────────────────────────────────┤
│           Application Layer             │  ← Server Actions / API Routes / tRPC Routers
├─────────────────────────────────────────┤
│             Domain Layer                │  ← Business Logic / Use Cases / Validators
├─────────────────────────────────────────┤
│         Infrastructure Layer            │  ← DB Client / External APIs / ORM
└─────────────────────────────────────────┘
```

### 原則
- **単方向依存**: 上位レイヤーが下位レイヤーを参照する。逆は禁止。
- **ドメインの純粋性**: Domain Layer にフレームワーク依存コードを混入しない。
- **型安全な境界**: レイヤー間のデータ受け渡しは Zod スキーマ or TypeScript 型で明示する。

---

## 2. 推奨ディレクトリ構成

### App Router (Next.js 13+) 標準構成

```
src/
├── app/                        # Next.js App Router
│   ├── (auth)/                 # Route Group: 認証必須ページ
│   ├── (public)/               # Route Group: 公開ページ
│   ├── api/                    # API Routes (RESTまたはtRPC endpoint)
│   └── layout.tsx
│
├── components/
│   ├── ui/                     # 汎用UIコンポーネント (shadcn/ui等)
│   └── features/               # 機能単位のコンポーネント
│       └── [feature-name]/
│           ├── index.tsx
│           ├── [Feature]Form.tsx
│           └── use[Feature].ts  # feature固有カスタムフック
│
├── server/                     # サーバーサイド専用コード
│   ├── db/                     # DB接続・スキーマ (Drizzle / Prisma等)
│   │   ├── schema.ts
│   │   └── index.ts
│   ├── routers/                # tRPC routers または API handlers
│   │   └── [feature].ts
│   └── services/               # ビジネスロジック (Use Cases)
│       └── [feature].service.ts
│
├── lib/
│   ├── auth.ts                 # 認証設定 (NextAuth / Supabase Auth等)
│   ├── trpc/                   # tRPC クライアント設定 (採用時)
│   └── validators/             # Zod スキーマ
│       └── [feature].schema.ts
│
├── types/
│   └── index.ts                # 共有型定義
│
└── hooks/                      # 汎用カスタムフック
    └── use[Name].ts
```

> **Pages Router を使う場合**: `app/` を `pages/` に置き換え、
> `pages/api/` に API Routes を配置する。構造の考え方は同一。

---

## 3. データフローパターン

### パターン A: Server Actions (Next.js 14+ 推奨)

```typescript
// server/services/user.service.ts — Domain/Infrastructure
export async function createUser(input: CreateUserInput) {
  const validated = createUserSchema.parse(input); // Zod で境界検証
  return db.insert(users).values(validated).returning();
}

// app/(auth)/register/actions.ts — Application Layer
'use server';
import { createUser } from '@/server/services/user.service';

export async function registerAction(formData: FormData) {
  const raw = Object.fromEntries(formData);
  const result = await createUser(raw);
  revalidatePath('/dashboard');
  return result;
}

// components/features/auth/RegisterForm.tsx — Presentation Layer
'use client';
import { registerAction } from '../actions';

export function RegisterForm() {
  return (
    <form action={registerAction}>
      <input name="email" type="email" required />
      <button type="submit">登録</button>
    </form>
  );
}
```

### パターン B: tRPC (型安全 RPC)

```typescript
// server/routers/user.ts
import { z } from 'zod';
import { router, protectedProcedure } from '../trpc';

export const userRouter = router({
  create: protectedProcedure
    .input(createUserSchema)         // 入力を Zod で型付け
    .mutation(async ({ input, ctx }) => {
      return ctx.db.insert(users).values(input).returning();
    }),
});

// クライアント: 型推論が end-to-end で効く
const { mutate } = api.user.create.useMutation();
```

### パターン C: REST API Routes

```typescript
// app/api/users/route.ts
import { NextRequest, NextResponse } from 'next/server';

export async function POST(req: NextRequest) {
  const body = await req.json();
  const validated = createUserSchema.safeParse(body);
  if (!validated.success) {
    return NextResponse.json({ error: validated.error }, { status: 400 });
  }
  const user = await createUser(validated.data);
  return NextResponse.json(user, { status: 201 });
}
```

---

## 4. 型安全性の確保

### Zod による境界定義

```typescript
// lib/validators/user.schema.ts
import { z } from 'zod';

export const createUserSchema = z.object({
  email: z.string().email(),
  name: z.string().min(1).max(100),
  role: z.enum(['student', 'teacher', 'admin']).default('student'),
});

// 型はスキーマから自動導出（手書き禁止）
export type CreateUserInput = z.infer<typeof createUserSchema>;
```

### DB スキーマとの同期

```typescript
// Drizzle ORM の場合: スキーマ
