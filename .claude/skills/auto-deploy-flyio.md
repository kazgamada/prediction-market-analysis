---
name: auto-deploy-flyio
description: >-
  Fly.io への全自動デプロイ運用ルール。GitHub Actions による push トリガー
  デプロイ、FLY_API_TOKEN の発行/登録手順、手動再デプロイ、デプロイ失敗時の
  切り分けを 1 ファイルで網羅。Streamlit / FastAPI / 任意のコンテナアプリで
  そのまま再利用できる。Fly + GitHub という構成のプロジェクトでデプロイ周りの
  作業に着手するときは、まずこの Skill を参照すること。
category: devops
---

# Fly.io 自動デプロイ運用ルール

このプロジェクトの本番デプロイは **GitHub Actions が `git push` を契機に自動実行する** 構成。
ユーザーがターミナルで `fly deploy` を打つ運用は **基本やらない**。手動オペレーションが必要なときも、
原則すべて `gh` CLI で完結し、ブラウザ UI を開かない。

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

## 2. 通常運用 (ユーザー操作)

### 2.1 コードを変えた → 反映したい
```bash
git push
```
これだけ。GitHub Actions が自動でビルド & デプロイ。

### 2.2 デプロイ進捗を見たい
```powershell
gh run list --repo kazgamada/prediction-market-analysis --workflow "Deploy to Fly.io" --limit 3
gh run watch <run-id> --repo kazgamada/prediction-market-analysis
```

### 2.3 コードを変えずに再デプロイしたい
```powershell
gh workflow run "Deploy to Fly.io" --repo kazgamada/prediction-market-analysis --ref <branch>
```

### 2.4 デプロイ失敗の原因を見たい
```powershell
gh run view <run-id> --repo kazgamada/prediction-market-analysis --log-failed
```
失敗ステップのログだけ抽出される。フルログは `--log` で。

### 2.5 アプリ側のクラッシュログを見たい (Alembic / Streamlit など)
```powershell
fly logs --app prediction-market-analysis | Select-Object -Last 80
```

---

## 3. 初回セットアップ (1 度だけ)

新規プロジェクトでこの構成を再現するときの手順。**全部 PowerShell / bash で完結する**。
ブラウザの GitHub Web UI を開く必要は無い。

### 3.1 必要なツール
```powershell
winget install --id GitHub.cli -e
gh auth login                # ブラウザでデバイスコード認証 (1 回だけ)
# flyctl は既にインストール済み + fly auth login 済みである前提
```

### 3.2 GitHub Actions ワークフロー
`.github/workflows/fly-deploy.yml` を以下の内容で作成:
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

### 3.3 トークン発行 + GitHub Secret 登録 + 初回デプロイ (3 行)
```powershell
$token = fly tokens create deploy --name github-actions --app <fly-app-name>
gh secret set FLY_API_TOKEN --repo <owner>/<repo> --body "$token"
gh workflow run "Deploy to Fly.io" --repo <owner>/<repo> --ref <branch>
```

これだけで自動デプロイが回り始める。これ以降ターミナルすら不要 (`git push` だけで OK)。

---

## 4. よくある失敗とその切り分け

| 症状 | 原因 | 復旧 |
|------|------|------|
| `Error: no access token available. Please login with 'flyctl auth login'` | `FLY_API_TOKEN` secret 未登録 / 名前不一致 / Variables タブに登録 / Environment secret になっている | `gh secret list --repo ...` で確認、`gh secret set FLY_API_TOKEN --body "..."` で再登録 |
| Smoke check fails: `the app appears to be crashing` | 起動コマンド (alembic / streamlit / app) のクラッシュ | `fly logs -i <machine-id>` で原因のスタックトレース確認 |
| `Can't locate revision identified by '<rev>'` (Alembic) | DB に未知のリビジョンが記録されている / 別ブランチで作った migration が手元に無い | リビジョンファイルを取り込む (cherry-pick or マージ)。DB を勝手に書き換えない |
| Deploy ループ (再起動を繰り返す) | 起動コマンドが exit 1 で終わる + smoke check 失敗 | 同上、まずログ確認。`min_machines_running = 0` でも 10 回失敗するとマシン停止 |
| Build cache のせいで古いコードが動く | `fly deploy` がレイヤキャッシュを使い続けた | ワークフローで `flyctl deploy --remote-only --no-cache` を一時的に使う |
| `branches:` に対象ブランチが無い | 自動デプロイの対象外 | `.github/workflows/fly-deploy.yml` の `branches:` に追記して push |

---

## 5. やってはいけないこと

- **`FLY_API_TOKEN` をリポジトリにコミットする** (絶対 NG)。secret は `gh secret set` 経由でだけ
- **デプロイのために手元で `fly deploy` を打つ**。ローカル環境差を本番に持ち込む原因になるので、自動デプロイに統一
- **`branches:` に何も書かず `on: push` 全部許可**。意図しないブランチ作業で本番に当たる
- **Web UI で secret を編集**。タブ違い (Variables / Environment) で使えなくなる事故が多い → `gh secret set` に統一
- **デプロイのリトライを `--no-verify` や `force-push` で誤魔化す**。原因 (alembic / smoke check) を直す

---

## 6. このプロジェクトでの具体値

| 項目 | 値 |
|------|----|
| `<fly-app-name>` | `prediction-market-analysis` |
| `<owner>/<repo>` | `kazgamada/prediction-market-analysis` |
| 主ブランチ | `claude/add-page-caching-OkerV` (将来 `main` に統合予定) |
| Web プロセス | `streamlit run src/copytrader/web/app.py` (port 8501) |
| Monitor プロセス | `copytrader monitor` (live WS + 5 分ごと自動 backfill catchup) |
| DB migration | `alembic upgrade head` (起動時に自動実行) |

---

## 7. このスキルを呼び出すべき場面

- 「デプロイがうまくいかない」「再デプロイしたい」「デプロイの仕組みを知りたい」と聞かれたとき
- 新規プロジェクトで Fly + GitHub Actions の自動デプロイを構築するとき
- `fly deploy` を手で打つ提案をしそうになったとき (→ `git push` か `gh workflow run` に置き換える)
- `FLY_API_TOKEN` / GitHub Secrets / `gh` CLI 関連のトラブルが起きたとき
