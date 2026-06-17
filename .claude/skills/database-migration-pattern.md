---
name: database-migration-pattern
description: >-
  Supabase/PostgreSQL/TypeScriptプロジェクトにおけるDBスキーマ設計・マイグレーション・RLS・ロール管理・型安全クエリパターンの包括的ガイド。テーブル設計の原則からRLSポリシー実装、Supabase型生成、ロール階層管理、冪等マイグレーション、スキーマ適応クエリまで一貫した実装パターンを提供する。本番DBへのマイグレーション適用手順・列不在時のServer
  Component安全処理・外部API同期テーブル設計・Webhook冪等性管理も含む。あらゆる規模のSaaSアプリケーションで再利用可能。Drizzle
  ORMパターンも付録として収録。
category: database
version: 3
changedAt: '2026-05-27T14:00:00.000Z'
changeType: merge
changeReason: >-
  glabaffil版(v2, 2026-05-22)を基準に、external-api-resilient-sync(KOKOKARA,
  2026-05-27)の 外部API同期テーブル設計・冪等性パターンを統合。drizzle-query-patterns(AISaaS)のORM比較、
  make-webhook-integration(aegis)のWebhook冪等性テーブル、monthly-security-review(AISaaS)の
  RLS監査チェックリスト、new-schema/new-crud/new-master-table(AISaaS)のスキャフォールドパターン、
  skills(glabaffil)のemail_template_overridesテーブル設計を吸収。ai-employee-runner(ai-company)は
  データベース関連要素なしのため棄却（エージェントランナーのロジック層に限定）。
sourceSkillIds:
  - a4ed7a36
  - a8640f40
  - 12ba1851
  - 2db98959
  - '35616135'
  - 91d394af
  - 82eca7f0
  - ea609157
  - a2d648e3
  - b7f939a7
  - add2c175
  - 46cf8d7e
  - edc9c129
  - daf97aca
  - 5e853d72
  - cc21eb64
  - b77fd81f
  - 32ede95b
  - 2d1c64c8
  - d676f894
  - d6637bb5
  - d95d73f8
  - 4adc4e5c
  - 806b5b83
  - cf920cdb
  - 0ee5a1e8
  - d51e038f
  - c5bded6d
  - '89024666'
  - a3e04bbe
  - 41f175ef
  - ddf22374
  - bc81c831
  - 85eeda05
  - 8e4316ac
  - 033f390d
  - 8598329c
generatedAt: '2026-06-17'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-27T13:30:00.000Z'
adoptedFromArchive:
  - archive/skills/external-api-resilient-sync.md
  - archive/skills/email-template-system.md
  - archive/skills/database-migration-pattern.md
  - archive/skills/ai-employee-runner.md
  - archive/skills/drizzle-query-patterns.md
  - archive/skills/make-webhook-integration.md
  - archive/skills/monthly-security-review.md
  - archive/skills/new-crud.md
  - archive/skills/new-master-table.md
  - archive/skills/new-schema.md
---

# database-migration-pattern

Supabase/PostgreSQL/TypeScript プロジェクトにおける DB スキーマ設計・マイグレーション・RLS・ロール管理・型安全クエリ・外部 API 同期テーブル・Webhook 冪等性管理の包括的実装ガイド。

---

## 目次

1. [テーブル設計の原則](#1-テーブル設計の原則)
2. [冪等マイグレーション](#2-冪等マイグレーション)
3. [RLS ポリシー実装](#3-rls-ポリシー実装)
4. [ロール階層管理](#4-ロール階層管理)
5. [Supabase 型生成と型安全クエリ](#5-supabase-型生成と型安全クエリ)
6. [スキーマ適応クエリ（列不在時安全処理）](#6-スキーマ適応クエリ列不在時安全処理)
7. [外部 API 同期テーブル設計](#7-外部-api-同期テーブル設計)
8. [Webhook 冪等性管理テーブル](#8-webhook-冪等性管理テーブル)
9. [スキャフォールドパターン（new-schema / new-crud）](#9-スキャフォールドパターン)
10. [RLS 月次監査チェックリスト](#10-rls-月次監査チェックリスト)
11. [付録：Drizzle ORM クエリパターン](#11-付録drizzle-orm-クエリパターン)

---

## 1. テーブル設計の原則

### 基本カラムセット

すべてのテーブルに以下を付与する。

```sql
id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
created_at  timestamptz NOT NULL DEFAULT now(),
updated_at  timestamptz NOT NULL DEFAULT now()
```

`updated_at` は trigger で自動更新する（後述）。

### updated_at 自動更新 Trigger（共通）

```sql
-- 一度だけ定義し、複数テーブルで再利用
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- テーブルごとに適用
CREATE TRIGGER trg_set_updated_at
BEFORE UPDATE ON public.your_table
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
```

### soft delete パターン

```sql
deleted_at  timestamptz,          -- NULL = 有効
is_archived boolean NOT NULL DEFAULT false
```

View で隠蔽する場合：

```sql
CREATE VIEW public.active_items AS
SELECT * FROM public.items WHERE deleted_at IS NULL;
```

### 列名・型の命名規則

| 種別 | 規則 | 例 |
|------|------|----|
| 外部キー | `{entity}_id` | `user_id uuid REFERENCES auth.users` |
| フラグ | `is_` prefix | `is_active`, `is_verified` |
| 金額 | `bigint`（cent 単位）| `price_cents bigint` |
| JSON 拡張 | `jsonb` + GIN index | `metadata jsonb DEFAULT '{}'` |
| Enum 的区分 | `text` + CHECK | `status text CHECK (status IN ('active','inactive'))` |

---

## 2. 冪等マイグレーション

### ファイル命名規則

```
supabase/migrations/
  YYYYMMDDHHMMSS_<verb>_<subject>.sql
  例: 20260520120000_add_role_to_users.sql
```

### 冪等パターン集

```sql
-- テーブル追加
CREATE TABLE IF NOT EXISTS public.plans (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- 列追加
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'member';

-- インデックス追加
CREATE INDEX IF NOT EXISTS idx_users_role ON public.users(role);

-- 列削除（存在確認付き）
DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name   = 'users'
      AND column_name  = 'legacy_field'
  ) THEN
    ALTER TABLE public.users DROP COLUMN legacy_field;
  END IF;
END $$;

-- Enum 値追加（PostgreSQL は冪等に追加できないため存在確認）
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_enum
    WHERE enumlabel = 'suspended'
      AND enumtypid = 'public.user_status'::regtype
  ) THEN
    ALTER TYPE public.user_status ADD VALUE 'suspended';
  END IF;
END $$;

-- ポリシー再作成（DROP IF EXISTS → CREATE）
DROP POLICY IF EXISTS "users_select_own" ON public.users;
CREATE POLICY "users_select_own" ON public.users
  FOR SELECT USING (auth.uid() = id);
```

### 本番 DB 適用手順
