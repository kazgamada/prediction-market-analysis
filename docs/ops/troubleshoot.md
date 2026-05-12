# トラブルシュート

## 1. 何かおかしい — まずどこを見るか

順番に開く（全部ブラウザだけで完結）:

1. **UI の Status ページ**: cursor block / lag / 1h trade count / dead-letter 数
2. **UI の Diagnostics ページ**: cursors, settings overrides, 最新 risk events, dead-letter details, recent jobs, build metadata
3. **Fly Dashboard → Apps → このアプリ → Monitoring**: 各プロセスの CPU / mem / restart count
4. **Fly Dashboard → Apps → このアプリ → Live Logs**: indexer / worker / web 全部のログがストリームされる

これで原因が当たれば対処。ダメなら下記の症状別。

## 2. 症状別

### `cursor block` が動かない

- Diagnostics の cursors を確認。`orderfilled_backfill` の `updated_at` が >5 分前なら indexer プロセスが停止している。
- Fly Dashboard の indexer プロセス machine を再起動。
- 直っても再発するなら、Live Logs で `iter_logs:` の出力を見て chunk_size が大きすぎないか確認。Settings から `indexer_chunk_size` を 500 に下げて再試行。

### `dead-letters` が増え続ける

- Diagnostics ページの "Dead-letters (pending)" でエラー本文を確認。
- 401/403 系: `POLYGON_RPC_HTTP` の API key 失効 → Fly secrets を更新 → indexer machine を再起動。
- "more than 10000 blocks" 系: chunk_size 過大 → Settings で `indexer_chunk_size` を下げる。
- WS 切断: 既知。WS は自動再接続するので無視可。10 分以上復帰しない場合は risk_events に出る。

### Phase 0 ボタンを押しても進まない

- Jobs ページで対象 job ID を開く。`status=PENDING` のままなら worker が動いていない → Fly Dashboard で worker 再起動。
- `status=RUNNING` で進捗が止まる: 子ステップが backfill 中。indexer が並行で catchup していれば数分後には進む。
- `status=FAILED`: `error_text` を確認。`backfill child failed` ならスキップして rank/replay は完走しているはず。それでも数値が出ないなら trades テーブルが空。

### UI が 5xx を返す

- Fly logs で `web` プロセスのスタックトレースを確認。
- `web_password` 未設定: 起動を拒否する仕様（fail-fast）。Fly secrets に `WEB_PASSWORD` を入れて再起動。

### `/readyz` が 503

- db: down → Fly Postgres の状態確認。
- rpc: down → `POLYGON_RPC_HTTP` の secret 確認。Dashboard で Re-attach できる。

## 3. 同じ場所を 3 回直してダメな場合

CLAUDE.md §0.5 の「全戻し」ルールに従う:
1. 直前の good release に Fly Dashboard からロールバック。
2. 何が壊れたかを `docs/requirements/REBUILD.md` §1.2 のトラブル表に追記。
3. その上で根本原因を解明してから再デプロイ。
