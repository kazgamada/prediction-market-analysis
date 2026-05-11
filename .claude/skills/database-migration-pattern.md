---
name: database-migration-pattern
description: >-
  Supabase/PostgreSQL/TypeScriptプロジェクトにおけるDBスキーマ設計・マイグレーション・RLS・ロール管理・型安全クエリパターンの包括的ガイド。
  Supabase生SQLマイグレーション、Drizzle ORM、冪等ALTER TABLE、シードデータ、月次セキュリティレビュー、
  完全CRUDスキャフォールドまで、あらゆる規模のSaaSアプリケーションで再利用可能な一貫した実装パターンを提供する。
category: database
sourceSkillIds:
  - 9d448d77
  - fecfeef9
  - 5bef0317
  - 7d0415e4
  - cbdc86c8
  - e5845d0c
  - 1995fa50
  - 8774c926
  - 25d8fc4d
  - c514c569
  - 28a849f8
  - 96d3d7f7
  - 21b9c181
  - cf410174
  - 1d622eda
  - 6c2269d6
  - a30701d8
  - e56bc2e3
  - e4a08f9b
  - d230fdc8
  - 82268d2d
  - 83707fc9
  - b044825d
  - cf418dd7
  - 2939a8d3
  - 167901c8
  - fc4cfdc8
  - ea286644
  - 2046db07
  - b5039c50
  - 4c136abd
  - 1b52eb9e
  - 30f4ddfd
  - c195dbea
  - 1a7e6aed
  - 508fa540
  - fb628cbd
  - '95e52879'
  - '47e09525'
  - 9070c634
  - ffb93ef2
  - eb8c7746
  - 136b5c66
  - 3016ef88
  - 5dd236b5
  - 3b5ef258
  - 55fed88d
  - 004ef737
  - 6e2cc8c0
  - c4f4a058
  - 1c4515e3
  - ac45e275
  - 70a5bdd1
  - c5c91622
  - '80e90864'
  - fffdba41
  - 518cc299
  - 59b5bc26
  - '49426722'
  - 316229ba
  - b0f4688e
  - 7fa58c94
  - 581cb13e
  - e9c92773
  - adcf7fac
  - faafbd6f
  - c43446ec
  - f307026c
  - fb55253b
  - 9410bf95
  - 19905f06
  - d71ca081
  - 035f6180
  - 35b8d486
  - 2a681626
  - b1d00934
  - 8f37a730
  - 682b6d0a
  - b425c23e
  - e72ea834
  - a4a74c16
  - c102fab4
  - 483baeca
  - d61c19fe
  - 1a132a53
  - 629b9751
  - 66816c66
  - cffa8a2f
  - 115e051f
  - a91bd380
  - 0c8fa595
  - 9b140983
  - 3e07c6ea
  - 1c090351
  - d9938ed7
  - 6acd0362
  - c169e753
  - 55a4242e
  - 82b8cdd0
generatedAt: '2026-05-11'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-10T19:11:30+00:00'
adoptedFromArchive:
  - >-
    archive/prediction-market-analysis/.claude/skills/database-migration-pattern.md
  - archive/aegis-market-os/.claude/skills/auth-role-demo-mode.md
  - archive/aegis-market-os/.claude/skills/drizzle-pg-patterns.md
  - archive/ai-company/.claude/skills/ai-employee-runner/SKILL.md
  - archive/ai-company/.claude/skills/schema-migration-idempotent/SKILL.md
  - archive/ai-company/.claude/skills/seed-demo-data/SKILL.md
  - archive/ai-company/.claude/skills/stripe-plan-setup/SKILL.md
  - archive/AISaaS/.claude/skills/drizzle-query-patterns.md
  - archive/AISaaS/.claude/skills/monthly-security-review.md
  - archive/AISaaS/.claude/skills/new-crud.md
---

# Database Migration Pattern

## 📋 目次

1. [テーブル設計の原則](#1-テーブル設計の原則)
2. [マイグレーション戦略](#2-マイグレーション戦略)
   - 2a. Supabase 生 SQL マイグレーション
   - 2b. Drizzle ORM スキーマ定義
   - 2c. 冪等 ALTER TABLE（ランタイムマイグレーション）
3. [RLS ポリシー実装](#3-rls-ポリシー実装)
4. [ロール階層管理](#4-ロール階層管理)
5. [型安全クエリパターン（Drizzle ORM）](#5-型安全クエリパターンdrizzle-orm)
6. [シードデータ管理](#6-シードデータ管理)
7. [完全 CRUD スキャフォールド](#7-完全-crud-スキャフォールド)
8. [月次セキュリティレビュー](#8-月次セキュリティレビュー)
9. [チェックリスト](#9-チェックリスト)

---

## 1. テーブル設計の原則

### 必須カラム（全テーブル共通）

```sql
-- すべてのテーブルに含めるべき標準カラム
id          uuid        PRIMARY KEY DEFAULT gen_random_uuid()
created_at  timestamptz NOT NULL DEFAULT now()
updated_at  timestamptz NOT NULL DEFAULT now()
```

### updated_at 自動更新トリガー

```sql
-- 共通トリガー関数（一度だけ定義）
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 各テーブルにアタッチ
CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON your_table
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

### 命名規則

| 対象 | 規則 | 例 |
|------|------|-----|
| テーブル名 | snake_case・複数形 | `user_profiles`, `org_members` |
| カラム名 | snake_case | `created_at`, `is_active` |
| 外部キー | `{参照テーブル単数形}_id` | `user_id`, `org_id` |
| インデックス | `idx_{テーブル}_{カラム}` | `idx_posts_user_id` |
| RLS ポリシー | `{操作}_{テーブル}_{主体}` | `select_posts_owner` |

### スキーマ設計パターン

```sql
-- マルチテナント SaaS の典型構造
CREATE TABLE organizations (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text        NOT NULL,
  slug        text        NOT NULL UNIQUE,
  plan        text        NOT NULL DEFAULT 'free',
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE org_members (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id     uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role        text        NOT NULL DEFAULT 'member', -- 'owner' | 'admin' | 'member' | 'viewer'
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE(org_id, user_id)
);

CREATE INDEX idx_org_members_org_id  ON org_members(org_id);
CREATE INDEX idx_org_members_user_id ON org_members(user_id);
```

---

## 2. マイグレーション戦略

### 2a. Supabase 生 SQL マイグレーション

```
supabase/migrations/
  YYYYMMDDHHMMSS_create_initial_schema.sql
  YYYYMMDDHHMMSS_add_user_profiles.sql
  YYYYMMDDHHMMSS_add_rls_policies.sql
```

**マイグレーションファイルの構造テンプレート**

```sql
-- supabase/migrations/20240101000000_create_posts.sql

-- ▼ UP（適用）
BEGIN;

CREATE TABLE IF NOT EXISTS posts (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  author_id   uuid        NOT NULL REFERENCES auth.users(id),
  title       text        NOT NULL,
  body        text,
  status      text        NOT NULL DEFAULT 'draft', -- 'draft' | 'published' | 'archived'
  published_at timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_posts_org_id    ON posts(org_id);
CREATE INDEX idx_posts_author_id ON posts(author_id);
CREATE INDEX idx_posts_status    ON posts(status) WHERE status = 'published';

CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON posts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;
```

**マイグレーション実行コマンド**

```bash
# ローカル適用
supabase db push

# 新規マイグレーション作成
supabase migration new add_posts_table

# 差分確認
supabase db diff --use-migra

# リモート（本番）への適用
supabase db push --db-url "$SUPABASE_DB_URL"
```

### 2b. Drizzle ORM スキーマ定義

> **PostgreSQL プロジェクト必須**: `pgTable` / `pgEnum` のみ使用。`mysqlTable` / `mysqlEnum` は使わない。

```ts
// db/schema.ts
import {
  boolean, index, integer, numeric, pgEnum, pgTable,
  serial, text, timestamp, uuid, varchar
} from "drizzle-orm/pg-core";
import { sql } from "drizzle-orm";

// ── Enum 定義 ──────────────────────────────────────────
export const roleEnum    = pgEnum("role",    ["owner", "admin", "member", "viewer"]);
export const statusEnum  = pgEnum("status",  ["draft", "published", "archived"]);
export const planEnum    = pgEnum("plan",    ["free", "pro", "enterprise"]);

// ── テーブル定義 ────────────────────────────────────────
export const organizations = pgTable("organizations", {
  id:        uuid("id").primaryKey
