# gen-types

Supabase から TypeScript 型を再生成して `src/types/database.ts` を更新する。

## 使い方
`/gen-types`

## 手順

1. Supabase CLI がインストールされているか確認:
   ```bash
   npx supabase --version
   ```

2. **Supabase CLI が使える場合**（推奨）:
   ```bash
   npx supabase gen types typescript \
     --project-id "$SUPABASE_PROJECT_REF" \
     --schema public \
     > src/types/database.ts
   ```
   `SUPABASE_PROJECT_REF` は `.env.local` の `NEXT_PUBLIC_SUPABASE_URL` から抽出:
   `https://<PROJECT_REF>.supabase.co`

3. **CLI が使えない場合**（手動更新）:
   最新のマイグレーションファイルを読み込んで、
   `src/types/database.ts` の `Database` インターフェースに不足テーブルを追記:

   ```typescript
   // 追加するテーブルのテンプレート
   <table_name>: {
     Row: {
       id: string;
       user_id: string;
       name: string;
       created_at: string;
       updated_at: string;
     };
     Insert: {
       id?: string;
       user_id: string;
       name: string;
       created_at?: string;
       updated_at?: string;
     };
     Update: Partial<Database["public"]["Tables"]["<table_name>"]["Insert"]>;
   };
   ```

4. 更新後の確認:
   - 全テーブルが `Database["public"]["Tables"]` に含まれているか
   - `supabase.from("<table>")` で TypeScript 補完が効くか
   - `Row` / `Insert` / `Update` の3種が定義されているか

5. 型更新後、影響を受けるファイルで型エラーがないか確認:
   ```bash
   npx next lint
   ```
