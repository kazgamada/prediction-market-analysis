# Google ログイン（OIDC）セットアップ手順

本アプリは Streamlit ネイティブ OIDC（`st.login`）で Google ログインに対応する。
`kazgamada@gmail.com`（= `ADMIN_EMAILS`）は**ログイン時に自動で管理者**になる。
誰でも Google でログインでき、許可リスト外は一般ユーザー（`role=user`）として登録される。
メール / パスワードでのログインも併用できる。

---

## 全体像

```
ブラウザ → 「Google でログイン」→ Google 同意画面 → /oauth2callback へ戻る
        → st.user に email が入る → DB の users に get-or-create
        → email が ADMIN_EMAILS なら role=admin、それ以外は role=user
```

設定するもの:
1. Google Cloud Console で OAuth クライアント（Client ID / Secret）を作成
2. Fly.io に Secrets を投入（`GOOGLE_CLIENT_ID` など）
3. デプロイ（起動時に `.streamlit/secrets.toml` が env から自動生成される）

---

## 1. Google Cloud Console で OAuth クライアントを作成

1. https://console.cloud.google.com/ にログイン
2. 上部のプロジェクト選択 → **新しいプロジェクト**（任意の名前、例 `copytrader`）
3. 左メニュー **API とサービス → OAuth 同意画面**
   - User Type: **外部 (External)** を選択 → 作成
   - アプリ名（例 `Copytrader`）、ユーザーサポートメール（自分のメール）、デベロッパー連絡先を入力 → 保存して続行
   - スコープ: 既定のまま（`openid` `email` `profile`）で次へ
   - テストユーザー: 公開設定を「テスト」のままにする場合は、ログインさせたい Google アカウント（例 `kazgamada@gmail.com`）を**テストユーザーに追加**。
     （誰でもログインさせたい場合は後で「アプリを公開」する）
4. 左メニュー **API とサービス → 認証情報 → 認証情報を作成 → OAuth クライアント ID**
   - アプリケーションの種類: **ウェブ アプリケーション**
   - 名前: 任意（例 `copytrader-web`）
   - **承認済みのリダイレクト URI** に以下を追加（両方入れておくとローカルでも試せる）:
     - 本番: `https://prediction-market-analysis.fly.dev/oauth2callback`
     - ローカル: `http://localhost:8501/oauth2callback`
   - 作成 → 表示される **クライアント ID** と **クライアント シークレット** を控える

> リダイレクト URI は末尾が必ず `/oauth2callback`。1 文字でも違うと `redirect_uri_mismatch` エラーになる。

---

## 2. Fly.io に Secrets を投入（ブラウザのみ・ターミナル不要）

Fly.io のダッシュボードから設定する。アプリ名は `prediction-market-analysis`。

1. https://fly.io/dashboard を開く → アプリ **prediction-market-analysis** をクリック
2. 左メニュー **Secrets** を開く
3. **New Secret**（または同等の入力欄）で、以下を **1 件ずつ Name / Value** で追加して保存:

   | Name | Value |
   |---|---|
   | `GOOGLE_CLIENT_ID` | Google で控えたクライアント ID（`...apps.googleusercontent.com`） |
   | `GOOGLE_CLIENT_SECRET` | Google で控えたクライアント シークレット（`GOCSPX-...`） |
   | `OAUTH_REDIRECT_URI` | `https://prediction-market-analysis.fly.dev/oauth2callback` |
   | `OAUTH_COOKIE_SECRET` | 長いランダム文字列（下記の生成済み値を使ってよい） |
   | `ADMIN_EMAILS` | `kazgamada@gmail.com` |

4. すべて保存すると Fly が自動で再デプロイ（マシン再起動）する。

メモ:
- `ADMIN_EMAILS` はカンマ区切りで複数可（例 `a@x.com,b@y.com`）。未設定でも既定で `kazgamada@gmail.com` が管理者。
- `OAUTH_REDIRECT_URI` は未設定でもアプリ側が `https://prediction-market-analysis.fly.dev/oauth2callback` を既定値にするが、明示設定を推奨。
- `OAUTH_COOKIE_SECRET` を未設定にすると起動毎にランダム生成され、再起動でログインセッションが切れる。固定値を入れること。

---

## 3. 動作確認

1. `https://prediction-market-analysis.fly.dev/` を開く（ハードリロード推奨）
2. ログインページに **「🔵 Google でログイン」** が表示される
3. クリック → Google 同意画面 → 戻ってくるとログイン完了
4. `kazgamada@gmail.com` でログインすると、サイドバーに **🔧 管理者メニュー**（ユーザー管理 / Billing 管理 / メール送信）が表示される

うまくいかないとき:
- ボタンが出ない → `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` が未設定。Fly ダッシュボードの **Secrets** 一覧で確認
- `redirect_uri_mismatch` → Google 側の承認済みリダイレクト URI と `OAUTH_REDIRECT_URI` が不一致
- `403 access_denied` → OAuth 同意画面が「テスト」状態で、当該アカウントがテストユーザー未登録。テストユーザー追加 or アプリを公開

---

## ローカルで試す場合

```sh
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# redirect_uri は http://localhost:8501/oauth2callback にして client_id/secret を記入
.venv/bin/streamlit run src/copytrader/web/app.py
```

`.streamlit/secrets.toml` は `.gitignore` 済み。**絶対にコミットしないこと。**

---

## 管理者の付与ロジック

- ログインのたびに、メールが `ADMIN_EMAILS` に含まれていれば `role=admin` に（昇格）。
- 含まれなければ新規は `role=user`。
- 管理者は「👥 ユーザー管理」ページから他ユーザーの role を変更することも可能。
