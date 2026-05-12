---
name: devops-deploy-checklist
description: >-
  Vercel/GitHub Actions/Next.jsプロジェクトのデプロイ前チェックリストと運用パターン。
  コード品質・セキュリティ・環境変数・Cron保護・ブランチ戦略・CI/CDパイプラインを網羅した汎用ガイド。
category: devops
sourceSkillIds:
  - 78d0ca03
  - 1e512dda
  - fad3a941
  - 3c24f4d4
  - 943e5ff5
  - 7114bb14
  - ea263728
  - d4c547dc
  - a3480d4e
  - 03b8d29a
  - 38182ce6
  - 4e6ea1fd
  - 8534b8f3
  - '48612727'
  - 3e434ce8
generatedAt: '2026-05-11'
---

# DevOps デプロイチェックリスト

Vercel / GitHub Actions / Next.js スタックで本番リリースする際に **必ず通す**総合チェックリスト。  
新機能追加・大規模改修・初回リリースのいずれにも使える。

---

## 0. 事前確認：ブランチ・作業環境

```bash
# 現在のブランチを確認
git branch --show-current

# リモートとの差分を確認
git fetch origin
git status
```

- [ ] 正しいブランチで作業しているか（`main` への直接 push は明示的な許可がある場合のみ）
- [ ] `node_modules` が必要な場合はインストール済みか
- [ ] ローカルの `.env.local` が最新か（後述の環境変数チェックリストを参照）

> **鉄則**: コミットは小さく・こまめに push。タグ push は読み取り専用トークン環境では 403 になることがある（ローカル保持で OK）。

---

## 1. コード品質チェック

```bash
# TypeScript 型チェック
npm run check          # tsc --noEmit 相当

# テスト実行
npm run test           # Vitest / Jest

# ビルド確認（本番バンドルでエラーが出ないか）
npm run build

# APIバンドル再構築（サーバーコードを変更した場合）
npm run build:api
```

### チェック項目

- [ ] `npm run check` がエラー 0 件
- [ ] `npm run test` が全パス（スキップは理由をコメントに残す）
- [ ] `npm run build` がエラー 0 件
- [ ] サーバーコード変更時は `npm run build:api` を実行済み

### よくある TypeScript エラーと修正パターン

```typescript
// ❌ TS2322: string | null を string に代入
const id: string = row.id;

// ✅ null 合体演算子
const id: string = row.id ?? "";

// ✅ null チェック
if (row.id) {
  const id: string = row.id;
}

// ✅ フィルタで除外
const ids = rows.filter((r): r is typeof r & { id: string } => r.id !== null);
```

---

## 2. API ルートの認可ガード

**全 API ルートに認可ガードが付いているか** を確認する。付け忘れは無認証公開エンドポイントになる最重要バグ。

```bash
# 認可ガードが付いていない API ルートを検出
grep -rL "requireAuth\|requireAdmin\|requireCron\|devOnly\|verifySignature" \
  app/api/ --include="*.ts" --include="*.tsx"
```

### ガードの種類と使い分け

| ガード | 用途 |
|--------|------|
| `requireAuth()` | 一般ユーザー認証が必要なエンドポイント |
| `requireAdmin()` | 管理者のみアクセス可能なエンドポイント |
| `requireCron()` | Vercel Cron からの呼び出しのみ許可 |
| `devOnly()` | 開発環境限定のデバッグエンドポイント |
| `verifySignature()` | Webhook など外部署名検証が必要なエンドポイント |

### Cron エンドポイントのテンプレート

```typescript
// app/api/cron/<name>/route.ts
import { NextResponse } from "next/server";
import { requireCron, safeError } from "@/lib/api-guard";

/**
 * GET /api/cron/<name>
 * Vercel Cron によって定期実行される。CRON_SECRET で保護。
 */
export async function GET(req: Request) {
  const guardError = requireCron(req);
  if (guardError) return guardError;

  try {
    // バッチ処理の実装
    const result = await runBatchJob();
    return NextResponse.json({ ok: true, result });
  } catch (err) {
    return safeError(err);
  }
}
```

```typescript
// lib/api-guard.ts（最小実装例）
import { NextResponse } from "next/server";

export function requireCron(req: Request): NextResponse | null {
  const authHeader = req.headers.get("authorization");
  const expected = `Bearer ${process.env.CRON_SECRET}`;
  if (authHeader !== expected) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return null;
}

export function safeError(err: unknown): NextResponse {
  const message = err instanceof Error ? err.message : "Internal Server Error";
  console.error(err);
  return NextResponse.json({ error: message }, { status: 500 });
}
```

```json
// vercel.json（Cron スケジュール定義）
{
  "crons": [
    {
      "path": "/api/cron/<name>",
      "schedule": "0 * * * *"
    }
  ]
}
```

### チェック項目

- [ ] 全 API ルートに適切なガードが付いている
- [ ] Cron エンドポイントには `requireCron()` ガードが付いている
- [ ] `vercel.json` の `crons` にスケジュールが登録されている
- [ ] `CRON_SECRET` が全環境（本番・プレビュー）に設定されている

---

## 3. 環境変数チェックリスト

### 必須変数の確認

```bash
# ローカル環境の変数確認（値は表示しない）
cat .env.local | grep -v "^#" | cut -d= -f1

# 本番環境の変数一覧（Vercel CLI）
vercel env ls --environment=production
```

### 変数カテゴリ別チェック

| カテゴリ | 変数例 | 生成方法 |
|----------|--------|----------|
| 認証・暗号化 | `AUTH_SECRET` / `NEXTAUTH_SECRET` | `openssl rand -base64 32` |
| データベース | `DATABASE_URL` | Supabase / PlanetScale ダッシュボード |
| Cron 保護 | `CRON_SECRET` | `openssl rand -hex 32` |
| 外部 API | `STRIPE_SECRET_KEY` など | 各サービスのダッシュボード |
| Webhook | `WEBHOOK_SECRET` | 各サービスのダッシュボード |

### 新規シークレット生成

```bash
# 汎用シークレット（Base64）
openssl rand -
