# review-rls

テーブルの RLS ポリシーを監査・修正する。

## 使い方
`/review-rls [<table-name>]`

例:
- `/review-rls items` → items テーブルのみ確認
- `/review-rls` → 全テーブルを確認

## 手順

1. `supabase/migrations/` 内の最新マイグレーション（または `supabase/bootstrap.sql`）を読み込んで現在のポリシーを確認

2. 指定テーブル（または全テーブル）について以下をチェック:

   **必須チェック項目**:
   - [ ] `alter table ... enable row level security;` が設定されているか
   - [ ] SELECT ポリシーが適切なスコープ条件（`user_id = auth.uid()` 等）になっているか
   - [ ] INSERT ポリシーに `with check` が設定されているか
   - [ ] DELETE ポリシーに適切な権限チェックが含まれているか
   - [ ] 管理者操作のみ許可すべきポリシーが適切にガードされているか

3. **セキュリティホールのパターン**:
   ```sql
   -- ❌ 危険: 条件なしで全件アクセス可能
   create policy "select" on public.items for select using (true);

   -- ❌ 危険: ユーザースコープなし
   create policy "select" on public.items for select using (1=1);

   -- ✅ 安全: ユーザー所有データのみ
   create policy "select" on public.items
     for select using (user_id = auth.uid());

   -- ✅ 安全（マルチテナント）: 組織スコープ
   create policy "select" on public.items
     for select using (organization_id = get_my_org_id());
   ```

4. 問題が見つかった場合、修正パッチを新しいマイグレーションとして作成:
   - `supabase/migrations/<NNN>_fix_rls_<table>.sql` を作成
   - 既存ポリシーを `drop policy if exists` で削除してから再作成

5. **公開データのみ `using (true)` を許可**（例: plans, public_profiles）:
   - 書き込み系（INSERT/UPDATE/DELETE）には必ず認証チェックを付ける
   - service_role / admin 専用テーブルは一般ユーザーから完全に隠す
