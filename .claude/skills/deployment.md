---
name: deployment-vercel-express-serverless
description: >-
  Express サーバーを Vercel サーバーレス関数としてデプロイする汎用パターン。 esbuild でバンドルして api/server.js
  を生成・git コミットする必要がある。 「Vercel で /api/* が
  404」「ERR_MODULE_NOT_FOUND」「api/server.js が認識されない」 「Function Runtimes
  の設定ミス」といった問題のときに参照する。 Next.js/TypeScript プロジェクトで Express バックエンドを Vercel
  にデプロイする際の 標準アプローチとして使用する。
category: deployment
abstractionLevel: 2
targetStack:
  - Next.js
  - TypeScript
  - Express
  - Vercel
version: 1
effectiveTimestamp: '2026-05-28T12:00:00.000Z'
sourceSkills:
  - vercel-express-serverless (medical-learning-ai)
sourceSkillIds:
  - 2d347268
generatedAt: '2026-06-17'
---

# Vercel + Express サーバーレスデプロイパターン

## 概要

Express サーバーを Vercel のサーバーレス関数として動かすには、
通常の `node server.js` 起動ではなく、**Vercel サーバーレス関数形式**に変換する必要がある。
esbuild でバンドルし、生成した `api/server.js` を Git にコミットしてデプロイする。

---

## なぜこのパターンが必要か

| 問題 | 原因 | このパターンでの解決 |
|------|------|---------------------|
| `/api/*` が 404 | `api/` ディレクトリに関数ファイルがない | esbuild でバンドルして `api/server.js` を生成 |
| `ERR_MODULE_NOT_FOUND` | ESM/CJS の混在、依存解決失敗 | esbuild の `bundle: true` で依存を一本化 |
| `api/server.js` が認識されない | Git 未コミット or `vercel.json` の設定漏れ | CI/CD 前にビルドしてコミット |
| Cold Start が遅い | 依存が多い | esbuild の minify + tree-shaking |

---

## ディレクトリ構成

```
project-root/
├── src/
│   └── server/
│       └── index.ts          # Express アプリ本体
├── api/
│   └── server.js             # ★ esbuild が生成する成果物（Git コミット必須）
├── vercel.json               # ルーティング設定
├── package.json
└── scripts/
    └── build-api.ts          # ビルドスクリプト（任意）
```

> **重要**: `api/server.js` は自動生成ファイルだが、Vercel はこれを参照するため
> `.gitignore` に追加してはいけない。

---

## 実装手順

### 1. Express アプリをサーバーレス形式でエクスポート

```typescript
// src/server/index.ts
import express from 'express';

const app = express();

app.use(express.json());

// --- ルート定義 ---
app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok' });
});

app.post('/api/example', async (req, res) => {
  const { data } = req.body;
  res.json({ received: data });
});

// ローカル開発時はサーバーを起動
if (process.env.NODE_ENV !== 'production' || !process.env.VERCEL) {
  const PORT = process.env.PORT ?? 3001;
  app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

// Vercel サーバーレス関数としてエクスポート
export default app;
```

### 2. esbuild でバンドル

```typescript
// scripts/build-api.ts
import { build } from 'esbuild';
import { resolve } from 'path';

async function buildApi() {
  await build({
    entryPoints: [resolve('src/server/index.ts')],
    outfile: resolve('api/server.js'),
    bundle: true,          // 依存を単一ファイルに同梱
    platform: 'node',
    target: 'node18',
    format: 'cjs',         // Vercel サーバーレスは CommonJS
    minify: true,          // Cold Start 軽減
    sourcemap: false,      // 本番では不要
    external: [            // Vercel 環境に既存の依存はバンドルから除外
      // 'sharp',           // バイナリ依存は外す例
    ],
  });
  console.log('✅ api/server.js generated');
}

buildApi().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

```json
// package.json（抜粋）
{
  "scripts": {
    "build:api": "ts-node scripts/build-api.ts",
    "build": "npm run build:api && next build",
    "dev": "concurrently \"next dev\" \"ts-node src/server/index.ts\""
  },
  "devDependencies": {
    "esbuild": "^0.20.0",
    "ts-node": "^10.9.0"
  }
}
```

### 3. vercel.json の設定

```json
// vercel.json
{
  "version": 2,
  "builds": [
    {
      "src": "api/server.js",
      "use": "@vercel/node"
    },
    {
      "src": "package.json",
      "use": "@vercel/next"
    }
  ],
  "routes": [
    {
      "src": "/api/(.*)",
      "dest": "/api/server.js"
    }
  ]
}
```

> **ポイント**: `/api/(.*)` を `api/server.js` に向けることで、
> Express の内部ルーターが `/api/health` や `/api/example` を処理できる。

### 4. Git コミットと CI/CD

```bash
# デプロイ前に必ずビルドしてコミット
npm run build:api
git add api/server.js
git commit -m "build: update api/server.js bundle"
git push
```

CI（GitHub Actions）で自動化する場合:

```yaml
# .github/workflows/deploy.yml
name: Deploy to Vercel

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '18'
      - run: npm ci
      - run: npm run build:api
      - run: git config user.email "ci@example.com"
      - run: git config user.name "CI Bot"
      - run: |
          git add api/server.js
          git diff --staged --quiet || git commit -m "ci: rebuild api/server.js"
          git push
      - uses: amondnet/vercel-action@v25
        with:
          vercel-token: ${{ secrets.VERCEL_
