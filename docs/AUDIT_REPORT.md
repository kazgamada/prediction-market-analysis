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

### 依存脆弱性スキャン（npm audit 相当）
```
$ pip-audit
Found 5 known vulnerabilities in 1 package
  pip 24.0  (PYSEC-2026-196 / CVE-2025-8869 / CVE-2026-1703 / CVE-2026-3219 / CVE-2026-6357)
```
- 検出された 5 件は **すべて venv 同梱の `pip`（ビルドツール）自体** の脆弱性で、本プロジェクトの
  ランタイム依存（web3, sqlalchemy, streamlit, psycopg 等）には既知脆弱性なし。
- 影響: 本番 Docker イメージの pip を新しめに固定すれば解消（Dockerfile は `pip install --upgrade pip` 済み）。実害低・P3。

---

## 3. E2E シミュレーション結果

ローカル Postgres を起動し、`web` プロセス（`copytrader.runtime.web_main`）を実起動して
実証検証した（本番 DB は不使用）。

| シナリオ | 検証内容 | 結果 | 証拠 |
|---|---|---|---|
| Streamlit 起動 | UI が応答するか | ✅ | `GET :8501/_stcore/health` → HTTP 200 |
| ヘルスサーバ常駐 | UI 起動後も `:8080` が応答するか | ✅（**修正後**） | `GET :8080/readyz` → 200 `{"status":"ok","db":"ok","migration":{"status":"ok"}}` |
| グレースフル停止 | SIGTERM が streamlit へ伝播するか | ✅（**修正後**） | parent に SIGTERM → streamlit `Stopping...` ログ |
| import スモーク | 全モジュール import | ✅ 53 OK | `web.app` のみ import 時 DB 接続（Streamlit 実行モデル上は許容） |

**重大発見（F-2）**: 修正前は UI 起動後に `:8080`（fly.toml の web プロセス向けサービス）が
無応答だった。原因は `web_main` が `os.execvp` でプロセスを置換し、`daemon` の health スレッドを
道連れに殺していたこと（§4 F-2）。子プロセス起動方式へ変更し、両ポート同時応答を確認。

---

## 4. 課題一覧表

| ID | 観点 | 優先度 | 課題 | 証拠 | 修正方針 | 状態 |
|---|---|---|---|---|---|---|
| A-1 | A 認証 | P0 | Web UI 認証が no-op。公開 URL から無認証で kill switch/手動 order 等を操作可能 | `web/auth.py:9-10` | 再有効化 or 閉域配置（要ユーザー判断） | 未対応（報告） |
| E-1 | E DB | P1 | 自己修復マイグレーションの DROP 列挙が stale。phase1 テーブル漏れで本番起動時に `already exists` クラッシュ | `db/engine.py:153-156`（旧） | `Base.metadata` から DROP 導出 | **修正済** |
| F-2 | F デプロイ | P1 | `web_main` が `os.execvp` でプロセス置換し health スレッドを kill。UI 起動後 `:8080` /readyz /healthz が永久に無応答（fly.toml の web サービス・README の死活確認が機能しない） | `runtime/web_main.py:138-142`（旧） | 子プロセス起動 + シグナル転送に変更。E2E で両ポート応答を確認 | **修正済** |
| F-1 | F 品質 | P1 | ruff 64 件（未使用 import 等）で lint ゲート赤 | `ruff check` 出力 | `--fix` + noqa 整理 | **修正済** |
| F-3 | F 依存 | P3 | venv 同梱 pip に既知脆弱性 5 件（ランタイム依存は健全） | `pip-audit` | Docker で pip 更新 | 報告のみ |
| E-2 | E テスト | P2 | 統合テストが絶対時刻 seed で window 外れ常時失敗（time-bomb） | `tests/integration/test_rank_streaming.py:29`（旧） | `now()` 基準 seed | **修正済** |
| E-3 | E テスト | P2 | `ver == "0001"` の stale 断定（head は 0002） | `tests/integration/test_migration_self_heal.py:56`（旧） | head 動的取得 | **修正済** |
| E-4 | E テスト | P2 | `fresh_db` が TRUNCATE のみでスキーマ破壊テスト後に ERROR 連鎖 | `tests/integration/conftest.py:47-59`（旧） | 各テスト前に migrate + metadata 由来 TRUNCATE | **修正済** |
| B-1 | F デプロイ | P1 | Docker/Fly ビルド未実証（daemon 不在） | — | CI で確認 | 要確認 |
| B-2 | B 設定 | P1 | 本番 secrets 充足確認 | `config.py` / `.env.example` | Fly secrets 設定 | 要確認 |
| D-1 | E 機能 | P3 | 残高フック未実装 TODO | `risk/evaluator.py:178` | PR #4 連携 | 未対応 |

---

## 5. 優先度別ロードマップ

- **P0**: A-1（認証）— 要ユーザー判断。これ無しに公開リリースは不可。
- **P1**: E-1（修正済）/ F-2（修正済）/ F-1（修正済）/ B-1・B-2（要確認）。
- **P2**: E-2/E-3/E-4（修正済）+ CI で DB 付きテスト常時化。
- **P3**: D-1 / F-3。

---

## 4.5 Step 3 6観点チェックリスト網羅結果

`AUDIT.md` Step 3 の A〜F を本スタックに読み替えて全項目を確認した結果。

### A. セキュリティ
- 秘密情報ハードコード: **無し**（§2）。秘密鍵・CLOB キーは `os.environ` から読込（`execution/clob_client.py:35,59`）。
- `service_role`/クライアント露出: N/A（Supabase 不使用）。
- DB 認可: 単一 `DATABASE_URL` 接続。RLS 概念は無く、アクセス制御は Web 認証層に依存 → **A-1（P0）に集約**。
- Webhook 署名検証: Stripe/Make.com webhook 無し。Telegram は **long-polling + user_id allowlist**（`telegram/commands.py:25,159-160` `⚠️ Unauthorized`）で認可済 → 署名検証は N/A。
- 入力検証: Telegram コマンド引数は型変換 + `except (TypeError, ValueError)` でフォールバック（`commands.py:131`）。SQL は SQLAlchemy ORM/バインドパラメータで injection リスク低。
- `.gitignore`: `.env*` 含む（確認済）。`git log -S "sk_live"` の検出はテスト用文字列のみ。

### B. 認証 / 外部設定
- 認証フロー: **`require_password()` が no-op**（A-1）。サインアップ等の概念は無い単一パスワード設計。
- 保護ルート: 各ページ冒頭で `require_password()` を呼ぶ構造はあるが中身が no-op。
- 環境変数: コードの `os.environ`/`settings.*` と `.env.example` を突合し完全リスト化（要件定義書 §8）。実行系キー（CLOB/TRADER_PRIVATE_KEY）は `.env.example` 未記載 → 追記推奨。

### C. UI 最適化
- Next.js 用 UI 規約は N/A（§6）。ダークテーマ一元管理（`web/theme.py`）+ ページ分割済。
- ローディング/空状態: 各ページは DB 空時にモックへフォールスルー（`web/app.py`, `2_Execute.py` の `_real_*` アクセサ）。空状態の明示表示は一部のみ → P3。

### D. UX
- 破壊的操作の確認: 手動 order は確認チェックボックスで送信ボタンを gate（`2_Execute.py:529-531`）、HALT も同様（`585-588`）。**保護あり・良好**。
- kill switch: トグル即時反映（確認なし）。停止は即時性優先で妥当だが、再開（OFF）に確認が無い点は軽微 → P3。
- エラーメッセージ: DB 障害時は `db_ok=False`+理由を画面に出す設計。致命的な無意味メッセージは未検出。

### E. 動作しない機能 / DB 不具合
- 未実装: TODO 1 件のみ（`risk/evaluator.py:178`、D-1）。空 onClick 等は未検出。
- DB 整合性: ORM クエリはモデルクラス参照のため存在しないテーブル/カラム参照は型/import で顕在化。統合テスト 66 件 green で主要経路を実証。
- マイグレーション: **E-1（自己修復クラッシュ）を検出・修正**。冪等性は `IF NOT EXISTS`/`ON CONFLICT` で担保。
- 非同期/例外: 空 `catch` は型指定付きパース fallback のみ（実害なし）。`await` 漏れは未検出。

### F. デプロイ / 監視 / パフォーマンス
- **F-2（health サーバが execvp で死ぬ）を検出・修正**（最重要）。
- Dockerfile: `python:3.12-slim` ベースで健全。`ENV PATH=/app/.venv/bin`（存在しない venv 参照）は無害だが要整理 → P3。
- 監視: `/healthz` `/readyz`（DB ping + RPC self-test キャッシュ）+ 起動時 secrets ダンプ（redacted）と観測性は良好（F-2 修正で本番でも有効化）。
- パフォーマンス: PnL は `stream_wallet_pnl`（yield_per）でメモリ抑制済。顕著な N+1 は未検出。

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
