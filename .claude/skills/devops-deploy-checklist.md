---
category: devops
sourceSkillIds:
  - 78d0ca03
  - e903b12c
  - bb27779e
  - 7d3868a0
  - 72d34ddf
  - fad3a941
  - 3c24f4d4
  - 943e5ff5
  - 7114bb14
  - ea263728
  - 1e512dda
  - d4c547dc
  - a3480d4e
  - 03b8d29a
  - 38182ce6
  - 4e6ea1fd
  - 8534b8f3
  - '48612727'
  - 3e434ce8
  - 3859fc95
generatedAt: '2026-05-23'
---
```yaml
---
name: devops-deploy-checklist
description: >-
  Vercel/GitHub Actions/Next.js プロジェクトのデプロイ前チェックリストと運用ガイド。
  セキュリティガード漏れ・環境変数不備・Cron 設定ミス・認証系バグなど、
  過去の実障害から抽出したチェック項目を網羅。新機能リリース前・認証系修正時・
  デプロイ異常感知時に必ず参照すること。
category: DevOps・CI
---
```

# DevOps デプロイチェックリスト

Vercel / GitHub Actions / Next.js プロジェクトで **本番 push 前に必ず実行**するチェックリスト＆運用ガイド。  
「⭐ 代表進化版」の改良点（インシデント再発防止・Cron ガード強制・認証系ガード網羅）をすべて取り込んでいる。

---

## 0. このSkillを使うタイミング

| タイミング | 参照セクション |
|---|---|
| 新機能・大規模改修を本番投入する前 | §1 コード、§2 環境変数、§3 CI/CD |
| Cron ジョブを追加・変更する前 | §4 Cron |
| 認証系（Auth / Session）を触った後 | §5 認証 |
| 「デプロイが届いていない？」と感じたとき | §6 トラブルシュート |
| Fly.io にデプロイする場合 | §7 Fly.io |

---

## 1. コード関連チェックリスト

### 1-1. API ルートの認可ガード

```bash
# 認可ガードが付いていない API ルートを検出
grep -rL "requireAuth\|requireAdmin\|requireCron\|devOnly\|verifySignature" \
  app/api/ --include="*.ts" | grep -v "__tests__"
```

- [ ] 新規 API ルートすべてに認可ガード（`requireAuth` / `requireAdmin` / `requireCron` / `devOnly` / `verifySignature`）が付いている
- [ ] Public にすべき意図がある場合はコメントで明記している
  ```typescript
  // PUBLIC: Stripe webhook — verifySignature で署名検証済み
  ```

### 1-2. 認可ガードの実装パターン

```typescript
// lib/api-guard.ts（共通ガード例）
import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";

/** 未認証なら 401 を返す。認証済みなら session を返す */
export async function requireAuth(req: NextRequest) {
  const session = await auth();
  if (!session?.user) {
    return { error: NextResponse.json({ error: "Unauthorized" }, { status: 401 }) };
  }
  return { session };
}

/** 管理者のみ許可 */
export async function requireAdmin(req: NextRequest) {
  const { session, error } = await requireAuth(req);
  if (error) return { error };
  if (session!.user.role !== "admin") {
    return { error: NextResponse.json({ error: "Forbidden" }, { status: 403 }) };
  }
  return { session };
}

/** Vercel Cron からのリクエストのみ許可 */
export function requireCron(req: NextRequest) {
  const secret = req.headers.get("authorization");
  if (secret !== `Bearer ${process.env.CRON_SECRET}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return null; // null = OK
}

/** 開発環境のみ許可 */
export function devOnly() {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json({ error: "Not available in production" }, { status: 403 });
  }
  return null;
}
```

### 1-3. ハードコード秘密情報の検出

```bash
# 秘密情報の直書き検出（CI でも実行）
grep -rn "sk-\|Bearer \|password\s*=\s*['\"]" \
  --include="*.ts" --include="*.tsx" \
  --exclude-dir=node_modules --exclude-dir=.next .
```

- [ ] API キー・シークレット・DB 接続文字列がコードにハードコードされていない
- [ ] `.env.local` が `.gitignore` に含まれている

### 1-4. 型・ビルドエラー

```bash
npx tsc --noEmit          # 型エラー確認
npx next build            # ビルド成功確認（ローカル）
```

- [ ] TypeScript 型エラーがない
- [ ] `next build` がエラーなく完了する

---

## 2. 環境変数チェックリスト

### 2-1. 必須環境変数の確認

```typescript
// lib/env-check.ts — アプリ起動時に呼び出す
const REQUIRED_VARS = [
  "NEXTAUTH_SECRET",
  "NEXTAUTH_URL",
  "DATABASE_URL",
  "CRON_SECRET",
  // プロジェクト固有の必須変数をここに追加
] as const;

export function checkRequiredEnv() {
  const missing = REQUIRED_VARS.filter((key) => !process.env[key]);
  if (missing.length > 0) {
    throw new Error(`Missing required environment variables: ${missing.join(", ")}`);
  }
}
```

- [ ] Vercel Dashboard の **全環境**（Production / Preview / Development）に必要な環境変数がセットされている
- [ ] `CRON_SECRET` が設定されている（Cron を使う場合）
- [ ] `NEXTAUTH_URL` が本番 URL になっている（`http://localhost:3000` のままでない）
- [ ] 環境変数を追加・変更した後に **Redeploy** を実行した

### 2-2. Vercel 環境変数の確認手順

```
Vercel Dashboard → プロジェクト → Settings → Environment Variables
→ 各変数の「Environments」列で Production にチェックが入っているか確認
→ 変更後: Deployments → 最新デプロイ → … → Redeploy
```

---

## 3. CI/CD チェックリスト（GitHub Actions）

### 3-1. ワークフロー基本テンプレート

```yaml
# .github/workflows/deploy.yml
name: CI / Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: "npm"

      - run: npm ci

      - name: Type check
        run: npx tsc --noEmit

      - name: Lint
        run: npx eslint . --max-warnings=0

      - name: Test
        run: npm test -- --
