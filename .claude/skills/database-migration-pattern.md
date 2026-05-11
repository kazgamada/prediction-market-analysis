---
name: database-migration-pattern
description: >-
  Supabase/PostgreSQL/TypeScriptプロジェクトにおけるDBスキーマ設計・マイグレーション・RLS・ロール管理・型安全クエリパターンの包括的ガイド。テーブル設計の原則からRLSポリシーの実装、Drizzle/Supabase
  Clientによる型安全なクエリ、ロール階層管理まで、一貫した実装パターンを提供する。
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
---

# Database Migration Pattern — Supabase / PostgreSQL / TypeScript

## 概要

このSkillは以下の領域を統合的にカバーします：

1. **スキーマ設計** — テーブル設計の原則・命名規則・共通カラム
2. **マイグレーション管理** — Supabase CLI / Drizzle によるバージョン管理
3. **RLS（Row Level Security）** — ポリシー設計パターンと検証手順
4. **ロール階層** — Supabase における認証ロールの管理
5. **型安全クエリ** — TypeScriptと統合したクエリパターン
6. **パフォーマンス** — インデックス設計・クエリ最適化

---

## 1. スキーマ設計の原則

### 1.1 共通カラム（すべてのテーブルに含める）

```sql
-- すべてのテーブルに以下を付与する
id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
created_at  timestamptz NOT NULL    DEFAULT now(),
updated_at  timestamptz NOT NULL    DEFAULT now()
```

`updated_at` は自動更新トリガーで管理する：

```sql
-- 共通トリガー関数（マイグレーション初期に1回定義）
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 各テーブルへ適用
CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON public.your_table
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
```

### 1.2 命名規則

| 対象 | 規則 | 例 |
|------|------|-----|
| テーブル | `snake_case` 複数形 | `user_profiles`, `lesson_sessions` |
| カラム | `snake_case` | `first_name`, `created_at` |
| 外部キー | `{参照テーブル単数形}_id` | `user_id`, `organization_id` |
| インデックス | `idx_{table}_{column(s)}` | `idx_profiles_user_id` |
| RLSポリシー | `{action}_{対象}_{条件}` | `select_own_records`, `insert_org_member` |

### 1.3 典型的なマルチテナント構成

```sql
-- 組織テーブル（マルチテナントの起点）
CREATE TABLE public.organizations (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text        NOT NULL,
  slug        text        UNIQUE NOT NULL,
  plan        text        NOT NULL DEFAULT 'free',
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- ユーザープロフィール（auth.usersと1:1）
CREATE TABLE public.profiles (
  id          uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  org_id      uuid        REFERENCES public.organizations(id) ON DELETE SET NULL,
  role        text        NOT NULL DEFAULT 'member' CHECK (role IN ('owner','admin','member')),
  display_name text,
  avatar_url  text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
```

---

## 2. マイグレーション管理

### 2.1 Supabase CLI によるワークフロー

```bash
# 新しいマイグレーション作成
supabase migration new add_user_profiles

# ローカルDBへ適用
supabase db reset          # 全マイグレーション再適用（開発時）
supabase migration up      # 差分のみ適用

# 本番へデプロイ
supabase db push           # リモートへ push

# 現在の状態をファイルへ pull（既存DBからの逆生成）
supabase db pull
```

### 2.2 マイグレーションファイルの構成規則

```
supabase/migrations/
  20240101000000_init_schema.sql          # 初期スキーマ
  20240102000000_add_organizations.sql    # 機能追加
  20240103000000_add_rls_policies.sql     # RLS設定
  20240104000000_add_indexes.sql          # パフォーマンス改善
```

**各ファイルのテンプレート：**

```sql
-- Migration: 20240102000000_add_organizations.sql
-- Description: 組織テーブルとプロフィールテーブルを追加

BEGIN;

-- スキーマ変更
CREATE TABLE IF NOT EXISTS public.organizations ( ... );

-- トリガー
CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON public.organizations
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- RLS 有効化（必ずセットで行う）
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;

COMMIT;
```

### 2.3 Drizzle ORM を使う場合

```typescript
// drizzle.config.ts
import { defineConfig } from 'drizzle-kit';

export default defineConfig({
  schema: './src/db/schema.ts',
  out: './supabase/migrations',
  dialect: 'postgresql',
  dbCredentials: {
    url: process.env.DATABASE_URL!,
  },
});
```

```typescript
// src/db/schema.ts
import { pgTable, uuid, text, timestamptz } from 'drizzle-orm/pg-core';
import { sql } from 'drizzle-orm';

export const organizations = pgTable('organizations', {
  id: uuid('id').primaryKey().defaultRandom(),
  name: text('name').notNull(),
  slug: text('slug').unique().notNull(),
  createdAt: timestamptz('created_at').notNull().default(sql`now()`),
  updatedAt: timestamptz('updated_at').notNull().default(sql`now()`),
});

export const profiles = pgTable('profiles', {
  id: uuid('id').primaryKey().references(() => authUsers.id, { onDelete: 'cascade' }),
  orgId: uuid('org_id').references(() => organizations.id, { onDelete: 'set null' }),
  role: text('role').notNull().default('member'),
  displayName: text('display_name'),
});
```

---

## 3. RLS（Row Level Security）

### 3.1 設計の基本原則

```sql
-- ① すべてのテーブルで RLS を有効化（デフォルト拒否）
ALTER TABLE public.your_table ENABLE ROW LEVEL SECURITY;

-- ② FORCE ROW LEVEL SECURITY でサービスロールも制御
