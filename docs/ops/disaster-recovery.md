# 障害復旧

## 全停止からの復旧（最悪シナリオ）

1. **Fly app と Postgres は分離** されているので、app machine が全滅しても DB データは無傷。
2. Fly Dashboard → Apps → `prediction-market-analysis` → Releases から直近の green release を Re-deploy。
3. 起動後、3 つの process（web / indexer / worker）が全部 `Started` になっているか Dashboard で確認。

## Postgres を吹き飛ばしてしまった場合

1. Fly Dashboard → Postgres → Restore from snapshot（Fly が自動取得した snapshot から戻す）。
2. snapshot がない場合は新規 attach + alembic が初期スキーマで起動 → indexer が過去 N 日分を再取り込み。
3. 過去データは `cursors.last_block = head - N_days * 43200` から自動 catchup。手動操作不要。

## ローカルへの定期ダンプ（推奨）

毎週手動で、または cron で:
```
fly proxy 5432 -a prediction-market-analysis-db
pg_dump "postgres://user:pass@localhost:5432/copytrader" | gzip > dump-$(date +%F).sql.gz
```
ダンプは `.gitignore` 配下に置く（リポジトリにはコミットしない）。

## RPC プロバイダ切り替え

1. Settings ページで一時的に `exchange_addresses` を上書きする（不要なら飛ばす）。
2. Fly secrets で `POLYGON_RPC_HTTP` / `POLYGON_RPC_WS` を新プロバイダの URL に更新。
3. indexer machine を Fly Dashboard から再起動。
4. Status ページで cursor が進み始めることを確認。
