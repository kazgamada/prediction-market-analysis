---
name: troubleshoot-checklist
description: エラーが続いて行き詰まったとき、速やかに問題を切り分け解決するためのチェックリスト。同じ修正を繰り返しても直らない / デプロイ後に動かない / DB エラーが連発 / 認証ループ / ビルド通らない / SQL 実行が失敗する、といった「ループに陥った」状況で起動する。Next.js + Supabase + Vercel + GitHub Actions + Stripe + Anthropic 横断。
user_invocable: true
---

# トラブルシュート・チェックリスト

> **頭が真っ白な時に開いて、上から順にチェックする** ためのスキル。  
> 同じエラーを 2 回以上踏んだ / 修正してもまた壊れた / 仮説を立て直したい、ときの起動推奨。

---

## 0. 状況リセット（30 秒）

最初にこれだけやる。仮説を立てる前。

```
- 開始時刻       : ____ : ____
- 直前にやった操作: __________________________
- 期待した結果    : __________________________
- 実際の結果      : __________________________ (エラー全文をコピー)
- 試した対処の数  : ____ 回
```

**3 回以上同じ修正を試しているなら、仮説が間違っている**。  
チェックリスト 1 へ進む前に、いったん全部の修正をリバートして「素の状態」のエラーを確認する。

---

## 1. 問題の分類（10 秒）

エラーが**どこ**で起きているかを 1 つだけ選ぶ:

| カテゴリ | 典型シグナル | 進む先 |
|---------|------------|-------|
| **DB / SQL** | `relation ... does not exist` / `RLS` / `permission denied` / `column ... not found` | §2 |
| **認証** | `unauthorized` / セッション切れ / Google OAuth エラー / sudo 要求 | §3 |
| **ビルド / 型** | `tsc` エラー / `next build` 失敗 / モジュール解決失敗 | §4 |
| **デプロイ** | Vercel ビルド成功なのに本番 500 / 環境変数 / ランタイム差 | §5 |
| **API** | 401/403/404/500、Webhook 不達、Stripe 署名失敗 | §6 |
| **フロント** | 画面が真っ白 / 認証ループ / hydration mismatch / 入力リセット | §7 |
| **CI / GitHub Actions** | ワークフロー失敗 / 権限 / シークレット未設定 | §8 |

迷ったら **エラー全文を上から順に読む** → 最初に出る Stack の "production code" 行が真の原因。

---

## 2. DB / SQL チェックリスト

```
□ Supabase Dashboard → Database → Tables で該当テーブルが存在するか
□ 存在しないなら supabase/bootstrap.sql を SQL Editor に貼って Run（idempotent）
□ 関数 (is_service_admin など) があるか: select * from pg_proc where proname='is_service_admin';
□ RLS が有効か: select tablename, rowsecurity from pg_tables where schemaname='public';
□ 該当ポリシーが期待通りか: select * from pg_policies where tablename='<table>';
□ 0 行返るとき:
   - WHERE 句の値が実データと一致しているか (lower(email) で比較しているか)
   - auth.users にそのユーザーがいるか:
     select id, email from auth.users where lower(email) = lower('...');
□ permission denied のとき:
   - SQL Editor は service_role 権限。RLS は影響しない。app 側で出るなら policy 不足
   - INSERT 用の policy (with check) と UPDATE 用 (using + with check) を区別
□ "column does not exist": migration 順序を確認 (ALTER TABLE ADD COLUMN IF NOT EXISTS で対応)
□ "duplicate key": ON CONFLICT 節を追加 or 先に DELETE
```

**ループ脱出**: テーブル / 関数 / ポリシー の 3 つを順に存在確認。**bootstrap.sql は何度流しても安全**。

---

## 3. 認証チェックリスト

```
□ middleware.ts: 想定通りのパスが PUBLIC か (/, /login, /signup, /auth/*, /api/stripe/webhook)
□ NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY が Vercel と .env.local に揃っているか
□ "session_expired" ループ: cookie の SameSite / Secure / domain が一致しているか
□ /admin に入れない: service_admins に行があるか
   select * from public.service_admins where user_id = (select id from auth.users where lower(email)=lower('...'));
□ /admin/admins (Superadmin) に入れない: service_admins.level = 'superadmin' か
□ 招待リンク 410: 期限切れ。新しいトークンで再送
□ "no_organization" / 組織関連エラー: v3 でテナント廃止済。requireMember / requireOrgRole は使わない
□ Google OAuth が returning to /login: callback URL が Supabase Auth Settings と一致しているか
□ パスワードリセット動かない: Supabase の Email テンプレートと redirect URL を確認
```

---

## 4. ビルド / 型チェック

```
□ rm -rf .next && npx tsc --noEmit
□ "Cannot find module '@/...'": tsconfig.json の paths と実ファイルパス
□ "Property does not exist on type 'never'":
   - Supabase 型: returns<MyType>() を付ける、または .update(... as never) でエスケープ
   - types/database.ts に該当テーブル / カラムが反映されているか
□ "Module not found 'react'": npm install を実行 (node_modules 不在)
□ "Type instantiation is excessively deep": 再帰型で過負荷。型定義を小さく
□ ESLint エラーで build 失敗: next.config.mjs の eslint.ignoreDuringBuilds を一時 true で先に通す
□ "Server / Client component" 混在: "use client" の付け忘れ、または server-only API のクライアント呼び出し
```

---

## 5. デプロイ (Vercel) チェックリスト

```
□ Vercel Dashboard → Deployments → 最新の Build Logs 全文 (最後の 200 行) を読む
□ Build 成功 + 本番 500: ランタイムエラー → Functions → Logs を確認
□ "Function exceeded the maximum execution duration":
   - vercel.json で maxDuration を上げる、または Edge runtime に切替
□ 環境変数の差:
   - Vercel Settings → Environment Variables (Production / Preview / Development) すべて埋める
   - NEXT_PUBLIC_ プレフィックス漏れに注意（クライアント露出変数）
   - 設定後は Redeploy が必要（ビルド時に焼き込まれる）
□ Edge runtime で動かない API: Node API (fs, crypto.randomUUID, Buffer) を使っていないか
□ ロールバック: Deployments → 安定版を Promote to Production
□ Custom Domain で 404: Domain Settings → SSL 発行待ちか、middleware の matcher を確認
```

---

## 6. API チェックリスト

```
□ 401 unauthorized: middleware が PUBLIC 扱いしていない、または getAuthContext() の cookie が読めない
□ 403 forbidden: requireServiceAdmin / requireSuperadmin の対象になっているか
□ 402 payment_required: getPlanLimits().features.* が false。plan_definitions と一致しているか
□ 404: route.ts の場所と HTTP メソッド (GET/POST/PATCH/DELETE) を確認
□ 500: console.log を追加してログを Vercel Functions で確認
□ Stripe Webhook 400 invalid_signature:
   - STRIPE_WEBHOOK_SECRET が Stripe Dashboard の signing secret と一致
   - body を req.text() で読んでいるか (req.json() は NG)
   - middleware が /api/stripe/webhook を public 扱いしているか
□ AI チャット 503 ai_unconfigured: ANTHROPIC_API_KEY 未設定
□ Resend メール送信失敗: RESEND_API_KEY と from ドメインの認証
□ Rate limit 429: 429 を返す前に retry-after ヘッダーを見る
```

---

## 7. フロントチェックリスト

```
□ 画面が白い: error.tsx の表示。ブラウザ DevTools → Console と Network を見る
□ 認証直後にループ: callback の redirectTo が無限再帰していないか (/login → / → /login)
□ Hydration mismatch: SSR と CSR で異なる値 (Date.now / Math.random / window) を出していないか
□ "use client" が必要なのに無い: useState / useEffect / event handler を使っているコンポーネント
□ 入力中に値が消える: 親で再レンダリング → key prop の付け方、または useState を上に上げる
□ Cmd+K / Cmd+J が効かない: window.addEventListener が SSR で動いていないか
□ SSE が切れる: Vercel Edge は 30s 制限。Node runtime + maxDuration 設定で延長
```

---

## 8. CI / GitHub Actions チェックリスト

```
□ Actions タブ → 失敗ワークフロー → Job → ステップごとのログ全文を見る
□ "permission denied to ...":
   - workflow の permissions: ブロック (contents: write など)
   - GITHUB_TOKEN ではなく PAT が必要なケース (リポ横断 push)
□ "secret not set": Settings → Secrets and variables → Actions に登録
□ Supabase db push 失敗:
   - SUPABASE_ACCESS_TOKEN / SUPABASE_DB_PASSWORD / SUPABASE_PROJECT_ID 全部設定
   - migration 順序: ファイル名のタイムスタンプが昇順か
   - すでに適用済みの migration: supabase migration repair が必要なら手動 SQL で同期
□ Vercel 自動デプロイが走らない:
   - Vercel と GitHub の連携 (Settings → Git) を確認
   - Production Branch が main になっているか
```

---

## 9. メタ手順: 同じ問題でループしているとき

3 回以上同じ修正をしてダメなら、戦術ではなく**前提**が間違っている。

```
1. すべての修正をリバート（git stash か git reset --hard <直前のコミット>）
2. エラー全文を一度だけ落ち着いて読む（最初の 1 行と最後の Stack の production 行）
3. その行のコードを実際に開く（推測しない）
4. データを実際に見る (Supabase Table Editor / Vercel Logs / ブラウザ DevTools)
5. **「再現できる最小ケース」を作る**（1 ファイル / 1 SQL / 1 リクエストに絞る）
6. 仮説を 1 つだけ立てる（複数同時に変えない）
7. 1 つ修正 → 検証 → 結果を記録
```

---

## 10. それでも詰んだら

```
□ いま試した手順をすべて Markdown で書き出す（時刻 + 操作 + 結果）
□ 関連する error message / console log / Network response を貼る
□ AI アシスタント (/app の Cmd+J) に「このログから次に試すべき仮説を 3 つ」と聞く
□ 公式ドキュメントの該当ページを読む (Next.js / Supabase / Vercel / Stripe / Anthropic)
□ Web 検索: 完全一致のエラーメッセージ + プロダクト名 + バージョン
□ サポートに問い合わせ:
   - Supabase: https://supabase.com/dashboard/support/new
   - Vercel: Help → Support
   - Stripe: Dashboard → Support
□ ロールバック判断:
   - 影響大 + 原因不明 → まず本番を直前バージョンに戻す（Vercel: Promote）
   - DB 変更が原因 → 逆操作 SQL を新 migration として追加
```

---

## 11. 解決後の事後アクション

```
□ 同じ罠を避けるため、原因と対処を 1 行ずつまとめて該当 docs に追記
□ 修正コミットメッセージに「fix(scope): <一行で原因>」と記録
□ 再発防止のテストやガード句を追加
□ チェックリスト (この skill) に新パターンを追記して育てる
```

---

## トリガー例

このスキルは以下のような場面で起動推奨:

- 「同じエラーがまた出た」
- 「3 回直したのに直らない」
- 「ビルド成功するのに本番で 500」
- 「relation does not exist」
- 「permission denied for table」
- 「unauthorized が消えない」
- 「Stripe Webhook が届かない」
- 「行き詰まった」「ループしている」「仕切り直したい」
