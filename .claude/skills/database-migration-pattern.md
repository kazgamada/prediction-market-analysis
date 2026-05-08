---
name: database-migration-pattern
description: >-
  Supabase/PostgreSQL/TypeScriptプロジェクトにおけるDBスキーマ設計・マイグレーション・RLS・ロール管理・型安全クエリパターンの包括的ガイド。テーブル設計の原則からRLSポリシー実装、Supabase型生成、ロール階層管理まで一貫した実装パターンを提供する。あらゆる規模のSaaSアプリケーションで再利用可能。
category: database
sourceSkillIds:
  - 9d448d77
  - 5bef0317
  - 7d0415e4
  - cbdc86c8
  - e5845d0c
  - 1995fa50
  - 25d8fc4d
  - c514c569
  - 96d3d7f7
  - 21b9c181
  - cf410174
  - 1d622eda
  - 6c2269d6
  - e56bc2e3
  - e4a08f9b
  - d230fdc8
  - 82268d2d
  - 83707fc9
  - b044825d
  - cf418dd7
  - 2939a8d3
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
  - 136b5c66
  - 3016ef88
  - 5dd236b5
  - 3b5ef258
  - 55fed88d
  - 004ef737
  - 6e2cc8c0
  - c4f4a058
  - 1c4515e3
  - 70a5bdd1
  - '80e90864'
  - 518cc299
  - 316229ba
  - b0f4688e
  - 7fa58c94
  - 581cb13e
  - e9c92773
  - adcf7fac
  - c43446ec
  - f307026c
  - fb55253b
  - 9410bf95
  - 19905f06
  - d71ca081
  - 035f6180
  - 35b8d486
  - b1d00934
  - 8f37a730
  - 682b6d0a
  - b425c23e
  - e72ea834
  - a4a74c16
  - c102fab4
  - 483baeca
  - d61c19fe
  - 629b9751
  - cffa8a2f
  - a91bd380
  - 0c8fa595
  - 9b140983
  - 3e07c6ea
  - 1c090351
  - d9938ed7
  - 6acd0362
  - c169e753
  - 55a4242e
generatedAt: '2026-05-08'
---

# Database Migration Pattern — Supabase / PostgreSQL / TypeScript

## 概要

このSkillはSupabase + PostgreSQL + TypeScriptスタックにおける以下の領域を網羅します。

| 領域 | 内容 |
|------|------|
| スキーマ設計 | テーブル命名規則・カラム設計・インデックス戦略 |
| マイグレーション | ファイル管理・適用手順・ロールバック |
| RLS | ポリシー設計・デバッグ手順 |
| ロール管理 | 階層設計・権限付与パターン |
| 型安全クエリ | Supabase型生成・TypeScriptクライアントパターン |

---

## 1. テーブル設計の原則

### 命名規則

```sql
-- ✅ Good: snake_case、複数形、明確な名前
CREATE TABLE user_profiles (...)
CREATE TABLE subscription_plans (...)
CREATE TABLE audit_logs (...)

-- ❌ Bad: camelCase、単数形、曖昧な名前
CREATE TABLE UserProfile (...)
CREATE TABLE data (...)
```

### 標準カラム構成

すべてのテーブルに以下の基本カラムを含める：

```sql
CREATE TABLE example_table (
  -- Primary Key
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Ownership (マルチテナントの場合)
  user_id       UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  -- または
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,

  -- ビジネスデータ
  name          TEXT NOT NULL,
  description   TEXT,
  status        TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'inactive', 'deleted')),
  metadata      JSONB DEFAULT '{}'::jsonb,

  -- 監査カラム（必須）
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at    TIMESTAMPTZ  -- ソフトデリートの場合
);
```

### updated_at 自動更新トリガー

```sql
-- 汎用トリガー関数（一度定義すれば全テーブルで再利用）
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 各テーブルに適用
CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON example_table
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
```

### インデックス戦略

```sql
-- 外部キーには必ずインデックス
CREATE INDEX idx_example_user_id ON example_table(user_id);
CREATE INDEX idx_example_org_id  ON example_table(organization_id);

-- 頻出フィルタ条件
CREATE INDEX idx_example_status  ON example_table(status)
  WHERE deleted_at IS NULL;  -- 部分インデックスで効率化

-- 複合インデックス（カーディナリティ高い列を先に）
CREATE INDEX idx_example_user_status
  ON example_table(user_id, status, created_at DESC);

-- JSONB検索
CREATE INDEX idx_example_metadata ON example_table USING GIN(metadata);

-- テキスト全文検索
CREATE INDEX idx_example_name_fts
  ON example_table USING GIN(to_tsvector('japanese', name));
```

---

## 2. マイグレーション管理

### ファイル命名規則

```
supabase/migrations/
├── 20240101000000_init_schema.sql          # 初期スキーマ
├── 20240115120000_add_organizations.sql    # 機能追加
├── 20240120093000_add_rls_policies.sql     # RLS追加
├── 20240201150000_add_subscription.sql     # サブスク機能
└── 20240210080000_alter_users_add_role.sql # カラム追加
```

**命名規則**: `YYYYMMDDHHMMSS_<動詞>_<対象>_<内容>.sql`

### マイグレーションファイルの構造

```sql
-- Migration: 20240201150000_add_subscription.sql
-- Description: サブスクリプション管理テーブルの追加
-- Author: team
-- Depends on: 20240115120000_add_organizations.sql

BEGIN;

-- ========================================
-- テーブル作成
-- ========================================
CREATE TABLE subscription_plans (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  price_jpy   INTEGER NOT NULL CHECK (price_jpy >= 0),
  features    JSONB NOT NULL DEFAULT '[]'::jsonb,
  is_active   BOOLEAN NOT NULL DEFAULT true,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_subscriptions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  plan_id     UUID NOT NULL REFERENCES subscription_plans(id),
  status      TEXT NOT NULL DEFAULT 'active'
              CHECK (status IN ('active', 'cancelled', 'expired', 'trial')),
  starts_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ends_at     TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id)  -- ユーザーは1プランのみ
);

-- ========================================
-- インデックス
-- ========================================
CREATE INDEX idx_user_subscriptions_user_id ON user_subscriptions(user_id);
CREATE INDEX idx_user_subscriptions_status  ON user_subscriptions(status)
  WHERE status = 'active';

-- ========================================
-- トリガー
-- ========================================
CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON subscription_plans
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON user_subscriptions
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ========================================
-- RLS
-- ========================================
ALTER TABLE subscription_plans    ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_subscriptions    ENABLE ROW LEVEL SECURITY;

-- plans は全員読める
CREATE POLICY "plans_select_all" ON subscription_plans
  FOR SELECT USING (is_active = true);

-- subscriptions は本人のみ
CREATE POLICY "subscriptions_select_own" ON user_subscriptions
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "subscriptions_insert_own" ON user_subscriptions
  
