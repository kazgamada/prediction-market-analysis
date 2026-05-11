---
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
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-10T19:11:30+00:00'
adoptedFromArchive:
  - archive/prediction-market-analysis/.claude/skills/devops-deploy-checklist.md
  - archive/aegis-market-os/.claude/skills/backtest-consistency.md
  - archive/aegis-market-os/.claude/skills/market-feeds.md
  - archive/aegis-market-os/.claude/skills/progressive-save.md
  - archive/AISaaS/.claude/skills/add-cron-job.md
  - archive/AISaaS/.claude/skills/pre-release-check.md
  - archive/AISaaS/.claude/skills/setup-env-vars.md
  - archive/task-matrix/.claude/skills/add-test.md
  - archive/task-matrix/.claude/skills/fix-errors.md
  - archive/task-matrix/.claude/skills/refactor.md
---
```yaml
---
name: devops-deploy-checklist
description: >-
  Vercel/GitHub Actions/Next.jsプロジェクトのデプロイ前チェックリストと運用パターン。
  コード品質・セキュリティ・環境変数・Cron保護・ブランチ戦略・CI/CDパイプラインを網羅した汎用ガイド。
  pre-release-check / setup-env-vars / add-cron-job の知見を統合済み。
category: devops
---
```

# DevOps デプロイチェックリスト

Vercel / GitHub Actions / Next.js プロジェクトで本番リリースする前に必ず実行するチェックリスト。  
**このSkillを呼び出して checkbox を1つずつ確認していく。**

---

## 目次

1. [コード品質チェック](#1-コード品質チェック)
2. [セキュリティ・認可ガード](#2-セキュリティ認可ガード)
3. [Cron ジョブ保護](#3-cron-ジョブ保護)
4. [環境変数セットアップ](#4-環境変数セットアップ)
5. [ブランチ戦略・CI/CDパイプライン](#5-ブランチ戦略cicdパイプライン)
6. [デプロイ後の確認](#6-デプロイ後の確認)
7. [トラブルシューティング早見表](#7-トラブルシューティング早見表)

---

## 1. コード品質チェック

### 1-1. 型チェック・Lint

```bash
# TypeScript 型エラーがないことを確認
npm run check          # tsc --noEmit

# Lint エラーがないことを確認
npm run lint

# テストが全て通ることを確認
npm run test
```

チェックリスト:

- [ ] `npm run check` がエラーゼロ
- [ ] `npm run lint` がエラーゼロ（Warning は可）
- [ ] `npm run test` が全パス
- [ ] `npm run build` がエラーなく完了（ビルド成果物を確認）

### 1-2. よくある TypeScript エラーの修正パターン

```typescript
// ❌ TS2322: string | null を string に代入
const id: string = row.id;

// ✅ null 合体演算子
const id: string = row.id ?? "";

// ✅ null チェック
if (row.id) { const id: string = row.id; }

// ✅ フィルタで除外（配列の場合）
const ids = rows.map(r => r.id).filter((id): id is string => id !== null);
```

### 1-3. リファクタリング時の安全手順

影響範囲を必ず事前調査する:

```bash
# 関数名・変数名の全参照箇所を検索
grep -rn "対象の関数名" src/ server/ shared/ --include="*.ts" --include="*.tsx"

# import の確認
grep -rn "from.*対象モジュール" src/ server/ --include="*.ts"
```

**ルール:**

1. テストがなければ先にテストを書く
2. 変更後に `npm run check && npm run test` を必ず実行
3. サーバーコード変更時は API バンドルを再構築: `npm run build:api`

---

## 2. セキュリティ・認可ガード

### 2-1. API ルート網羅チェック

```bash
# 認可ガードが付いていない API ルートを検出（要目視確認）
grep -rL "requireAuth\|requireAdmin\|requireCron\|devOnly\|verifySignature" \
  app/api/ --include="*.ts"
```

- [ ] 新規 API ルートすべてに適切な認可ガードが付いている
- [ ] `devOnly` 関数が本番コードに混入していない
- [ ] レート制限が必要なエンドポイントに設定済み

### 2-2. 認可ガードの実装パターン

```typescript
// lib/api-guard.ts の標準ガード関数
import { auth } from "@/lib/auth";
import { NextRequest, NextResponse } from "next/server";

/** 一般ユーザー認証 */
export async function requireAuth(req: NextRequest) {
  const session = await auth();
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return session;
}

/** 管理者のみ */
export async function requireAdmin(req: NextRequest) {
  const session = await auth();
  if (session?.user?.role !== "admin") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  return session;
}

/** Cron 専用（後述） */
export function requireCron(req: NextRequest) {
  const secret = req.headers.get("authorization");
  if (secret !== `Bearer ${process.env.CRON_SECRET}`) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
}

/** 開発環境のみ — 本番では絶対に使わない */
export function devOnly(req: NextRequest) {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json({ error: "Not Found" }, { status: 404 });
  }
}
```

### 2-3. セキュリティ設定確認

- [ ] `Content-Security-Policy` ヘッダーが設定されている（`next.config.js`）
- [ ] `NEXTAUTH_URL` が本番 URL に設定されている
- [ ] JWT / セッション有効期限が適切に設定されている
- [ ] SQL インジェクション対策（ORM を使用、または Prepared Statement）
- [ ] `console.log` に機密情報（トークン・パスワード）が混入していない

```bash
# 機密情報の console.log 混入チェック
grep -rn "console.log.*token\|console.log.*password\|console.log.*secret" \
  src/ server/ app/ --include="*.ts" --include="*.tsx"
```

---

## 3. Cron ジョブ保護

### 3-1. Cron エンドポイントの追加手順

```typescript
// app/api/cron/<name>/route.ts
import { NextRequest, NextResponse } from "next/server";
import { requireCron, safeError } from "@/lib/api-guard";

/**
 * GET /api/cron/<name>
 * Vercel Cron: 毎時0分実行
 * 保護: CRON_SECRET ヘッダー必須
 */
export async function GET(req: NextRequest) {
  // ⚠️ この行を省略すると無認証で誰でも叩ける
  const guard = requireCron(req);
  if (guard) return guard;

  try {
    // バッチ処理をここに実装
    const result = await doBatchWork();
    return NextResponse.json({ ok: true, result });
