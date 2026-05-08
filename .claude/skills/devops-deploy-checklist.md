---
name: devops-deploy-checklist
description: >-
  Vercel/GitHub Actions/Next.jsプロジェクトのデプロイ前チェックリストと運用パターン。
  コード品質・セキュリティ・環境変数・Cron保護・ブランチ戦略・CI/CDパイプラインを網羅した汎用ガイド。
category: devops
sourceSkillIds:
  - 820cc3f2
  - b1da6443
  - 68f5d615
  - 146803d5
  - e7d366ff
  - 97734b6c
  - af50e4b7
  - 670db250
  - 1fe77be8
  - '70452492'
  - 37f074ef
  - 64b04175
  - 1095d4f8
  - 508b354a
  - b0d998cd
  - 46d099b6
  - 06212e83
  - 7954a210
  - 57966bf7
  - 5d66c491
  - c481b53b
  - 94a98cd9
  - 17c743b2
  - bc464b65
  - ce9e57e1
  - 4c6ef214
  - 6c2fb525
  - b0afe3eb
  - 30939cf3
  - 958029db
  - f7569a49
  - a629c68c
  - 09bac265
  - 32b13307
  - e4bfdb6a
  - 6e71714f
  - e25c6a79
  - 9d0b29ca
generatedAt: '2026-05-08'
---

# DevOps デプロイチェックリスト

Vercel + GitHub Actions + Next.js スタックにおける**デプロイ前の必須確認事項**と**運用パターン**をまとめたガイド。
本番リリース前に必ずこのチェックリストを通過させること。

---

## 1. コード品質チェック

### 1-1. ローカルビルド確認

```bash
# TypeScript型チェック
npx tsc --noEmit

# ESLint
npx eslint . --ext .ts,.tsx --max-warnings 0

# ビルド成功確認
npm run build
```

**判定基準**: エラー0件、警告0件でビルドが通ること。

### 1-2. 依存関係の健全性

```bash
# 脆弱性スキャン
npm audit --audit-level=high

# 未使用依存の確認（任意）
npx depcheck
```

> ⚠️ `high` 以上の脆弱性がある場合はデプロイをブロックする。

---

## 2. 環境変数チェック

### 2-1. 必須変数の存在確認

`lib/env.ts` などに環境変数バリデーションを集約する：

```typescript
// lib/env.ts
import { z } from "zod";

const envSchema = z.object({
  // DB
  DATABASE_URL: z.string().url(),
  // Auth
  NEXTAUTH_SECRET: z.string().min(32),
  NEXTAUTH_URL: z.string().url(),
  // 外部サービス（例）
  OPENAI_API_KEY: z.string().startsWith("sk-"),
  // Cron保護
  CRON_SECRET: z.string().min(32),
});

export const env = envSchema.parse(process.env);
```

### 2-2. Vercel 環境変数チェックリスト

| 変数名 | Production | Preview | Development | 備考 |
|--------|:---:|:---:|:---:|------|
| `DATABASE_URL` | ✅ | ✅ | ✅ | 本番/ステージングで別DB |
| `NEXTAUTH_SECRET` | ✅ | ✅ | ✅ | 環境ごとに異なる値 |
| `NEXTAUTH_URL` | ✅ | ✅ | ✅ | 各環境のURL |
| `CRON_SECRET` | ✅ | — | — | Production のみ必須 |
| `NEXT_PUBLIC_*` | ✅ | ✅ | ✅ | クライアント公開変数 |

> ⚠️ `NEXT_PUBLIC_` プレフィックスの変数はクライアントバンドルに含まれる。**シークレット値を絶対に設定しない**。

### 2-3. `.env.example` の同期確認

```bash
# .env.example に全キーが記載されているか確認
diff <(grep -E '^[A-Z]' .env.local | cut -d= -f1 | sort) \
     <(grep -E '^[A-Z]' .env.example | cut -d= -f1 | sort)
```

---

## 3. セキュリティチェック

### 3-1. API Route の認証ガード

すべての保護が必要なエンドポイントに認証チェックを実装する：

```typescript
// lib/api-guard.ts
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";

/** 通常APIの認証ガード */
export async function requireAuth() {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return null; // OK
}

/** Cron専用ガード */
export function requireCron(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  const expected = `Bearer ${process.env.CRON_SECRET}`;
  if (authHeader !== expected) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  return null; // OK
}

/** エラーを安全にシリアライズ（スタックトレース漏洩防止） */
export function safeError(error: unknown, context?: string) {
  const message = error instanceof Error ? error.message : "Unknown error";
  console.error(`[${context ?? "API"}]`, error);
  return NextResponse.json(
    { error: process.env.NODE_ENV === "production" ? "Internal Server Error" : message },
    { status: 500 }
  );
}
```

### 3-2. Cron エンドポイントの実装パターン

```typescript
// app/api/cron/[name]/route.ts
import { NextRequest, NextResponse } from "next/server";
import { requireCron, safeError } from "@/lib/api-guard";

/**
 * GET /api/cron/[name]
 * Vercel Cron から呼び出される。CRON_SECRET による認証必須。
 */
export async function GET(req: NextRequest) {
  const guard = requireCron(req);
  if (guard) return guard; // 401/403 を返す

  try {
    // バッチ処理の実装
    await runBatchJob();
    return NextResponse.json({ ok: true, timestamp: new Date().toISOString() });
  } catch (error) {
    return safeError(error, "cron/[name]");
  }
}
```

```json
// vercel.json
{
  "crons": [
    {
      "path": "/api/cron/daily-summary",
      "schedule": "0 9 * * *"
    }
  ]
}
```

### 3-3. セキュリティヘッダーの設定

```typescript
// next.config.ts
const securityHeaders = [
  { key: "X-DNS-Prefetch-Control", value: "on" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-eval' 'unsafe-inline'", // Next.js要件
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: https:",
      "font-src 'self'",
      "connect-src 'self' https:",
    ].join
