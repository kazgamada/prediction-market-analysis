---
name: supabase-migration-pattern
description: Supabase の migration（SQL ファイル）を書くときに使う。ファイル命名規則（`<YYYYMMDDHHMMSS>_<概要>.sql`）、RLS ポリシー設計（SELECT / INSERT / UPDATE / DELETE の4種すべて定義）、`updated_at` トリガー、外部キー制約、インデックス戦略、`auth.users` との連携（`user_profiles` パターン）、シードデータの扱いを含む。破壊的変更（DROP, ALTER DROP COLUMN）の分離運用も扱う。ユーザーが「migration を作る」「テーブルを追加」「RLS を書く」「スキーマ変更」「Supabase にカラム追加」と言及したときにトリガー。
---

# Supabase Migration パターン

## 概要

Supabase の migration を一貫したスタイルで書くための規約と雛形を集約する Skill。命名規則、RLS 設計、トリガー、型生成のループまでを標準化する。

## 使用タイミング

- 新規テーブルを追加するとき
- 既存テーブルにカラムを追加・変更するとき
- RLS ポリシーを新規追加・修正するとき
- migration ファイルを作成するとき全般

## 手順

TODO: 追記予定

### ファイル命名

```
supabase/migrations/<YYYYMMDDHHMMSS>_<概要>.sql
```

例:
- `20260424120000_add_user_profiles.sql`
- `20260424120500_add_rls_to_user_profiles.sql`

タイムスタンプは `supabase migration new <name>` で自動生成される。

### 1 migration = 1 論理変更

- 複数テーブルの追加を1ファイルに混ぜない
- 破壊的変更（DROP, ALTER DROP COLUMN, 制約削除）は **別ファイルに分離**
- migration のロールバックスクリプトは作らない（Supabase は forward-only で運用）

### RLS 必須ルール

新規テーブル作成時は **必ず** RLS を有効化:

```sql
alter table public.<table> enable row level security;
```

4種すべてのポリシーを明示定義（必要ないものは書かない判断もあり、ただしコメントで理由を残す）:

```sql
-- SELECT: 本人のみ
create policy "Users can select own rows"
  on public.<table> for select
  using (auth.uid() = user_id);

-- INSERT: 認証ユーザーが自分のレコードを作成
create policy "Users can insert own rows"
  on public.<table> for insert
  with check (auth.uid() = user_id);

-- UPDATE: 本人のみ
-- DELETE: 管理者のみ、または禁止
```

### 標準カラム

すべてのテーブルに以下を含める（例外は理由をコメント）:

```sql
id uuid primary key default gen_random_uuid(),
created_at timestamptz not null default now(),
updated_at timestamptz not null default now()
```

`updated_at` 自動更新トリガー:

```sql
create trigger set_updated_at
  before update on public.<table>
  for each row execute function public.moddatetime('updated_at');
```

（`moddatetime` extension を有効化しておく）

### `auth.users` との連携

ユーザー紐付けは `auth.users(id)` を外部キーにする:

```sql
user_id uuid references auth.users(id) on delete cascade not null
```

追加情報は `public.user_profiles` に持たせる（`auth.users` は直接編集しない）。

### インデックス

- 外部キーカラムには必ずインデックス
- 検索条件に使うカラム（`created_at`, `status` など）もインデックス
- 複合インデックスは実クエリを見てから追加

### シードデータ

- `supabase/seed.sql` で管理
- 本番環境には流さない（マスターデータのみ）
- 顧客データ・テストユーザーは含めない

### 型生成

migration 後は必ず実行:

```bash
supabase gen types typescript --local > src/types/database.ts
```

## 補助ファイル

TODO: `examples/new-table-template.sql`, `examples/rls-policy-set.sql` を追加予定

## 備考

- 本番に当てる前にステージング環境で必ず検証
- `drop table` は避け、不要なら `_deprecated` prefix をつけて残す運用も選択肢
- ポリシー変更は既存データへのアクセス権を壊す可能性があるので特に慎重に
