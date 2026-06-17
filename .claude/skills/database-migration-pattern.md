---
name: database-migration-pattern
description: >-
  Supabase/PostgreSQL/TypeScriptプロジェクトにおけるDBスキーマ設計・マイグレーション・RLS・ロール管理・型安全クエリパターンの包括的ガイド。
  テーブル設計の原則からRLSポリシー実装、Supabase型生成、ロール階層管理、冪等マイグレーション、スキーマ適応クエリ、
  外部API同期、Webhook統合、セキュリティレビューまで一貫した実装パターンを提供する。 本番DBへのマイグレーション適用手順・列不在時のServer
  Component安全処理も含む。 あらゆる規模のSaaSアプリケーションで再利用可能。
category: database
version: 3
effectiveTimestamp: '2026-05-27T13:30:00.000Z'
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
---

# database-migration-pattern

Supabase / PostgreSQL / TypeScript プロジェクトにおける
DB スキーマ設計・マイグレーション・RLS・型安全クエリ・外部連携の包括ガイド。

---

## 目次

1. [テーブル設計の原則](#1-テーブル設計の原則)
2. [冪等マイグレーション](#2-冪等マイグレーション)
3. [RLS ポリシー実装](#3-rls-ポリシー実装)
4. [ロール階層管理](#4-ロール階層管理)
5. [Supabase 型生成・型安全クエリ](#5-supabase-型生成型安全クエリ)
6. [Drizzle ORM クエリパターン](#6-drizzle-orm-クエリパターン)
7. [スキーマ適応クエリ（列不在対応）](#7-スキーマ適応クエリ列不在対応)
8. [外部 API 同期パターン](#8-外部-api-同期パターン)
9. [Webhook 統合パターン](#9-webhook-統合パターン)
10. [月次セキュリティレビュー](#10-月次セキュリティレビュー)
11. [本番 DB マイグレーション適用手順](#11-本番-db-マイグレーション適用手順)

---

## 1. テーブル設計の原則

### 基本規約

| 項目 | 規約 |
|------|------|
| PK | `uuid` (default `gen_random_uuid()`) |
| タイムスタンプ | `created_at`, `updated_at` (timezone付き) |
| 論理削除 | `deleted_at TIMESTAMPTZ` — 物理削除禁止 |
| 外部キー | `ON DELETE RESTRICT` をデフォルト、CASCADE は明示的に |
| カラム命名 | `snake_case` |
| インデックス | 外部キー・検索列には必ず付与 |

### テンプレート

```sql
-- supabase/migrations/YYYYMMDDHHMMSS_create_<table>.sql
CREATE TABLE IF NOT EXISTS public.<table_name> (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  -- ↓ ドメイン固有カラム
  name        TEXT        NOT NULL,
  status      TEXT        NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'archived')),
  metadata    JSONB       DEFAULT '{}'::jsonb,
  -- ↓ 監査カラム（全テーブル共通）
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at  TIMESTAMPTZ
);

-- updated_at 自動更新トリガー
CREATE OR REPLACE TRIGGER set_updated_at
  BEFORE UPDATE ON public.<table_name>
  FOR EACH ROW EXECUTE FUNCTION moddatetime(updated_at);

-- インデックス
CREATE INDEX IF NOT EXISTS <table_name>_status_idx
  ON public.<table_name> (status)
  WHERE deleted_at IS NULL;
```

### SaaS テナント分離パターン

```sql
-- organizations テーブル（マルチテナントの基点）
CREATE TABLE IF NOT EXISTS public.organizations (
  id          UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
  slug        TEXT  NOT NULL UNIQUE,
  name        TEXT  NOT NULL,
  plan        TEXT  NOT NULL DEFAULT 'free'
                   CHECK (plan IN ('free', 'pro', 'enterprise')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- テナント所属テーブルの共通パターン
CREATE TABLE IF NOT EXISTS public.<resource> (
  id              UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID  NOT NULL REFERENCES public.organizations(id)
                        ON DELETE RESTRICT,
  -- ...
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS <resource>_org_idx
  ON public.<resource> (organization_id);
```

---

## 2. 冪等マイグレーション

本番環境に **何度実行しても壊れない** SQL を書く。

### カラム追加

```sql
-- IF NOT EXISTS で冪等性を保証
ALTER TABLE public.<table_name>
  ADD COLUMN IF NOT EXISTS <column_name> TEXT;

-- NOT NULL + DEFAULT のセット（既存行対応）
ALTER TABLE public.<table_name>
  ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
```

### インデックス追加

```sql
CREATE INDEX IF NOT EXISTS <index_name>
  ON public.<table_name> (<column>);
```

### テーブル削除（ロールバック用）

```sql
DROP TABLE IF EXISTS public.<table_name>;
```

### /api/setup エンドポイントパターン（Prisma 非使用プロジェクト）

```typescript
// app/api/setup/route.ts
import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

// 本番では Authorization ヘッダーで保護すること
export async function POST(req: Request) {
  const supabase = createClient();

  const migrations: Array<{ name: string; sql: string }> = [
    {
      name: "add_metadata_to_users",
      sql: `ALTER TABLE public.users
              ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;`,
    },
    {
      name: "create_audit_logs",
      sql: `CREATE TABLE IF NOT EXISTS public.audit_logs (
              id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              user_id    UUID REFERENCES auth.users(id),
              action     TEXT NOT NULL,
              payload    JSONB,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );`,
    },
  ];

  const results: Record<string, string> = {};

  for (const m of migrations) {
    const { error } = await supabase.rpc("exec_sql", { query: m.sql });
    results[m.name] = error ? `ERROR: ${error.message}` : "OK";
  }

  return NextResponse.json({ results });
}
```

>
