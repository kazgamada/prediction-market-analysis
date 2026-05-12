---
name: database-migration-pattern
description: >-
  Supabase/PostgreSQL/TypeScriptプロジェクトにおけるDBスキーマ設計・マイグレーション・RLS・ロール管理・型安全クエリパターンの包括的ガイド。テーブル設計の原則からRLSポリシー実装、Supabase型生成、ロール階層管理、冪等マイグレーション、スキーマ適応クエリまで一貫した実装パターンを提供する。あらゆる規模のSaaSアプリケーションで再利用可能。
category: database
sourceSkillIds:
  - a4ed7a36
  - a8640f40
  - 12ba1851
  - '35616135'
  - 91d394af
  - 82eca7f0
  - ea609157
  - a2d648e3
  - b7f939a7
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
  - 16966ace
  - bc81c831
  - 85eeda05
  - 8e4316ac
  - 8598329c
generatedAt: '2026-05-11'
---

# database-migration-pattern

Supabase / PostgreSQL / TypeScript プロジェクトにおける DB 設計・マイグレーション・RLS・ロール管理・型安全クエリの包括的実装ガイド。

---

## 目次

1. [テーブル設計の原則](#1-テーブル設計の原則)
2. [冪等マイグレーションパターン](#2-冪等マイグレーションパターン)
3. [RLS ポリシー実装](#3-rls-ポリシー実装)
4. [ロール階層管理](#4-ロール階層管理)
5. [Supabase クライアント使い分け](#5-supabase-クライアント使い分け)
6. [型安全クエリパターン](#6-型安全クエリパターン)
7. [スキーマ適応クエリ（列存在チェック）](#7-スキーマ適応クエリ列存在チェック)
8. [月次セキュリティレビューチェックリスト](#8-月次セキュリティレビューチェックリスト)

---

## 1. テーブル設計の原則

### 基本構造

```sql
-- 全テーブル共通の基底構造
CREATE TABLE IF NOT EXISTS public.{table_name} (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- updated_at 自動更新トリガー（プロジェクト全体で共有）
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_{table_name}_updated_at
  BEFORE UPDATE ON public.{table_name}
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
```

### 設計チェックリスト

| 項目 | 確認内容 |
|------|----------|
| PK | `uuid` + `gen_random_uuid()` を使用（連番は避ける） |
| タイムスタンプ | `created_at` / `updated_at` を全テーブルに付与 |
| soft delete | 必要なら `deleted_at timestamptz` を追加（物理削除は最後の手段） |
| 外部キー | `ON DELETE` 動作を明示（`CASCADE` / `SET NULL` / `RESTRICT`） |
| インデックス | 検索条件・結合キーに必ず作成 |
| RLS | 全テーブルで `ENABLE ROW LEVEL SECURITY` を宣言 |

---

## 2. 冪等マイグレーションパターン

既存デプロイを壊さずに列・インデックス・テーブルを追加する。  
`IF NOT EXISTS` / `IF EXISTS` を必ず付け、何度実行しても安全にする。

```sql
-- ✅ 列を追加（冪等）
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS display_name text,
  ADD COLUMN IF NOT EXISTS avatar_url   text,
  ADD COLUMN IF NOT EXISTS role         text NOT NULL DEFAULT 'member';

-- ✅ インデックスを追加（冪等）
CREATE INDEX IF NOT EXISTS idx_users_role
  ON public.users (role);

CREATE INDEX IF NOT EXISTS idx_orders_user_created
  ON public.orders (user_id, created_at DESC);

-- ✅ テーブルを追加（冪等）
CREATE TABLE IF NOT EXISTS public.org_members (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     uuid        NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  user_id    uuid        NOT NULL REFERENCES auth.users(id)  ON DELETE CASCADE,
  role       text        NOT NULL DEFAULT 'member',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, user_id)
);

-- ✅ 列削除（冪等）
ALTER TABLE public.orders
  DROP COLUMN IF EXISTS legacy_column;

-- ✅ ENUM 値追加（冪等 — PostgreSQL 12+）
DO $$
BEGIN
  ALTER TYPE public.status_enum ADD VALUE IF NOT EXISTS 'archived';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
```

### `/api/setup` エンドポイントパターン（Prisma 非使用プロジェクト）

```typescript
// app/api/setup/route.ts
import { createAdminClient } from '@/lib/supabase/admin';
import { NextResponse } from 'next/server';

const MIGRATION_SQL = /* sql */`
  ALTER TABLE public.users ADD COLUMN IF NOT EXISTS display_name text;
  CREATE INDEX IF NOT EXISTS idx_users_display_name ON public.users (display_name);
`;

export async function POST(request: Request) {
  // 本番では認証ヘッダーやシークレットで保護すること
  const authHeader = request.headers.get('authorization');
  if (authHeader !== `Bearer ${process.env.SETUP_SECRET}`) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const admin = createAdminClient();
  const { error } = await admin.rpc('exec_sql', { sql: MIGRATION_SQL });
  // ※ exec_sql は社内定義の PostgreSQL 関数。直接 supabase.rpc を使う場合は
  //   postgres.js / pg ドライバ経由で実行する
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true });
}
```

---

## 3. RLS ポリシー実装

### 基本パターン

```sql
-- RLS を有効化（テーブル作成直後に必ず実行）
ALTER TABLE public.posts ENABLE ROW LEVEL SECURITY;

-- ① 本人のみ読み書き可能
CREATE POLICY "users: own rows"
  ON public.posts
  FOR ALL
  USING  (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- ② 認証済みユーザーは SELECT のみ
CREATE POLICY "posts: authenticated read"
  ON public.posts
  FOR SELECT
  USING (auth.role() = 'authenticated');

-- ③ 組織メンバーのみアクセス（サブクエリ）
CREATE POLICY "org_items: member access"
  ON public.org_items
  FOR ALL
  USING (
    EXISTS
