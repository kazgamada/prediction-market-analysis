# debug-auth

Supabase 認証フローの問題を体系的にデバッグする。

## 使い方
`/debug-auth [<symptom>]`

例:
- `/debug-auth` → 全チェックリストを実行
- `/debug-auth magic-link` → マジックリンク専用デバッグ
- `/debug-auth recovery` → パスワードリセット専用デバッグ
- `/debug-auth oauth` → OAuth（Google 等）専用デバッグ

## 共通チェックリスト

### 1. 環境変数確認
```bash
grep -E "NEXT_PUBLIC_SUPABASE|SUPABASE_SERVICE_ROLE|NEXT_PUBLIC_SITE_URL" .env.local
```
- `NEXT_PUBLIC_SUPABASE_URL` — `https://<ref>.supabase.co` 形式
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` — Supabase > Settings > API
- `SUPABASE_SERVICE_ROLE_KEY` — service_role キー（公開厳禁）
- `NEXT_PUBLIC_SITE_URL` — `http://localhost:3000`（開発）/ 本番 URL

### 2. Supabase Auth 設定（Dashboard で確認）
- [ ] Site URL が `NEXT_PUBLIC_SITE_URL` と一致しているか
- [ ] Redirect URLs に `<SITE_URL>/api/auth/callback` が含まれるか

---

## マジックリンク / メール認証デバッグ

**症状**: リンクをクリックしても認証されない・エラーになる

1. `src/app/api/auth/callback/route.ts` を確認:
   - `token_hash` + `type` → `supabase.auth.verifyOtp()` を使っているか
   - `code` → `supabase.auth.exchangeCodeForSession()` を使っているか
   - 両方を混在していないか（OTP と OAuth は別フロー）

2. Supabase Email テンプレートの URL 形式:
   ```
   # ✅ 正しい（token_hash 形式）
   {{ .SiteURL }}/api/auth/callback?token_hash={{ .TokenHash }}&type=magiclink

   # ❌ 間違い（code 形式はマジックリンクでは使えない）
   {{ .SiteURL }}/api/auth/callback?code={{ .Code }}
   ```

3. OTP/token_hash はデバイス非依存。PKCE フローの `code` は同一ブラウザセッションが必要。

---

## パスワードリセットデバッグ

**症状**: リセットリンクが無効・更新ページでエラー

1. Supabase Email テンプレート（Recovery）:
   ```
   {{ .SiteURL }}/api/auth/callback?token_hash={{ .TokenHash }}&type=recovery
   ```

2. callback route で `verifyOtp()` 後に `/update-password` にリダイレクトしているか確認

---

## Google OAuth デバッグ

**症状**: Google ログイン後にエラーまたはループ

1. Google Cloud Console:
   - Authorized redirect URIs に `<SITE_URL>/api/auth/callback` を追加済みか
   - Client ID/Secret が Supabase > Auth > Providers > Google に設定されているか

2. `signInWithOAuth()` の `redirectTo` が `<SITE_URL>/api/auth/callback` か確認

3. callback route の OAuth フロー:
   - `code` パラメータ → `exchangeCodeForSession(code)` を使っているか（PKCE フロー）

---

## Supabase クライアントの使い分け確認

- **Server Component / Server Action / API Route**: `createServerClient()` を使用
- **Client Component**: `createBrowserClient()` を使用
- **service_role が必要な管理操作**: admin クライアントをサーバーサイド専用で使用
- クライアントコンポーネントで service_role キーを使ってはならない
