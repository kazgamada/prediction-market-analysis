---
name: devops-deploy-checklist
description: >-
  Vercel/GitHub Actions/Next.jsプロジェクトのデプロイ前チェックリストと運用パターン。
  コード品質・セキュリティ・環境変数・Cron保護・ブランチ戦略・デモモード対応を網羅した汎用ガイド。
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
  - d4aa5f9c
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
generatedAt: '2026-05-11'
---

# DevOps デプロイチェックリスト

Vercel + GitHub Actions + Next.js スタックでの本番デプロイ前に確認すべき項目と、
再利用可能な実装パターンをまとめたガイド。

---

## 1. コード品質チェック

デプロイ前に必ずローカルで以下を通過させる。

```bash
# TypeScript 型チェック
npx tsc --noEmit

# Lint
npx eslint . --ext .ts,.tsx --max-warnings 0

# ビルド確認（最重要: Vercel と同じ出力を確認）
npm run build
```

### CI（GitHub Actions）での自動チェック

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      - run: npm ci
      - run: npx tsc --noEmit
      - run: npx eslint . --ext .ts,.tsx --max-warnings 0
      - run: npm run build
```

**チェックリスト**
- [ ] `tsc --noEmit` がエラーゼロ
- [ ] ESLint が warning ゼロ（`--max-warnings 0`）
- [ ] `npm run build` がローカルで成功
- [ ] CI が green

---

## 2. 環境変数管理

### 必須ファイル構成

```
.env.local          # ローカル開発用（git ignore 済み）
.env.example        # 必要な変数一覧（git 管理・値は空）
```

### `.env.example` テンプレート

```bash
# === アプリケーション ===
NEXT_PUBLIC_APP_URL=

# === 認証 ===
NEXTAUTH_URL=
NEXTAUTH_SECRET=

# === データベース ===
DATABASE_URL=

# === 外部サービス ===
OPENAI_API_KEY=
STRIPE_SECRET_KEY=
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=

# === Cron 保護 ===
CRON_SECRET=

# === デモモード（任意） ===
NEXT_PUBLIC_DEMO_MODE=
```

### 起動時の環境変数バリデーション

```typescript
// lib/env.ts
const requiredEnvVars = [
  'NEXTAUTH_SECRET',
  'DATABASE_URL',
  'OPENAI_API_KEY',
] as const;

export function validateEnv() {
  const missing = requiredEnvVars.filter((key) => !process.env[key]);
  if (missing.length > 0) {
    throw new Error(
      `Missing required environment variables:\n${missing.map((k) => `  - ${k}`).join('\n')}`
    );
  }
}

// app/layout.tsx（サーバーコンポーネント）
import { validateEnv } from '@/lib/env';
validateEnv(); // 起動時に即検出
```

### Vercel での設定

```
Vercel Dashboard
  → Settings → Environment Variables
  → Production / Preview / Development で分けて設定
```

**チェックリスト**
- [ ] `.env.example` が最新（新規変数を追加したら必ず更新）
- [ ] `.env.local` が `.gitignore` に含まれている
- [ ] Vercel の Production 環境変数がすべて設定済み
- [ ] `NEXTAUTH_SECRET` は `openssl rand -base64 32` で生成した強いランダム値
- [ ] `CRON_SECRET` が設定済み（Cron を使う場合）

---

## 3. Cron ジョブのセキュリティ保護

### `requireCron` ガード（必須）

**⚠️ このガードなしでデプロイすると、誰でも Cron エンドポイントを叩ける。**

```typescript
// lib/api-guard.ts
import { NextRequest, NextResponse } from 'next/server';

/** Cron エンドポイント保護。CRON_SECRET が一致しない場合は 401 を返す */
export function requireCron(req: NextRequest): NextResponse | null {
  const authHeader = req.headers.get('authorization');
  const expectedToken = process.env.CRON_SECRET;

  if (!expectedToken) {
    console.error('CRON_SECRET is not set');
    return NextResponse.json({ error: 'Server misconfiguration' }, { status: 500 });
  }

  if (authHeader !== `Bearer ${expectedToken}`) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  return null; // 認証成功
}

/** エラーオブジェクトを安全にシリアライズ */
export function safeError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}
```

### Cron ルートの実装パターン

```typescript
// app/api/cron/daily-summary/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { requireCron, safeError } from '@/lib/api-guard';

/**
 * GET /api/cron/daily-summary
 * Vercel Cron から毎日 09:00 JST に呼ばれる
 */
export async function GET(req: NextRequest) {
  // 1. 認証チェック（必ず最初に）
  const authError = requireCron(req);
  if (authError) return authError;

  try {
    // 2. バッチ処理本体
    const result = await runDailySummary();
    return NextResponse.json({ ok: true, processed: result.count });
  } catch (err) {
    console.error('[cron/daily-summary]', err);
    return NextResponse.json({ error: safeError(err) }, { status: 500 });
  }
}
```

### `vercel.json` でのスケジュール設定

```json
{
  "crons": [
    {
      "path": "/api/cron/daily-summary",
      "schedule": "0 0 * * *"
    },
    {
      "path": "/api/cron/weekly-report",
      "schedule": "0 0 * * 0"
    }
  ]
}
```

> **JST 変換**: Vercel Cron は UTC。JST 09:00 → UTC `0 0 * * *`

**チェックリスト**
- [ ] すべての `/api/cron/*` に `requireCron()` が付いている
- [ ] `CRON_SECRET` が Vercel 環境変数に設定済み
- [ ] `vercel.json` の cron
