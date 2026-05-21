# Phase 1+: 自律運用までの実装要件定義書

最終更新: 2026-05-21
対象リポジトリ: `kazgamada/prediction-market-analysis`
前提: Phase 0 (オフライン backtest) は実装済み。UI (Home / Strategy / Execute / Ops) はモックで稼働中。

---

## 0. このドキュメントのゴール

本書は **「Phase 0 → 自律運用」までに作るもの全部** を、すぐ実装開始できる粒度で定義する。

実装完了後、本書の §13 のチェックリストを 1 つずつ消していけば、Phase A (Paper) → B (Micro) → C (Small) → D (Scale) のロールアウトに即移行できる状態を目指す。

---

## 1. 現状とギャップ

### 1.1 実装済 (Phase 0)

| レイヤ | 内容 | 状態 |
|---|---|---|
| 観測 | Polygon indexer (backfill + WS), Trade テーブル | ✅ |
| 分析 | weighted-avg PnL, wallet ranking, delayed copy replay | ✅ |
| ジョブ | DB ポーリング型ジョブキュー, phase0 e2e | ✅ |
| UI | Home / Strategy / Execute / Ops の 4 ページ (主に mock) | ✅ |

### 1.2 未実装 (本書のスコープ)

| レイヤ | 内容 | 章 |
|---|---|---|
| L1 強化 | Gamma API 連携 (resolve PnL) | §3 |
| L2 執行 | py-clob-client write, signals, positions, executions | §4 |
| L3 リスク | kill switch, 停止条件 7, 上限 4, 連敗 size 半減 | §5 |
| L4 メタ自律 | 自動 phase0 cron, watchlist promotion/demotion | §6 |
| L5 監督 | Telegram 通知, 日次サマリ, audit log | §7 |
| L6 UI 連携 | mock を実データに差し替え | §8 |
| Ops | 監視, バックアップ, secrets 管理 | §9 |

---

## 2. 設計原則

1. **Fail-closed**: どこか 1 つでも判断不能になったら発注停止。「不明 = 危険」を徹底。
2. **べき等**: 全ての発注 / job は idempotency key で多重防止。
3. **DB 一元化**: state は全部 Postgres。Redis / Celery / S3 は使わない。
4. **小さい変更**: 各 PR は 1 つの責務だけ。本書の §3〜§7 は順番に独立 PR で。
5. **観測可能**: 何かおかしい時、Ops ページ + Telegram + Fly logs の 3 つで原因が分かるようにする。
6. **撤退容易**: kill switch + Fly machine 停止で **30 秒以内に全停止** できる。
7. **ブラウザ完結**: 運用者の作業は基本ブラウザのみ。CLI は緊急時のみ。

---

## 3. Layer 1 強化 — Gamma API 連携 (resolve PnL)

### 3.1 目的
今の Phase 0 は「クローズした trade の差益」しか見ていない。Polymarket は最終的に 0/1 USDC に確定するので、**resolve 後の最終 PnL** で edge を判定したい。

### 3.2 実装

**新規モジュール**: `src/copytrader/gamma/`

```
gamma/
  __init__.py
  client.py          # httpx で Gamma API GET
  models.py          # MarketResolution dataclass
  resolver.py        # cron: 解決済 market を取り込み、resolutions テーブルに保存
```

**新規テーブル**:

```sql
CREATE TABLE market_resolutions (
  condition_id    bytea PRIMARY KEY,
  outcome         smallint NOT NULL,   -- 0=No, 1=Yes
  payout_per_share numeric(18,6) NOT NULL,  -- 通常 0 or 1
  resolved_at     timestamptz NOT NULL,
  fetched_at      timestamptz NOT NULL DEFAULT now()
);
```

**`analysis/pnl.py` 拡張**:
- `compute_wallet_pnl()` に `include_resolved: bool = False` パラメータ追加
- True なら open positions を resolution で清算して realized に合算

### 3.3 設定値

| key | デフォルト | 説明 |
|---|---|---|
| `gamma_api_base` | `https://gamma-api.polymarket.com` | API endpoint |
| `gamma_fetch_interval_minutes` | `60` | 解決済 market を引いてくる頻度 |
| `gamma_max_lookback_days` | `90` | 何日前までの解決済 market を取り込むか |

---

## 4. Layer 2 — 執行レイヤ

### 4.1 目的
シグナルを受け取って Polymarket CLOB に実発注し、約定を追跡する。

### 4.2 アーキテクチャ

```
[indexer WS]
  → 検知: watchlist wallet の OrderFilled
  → INSERT INTO signals (status=PENDING)
       ↓
[worker poll]
  → SELECT signals WHERE status=PENDING AND age > delay
  → Layer 3 リスク check (全 7 件 + 4 上限)
  → OK なら CLOB POST order
  → INSERT INTO executions (status=PLACED)
       ↓
[CLOB callback / poll]
  → 約定検知 → UPDATE executions (status=FILLED, fill_price, fill_size)
  → INSERT INTO positions (or UPDATE if exists)
  → INSERT INTO trade_pnl (per-fill realized PnL)
```

### 4.3 新規テーブル

```sql
-- 受信シグナル
CREATE TABLE signals (
  id                bigserial PRIMARY KEY,
  source_wallet     bytea NOT NULL,           -- copy 元
  token_id          numeric(78,0) NOT NULL,
  side              smallint NOT NULL,        -- 0=BUY 1=SELL
  source_price      numeric(8,6) NOT NULL,    -- copy 元の約定価格
  source_size_usdc  numeric(18,6) NOT NULL,
  detected_at       timestamptz NOT NULL,     -- WS で検知した時刻
  execute_after     timestamptz NOT NULL,     -- detected_at + delay
  status            text NOT NULL,            -- PENDING/EXECUTING/EXECUTED/SKIPPED/REJECTED
  skip_reason       text,                     -- リスク 上限 / wallet 非 active 等
  execution_id      bigint REFERENCES executions(id)
);
CREATE INDEX idx_signals_pending ON signals(status, execute_after)
  WHERE status = 'PENDING';

-- CLOB 発注ログ
CREATE TABLE executions (
  id              bigserial PRIMARY KEY,
  signal_id       bigint NOT NULL REFERENCES signals(id),
  clob_order_id   text,                       -- Polymarket CLOB の order id
  token_id        numeric(78,0) NOT NULL,
  side            smallint NOT NULL,
  size_usdc       numeric(18,6) NOT NULL,
  limit_price     numeric(8,6) NOT NULL,
  placed_at       timestamptz NOT NULL,
  status          text NOT NULL,              -- PLACED/PARTIAL/FILLED/CANCELLED/REJECTED
  filled_size     numeric(18,6) DEFAULT 0,
  filled_price    numeric(8,6),
  fill_time       timestamptz,
  signal_to_place_ms int,                     -- latency 計測
  place_to_fill_ms   int,
  error_text      text,
  idempotency_key text UNIQUE NOT NULL
);

-- 現在ポジション
CREATE TABLE positions (
  token_id          numeric(78,0) PRIMARY KEY,
  market_label      text,                     -- 表示用、Gamma から
  side              smallint NOT NULL,        -- 0=long 1=short
  open_size_shares  numeric(18,6) NOT NULL,
  open_size_usdc    numeric(18,6) NOT NULL,
  avg_price         numeric(8,6) NOT NULL,
  opened_at         timestamptz NOT NULL,
  updated_at        timestamptz NOT NULL
);

-- per-fill realized PnL
CREATE TABLE trade_pnl (
  id            bigserial PRIMARY KEY,
  execution_id  bigint NOT NULL REFERENCES executions(id),
  token_id      numeric(78,0) NOT NULL,
  realized_usdc numeric(18,6) NOT NULL,
  fees_usdc     numeric(18,6) NOT NULL DEFAULT 0,
  ts            timestamptz NOT NULL DEFAULT now()
);
```

### 4.4 新規モジュール

```
src/copytrader/execution/
  __init__.py
  clob_client.py     # py-clob-client wrapper, sign + post
  order_state.py     # ステートマシン (PLACED→PARTIAL→FILLED 等)
  signal_consumer.py # watchlist OrderFilled → signals テーブル
  executor.py        # worker メインループ: signals → CLOB
  position_tracker.py # executions → positions 更新
  fee_calc.py        # Polymarket 手数料推定
```

### 4.5 環境変数 (Fly secrets)

```
CLOB_API_KEY=...                # Polymarket CLOB API key
CLOB_API_SECRET=...
CLOB_API_PASSPHRASE=...
TRADER_PRIVATE_KEY=...          # Polygon wallet 秘密鍵 (絶対に公開しない)
TRADER_ADDRESS=0x...            # 公開アドレス
```

### 4.6 設定値 (settings テーブル)

| key | デフォルト | 説明 |
|---|---|---|
| `execution_enabled` | `false` | 全執行のマスタースイッチ。false なら paper trading |
| `copy_size_usdc` | `10` | 1 trade あたりのサイズ |
| `copy_size_mode` | `"fixed"` | `fixed` または `proportional` (copy 元の比率に合わせる) |
| `copy_delay_seconds` | `30` | signal 検知から発注までの遅延 |
| `order_type` | `"limit_best"` | `limit_best` / `limit_mid` / `market` |
| `order_tif` | `"GTC"` | `GTC` / `IOC` / `FOK` |
| `limit_slippage_bps` | `100` | best bid/ask から許容する slippage (basis points) |
| `partial_fill_min_pct` | `0.5` | 部分約定の最低割合。下回ったらキャンセル |
| `order_timeout_seconds` | `60` | 発注後この時間で約定しなければキャンセル |

---

## 5. Layer 3 — リスク管理

### 5.1 目的
発注前 / 発注中 / 発注後の各タイミングで、定義済みの 7 停止条件 + 4 上限を評価し、1 つでも違反したら新規発注停止 (fail-closed)。

### 5.2 評価関数

`src/copytrader/risk/evaluator.py`:

```python
@dataclass(frozen=True)
class RiskCheck:
    allow_new_orders: bool
    halted_conditions: list[str]   # 違反した条件名
    warnings: list[str]            # 警告レベル
    timestamp: datetime


def evaluate_risk(*, db_session) -> RiskCheck: ...
```

毎 worker tick の冒頭で呼び、`allow_new_orders=False` なら全 signal を skip する。

### 5.3 停止条件 (7 件、いずれか 1 件で halt)

| 条件 | 閾値キー | デフォルト | 評価式 |
|---|---|---|---|
| 日次 PnL | `halt_daily_pnl_pct` | `-5.0` | 当日 0:00 UTC からの実現 PnL / 開始残高 |
| 7d PnL | `halt_weekly_pnl_pct` | `-8.0` | 過去 7 日の実現 PnL / 7 日前の残高 |
| 連敗数 | `halt_consecutive_losses` | `5` | 直近 N 件連続で realized < 0 |
| 単一 market 比率 | `halt_single_market_pct` | `25.0` | 1 market のエクスポージャ / 総資金 |
| indexer lag | `halt_indexer_lag_seconds` | `120` | now - cursor.updated_at |
| USDC 残高 | `halt_usdc_min` | `500` | wallet の USDC.balanceOf |
| MATIC 残高 | `halt_matic_min` | `1.0` | wallet の MATIC balance |

### 5.4 上限 (4 件、超過で新規 skip だが既存は維持)

| 上限 | キー | デフォルト | 評価式 |
|---|---|---|---|
| 総 exposure | `limit_total_exposure_pct` | `70.0` | open positions の総額 / 総資金 |
| 単一 token | `limit_single_token_pct` | `25.0` | 1 token への投下額 / 総資金 |
| 日次 trade 数 | `limit_daily_trades` | `100` | 当日の execution 件数 |
| 連敗で size 半減 | `risk_loss_size_halve_at` | `3` | この連敗で次回 size を 50% に |

### 5.5 Kill Switch

`settings.kill_switch_on = true` の時、`evaluate_risk()` は無条件で `allow_new_orders=False` を返す。  
worker は毎 tick この flag を見る。  
UI (Execute ページ) からトグルで切替、Telegram bot からも `/halt` コマンドで ON 可能。

### 5.6 新規テーブル

```sql
-- リスク評価ログ (audit)
CREATE TABLE risk_evaluations (
  id              bigserial PRIMARY KEY,
  ts              timestamptz NOT NULL DEFAULT now(),
  allow_new       boolean NOT NULL,
  halted_reasons  jsonb,                      -- list of condition names
  warnings        jsonb,
  metrics_snapshot jsonb                      -- 各指標の現在値
);
CREATE INDEX idx_risk_eval_ts ON risk_evaluations(ts DESC);
```

毎 tick 評価結果を 1 行 INSERT。最大 30 日保持で auto-purge。

---

## 6. Layer 4 — メタ自律 (戦略の自己更新)

### 6.1 目的
人間が触らなくても、edge を保ち続けるよう自動で:
- 毎晩 Phase 0 を回して上位 wallet をピックアップ
- 劣化した wallet を自動 deactivate
- A/B 戦略並行運用で勝者を採用

### 6.2 自動 Phase 0 cron

**実装**: worker に scheduler 機能追加。`apscheduler` 不要、DB の `scheduled_jobs` テーブルで管理。

```sql
CREATE TABLE scheduled_jobs (
  name           text PRIMARY KEY,
  cron_expr      text NOT NULL,         -- "0 18 * * *" 形式
  job_kind       text NOT NULL,
  job_params     jsonb NOT NULL,
  last_run_at    timestamptz,
  next_run_at    timestamptz NOT NULL,
  enabled        boolean NOT NULL DEFAULT true
);
```

初期データ:
```sql
INSERT INTO scheduled_jobs VALUES
  ('nightly_phase0', '0 18 * * *',
   'phase0', '{"window": 30, "watchlist_top": 10, "delays": [30,60,120], "copy_usd_per_trade": 50}',
   NULL, now() + interval '1 hour', true);
```

worker は 1 分ごとに `WHERE next_run_at <= now() AND enabled` を確認し、該当行を job_queue に enqueue する。

### 6.3 自動 watchlist promotion/demotion

**新規 job**: `kind = 'watchlist_rotate'`

実装 (`src/copytrader/jobs/handlers.py` に追加):

```python
def run_watchlist_rotate(params: dict) -> dict:
    # 1. 直近の phase0 result から rank_wallets() を呼ぶ
    # 2. top_n に入った wallet を Watchlist に upsert (active=true)
    # 3. 既存 active wallet のうち、過去 7d rolling PnL が deactivate_threshold 未満なら active=false
    # 4. audit log に記録
```

設定値:

| key | デフォルト | 説明 |
|---|---|---|
| `auto_rotate_enabled` | `true` | 自動 watchlist 更新 |
| `auto_rotate_top_n` | `15` | 採用 wallet 数 (執行 size と相談) |
| `auto_rotate_demote_pnl_7d` | `-200.0` | 7d PnL がこれ以下で deactivate (USDC) |
| `auto_rotate_min_trades_7d` | `5` | 直近 trade がこれ未満で deactivate (zombie 検出) |
| `auto_rotate_max_age_days` | `60` | promotion から N 日経過後は強制再評価 |

### 6.4 戦略 A/B 並行運用 (Phase D 以降のオプション)

**新規テーブル**:

```sql
CREATE TABLE strategy_variants (
  name           text PRIMARY KEY,
  config         jsonb NOT NULL,         -- delay, size, etc
  weight         numeric(3,2) NOT NULL,  -- 0.0〜1.0、何割の signal をこっちで実行するか
  enabled        boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now()
);
```

signal が来たら weight で variant を抽選 (deterministic by signal.id hash) し、その variant の config で発注。

月次 cron で variant 別 PnL を比較、勝者の weight を上げる / 敗者を deactivate。

---

## 7. Layer 5 — 監督・通知

### 7.1 Telegram bot

**目的**: 重要イベントを運用者の手元へ push。最低限の判断 (kill switch ON / OFF) を Telegram からも実行可能に。

**実装**: 新規モジュール `src/copytrader/telegram/`

```
telegram/
  __init__.py
  bot.py          # python-telegram-bot wrapper
  notifier.py     # 通知送信関数群
  commands.py     # /halt /resume /status /balance /positions などの handler
```

依存追加: `python-telegram-bot>=20`

**通知トリガー** (notifier.py 内の専用関数):

| イベント | severity | 内容 |
|---|---|---|
| kill switch ON/OFF | alert | 発動理由 / 解除者 |
| 停止条件ヒット | alert | どの条件が、現在値 vs 閾値 |
| 大型 fill (>$100) | info | market, side, size, PnL予測 |
| 日次 PnL サマリー (毎朝 9:00 JST) | info | 前日 PnL, 累計, 現状 phase |
| Indexer 長期停止 (10 分) | alert | 最終 cursor 時刻 |
| dead-letter 100 件突破 | warn | 件数, 最古エラー |
| backtest 乖離 30% 超 | warn | 期待 vs 実績の差 |
| watchlist rotation 完了 | info | 追加 N 件 / 削除 M 件 |

**チャットコマンド**:

| コマンド | 動作 |
|---|---|
| `/status` | 残高, ポジション数, 今日 PnL, kill switch 状態 |
| `/halt` | kill switch ON。確認 prompt 後実行 |
| `/resume` | kill switch OFF。確認 prompt 後実行 |
| `/balance` | USDC + MATIC 残高 |
| `/positions` | オープンポジション一覧 (上位 5) |
| `/pnl 7d` | 過去 7 日の日次 PnL |

### 7.2 環境変数

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...      # 通知先 chat (個人 or グループ)
TELEGRAM_ADMIN_USER_IDS=123,456   # /halt 等の特権コマンド許可 user
```

### 7.3 audit log

全ての重大変更を 1 つのテーブルに記録。

```sql
CREATE TABLE audit_log (
  id          bigserial PRIMARY KEY,
  ts          timestamptz NOT NULL DEFAULT now(),
  actor       text NOT NULL,                  -- "system" / "telegram:<user_id>" / "web"
  action      text NOT NULL,                  -- "kill_switch_on" / "phase_promote" / "wallet_add" 等
  details     jsonb NOT NULL
);
CREATE INDEX idx_audit_ts ON audit_log(ts DESC);
```

UI (Ops ページ) からブラウザで閲覧可。

---

## 8. UI: モック → 実データ差し替え

現在の 4 ページのモック部分を、本書 §3〜§7 で作るテーブルに繋ぐ。

| 画面要素 | データソース |
|---|---|
| Home tile: Wallet equity | `analysis.pnl.compute_wallet_pnl(window=30, include_resolved=True)` |
| Home tile: Drawdown | `trade_pnl` の累積から算出 |
| Home tile: Replay heatmap | 直近 phase0 job の result |
| Home tile: Top 10 戦略 | `analysis.replay` の grid 結果 (job_results) |
| Home tile: 市場×戦略 matrix | 同上 |
| Home tile: シグナル時間帯 | `signals.detected_at` の集計 |
| Home tile: DD gauge | 今日の `trade_pnl` 累積 / 残高 |
| Home tile: Latency | `executions.signal_to_place_ms` |
| Home tile: Position exposure | `positions` テーブル |
| Home tile: Watchlist Top 5 | `analysis.rank.rank_wallets(top_n=5)` |
| Home tile: 受信シグナル | `signals` 直近 5 件 |
| Home tile: Indexer lag | `cursors.updated_at` |
| Execute: ステータスバー | `usdc/matic balance` API + `positions` |
| Execute: リスクゲージ | `risk_evaluations` 最新行 + `metrics_snapshot` |
| Execute: ポジション tab | `positions` JOIN `market_resolutions` |
| Execute: シグナル tab | `signals` 直近 8 件 |
| Execute: fills tab | `executions WHERE status=FILLED` 直近 8 |
| Execute: Watchlist tab | 既に実装済 (real) |
| Execute: Jobs tab | 既に実装済 (real) |
| Execute: 手動 order | `execution.clob_client` を直接叩く |
| Execute: Rollout stepper | `settings.rollout_phase` + `rollout_started_at` |
| Execute: 昇格条件 | `analysis.rollout.evaluate_promotion_criteria()` |
| Execute: 停止条件 | `risk.evaluator.evaluate_risk()` の最新 |
| Ops: 全部 | 既に実装済 (real) |

差し替えは **1 タイル単位 1 PR**。本書 §13 のチェックリストで管理。

---

## 9. Ops インフラ

### 9.1 DB バックアップ

- Fly Postgres は **デフォルトで daily snapshot**。それで OK。
- 月次で `pg_dump` を別リージョン (Tigris S3) に転送する cron を追加 (Phase C 以降)。

### 9.2 secrets 管理

全ての秘密情報は Fly secrets で管理。コード / CI / Docker image には絶対に焼かない。

```
flyctl secrets set \
  DATABASE_URL=... \
  POLYGON_RPC_HTTP=... \
  POLYGON_RPC_WS=... \
  CLOB_API_KEY=... \
  CLOB_API_SECRET=... \
  CLOB_API_PASSPHRASE=... \
  TRADER_PRIVATE_KEY=... \
  TRADER_ADDRESS=0x... \
  TELEGRAM_BOT_TOKEN=... \
  TELEGRAM_CHAT_ID=... \
  TELEGRAM_ADMIN_USER_IDS=...
```

### 9.3 監視

- `/healthz` (既存): liveness
- `/readyz` (既存): DB + migration + indexer の health
- Fly のネイティブ monitoring を Better Stack / Grafana Cloud に流す (オプション)

### 9.4 ログ保持

- Fly logs: 直近 7 日のみ。重要なものは `audit_log` / `risk_evaluations` テーブルに残す。

---

## 10. settings テーブル: 全キー初期値リスト

新規セットアップ時、以下を一括 INSERT。`docs/manual/INITIAL_SEED.sql` に同じ内容を置く。

```sql
-- Execution
INSERT INTO settings (key, value) VALUES
  ('execution_enabled', 'false'),
  ('copy_size_usdc', '10'),
  ('copy_size_mode', '"fixed"'),
  ('copy_delay_seconds', '30'),
  ('order_type', '"limit_best"'),
  ('order_tif', '"GTC"'),
  ('limit_slippage_bps', '100'),
  ('partial_fill_min_pct', '0.5'),
  ('order_timeout_seconds', '60'),
-- Risk
  ('kill_switch_on', 'false'),
  ('halt_daily_pnl_pct', '-5.0'),
  ('halt_weekly_pnl_pct', '-8.0'),
  ('halt_consecutive_losses', '5'),
  ('halt_single_market_pct', '25.0'),
  ('halt_indexer_lag_seconds', '120'),
  ('halt_usdc_min', '500'),
  ('halt_matic_min', '1.0'),
  ('limit_total_exposure_pct', '70.0'),
  ('limit_single_token_pct', '25.0'),
  ('limit_daily_trades', '100'),
  ('risk_loss_size_halve_at', '3'),
-- Meta-autonomy
  ('auto_rotate_enabled', 'true'),
  ('auto_rotate_top_n', '15'),
  ('auto_rotate_demote_pnl_7d', '-200.0'),
  ('auto_rotate_min_trades_7d', '5'),
  ('auto_rotate_max_age_days', '60'),
-- Gamma
  ('gamma_api_base', '"https://gamma-api.polymarket.com"'),
  ('gamma_fetch_interval_minutes', '60'),
  ('gamma_max_lookback_days', '90'),
-- Rollout
  ('rollout_phase', '"A"'),
  ('rollout_started_at', 'now()'),
-- Strategy (existing)
  ('rank_min_trades', '30'),
  ('rank_min_volume_usdc', '5000'),
  ('replay_default_delays', '[30, 60, 120]')
ON CONFLICT (key) DO NOTHING;
```

---

## 11. 実装順序 (PR 単位)

| # | PR タイトル | 内容 | 推定工数 |
|---|---|---|---|
| 1 | feat(gamma): client + resolutions table | §3 全部 | 2d |
| 2 | feat(analysis): resolve-aware pnl | `compute_wallet_pnl(include_resolved=True)` | 1d |
| 3 | feat(execution): tables + scaffolding | §4.3 テーブル, モジュール骨格 | 1d |
| 4 | feat(execution): clob client wrapper | py-clob-client 統合, 単体テスト | 3d |
| 5 | feat(execution): signal consumer | indexer → signals | 2d |
| 6 | feat(execution): executor worker | signals → CLOB → executions | 3d |
| 7 | feat(execution): position tracker | executions → positions | 2d |
| 8 | feat(risk): evaluator + tables | §5 全部 | 3d |
| 9 | feat(meta): scheduled_jobs + cron | §6.2 | 1d |
| 10 | feat(meta): watchlist_rotate job | §6.3 | 2d |
| 11 | feat(telegram): bot + notifier | §7.1 | 3d |
| 12 | feat(telegram): commands | /halt /status etc | 1d |
| 13 | feat(audit): audit_log + UI 統合 | §7.3 | 1d |
| 14 | refactor(web): mock → real (Home) | §8 の Home tiles 全部 | 2d |
| 15 | refactor(web): mock → real (Execute) | §8 の Execute タブ全部 | 3d |
| 16 | refactor(web): mock → real (Strategy) | §8 の Strategy 全部 | 2d |
| 17 | chore(ops): backup cron + monitoring | §9 | 1d |

**合計推定: 約 33 営業日 (= 約 1.5 ヶ月)**

---

## 12. テスト計画

### 12.1 単体テスト (`tests/unit/`)
- 各モジュールの handler 関数を mock で
- リスク評価関数は edge case (全条件 ON、複数違反)
- CLOB client は responses で stub

### 12.2 統合テスト (`tests/integration/`)
- Postgres 起動して migration → 各 job kind を投入 → 結果検証
- 既存の phase0 e2e に倣う

### 12.3 paper trading 期間 (Phase A、4 週)
- `execution_enabled=false` で全 signal が SKIPPED (skip_reason="paper") として記録
- backtest 結果 と paper 結果 を比較、乖離 < 20% を確認

### 12.4 受け入れ条件 (本書全体の DoD)

- [ ] 全 17 PR が main に merge され、deploy 成功
- [ ] Ops ページの cursor が更新され続けている (indexer 稼働)
- [ ] Telegram に毎朝 9:00 JST のサマリーが届く
- [ ] kill switch を Web / Telegram 双方から ON/OFF できる
- [ ] settings の全 30 キーが初期値で入っている
- [ ] `execution_enabled=false` で paper trading が 24h 連続動作 (signals 数 > 10)

---

## 13. ロールアウト手順 (Phase A → D)

ユーザーマニュアル `docs/manual/USER_MANUAL.md` §3 を参照。本書では条件のみ規定:

### Phase A → B 昇格条件 (全て満たす)
- Paper trading 28 日以上稼働
- backtest vs paper の累計 PnL 乖離 ≤ 20%
- latency p95 ≤ 3000ms
- kill switch test (擬似障害) 合格
- 全 17 PR の DoD クリア

### Phase B → C 昇格条件
- B で 28 日以上稼働
- 累計 ROI ≥ +3%
- 最大 DD ≤ 8%
- 勝率 ≥ 52%

### Phase C → D 昇格条件
- C で 56 日以上稼働
- 累計 ROI ≥ +8%
- 月次 Sharpe ≥ 0.8
- 最大 DD ≤ 10%

### 撤退条件 (Phase B 以降、いずれか 1 件で撤退検討)
- 1 ヶ月以上連続赤字
- 最大 DD > 20%
- backtest vs 実績 乖離 > 40%

---

## 14. このドキュメントの更新

- 設定値変更時: §10 の SQL と本文を **同時更新**
- 新規 PR で機能追加時: §11 の表に追記、§8 の UI マッピング更新
- 撤退判定時: §13 の条件を実数値で更新
