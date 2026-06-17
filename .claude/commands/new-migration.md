# new-migration

次の番号で Supabase マイグレーションファイルを作成する。

## 使い方
`/new-migration <description>`

例:
- `/new-migration add_tags_table`
- `/new-migration add_status_to_items`

## 手順

1. `supabase/migrations/` 内の既存ファイルを確認して連番を決定:
   ```bash
   ls supabase/migrations/ | sort | tail -1
   ```

2. 番号を +1 してゼロ埋め3桁でファイルを作成:
   `supabase/migrations/<NNN>_<description>.sql`

3. **テーブル新規作成テンプレート**:

```sql
-- <description>
create table if not exists public.<table_name> (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  name       text not null,
  -- TODO: その他フィールド
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index <table_name>_user_idx on public.<table_name>(user_id);

-- RLS
alter table public.<table_name> enable row level security;

create policy "<table_name>_select" on public.<table_name>
  for select using (user_id = auth.uid());

create policy "<table_name>_insert" on public.<table_name>
  for insert with check (user_id = auth.uid());

create policy "<table_name>_update" on public.<table_name>
  for update using (user_id = auth.uid());

create policy "<table_name>_delete" on public.<table_name>
  for delete using (user_id = auth.uid());
```

   > **マルチテナント構成の場合**: `user_id` を `organization_id` に置き換え、
   > アクセス制御用のヘルパー関数（例: `get_org_id()`）を使うよう調整する。

4. **カラム追加テンプレート**:

```sql
-- <description>
alter table public.<table_name>
  add column if not exists <column_name> <type> [not null] [default <value>];
```

5. 作成後、`src/types/database.ts` への型追加が必要か確認し、必要なら `/gen-types` を実行
6. RLS ポリシーは必ず有効化する（`alter table ... enable row level security`）
