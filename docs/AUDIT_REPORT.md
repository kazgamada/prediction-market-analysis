# polymarket-copytrader 監査レポート

> `AUDIT.md` のフェーズ1（リポジトリ個別監査）に基づく監査記録。
> 完成化要件は `docs/requirements.md` を参照。
> スタックが Python/Streamlit のため、Next.js/Supabase/Stripe 前提の項目は読み替えた（要件定義書 §0）。

実施日: 2026-06-17 / 実施環境: Python 3.12.3 / Postgres 16 / ruff 0.15.17

---

## 1. 全体把握

- 3 プロセス（`web` / `indexer` / `worker`、`fly.toml [processes]`）。
- ルーティング: Streamlit マルチページ `src/copytrader/web/pages/{1_Strategy,2_Execute,3_Ops,4_Help}.py` + Home（`web/app.py`）。
- health: `src/copytrader/health/server.py`（内部 8080、`/readyz`）。
- スキーマ: `alembic/versions/0001_initial.py`（cursors, blocks_seen, trades, wallet_stats_daily,
  watchlist, signals, risk_events, jobs, job_logs, rpc_dead_letters, settings）+
  `0002_phase1_tables.py`（market_resolutions, executions, positions, trade_pnl,
  risk_evaluations, scheduled_jobs, strategy_variants, audit_log）。ORM は `src/copytrader/db/models.py`。

---

## 2. 検証ログ（実行結果）

### Lint（監査時 → 修正後）
```
$ ruff check src tests
Found 64 errors.   # 内訳: F401×45, F811×6, I001×6, E402×4, B007×2, UP037×1
...
$ ruff check src tests      # 修正後
All checks passed!          # exit 0
```

### テスト
```
$ pytest tests/unit -q
42 passed

# Postgres 16 + alembic upgrade head の上で全件:
$ pytest -q                 # 監査時
2 failed, 52 passed, 12 errors
  FAILED test_migration_self_heal.py::test_clear_stale_alembic_when_jobs_missing
  FAILED test_migration_self_heal.py::test_legacy_trade_data_is_carried_over
  ERROR  test_phase0_e2e.py / test_rank_streaming.py（fresh_db の連鎖 ERROR）

$ pytest -q                 # 修正後
66 passed
```

### 秘密情報スキャン
```
$ grep -rnE "sk_live|sk_test|service_role|PRIVATE_KEY" src tests
# ハードコード無し。clob_client.py は os.environ から読み込み（src/copytrader/execution/clob_client.py:35,59）。
# tests/unit/test_chain_errors.py の sk_live はログ redaction の検証用文字列。
```

---

## 3. E2E シミュレーション結果

Streamlit + 外部 RPC/CLOB 依存のためブラウザ E2E は本監査範囲外（手動確認項目化、要件定義書 §5）。
代替として全モジュールの import スモークを実施: 53 OK。`web.app` のみ import 時に
DB 接続を試みる設計（Postgres 未起動時は OperationalError）。

---

## 4. 課題一覧表

| ID | 観点 | 優先度 | 課題 | 証拠 | 修正方針 | 状態 |
|---|---|---|---|---|---|---|
| A-1 | A 認証 | P0 | Web UI 認証が no-op。公開 URL から無認証で kill switch/手動 order 等を操作可能 | `web/auth.py:9-10` | 再有効化 or 閉域配置（要ユーザー判断） | 未対応（報告） |
| E-1 | E DB | P1 | 自己修復マイグレーションの DROP 列挙が stale。phase1 テーブル漏れで本番起動時に `already exists` クラッシュ | `db/engine.py:153-156`（旧） | `Base.metadata` から DROP 導出 | **修正済** |
| F-1 | F 品質 | P1 | ruff 64 件（未使用 import 等）で lint ゲート赤 | `ruff check` 出力 | `--fix` + noqa 整理 | **修正済** |
| E-2 | E テスト | P2 | 統合テストが絶対時刻 seed で window 外れ常時失敗（time-bomb） | `tests/integration/test_rank_streaming.py:29`（旧） | `now()` 基準 seed | **修正済** |
| E-3 | E テスト | P2 | `ver == "0001"` の stale 断定（head は 0002） | `tests/integration/test_migration_self_heal.py:56`（旧） | head 動的取得 | **修正済** |
| E-4 | E テスト | P2 | `fresh_db` が TRUNCATE のみでスキーマ破壊テスト後に ERROR 連鎖 | `tests/integration/conftest.py:47-59`（旧） | 各テスト前に migrate + metadata 由来 TRUNCATE | **修正済** |
| B-1 | F デプロイ | P1 | Docker/Fly ビルド未実証（daemon 不在） | — | CI で確認 | 要確認 |
| B-2 | B 設定 | P1 | 本番 secrets 充足確認 | `config.py` / `.env.example` | Fly secrets 設定 | 要確認 |
| D-1 | E 機能 | P3 | 残高フック未実装 TODO | `risk/evaluator.py:178` | PR #4 連携 | 未対応 |

---

## 5. 優先度別ロードマップ

- **P0**: A-1（認証）— 要ユーザー判断。これ無しに公開リリースは不可。
- **P1**: E-1（修正済）/ F-1（修正済）/ B-1・B-2（要確認）。
- **P2**: E-2/E-3/E-4（修正済）+ CI で DB 付きテスト常時化。
- **P3**: D-1。

---

## 6. 共通 UI 規約 GAP

Streamlit 文脈につき Next.js 用 UI 規約は対象外（要件定義書 §6）。既存ダークテーマ
（`web/theme.py`）+ ページ分割で UX は成立。ポートフォリオ横断の共有 UI パッケージ化とは別軸。

## 7. Billing GAP

Stripe/課金フロー無し。SaaS 化する場合は別 Phase（要件定義書 §7）。

## 8〜11

外部設定・手動確認・環境変数・30分セットアップは `docs/requirements.md` §5/§8/§9 に集約。

---

## 査読メモ（自己レビュー）

- A-1 を P0 とした根拠: 資金移動操作を持つ管理 UI の無認証公開は、ビルド不能や RLS 無効と
  同等の「リリース前に必ず塞ぐべき」リスクであり P1 ではなく P0。ただし開発者が意図的に
  無効化しているため、修正方式は本監査で確定させず要判断とした（証拠主義・推測の明示）。
- E-1 は「テストだけの問題」ではなく、self-heal が走る本番経路で実際にクラッシュする実害バグ。
  修正をテスト（`test_clear_stale_alembic_when_jobs_missing` が phase1 テーブル存置下で
  self-heal を通すシナリオ）で green 化し回帰を固定した。
