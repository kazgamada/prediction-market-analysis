# Polymarket Copytrader 実装計画書

最終更新: 2026-05-12
基準: `docs/requirements/REBUILD.md`（要件定義書）
対象ブランチ: `claude/requirements-complete-rebuild-oxQKV`（main 反映は PR で）

---

## 0. このドキュメントの位置づけ

REBUILD.md は **何を作るか / なぜ作るか / 完了条件**を定義した。
本書はそれを **どう作るか** に落とす。具体的には:

- ディレクトリ・モジュール構成
- DB スキーマ（DDL レベル）
- プロセス間契約（job_queue 仕様）
- Step S0〜S6 の各ステップで「触るファイル / 完了テスト / コミット粒度」
- 過去トラブル T1〜T22 をどのレイヤで構造的に潰すか

実装着手前に本書をユーザー承認すること。承認後は **本書から逸脱しない**。

---

## 1. 技術選定（要件 §2 / CLAUDE.md §2 を再確認）

| 層 | 採用 | 備考 |
|----|------|------|
| 言語 | Python 3.12 | 既存資産なし（リポ丸裸）なので新規。型ヒント必須 |
| 依存管理 | uv（pyproject.toml） | Dockerfile からも uv で sync |
| Web フレームワーク | Streamlit 1.36+ | 要件 §6.4。長時間処理は持たせない |
| ORM | SQLAlchemy 2.0 (async は使わない) | psycopg3 driver |
| DB マイグレーション | Alembic | 既存 alembic/ ディレクトリを再利用 |
| RPC クライアント | web3.py 7.x | Polygon JSON-RPC + WS subscription |
| Polymarket SDK | `py-clob-client>=0.20` | Phase 0〜2 では read-only。発注は使わない |
| ジョブキュー | **DB ポーリング方式（自作）** | Redis / Celery を持ち込まない（最小構成原則） |
| プロセス管理 | Fly.io processes | `web` / `indexer` / `worker` の 3 プロセス |
| ログ | 標準 logging + DB `job_logs` 二重書き | 構造化 JSON は不要 |
| 設定 | pydantic-settings + `settings` テーブル | env と DB の二段重ね（要件 D6） |
| テスト | pytest + pytest-asyncio | RPC は responses で stub |
| Lint / Format | ruff | line-length 100 |
| CI | GitHub Actions | unit + integration + post-deploy smoke |
| デプロイ | Fly.io | release_command は使わず、各プロセス起動時に migration |

**意図的に入れないもの**: Redis、Celery、SQS、Lambda、Vercel、別言語のサービス、フロントエンド SPA、JWT、OAuth、GraphQL。

---

## 2. ディレクトリ構成（最終形）

```
.
├── README.md                       # ブラウザ完結の運用手順を含む
├── .gitignore
├── .env.example                    # 必須 env のテンプレ
├── .python-version                 # 3.12
├── .dockerignore
├── pyproject.toml                  # uv lock 管理
├── uv.lock
├── Dockerfile                      # multi-stage; uv で sync
├── docker-compose.yml              # local: postgres + 3 プロセス
├── fly.toml                        # 3 processes, auto_stop=off, min=1
├── Makefile                        # local 用ショートカット（最小）
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial.py         # §3 のスキーマを 1 ファイルで投入
├── docs/
│   ├── requirements/REBUILD.md     # 既存
│   ├── plans/IMPLEMENTATION_PLAN.md  # 本書
│   └── ops/                        # 運用手順（後で書く）
│       ├── deploy.md
│       ├── troubleshoot.md
│       └── disaster-recovery.md
├── src/copytrader/
│   ├── __init__.py
│   ├── config.py                   # pydantic-settings
│   ├── logging_setup.py            # logger を 1 箇所で組む
│   ├── db/
│   │   ├── __init__.py
│   │   ├── engine.py               # SQLAlchemy engine + URL 正規化 (T17)
│   │   ├── models.py               # 全テーブル
│   │   └── chunked_insert.py       # 65535 パラメータ上限ヘルパ (T7)
│   ├── chain/
│   │   ├── __init__.py
│   │   ├── client.py               # JsonRpcClient: chunk 分割 + 並列 + retry
│   │   ├── stream.py               # WS subscription（再接続つき）
│   │   ├── contracts.py            # CTF Exchange V2 アドレス + ABI (T2)
│   │   ├── decoder.py              # OrderFilled デコード
│   │   └── errors.py               # API key redact (T3) + body 保持 (T4)
│   ├── indexer/
│   │   ├── __init__.py
│   │   ├── cursor.py               # GREATEST 更新 (T6) + recent_floor ジャンプ (T9)
│   │   ├── backfill.py             # range backfill + dead-letter (T1)
│   │   ├── stream_consumer.py      # WS 経由のリアルタイム取り込み
│   │   └── retry_dead_letters.py   # T1 の dead-letter を 1 分おきに再試行
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── pnl.py                  # ウォレット PnL 計算
│   │   ├── rank.py                 # 上位ウォレット選定
│   │   └── replay.py               # 遅延コピー replay
│   ├── monitor/
│   │   ├── __init__.py
│   │   └── watchlist_signal.py     # F12: watchlist 約定 → signals
│   ├── jobs/
│   │   ├── __init__.py
│   │   ├── queue.py                # enqueue / dequeue / progress
│   │   ├── handlers.py             # kind ごとの handler 登録
│   │   └── runner.py               # worker のメインループ
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── indexer_main.py         # `indexer` プロセスの entry
│   │   ├── worker_main.py          # `worker` プロセスの entry
│   │   └── web_main.py             # 内部ジョブ起動を共通化
│   ├── health/
│   │   ├── __init__.py
│   │   └── server.py               # /healthz /readyz (FastAPI ではなく aiohttp 1 本)
│   └── web/
│       ├── __init__.py
│       ├── app.py                  # streamlit エントリ
│       ├── auth.py                 # WEB_PASSWORD ゲート (F20)
│       ├── format.py               # 表示用 helper
│       └── pages/
│           ├── 0_status.py         # F15
│           ├── 1_phase0.py         # F16: ボタン 1 つで enqueue
│           ├── 2_jobs.py           # F17: job 一覧 + 個別 live log
│           ├── 3_watchlist.py      # F18
│           ├── 4_settings.py       # F19
│           └── 9_diagnostics.py    # F23
├── tests/
│   ├── unit/
│   │   ├── test_chain_client.py    # chunk 分割 / retry / redact (T1, T3, T4)
│   │   ├── test_decoder.py         # CTF V2 ABI デコード (T2)
│   │   ├── test_cursor.py          # monotonic 更新 (T6, T9)
│   │   ├── test_chunked_insert.py  # 65535 上限 (T7)
│   │   ├── test_db_url.py          # postgres:// → postgresql+psycopg:// (T17)
│   │   └── test_jobs_queue.py      # idempotency / claim / progress
│   └── integration/
│       └── test_phase0_e2e.py      # mock RPC で backfill→rank→replay の e2e
├── scripts/
│   └── dump-db.sh                  # ブラウザ完結の手順から呼ぶ pg_dump ラッパ
└── .github/
    └── workflows/
        ├── ci.yml                  # ruff + pytest
        ├── deploy.yml              # main push → fly deploy
        └── post-deploy-smoke.yml   # /readyz 確認
```

---

## 3. データモデル DDL（alembic/versions/0001_initial.py）

要件 §5 の最小セットを 1 マイグレーションで投入する。**スキーマ変更は別ファイル**（破壊的なら別途）。

```sql
-- カーソル（取り込み進捗）
CREATE TABLE cursors (
  name           TEXT PRIMARY KEY,         -- 'orderfilled_backfill' 等
  last_block     BIGINT NOT NULL,
  last_block_at  TIMESTAMPTZ,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- chunk 取り込み済みマーク（再開時の冪等性確保）
CREATE TABLE blocks_seen (
  block_number   BIGINT PRIMARY KEY,
  log_count      INT NOT NULL,
  fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 約定（CTF Exchange OrderFilled イベント）
CREATE TABLE trades (
  tx_hash        BYTEA NOT NULL,
  log_index      INT NOT NULL,
  block_number   BIGINT NOT NULL,
  ts             TIMESTAMPTZ NOT NULL,
  maker          BYTEA NOT NULL,
  taker          BYTEA NOT NULL,
  token_id       NUMERIC(78,0) NOT NULL,   -- ERC1155 token id
  side           SMALLINT NOT NULL,        -- 0=BUY 1=SELL (taker 視点)
  price          NUMERIC(20,8) NOT NULL,   -- 0..1
  size_shares    NUMERIC(38,18) NOT NULL,
  size_usdc      NUMERIC(28,6) NOT NULL,
  PRIMARY KEY (tx_hash, log_index)
);
CREATE INDEX trades_ts_idx       ON trades (ts);
CREATE INDEX trades_block_idx    ON trades (block_number);
CREATE INDEX trades_taker_ts_idx ON trades (taker, ts DESC);
CREATE INDEX trades_token_ts_idx ON trades (token_id, ts DESC);

-- ウォレット集計（rank 用の事前集計）
CREATE TABLE wallet_stats_daily (
  address           BYTEA NOT NULL,
  date              DATE NOT NULL,
  trades            INT NOT NULL,
  volume_usdc       NUMERIC(28,6) NOT NULL,
  realized_pnl_usdc NUMERIC(28,6),
  win_rate          NUMERIC(6,4),
  PRIMARY KEY (address, date)
);

-- watchlist
CREATE TABLE watchlist (
  address    BYTEA PRIMARY KEY,
  note       TEXT,
  added_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  active     BOOLEAN NOT NULL DEFAULT TRUE
);

-- 監視 signal（Phase 1+）
CREATE TABLE signals (
  id          BIGSERIAL PRIMARY KEY,
  address     BYTEA NOT NULL,
  token_id    NUMERIC(78,0) NOT NULL,
  side        SMALLINT NOT NULL,
  price       NUMERIC(20,8) NOT NULL,
  size_usdc   NUMERIC(28,6) NOT NULL,
  ts          TIMESTAMPTZ NOT NULL,
  source      TEXT NOT NULL              -- 'stream' / 'replay'
);
CREATE INDEX signals_ts_idx ON signals (ts DESC);

-- リスクイベント（WS 切断 / dead-letter 飽和等）
CREATE TABLE risk_events (
  id        BIGSERIAL PRIMARY KEY,
  kind      TEXT NOT NULL,
  severity  SMALLINT NOT NULL,           -- 1=info 2=warn 3=alert
  message   TEXT NOT NULL,
  context   JSONB,
  ts        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX risk_events_ts_idx ON risk_events (ts DESC);

-- ジョブキュー
CREATE TYPE job_status AS ENUM ('PENDING','RUNNING','SUCCEEDED','FAILED','CANCELLED');
CREATE TABLE jobs (
  id               BIGSERIAL PRIMARY KEY,
  kind             TEXT NOT NULL,        -- 'phase0' / 'backfill' / 'rank' / 'replay' / 'inspect' / 'reconcile' / 'poll'
  status           job_status NOT NULL DEFAULT 'PENDING',
  params           JSONB NOT NULL,
  progress         JSONB NOT NULL DEFAULT '{}'::jsonb,
  result           JSONB,
  error_text       TEXT,
  idempotency_key  TEXT UNIQUE,          -- D4: 同一 key で再投入可
  parent_job_id    BIGINT REFERENCES jobs(id),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at       TIMESTAMPTZ,
  finished_at      TIMESTAMPTZ,
  worker_id        TEXT                  -- claim 中の worker
);
CREATE INDEX jobs_status_idx ON jobs (status, created_at);

-- ジョブログ（live log を UI に流す）
CREATE TABLE job_logs (
  id        BIGSERIAL PRIMARY KEY,
  job_id    BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
  level     SMALLINT NOT NULL,           -- 10=DEBUG 20=INFO 30=WARN 40=ERROR
  message   TEXT NOT NULL
);
CREATE INDEX job_logs_job_ts_idx ON job_logs (job_id, ts);

-- RPC dead-letter（chunk 単位の失敗）
CREATE TABLE rpc_dead_letters (
  id          BIGSERIAL PRIMARY KEY,
  kind        TEXT NOT NULL,             -- 'logs_range'
  request     JSONB NOT NULL,
  error_text  TEXT NOT NULL,
  retries     INT NOT NULL DEFAULT 0,
  next_retry  TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);
CREATE INDEX rpc_dl_pending_idx ON rpc_dead_letters (next_retry) WHERE resolved_at IS NULL;

-- 設定（コントラクトアドレスやしきい値の上書き）
CREATE TABLE settings (
  key        TEXT PRIMARY KEY,
  value      JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

INSERT は **必ず `chunked_insert.py` 経由**。
`max_rows = floor((65535 - 100) / column_count)` を 1 関数に閉じ込める（T7 構造的予防）。

---

## 4. プロセス間契約（jobs）

### 4.1 enqueue

```python
job_id = jobs_queue.enqueue(
    kind="phase0",
    params={"window": 30, "delays": [30, 60, 120], "copy_usd": 50, "watchlist_top": 10},
    idempotency_key="phase0:2026-05-12",   # 同日 2 回押しても 1 ジョブ
)
```

- 既存 `idempotency_key` があれば既存 job を返す（重複起動を構造的に防ぐ）。
- web は **enqueue するだけ**で execute しない（D2）。

### 4.2 dequeue (worker)

```python
with jobs_queue.claim(worker_id) as job:   # SELECT ... FOR UPDATE SKIP LOCKED
    handler = HANDLERS[job.kind]
    handler(job)
```

- `SKIP LOCKED` で複数 worker のレースを防ぐ。
- handler 内では `job.log("...")`, `job.set_progress({...})`, `job.set_result({...})`。
- 例外は `runner.py` で catch → `status=FAILED` + `error_text` を保存 → worker は次のジョブへ（T10 構造的予防）。

### 4.3 子ジョブ

`kind=phase0` の handler は内部で:

```python
backfill_id = enqueue("backfill", {"window": params["window"]}, parent=job.id)
wait_for(backfill_id)
rank_id = enqueue("rank", {...}, parent=job.id)
wait_for(rank_id)
replay_id = enqueue("replay", {...}, parent=job.id)
wait_for(replay_id)
job.set_result({"replay_job_id": replay_id})
```

`wait_for` は同 worker 内で polling（粒度 2 秒）。`parent_job_id` を持っておくと UI のツリー表示が容易。

---

## 5. プロセス起動 (fly.toml)

```toml
[processes]
  web      = "sh -c 'alembic upgrade head && python -m copytrader.runtime.web_main'"
  indexer  = "sh -c 'alembic upgrade head && python -m copytrader.runtime.indexer_main'"
  worker   = "sh -c 'alembic upgrade head && python -m copytrader.runtime.worker_main'"
```

- migration は各プロセス起動時に実行。**Postgres advisory lock** で多重実行を防ぐ:
  ```python
  with conn.begin():
      conn.execute(text("SELECT pg_advisory_lock(8675309)"))
      command.upgrade(alembic_cfg, "head")
      conn.execute(text("SELECT pg_advisory_unlock(8675309)"))
  ```
- `release_command` は **使わない**（T12 構造的予防）。
- 全プロセス `auto_stop_machines='off'`, `min_machines_running=1`（T13）。

---

## 6. RPC クライアント設計（chain/client.py）

過去トラブル T1〜T4, T8 を構造で潰す:

```python
class JsonRpcClient:
    def __init__(self, http_url: str, *, max_parallel: int = 4, max_retries: int = 3):
        ...

    async def get_logs(
        self,
        from_block: int,
        to_block: int,
        topics: list[str],
        addresses: list[str],
        chunk_size: int = 1000,
    ) -> AsyncIterator[ChunkResult]:
        """
        - [from_block, to_block] を chunk_size で割って並列実行
        - 1 chunk の失敗は ChunkResult(status=FAILED, error=...) として yield
        - 上位レイヤで dead-letter に積む（T1）
        - retry は per-chunk で max_retries 回、429/503 のみ
        - エラー文字列は redact_url(http_url) で API key を伏せ字（T3）
        - JSON-RPC error.body は ChunkResult.error_body に保持（T4）
        """
```

`ChunkResult` の status は `OK / EMPTY / FAILED` の 3 値。OK のときだけ logs を返す。

---

## 7. UI 設計（Streamlit）

要件 §6.4 を厳守。**長時間処理は持たない**。

```
0_status.py        # 既定ページ
  - cursor / head / lag / 直近 1h trades / dead-letter 件数 / RPC self-test
  - すべて `st.query` で 5 秒キャッシュ（要件 D2 / 蟻地獄 §0.3 の診断ファースト）

1_phase0.py
  - "Run Phase 0" ボタン → jobs_queue.enqueue("phase0", ...)
  - 直近の phase0 job 一覧 + ステータス

2_jobs.py
  - jobs テーブルを SELECT して表示
  - 個別 job 詳細: progress JSON + job_logs を 2 秒 polling

3_watchlist.py
  - watchlist の add / remove / toggle active

4_settings.py
  - settings テーブルを key/value 編集

9_diagnostics.py
  - cursors / settings / git SHA / build time / 最新 risk_events / dead-letter
```

認証: `auth.py` で `WEB_PASSWORD` 未設定なら起動を拒否（fail-fast、要件 F20）。

---

## 8. ステップ別実装計画

### S0: 承認 ← 現在地

- 本書をユーザーがレビューし承認する。
- §11 の Q1〜Q5（要件側のオープン質問）に回答が揃う。

### S1: スケルトン + 観測性（PR 1 本）

**目的**: `docker compose up` で 3 プロセスが起動し `/readyz` が 200 を返すまで。

実装:
- `pyproject.toml` / `Dockerfile` / `docker-compose.yml` / `fly.toml` / `.env.example` / `Makefile`
- `src/copytrader/{config,logging_setup,db/{engine,models,chunked_insert}}` のスケルトン
- `alembic/versions/0001_initial.py`（§3 の DDL を全部）
- `src/copytrader/health/server.py`（aiohttp で `/healthz` `/readyz`）
- `src/copytrader/runtime/{web,indexer,worker}_main.py`（health server だけ起動して loop）
- `tests/unit/test_db_url.py`（T17）
- `tests/unit/test_chunked_insert.py`（T7）
- `.github/workflows/ci.yml`

完了条件:
- `docker compose up` でローカル 3 プロセスが green
- `curl localhost:8501/_stcore/health` が 200
- `curl localhost:8080/readyz`（health server）が `{"status":"ok","db":"ok","rpc":"unknown"}`
- `pytest -q` が緑
- ruff が緑

### S2: indexer MVP（PR 1 本）

**目的**: 過去 7 日分の OrderFilled が 30 分以内に取り込めること。

実装:
- `chain/{client,contracts,decoder,errors,stream}`
- `indexer/{cursor,backfill,stream_consumer,retry_dead_letters}`
- `runtime/indexer_main.py` を本実装に差し替え（backfill 起動 → stream subscribe → dead-letter retry の 3 タスクを supervise）
- supervisor は asyncio.gather で個別タスク例外を catch し再起動（T10）
- `tests/unit/test_chain_client.py`（chunk 分割 / API key redact / JSON-RPC body 保持）
- `tests/unit/test_decoder.py`（CTF V2 ABI で実イベント 1 件を decode）
- `tests/unit/test_cursor.py`（GREATEST 更新 / recent_floor ジャンプ）
- `tests/integration/test_indexer_smoke.py`（mock RPC で 1000 ブロック取り込み）

完了条件:
- ローカル Docker で indexer プロセスが過去 7 日分を 30 分以内に取り込み完走
- 取り込み失敗 chunk が `rpc_dead_letters` に積まれ、`retry_dead_letters` が成功させる
- indexer プロセスを SIGKILL → 再起動で進捗が継続（cursor が巻き戻らない）
- `/readyz` で `rpc:"ok"` になる

### S3: worker / jobs MVP（PR 1 本）

**目的**: `phase0` ジョブをコマンド or psql で enqueue → worker が rank+replay を完走 → 結果が `jobs.result` に入る。

実装:
- `jobs/{queue,handlers,runner}`
- `analysis/{pnl,rank,replay}`
- `runtime/worker_main.py` 本実装
- `tests/unit/test_jobs_queue.py`（idempotency / claim / FAILED 時の挙動）
- `tests/integration/test_phase0_e2e.py`（trades テーブルに seed → phase0 enqueue → 完走確認）

完了条件:
- `psql -c "INSERT INTO jobs (kind, params) VALUES ('phase0', '{...}')"` で起動
- 数分で `status=SUCCEEDED` + `result` に replay レポートが入る
- 1 ジョブを途中で `kill -9` worker → 別 worker が claim せず PENDING に戻ること（または FAILED として明示）

### S4: Web UI MVP（PR 1 本）

**目的**: ブラウザから Phase 0 ボタン 1 つで S2+S3 が走り、結果が画面で見えること。

実装:
- `web/{app,auth,format,pages/{0_status,1_phase0,2_jobs,3_watchlist,4_settings,9_diagnostics}}`
- `runtime/web_main.py` を Streamlit + health server 同居に差し替え

完了条件:
- ローカル `http://localhost:8501` を開く → パスワードゲート
- Status ページに cursor / lag / RPC self-test が出る
- Phase 0 ボタンを押す → Jobs ページで RUNNING → SUCCEEDED まで live log が流れる
- 結果テーブルに上位ウォレット + replay PnL が表示
- ページ遷移してもジョブが消えない（worker 側で動いているため）

### S5: Fly.io 本番化（PR 1 本）

**目的**: 本番でも S4 と同じ操作がブラウザのみで完了すること。

実装:
- `.github/workflows/{deploy.yml,post-deploy-smoke.yml}`
- `docs/ops/{deploy,troubleshoot,disaster-recovery}.md`（ブラウザ完結手順）
- README に「セットアップ・運用・障害対応」を追記

完了条件:
- main へ merge → GitHub Actions で自動デプロイ → 5 分以内に反映
- 本番 `/readyz` が緑
- ブラウザで Phase 0 を完走
- 1 プロセスを Fly Dashboard で stop → 自動再起動 + 進捗継続

### S6: Phase 0 本番計測

**目的**: 過去 30 日で edge があるかを判定。

- `window=30, watchlist_top=Q2, delays=[30,60,120], copy_usd=50` で実行
- 結果を §11 Q1 の基準に照らして go / no-go を判定
- no-go なら撤退（Phase 1+ には進まない）

---

## 9. トラブル T1〜T22 ↔ 実装上の予防策マッピング

| # | 予防策が入る場所 |
|---|------------------|
| T1 | `chain/client.py` の `ChunkResult.status=FAILED` + `indexer/backfill.py` で dead-letter 追加 |
| T2 | `chain/contracts.py` で V2 のみハードコード + `settings` テーブルで上書き可 |
| T3 | `chain/errors.py::redact_url` を全例外メッセージで通す |
| T4 | `chain/errors.py` の `RpcError(body=...)` を保持 |
| T5 | `indexer/backfill.py` は常に `window` を引数で受ける（無制限実行を構造的に不可能化） |
| T6 | `indexer/cursor.py::advance(new)` は `last_block = GREATEST(last_block, :new)` |
| T7 | `db/chunked_insert.py` を **すべての** bulk INSERT で経由 |
| T8 | `JsonRpcClient(max_parallel=4)` + `chunked_insert.py` で 1 回の commit を最大化 |
| T9 | `cursor.py::ensure_floor(head_block - N_days_blocks)` を起動時に同期実行 |
| T10 | `runtime/{indexer,worker}_main.py` の supervisor が個別タスク例外を catch + 再起動 |
| T11 | indexer / worker / web を物理プロセス分離。web に長時間ジョブを置かない（D2） |
| T12 | `release_command` を使わず、各プロセス起動時 alembic + advisory lock |
| T13 | fly.toml に `auto_stop_machines='off'` + `min_machines_running=1` を全 process |
| T14 | fly.toml は `[http_service]` の最新構文のみ。CI の post-deploy で fly config validate |
| T15 | fly app 名は `prediction-market-analysis` を維持（既存資産流用） |
| T16 | Dockerfile の COPY 文に README.md / pyproject.toml / src/ を明示。.dockerignore で `**` 除外しない |
| T17 | `db/engine.py::normalize_db_url` で `postgres://` → `postgresql+psycopg://` 変換 |
| T18 | UI のボタンは `jobs_queue.enqueue` のみ。同期実行を構造的に禁止 |
| T19 | live log は `job_logs` テーブル経由。Streamlit からは 2 秒 polling |
| T20 | ジョブは worker プロセスで実行。Streamlit セッションに依存しない |
| T21 | `health/server.py` を S1 から実装（後付けではない） |
| T22 | S6 の go/no-go 基準を S0 で確定（要件 Q1）。基準未充足なら以降の機能追加禁止 |

---

## 10. 各 Step のコミット粒度

| Step | コミット数（目安） |
|------|--------------------|
| S1 | 1 PR / 5〜8 commits（pyproject → docker → DDL → health → CI） |
| S2 | 1 PR / 6〜10 commits（client → decoder → cursor → backfill → stream → supervisor → tests） |
| S3 | 1 PR / 5〜8 commits（queue → handlers → analysis → runner → e2e test） |
| S4 | 1 PR / 5〜8 commits（auth → 各ページ → format helper） |
| S5 | 1 PR / 3〜5 commits（CI → ops docs → README 改訂） |
| S6 | コミットなし（運用フェーズ） |

各 PR は **CI green** + **手動受け入れ条件 (REBUILD §13 A1〜A6 のうち該当)** を満たすまで merge しない。

---

## 11. リスクと前提

R1. **Polygon RPC の rate limit**: Alchemy 無料枠で Phase 0 を回しきれるかは未検証。S2 で初回計測。
R2. **CTF Exchange V2 の ABI**: 公式リポジトリから ABI を取得できる前提。取得不能なら S2 着手不可。
R3. **Fly.io の月額**: web 1GB + indexer 512MB + worker 512MB + Postgres dev tier。$10〜$20/月程度を想定。
R4. **WS subscription の安定性**: Alchemy WS は 5 分で idle 切断する仕様あり。`stream.py` で keepalive ping を必須にする。
R5. **要件側 Q1 (撤退ライン) の数値**: S0 で確定しないまま S6 に進むと「edge ありか不明」のまま延々続く（T22 再発）。**S0 で必ず数値化**。

---

## 12. 完了の定義

S5 まで完了し、以下が **すべて** 真であれば本計画は実装完了とみなす:

- REBUILD.md §13 A1〜A6 をすべて満たす
- 本書 §9 の T1〜T22 すべてに対応コードまたは構造的予防が入っている
- README に「セットアップ・運用・障害対応」がブラウザ完結ベースで書かれている
- post-deploy smoke が CI で緑

S6 は実装ではなく運用判定なので、本計画のスコープ外。

以上。
