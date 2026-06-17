# deploy-check

Vercel デプロイ前に必要な設定を全て確認する。

## 使い方
`/deploy-check`

## チェックリスト

### 1. ビルド確認
```bash
npx next lint
npx next build
```
エラーがあればすべて修正してからデプロイ

### 2. 環境変数チェック（`.env.example` との比較）
```bash
cat .env.example
```
Vercel ダッシュボードに以下が設定されているか確認（プロジェクト固有の変数は `.env.example` で確認）:

| 変数名 | 取得場所 |
|--------|---------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase > Settings > API > Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase > Settings > API > anon public |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase > Settings > API > service_role |
| `NEXT_PUBLIC_SITE_URL` | Vercel のデプロイ URL |
| `ANTHROPIC_API_KEY` | Anthropic Console（AI 機能を使う場合） |

### 3. Supabase 設定確認
- [ ] Authentication > URL Configuration:
  - Site URL: `https://<本番ドメイン>`
  - Redirect URLs: `https://<本番ドメイン>/api/auth/callback`
- [ ] マイグレーションが全て適用されているか:
  ```bash
  ls supabase/migrations/ | sort
  ```
- [ ] RLS が全テーブルで有効か（`/review-rls` で確認）

### 4. セキュリティチェック
- [ ] `.env.local` が `.gitignore` に含まれているか:
  ```bash
  grep ".env.local" .gitignore
  ```
- [ ] `SUPABASE_SERVICE_ROLE_KEY` がクライアントコンポーネントで使われていないか:
  ```bash
  grep -r "SUPABASE_SERVICE_ROLE" src/app --include="*.tsx" | grep -v "use server"
  ```
- [ ] service_role クライアントがサーバーサイドのみで使われているか

### 5. デプロイ手順
```bash
git checkout main
git push origin main
# Vercel が自動デプロイを開始
# https://vercel.com/dashboard でビルドログを確認
```

### 6. デプロイ後確認
- [ ] トップページが表示されるか
- [ ] `/login` でログインフォームが表示されるか
- [ ] 認証フローが動作するか
- [ ] ダッシュボードに正常にアクセスできるか
