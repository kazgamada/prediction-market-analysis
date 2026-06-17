---
name: devops-deploy-checklist
description: >-
  Vercel / GitHub Actions / Next.js プロジェクト向けの汎用デプロイ運用チェックリスト。
  リリース前セキュリティ確認・環境変数セットアップ・Cron ジョブ追加・インシデント再発防止・
  自動デプロイ設定まで、デプロイライフサイクル全体をカバーする。 新機能リリース・環境立ち上げ・トラブル発生時に必ず参照すること。
category: devops
version: 1
effectiveTimestamp: '2026-05-23T00:00:00.000Z'
tags:
  - vercel
  - github-actions
  - nextjs
  - typescript
  - checklist
  - security
  - cron
  - incident-prevention
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
generatedAt: '2026-06-17'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-23T00:00:00.000Z'
adoptedFromArchive:
  - archive/skills/slideforgeai-incident-prevention.md
  - archive/skills/google-drive-shared-drive-setup.md
  - archive/skills/add-cron-job.md
  - archive/skills/auto-deploy-flyio.md
  - archive/skills/cron-sync.md
  - archive/skills/data-ingest-automation.md
  - archive/skills/pre-release-check.md
  - archive/skills/setup-env-vars.md
  - archive/skills/35-claude-code-on-web-workflow.md
  - archive/skills/add-test.md
---

# DevOps デプロイ チェックリスト

Vercel / GitHub Actions / Next.js プロジェクト共通の運用ガイド。  
**デプロイ前・環境立ち上げ・トラブル発生時**に本スキルを参照してください。

---

## 目次

1. [フェーズ概要](#1-フェーズ概要)
2. [リリース前チェック](#2-リリース前チェック)
3. [環境変数セットアップ](#3-環境変数セットアップ)
4. [Cron ジョブ追加](#4-cron-ジョブ追加)
5. [自動デプロイ設定](#5-自動デプロイ設定)
6. [インシデント再発防止](#6-インシデント再発防止)
7. [トラブルシューティング早見表](#7-トラブルシューティング早見表)

---

## 1. フェーズ概要

```
[コード変更]
    │
    ▼
[2. リリース前チェック]  ← 毎回必須
    │
    ▼
[3. 環境変数確認]        ← 新環境・棚卸し時
    │
    ▼
[4. Cron 設定]           ← 定期処理追加時
    │
    ▼
[5. 自動デプロイ]        ← git push → CI/CD
    │
    ▼
[本番稼働]
    │
    ▼
[6. インシデント防止監視]
```

---

## 2. リリース前チェック

> 新機能・大規模改修を本番投入する前に **必ず全項目を確認**する。

### 2-1. APIルート認可ガード

```bash
# 未保護ルートを検出するコマンド
grep -rL "requireAuth\|requireAdmin\|requireCron\|devOnly\|verifySignature" \
  app/api/ --include="route.ts"
```

**判定基準:**

| ルート種別 | 必須ガード |
|-----------|-----------|
| ユーザー操作系 | `requireAuth()` |
| 管理者操作系 | `requireAdmin()` |
| Cron ジョブ | `requireCron()` |
| 開発専用 | `devOnly()` |
| Webhook | `verifySignature()` |

- [ ] 新規 API ルートすべてに認可ガードが付いている
- [ ] `console.log` にユーザー個人情報・トークンが含まれていない
- [ ] シークレット値がソースコードにハードコードされていない

### 2-2. 環境変数

- [ ] `.env.example` が最新の状態に更新されている
- [ ] Vercel ダッシュボードの環境変数が `production` / `preview` / `development` 全環境に設定されている
- [ ] 新規追加の環境変数が `README` または `docs/` に記載されている

### 2-3. ビルド・型安全性

```bash
# ローカル確認コマンド
npm run build        # ビルドエラーがないこと
npm run type-check   # 型エラーがないこと
npm run lint         # Lint エラーがないこと
```

- [ ] `npm run build` が成功する
- [ ] TypeScript の型エラーがゼロ
- [ ] 不要な `// @ts-ignore` / `any` キャストが増えていない

### 2-4. セキュリティ

- [ ] 依存パッケージに Critical / High の脆弱性がない (`npm audit`)
- [ ] CORS 設定が意図した Origin のみ許可している
- [ ] Rate Limiting が API に適用されている（必要な場合）

### 2-5. ブランチ・Git

```bash
# 現在のブランチを確認
git branch --show-current

# main との差分を確認
git log main..HEAD --oneline
```

- [ ] 正しいブランチで作業している
- [ ] コミットメッセージが変更内容を説明している
- [ ] `main` への push は明示的な許可がある場合のみ

---

## 3. 環境変数セットアップ

> 新環境の立ち上げ・年次棚卸し・プロジェクト複製時に使用する。

### 3-1. 必須変数チェックリスト（汎用テンプレート）

```bash
# 設定済み変数を確認
vercel env ls
```

#### 認証・暗号化（最重要）

```bash
# AUTH_SECRET / NEXTAUTH_SECRET の生成
openssl rand -base64 32
```

- [ ] `DATABASE_URL` — DB接続文字列（例: Supabase > Settings > Database > Connection string）
- [ ] `AUTH_SECRET` / `NEXTAUTH_SECRET` — 32バイト以上のランダム文字列
- [ ] `NEXTAUTH_URL` — 本番URL（例: `https://your-app.vercel.app`）

#### 外部サービス連携

- [ ] OAuth クライアント ID / Secret（Google, GitHub 等）
- [ ] Stripe API キー（`sk_live_` が本番、`sk_test_` がテスト）
- [ ] メール送信サービスのキー（Resend, SendGrid 等）
- [ ] その他 SaaS API キー

#### Cron・内部通信

```bash
# CRON_SECRET の生成
openssl rand -hex 32
```

- [ ] `CRON_SECRET` — Cron エンドポイント保護用

### 3-2. Vercel への設定方法

```bash
# CLI で設定（推奨）
vercel env add DATABASE_URL production
vercel env add DATABASE_URL preview
vercel env add DATABASE_URL development

# または一括インポート
vercel env pull .env.local   # 既存環境から取得
vercel env push              # ローカルから反映
```

### 3-3. 環境変数の検証スクリプト

```typescript
// lib/env-check.ts
const REQUIRED_VARS = [
  'DATABASE_URL',
  'AUTH_SECRET',
  'NEXTAUTH_URL',
