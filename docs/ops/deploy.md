# デプロイ手順（ブラウザ完結）

CLAUDE.md §0.1 に従って、Fly.io への反映は **GitHub と Fly.io Dashboard のブラウザ操作** だけで完了します。ターミナルは原則使いません。

## 初回セットアップ（1 回だけ）

1. **GitHub Secrets に `FLY_API_TOKEN` を登録**
   - Fly.io Dashboard → Tokens → Personal access tokens で発行
   - GitHub リポジトリ → Settings → Secrets and variables → Actions → New repository secret

2. **Fly Postgres を attach**
   - Fly Dashboard → Apps → `prediction-market-analysis` → Postgres → Attach
   - これで `DATABASE_URL` が自動で secret として注入される

3. **必須 secrets を Fly に登録**（Dashboard → Secrets）
   - `POLYGON_RPC_HTTP` (Alchemy / QuickNode の URL)
   - `POLYGON_RPC_WS` (同上、WS)
   - `WEB_PASSWORD` (任意の長い文字列)
   - 任意: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

## 通常のデプロイ

main へ push（または PR を merge）すると `.github/workflows/deploy.yml` が走り、Fly.io へ自動デプロイされます。`post-deploy-smoke.yml` が完了後に `/_stcore/health` を叩いて緑かを確認します。

## ロールバック

Fly Dashboard → Apps → `prediction-market-analysis` → Releases → 古いリリースの "..." メニュー → "Deploy this release"。

または GitHub Actions の Re-run で前回 commit の deploy を再実行。

## 設定の変更（再デプロイなし）

UI の Settings ページから `settings` テーブル経由で:
  - `exchange_addresses`: 監視するコントラクトの上書き
  - `order_filled_topic0`: ABI 変更時の上書き
  - `rank_min_trades` / `rank_min_volume_usdc` / `replay_default_delays`

再デプロイは不要、worker / indexer はクエリ時に DB から読みます。
