# polymarket-copytrader 監査レポート

作成日: 2026-06-19  
監査対象: `/home/user/prediction-market-analysis`  
ブランチ: `claude/nice-clarke-lnm3kv`

---

## 1. 現状サマリー

| 項目 | 状態 |
|------|------|
| ユニットテスト | ✅ 62/62 pass（監査後に 20 件追加） |
| インテグレーションテスト | ⚠️ 24 件全 skip（Postgres 未接続。CI 環境では通る想定） |
| ruff lint | 要確認（mypy/ruff は未インストールのため未実行） |
| Docker 起動 | 要確認（ローカル Postgres 未起動） |
| 実装ステップ | S1〜S4 完了、S5（CI/ops docs）は部分実装 |
| Phase 0 エンドツーエンド | コード上は実装済。本番 Polygon RPC 未接続につき未検証 |

**完成度概算: 75%**（S1〜S4 コアは揃っている。S5 本番化 + S6 計測が残り）

---

## 2. 実行ログ

### 2.1 ユニットテスト（監査前）

```
42 passed in 0.75s
```

### 2.2 ユニットテスト（監査後 — test_cursor.py, test_jobs_queue.py 追加）

```
62 passed in 0.77s
```

### 2.3 インテグレーションテスト

```
24 skipped in 0.37s
```

理由: `conftest.py` が `localhost:55432` への Postgres 接続を試み、失敗で全件 skip。  
CI 環境（docker-compose.yml に postgres サービスあり）では通ると推定。

### 2.4 mypy / ruff

mypy・ruff ともに未インストール。`python3.12 -m mypy src/` → `No module named mypy`。  
CI ワークフロー（`.github/workflows/ci.yml`）上で実行される。

---

## 3. 実装済み vs 未実装

### 3.1 実装済み（コード確認済み）

| コンポーネント | ファイル | REBUILD §要件 |
|---|---|---|
| DB エンジン + URL 正規化 | `db/engine.py` | T17, D3 |
| ORM モデル（全テーブル） | `db/models.py` | §5 |
| Chunked INSERT ヘルパ | `db/chunked_insert.py` | T7 |
| Settings テーブル | `db/settings_table.py` | D6 |
| RPC クライアント（並列 chunk, FAILED yield） | `chain/client.py` | T1, T8, F3 |
| contracts（V2 アドレス + settings 上書き） | `chain/contracts.py` | T2, F6 |
| OrderFilled デコーダ | `chain/decoder.py` | T2 |
| エラー redact + body 保持 | `chain/errors.py` | T3, T4 |
| WebSocket 再接続ストリーム | `chain/stream.py` | F14 |
| Cursor monotonic advance + ensure_floor | `indexer/cursor.py` | T6, T9, F2, F5 |
| Backfill + dead-letter push | `indexer/backfill.py` | T1, T5, F1, F3 |
| Persist（trade upsert + signal emit） | `indexer/persist.py` | D4 |
| Stream consumer（WS → trades） | `indexer/stream_consumer.py` | F12, F14 |
| Dead-letter retry ループ | `indexer/retry_dead_letters.py` | F4 |
| Indexer supervisor（asyncio, 再起動つき） | `indexer/supervisor.py` | T10, T11 |
| Job queue（idempotency, SKIP LOCKED） | `jobs/queue.py` | D4, §4 |
| Job handlers（phase0, backfill, rank, replay, ...） | `jobs/handlers.py` | F8-F11 |
| Worker runner | `jobs/runner.py` | T10, §4.2 |
| Scheduler（cron + DB backed） | `jobs/scheduler.py` | — |
| PnL 計算（WACB） | `analysis/pnl.py` | F9 |
| Wallet rank | `analysis/rank.py` | F8 |
| Replay（遅延コピー simulation） | `analysis/replay.py` | F9 |
| Risk evaluator（halt 条件 7 項目） | `risk/evaluator.py` | §6.3 |
| Health server（aiohttp /healthz /readyz） | `health/server.py` | F21, F22 |
| Alembic migration（DDL 全テーブル） | `alembic/versions/0001_initial.py`, `0002_phase1_tables.py` | §5 |
| Config（pydantic-settings） | `config.py` | D6 |
| 3 プロセス entry（web/indexer/worker） | `runtime/` | §4.1, D2 |
| Execution layer（CLOB client, executor, position tracker） | `execution/` | Phase 1 先行実装 |
| Gamma resolver | `gamma/` | Phase 1 先行実装 |
| Web UI ホーム（12 タイル） | `web/app.py` | F15 相当 |
| Web UI Strategy（Phase 0 実行 + 結果） | `web/pages/1_Strategy.py` | F16 相当 |
| Web UI Execute（執行 + Watchlist） | `web/pages/2_Execute.py` | F17, F18 相当 |
| Web UI Ops（診断 + 設定） | `web/pages/3_Ops.py` | F19, F23 相当 |

### 3.2 未実装 / 要対応（IMPLEMENTATION_PLAN.md との差分）

| # | 種別 | 詳細 | 対応ファイル |
|---|------|------|------------|
| M1 | テスト欠落 | `tests/unit/test_cursor.py` が PLAN に記載なし → 本監査で追加 | 追加済 |
| M2 | テスト欠落 | `tests/unit/test_jobs_queue.py` が PLAN に記載なし → 本監査で追加 | 追加済 |
| M3 | Web ページ名ずれ | PLAN: `0_status.py`, `1_phase0.py`, `2_jobs.py`, `3_watchlist.py`, `4_settings.py`, `9_diagnostics.py` → 実際: `app.py`(home), `1_Strategy.py`, `2_Execute.py`, `3_Ops.py`, `4_Help.py` | 非ブロッカー（機能は揃っているが URL/名称が違う） |
| M4 | 認証 no-op | `web/auth.py::require_password()` が空実装（コメントに「再導入する場合は git 履歴から復元」） | `src/copytrader/web/auth.py` |
| M5 | WEB_PASSWORD fail-fast 未実装 | 要件 F20「WEB_PASSWORD 未設定なら起動を拒否」が auth.py では実現されていない | `src/copytrader/web/auth.py`, `runtime/web_main.py` |
| M6 | CI deployment workflow | `.github/workflows/deploy.yml` は存在するが内容要確認（Fly.io secrets 設定に依存） | `.github/workflows/deploy.yml` |
| M7 | ops docs 未完 | `docs/ops/` の deploy.md, troubleshoot.md, disaster-recovery.md は存在するが中身が要確認 | `docs/ops/` |

---

## 4. 課題一覧

| ID | 優先度 | 観点 | 課題 | 証拠（ファイル:行） | 修正方針 |
|----|--------|------|------|-------------------|----------|
| P0-1 | P0 | セキュリティ | `require_password()` が no-op。認証なしで全 UI にアクセス可能 | `src/copytrader/web/auth.py:10-13` | パスワードゲートを再有効化。`WEB_PASSWORD` 未設定なら `st.stop()` |
| P0-2 | P0 | セキュリティ | `WEB_PASSWORD` 未設定でも web_main が起動する（F20 fail-fast 違反） | `src/copytrader/runtime/web_main.py` | 起動時に `WEB_PASSWORD` チェックを追加 |
| P1-1 | P1 | テスト | `test_cursor.py` 未存在（PLAN §S2 必須）→ 本監査で追加 | `tests/unit/`（追加済） | 完了 |
| P1-2 | P1 | テスト | `test_jobs_queue.py` 未存在（PLAN §S3 必須）→ 本監査で追加 | `tests/unit/`（追加済） | 完了 |
| P2-1 | P2 | 観測性 | `web/auth.py` の無効化コメントが混乱を招く。意図が不明確 | `src/copytrader/web/auth.py:1-13` | コメントを明確化、または再有効化 |
| P2-2 | P2 | ドキュメント | `docs/ops/` の内容が充実しているか要確認 | `docs/ops/*.md` | 内容確認・補足 |
| P3-1 | P3 | コード品質 | web/pages のファイル名が PLAN と異なる（機能的には問題なし） | `src/copytrader/web/pages/` | オプション: リネーム or PLAN 側を現実に合わせて更新 |
| P3-2 | P3 | テスト | インテグレーションテストはローカル Postgres なしで全 skip | `tests/integration/conftest.py:19` | CI の docker-compose に postgres を確認 |

---

## 5. 優先度別ロードマップ

### P0: 即対応（セキュリティ）

1. **`web/auth.py` のパスワードゲート再有効化** — 現在 no-op。本番では誰でも UI にアクセス可能。
2. **`web_main.py` の WEB_PASSWORD fail-fast** — `WEB_PASSWORD` 未設定なら起動エラーにする。

### P1: リリース前必須

3. ~~`test_cursor.py` 追加~~ — 本監査で完了（62 tests pass）
4. ~~`test_jobs_queue.py` 追加~~ — 本監査で完了（62 tests pass）

### P2: リリース後 2 週間以内

5. ops docs の充実（deploy.md / troubleshoot.md / disaster-recovery.md）
6. Fly.io 本番での end-to-end 検証（S5）

### P3: 改善余地

7. Web ページ名の PLAN との整合（機能的影響なし）
8. インテグレーションテストの CI 環境整備確認

---

## 6. T1〜T22 トラブル予防マッピング（実装確認）

| # | トラブル | 予防コード | 確認済 |
|---|---------|-----------|--------|
| T1 | chunk 失敗で全停止 | `chain/client.py` ChunkResult FAILED yield + `indexer/backfill.py` dead-letter | ✅ |
| T2 | V1 アドレス混入 | `chain/contracts.py` V2 ハードコード + settings 上書き | ✅ |
| T3 | API key ログ露出 | `chain/errors.py::redact_url` | ✅ |
| T4 | JSON-RPC body 喪失 | `chain/errors.py` RpcError.body | ✅ |
| T5 | 全期間走査 | `indexer/backfill.py` window 引数必須 | ✅ |
| T6 | cursor 巻き戻り | `indexer/cursor.py::advance` GREATEST | ✅ |
| T7 | 65535 パラメータ超過 | `db/chunked_insert.py::max_rows_per_chunk` | ✅ |
| T8 | バックフィル遅延 | `chain/client.py` max_parallel=4 | ✅ |
| T9 | cursor 過去張り付き | `indexer/cursor.py::ensure_floor` | ✅ |
| T10 | タスク死亡でプロセス全停止 | `indexer/supervisor.py` asyncio.gather + 再起動 | ✅ |
| T11 | プロセス役割の曖昧さ | 3 プロセス分離（web/indexer/worker） | ✅ |
| T12 | release_command 失敗 | `runtime/*_main.py` 起動時 alembic + advisory lock | ✅ |
| T13 | auto-stop でジョブ消滅 | fly.toml 要確認（auto_stop_machines='off' の設定） | ⚠️ 要確認 |
| T14 | fly.toml 旧構文 | fly.toml を確認 | ⚠️ 要確認 |
| T15 | app 名不一致 | fly.toml app 名維持 | ✅ |
| T16 | Docker ビルド失敗 | Dockerfile COPY 明示 | ✅（要確認） |
| T17 | postgres:// 拒否 | `db/engine.py::normalize_db_url` | ✅ |
| T18 | UI ボタンでブロック | `jobs/queue.py::enqueue` で DB 書き込みのみ | ✅ |
| T19 | live log 見えない | `job_logs` テーブル + UI 2 秒 polling | ✅ |
| T20 | ページ遷移でジョブ消滅 | worker プロセスで実行（Streamlit セッション非依存） | ✅ |
| T21 | 観測性なし | `health/server.py` /healthz /readyz（S1 から） | ✅ |
| T22 | Phase 0 未完走のまま進行 | go/no-go 判断フローは REBUILD §11 で文書化 | ✅（運用で対応） |

---

## 7. テスト結果まとめ

```
# 監査前
42 tests passed, 24 integration tests skipped

# 本監査での追加実装
+ tests/unit/test_cursor.py   (9 tests)
+ tests/unit/test_jobs_queue.py (11 tests)

# 監査後
62 tests passed, 24 integration tests skipped
```

---

## 8. ブロッカー

なし（core 機能は実装済）。Fly.io 本番デプロイには以下が必要:

- `FLY_API_TOKEN`（GitHub Actions secret）
- `DATABASE_URL`, `POLYGON_RPC_HTTP`, `POLYGON_RPC_WS`, `WEB_PASSWORD`（Fly secrets）
- Fly Postgres attach 確認

---

## 9. 次のアクション（優先順）

1. **P0-1/P0-2**: `web/auth.py` と `web_main.py` のパスワードゲート再有効化
2. Fly.io 本番 secrets 設定 → `fly deploy` でデプロイ検証（S5）
3. `curl <app>.fly.dev/readyz` が `{"status":"ok","db":"ok","rpc":"ok"}` になることを確認
4. Phase 0 ジョブを UI から 1 回実行し、replay レポートを確認（S6）
