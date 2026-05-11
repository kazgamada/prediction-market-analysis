---
name: auto-deploy-flyio
description: >-
  Fly.io への全自動デプロイ運用ルール。原則ターミナルを使わず、すべて
  ブラウザ UI または Claude Code チャット経由で完結させる。コード変更は
  Claude に依頼するか github.dev で編集し、git push と同時に GitHub Actions
  が自動デプロイを実行する。再デプロイ・ログ確認・Secret 編集・マシン再起動
  などの運用操作も Web UI から行う方法を網羅。Fly + GitHub 構成のプロジェクトで
  デプロイ周りの作業に着手するときは、まずこの Skill を参照すること。
category: devops
---

# Fly.io 自動デプロイ運用ルール (ターミナル不使用)

このプロジェクトの本番デプロイは **GitHub Actions が `git push` を契機に自動実行** する。
ユーザーが PowerShell や bash を開く運用は **しない**。コード変更・再デプロイ・ログ確認・
Secret 編集まで含めて、すべて Web ブラウザか Claude Code チャットで完結する。

---

## 1. 構成サマリ

| 役割 | 場所 / 値 |
|------|-----------|
| ホスト | Fly.io app `prediction-market-analysis` (region `nrt`) |
| ビルド設定 | `fly.toml` + `Dockerfile` (リポジトリ ルート) |
| 自動デプロイ | `.github/workflows/fly-deploy.yml` |
| トリガー | `main` / `claude/add-page-caching-OkerV` への push、または `workflow_dispatch` |
| 認証 | GitHub Repository Secret `FLY_API_TOKEN` (Fly のデプロイ専用トークン) |
| デプロイ実行 | `superfly/flyctl-actions/setup-flyctl@master` + `flyctl deploy --remote-only` |

`--remote-only` を指定しているので、ローカルに Docker 不要。Fly のリモートビルダーがコンテナを焼く。

---

## 2. ターミナルを使わない通常運用

### 2.1 コードを変更したい
**選択肢 A — Claude Code チャットで依頼 (推奨)**
このチャット画面で「○○を直して」と書く。Claude が編集 → commit → push まで実行する。
push 完了と同時に GitHub Actions が自動デプロイを開始する。

**選択肢 B — github.dev (ブラウザ版 VS Code)**
1. ブラウザで `https://github.com/<owner>/<repo>` を開く
2. キーボードで `.` (ドット) を押す → `github1s.com` 風のフル画面 VS Code が開く
3. ファイルを編集
4. 左サイドバーの **Source Control** (Ctrl+Shift+G) でメッセージを書き **Commit & Push**

**選択肢 C — GitHub Web UI の鉛筆アイコン**
1. GitHub で対象ファイルを開く → 右上の鉛筆アイコン
2. 編集 → 下の **Commit changes** ボタン

### 2.2 デプロイ進捗を見たい
ブラウザで `https://github.com/<owner>/<repo>/actions` を開く。
最新のラン (`Deploy to Fly.io`) をクリックすると各ステップとログが見える。

### 2.3 コードを変えずに再デプロイしたい
1. `https://github.com/<owner>/<repo>/actions/workflows/fly-deploy.yml`
2. 右上の **Run workflow** ボタン → ブランチ選択 → **Run workflow**

### 2.4 デプロイ失敗ログを見たい
Actions タブの該当ランを開いて失敗したジョブをクリック。失敗ステップは赤×アイコンで折り畳まれているので、開いて末尾を見る。

### 2.5 アプリのライブログ (Streamlit / Alembic クラッシュ等)
`https://fly.io/apps/<fly-app>/monitoring` を開く。Live Logs が流れる。
特定マシンに絞りたいときは Machines タブ → マシンを選択 → Logs。

### 2.6 アプリのマシンを再起動したい
`https://fly.io/apps/<fly-app>/machines` → 対象マシン → **Restart**

### 2.7 Secrets を変えたい
- アプリの環境変数: `https://fly.io/apps/<fly-app>/secrets`
- GitHub Actions の secret: `https://github.com/<owner>/<repo>/settings/secrets/actions`

---

## 3. 初回セットアップ (Web UI のみ)

新規プロジェクトでこの構成を再現するときの手順。**ターミナルを 1 度だけ開く必要があるのは
`fly tokens create` の代替が公式 UI に存在する場合のみ無し**。代替手段:

### 3.1 Fly app と Postgres の作成
- Fly Web ダッシュボード `https://fly.io/dashboard` → **New App** → リポジトリと連携
- Postgres も Web 上から **Create Postgres cluster** で作成・アタッチできる

### 3.2 GitHub Actions ワークフロー追加
github.dev (`.` キー) で `.github/workflows/fly-deploy.yml` を新規作成し、以下を貼って commit:
```yaml
name: Deploy to Fly.io
on:
  push:
    branches: [main, <feature-branch>]
  workflow_dispatch:
concurrency:
  group: fly-deploy
  cancel-in-progress: false
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only --app <fly-app-name>
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

### 3.3 FLY_API_TOKEN を発行 → 登録
1. `https://fly.io/dashboard/personal/tokens` (または app ページの **Tokens**) で **Create deploy token** をクリック → トークンをコピー
2. `https://github.com/<owner>/<repo>/settings/secrets/actions/new` で
   - Name: `FLY_API_TOKEN`
   - Secret: 貼り付け
   - **Add secret**

### 3.4 初回デプロイをキック
`https://github.com/<owner>/<repo>/actions/workflows/fly-deploy.yml` → **Run workflow**。
これ以降 push のたびに自動デプロイ。

> 注: Fly UI から deploy token を発行する経路が表示されない場合だけ、Claude Code チャットに
> 「fly tokens create deploy を実行して」と依頼すれば、Claude が一時的に CLI を呼んで
> token 文字列を返すので、それを GitHub Secrets に貼ればよい。ユーザーがターミナルを開く必要は無い。

---

## 4. よくある失敗とその切り分け (UI ベース)

| 症状 | 原因 | 復旧 (UI) |
|------|------|-----------|
| `Error: no access token available. Please login with 'flyctl auth login'` | `FLY_API_TOKEN` secret 未登録 / 名前不一致 / Variables タブに登録 / Environment secret になっている | GitHub Settings → Secrets and variables → Actions で `FLY_API_TOKEN` の有無を確認、無ければ手順 3.3 で再登録 |
| Smoke check fails: `the app appears to be crashing` | 起動コマンド (alembic / streamlit / app) のクラッシュ | Fly ダッシュボード → Monitoring で Live Logs を確認 |
| `Can't locate revision identified by '<rev>'` (Alembic) | DB に未知のリビジョンが記録されている / 別ブランチの migration が手元に無い | Claude Code に「このブランチに不足している migration を取り込んで」と依頼。DB を勝手に書き換えない |
| Deploy ループ (再起動を繰り返す) | 起動コマンドが exit 1 + smoke check 失敗 | 同上、まず Fly Live Logs。`min_machines_running = 0` でも 10 回失敗するとマシン停止 |
| 古いコードが動いている | Build cache のレイヤを使い続けた | Actions の `Run workflow` ボタンから再実行。それでも直らない場合は Claude に「ワークフローを `--no-cache` にして」と依頼 |
| 自動デプロイが走らない | `branches:` に対象ブランチが無い | Claude に「`<branch>` を auto-deploy 対象に追加して」と依頼 |

---

## 5. やってはいけないこと

- **`FLY_API_TOKEN` をリポジトリにコミットする** (絶対 NG)。secret は GitHub Settings 画面か `gh secret set` 経由でだけ
- **デプロイのために手元で `fly deploy` を打つ**。ローカル環境差を本番に持ち込む原因になるので、自動デプロイに統一
- **`branches:` に何も書かず `on: push` 全部許可**。意図しないブランチ作業で本番に当たる
- **GitHub Web UI の Variables タブに secret を登録**。Actions からは読めない
- **Environment secrets に登録**。workflow が environment 指定していなければ読めない
- **デプロイのリトライを `--no-verify` や `force-push` で誤魔化す**。原因 (alembic / smoke check) を直す

---

## 6. このプロジェクトでの具体値 / クイックリンク

| 項目 | 値 / URL |
|------|----------|
| `<fly-app>` | `prediction-market-analysis` |
| `<owner>/<repo>` | `kazgamada/prediction-market-analysis` |
| 主ブランチ | `claude/add-page-caching-OkerV` (将来 `main` に統合予定) |
| Web プロセス | `streamlit run src/copytrader/web/app.py` (port 8501) |
| Monitor プロセス | `copytrader monitor` (live WS + 5 分ごと自動 backfill catchup) |
| DB migration | `alembic upgrade head` (起動時に自動実行) |
| Repo | https://github.com/kazgamada/prediction-market-analysis |
| Actions | https://github.com/kazgamada/prediction-market-analysis/actions |
| Fly dashboard | https://fly.io/apps/prediction-market-analysis |
| Live logs | https://fly.io/apps/prediction-market-analysis/monitoring |
| Machines | https://fly.io/apps/prediction-market-analysis/machines |
| Public URL | https://prediction-market-analysis.fly.dev |

---

## 7. このスキルを呼び出すべき場面

- 「デプロイがうまくいかない」「再デプロイしたい」「デプロイの仕組みを知りたい」と聞かれたとき
- 新規プロジェクトで Fly + GitHub Actions の自動デプロイを構築するとき
- ユーザーに「ターミナルでこのコマンドを打って」と提案しそうになったとき (→ Claude が代わりに実行するか UI 経路を提示する)
- `FLY_API_TOKEN` / GitHub Secrets / `fly` / `gh` 関連のトラブルが起きたとき

### 7.1 ユーザーへの応答ルール

- **デフォルトで PowerShell / bash コマンドをユーザーに提示しない**。Claude が自分で実行するか、URL を提示する
- どうしても CLI が必要な場面 (例: token 発行) では Claude が代行し、結果文字列だけユーザーに返す
- ユーザーが「ターミナルで打つ」を明示的に望んだ場合のみコマンド列を返す
