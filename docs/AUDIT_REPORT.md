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
| E-5 | E 資金安全 | **P0** | **二重発注**: catchup と live stream が同一 OrderFilled を観測し、1 トレードから signals 2 行→注文 2 回。`maybe_record_signal` に DB レベル重複排除が無く、persist のコメントが約束する executor de-dup は実在しなかった | `indexer/persist.py:41-57` `execution/signal_consumer.py:52-67`（旧） | signals に (tx_hash, log_index) 部分 unique index（migration 0003）+ ON CONFLICT DO NOTHING。回帰テスト 3 本追加 | **修正済** |
| E-1 | E DB | P1 | 自己修復マイグレーションの DROP 列挙が stale。phase1 テーブル漏れで本番起動時に `already exists` クラッシュ | `db/engine.py:153-156`（旧） | `Base.metadata` から DROP 導出 | **修正済**（※残: 0002 部分適用シナリオは未救済。下記 査読反映） |
| F-2 | F デプロイ | P1 | `web_main` が `os.execvp` でプロセス置換し health スレッドを kill。UI 起動後 `:8080` /readyz /healthz が永久に無応答（fly.toml の web サービス・README の死活確認が機能しない） | `runtime/web_main.py:138-142`（旧） | 子プロセス起動 + シグナル転送に変更。E2E で両ポート応答を確認 | **修正済** |
| F-1 | F 品質 | P1 | ruff 64 件（未使用 import 等）で lint ゲート赤 | `ruff check` 出力 | `--fix` + noqa 整理 | **修正済** |
| F-3 | F 依存 | P3 | venv 同梱 pip に既知脆弱性 5 件（ランタイム依存は健全） | `pip-audit` | Docker で pip 更新 | 報告のみ |
| E-2 | E テスト | P2 | 統合テストが絶対時刻 seed で window 外れ常時失敗（time-bomb） | `tests/integration/test_rank_streaming.py:29`（旧） | `now()` 基準 seed | **修正済** |
| E-3 | E テスト | P2 | `ver == "0001"` の stale 断定（head は 0002） | `tests/integration/test_migration_self_heal.py:56`（旧） | head 動的取得 | **修正済** |
| E-4 | E テスト | P2 | `fresh_db` が TRUNCATE のみでスキーマ破壊テスト後に ERROR 連鎖 | `tests/integration/conftest.py:47-59`（旧） | 各テスト前に migrate + metadata 由来 TRUNCATE | **修正済** |
| B-1 | F デプロイ | P1 | Docker/Fly ビルド未実証（daemon 不在） | — | CI で確認 | 要確認 |
| B-2 | B 設定 | P1 | 本番 secrets 充足確認 | `config.py` / `.env.example` | Fly secrets 設定 | 要確認 |
| E-6 | E 資金安全 | P1 | executor のクラッシュ復旧ギャップ + halt セマンティクス判断。①claim 後〜CLOB 完了前にクラッシュすると signal が EXECUTING のまま滞留し再処理されない（`_claim_pending` は PENDING のみ拾う）。②halt 中は signal を SKIPPED で破棄する実装だが、Help ページは「溜まった signal」=保留を示唆し矛盾 | `execution/executor.py:54-81,92-98,200` | ①executions 行の有無を見て EXECUTING を安全に再 claim（idempotency_key unique のため二重発注は不可）②discard か pause か方針確定（要設計判断・資金経路のため未実装） | 報告（要判断） |
| E-7 | E 資金安全 | P1 | backfill が失敗/未到着チャンクを飛ばしてカーソルを単調前進（iter_logs は完了順=ブロック順でない並行 yield）。クラッシュ時/ dead-letter retry 失敗時にコピー元トレードを永久取りこぼし | `indexer/backfill.py`（旧 108-118） | カーソルを「from_block から連続して完了した区間の末尾」= 真の low-water mark に変更。失敗/未到着チャンクが frontier を堰き止め、次 catchup で再走査（冪等）。回帰テスト 4 本追加 | **修正済** |
| E-8 | E 整合性 | P2 | Position PK が token_id 単独で side 非考慮。建玉の実質反転時に realized PnL 符号が誤り、risk 判定を汚染 | `db/models.py:233` `execution/position_tracker.py:115-122` | Position キーに side を含める（Polymarket セマンティクス要確認） | 報告（要判断） |
| E-9 | F 運用 | P2 | jobs lease 失効が固定 30 分。30 分超の正常 backfill が「worker died」誤判定で FAILED 化。heartbeat 不在 | `jobs/queue.py:124-131` | heartbeat 更新 or lease をジョブ種別ごとに可変 | 報告 |
| E-10 | E 整合性 | P3 | FK に `ON DELETE` 未指定（executions.signal_id, trade_pnl.execution_id）→ 孤児データの可能性 | `alembic 0002:68,105` | カスケード方針を定義 | 報告 |
| D-1 | E 機能 | P3 | 残高フック未実装 TODO。なお既存フォールバック `usdc_balance>0 and <min` は残高0(=未取得)で halt しない=安全側に倒れていないが、現状 balance source が常時0のため `>0` ガードは「未実装の no-op」として正しい。フック実装時に方向を是正すること | `risk/evaluator.py:184` | PR #4 で実残高取得 + 0=未取得/枯渇の区別 | 未対応 |

---

## 5. 優先度別ロードマップ

- **P0**: A-1（認証, 要判断）/ **E-5 二重発注（修正済）**。
- **P1**: E-1（修正済）/ F-2（修正済）/ F-1（修正済）/ **E-7 backfill 取りこぼし（修正済）** / **E-6 executor 復旧/halt 方針（要判断）** / B-1・B-2（要確認）。
- **P2**: E-2/E-3/E-4（修正済）/ E-8 Position side / E-9 jobs lease / CI で DB 付きテスト常時化。
- **P3**: D-1 / E-10 FK / F-3。

> **E-6 のみ要判断として未実装**: 資金経路（執行）の復旧ロジックと halt セマンティクス
> （破棄 vs 保留）の確定を伴い、誤った修正は二重発注/取りこぼしを生むため、推測で実装しない
> 原則に従い証拠付きで報告に留めた。E-5/E-7/E-1/F-1/F-2 は contained かつ回帰テスト可能と
> 判断し修正・green 化した。

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

## 査読反映: 敵対的セカンドパス結果（AUDIT.md モデル運用方針 §2）

監査本体とは別パスで「査読者」視点の敵対的レビューを実施し、実コードを直接確認して
本レポートの判定を反証させた。主要な指摘と対応:

1. **execution レイヤの素通り（最重要指摘）**: 初版は lint/health/migration 等インフラ層に
   偏り、資金安全に直結する execution/risk/indexer をほぼ検証していなかった。→ E-5〜E-10 を
   追加。特に **E-5 二重発注（P0）** を検出・修正した。
2. **「修正済」判定の甘さ**:
   - E-1 は metadata 由来 DROP で大半は妥当だが、**0002 が部分適用された状態**（jobs はあるが
     executions 等が中途半端）ではトリガ条件（`engine.py:136`）が発動せず再クラッシュし得る。
     また self-heal 発動時に既存 `signals` を DROP するためデータ損失の可能性（注記済）。
     → 「修正済（残課題あり）」に格下げ。
   - F-2 は主目的（両ポート常駐）は達成だが、SIGKILL 時の子孤児化等のエッジは残存。
     シグナルハンドラ登録を Popen の**前**へ移し登録レースは解消、stale docstring も是正。
3. **優先度の誤り是正**: kill switch を「即時反映・良好」とした §4.5 D の評価を撤回し E-6（P1）化。
   E-4「冪等性担保」も backfill カーソルの取りこぼし（E-7, P1）を見落としていたため補足。
4. **査読への反証（pushback）**:
   - 残高ガード（`evaluator.py:184`）を査読は P1 としたが、`usdc_balance_cache` は balance hook
     未実装ゆえ常時 0 であり、`>0` ガードを今「修正」すると paper モードで risk が**常時 halt**
     してしまう。現状は「未実装機能の正しい no-op」であり P3（D-1 に統合）が妥当と判断した。
   - E-6 の査読主張「halt 中に claim された行が EXECUTING で滞留（孤児化）」は**誤り**。実装は
     halt 時に `_execute_signal` が即 `SIGNAL_SKIPPED` にする（`executor.py:95-98`）ため正常時に
     EXECUTING 滞留は起きない。真の残課題は (a) claim 後〜CLOB 完了前のクラッシュ復旧、
     (b) halt=破棄 vs 保留の方針（Help ページ記述と矛盾）であり、いずれも資金経路の設計判断を
     要するため未実装で報告とした。「tick 内のリスク変化無視」も 2 秒 tick では実害なしと評価。

5. **査読を起点に追加修正した項目**: E-7（backfill カーソル）は当初「要判断」としていたが、
   `iter_logs` が**完了順（ブロック順でない）並行 yield** である事実（`chain/client.py:207-210`）を
   確認し、per-chunk 単調前進ではクラッシュ時に下位チャンクを取りこぼす**明白なバグ**と判明。
   liveness 優先設計（dead-letter は維持）を壊さず、カーソルを連続 frontier 化する形で修正した。

### 自己レビュー（初版からの継続）
- A-1 を P0 とした根拠: 資金移動操作を持つ管理 UI の無認証公開はリリース前に必ず塞ぐべき。
  ただし開発者が意図的に無効化しているため修正方式は要判断とした。
- E-5 の回帰固定: `tests/integration/test_signal_dedup.py` で catchup+stream 重複観測が
  signals 1 件に収束することをテスト化した（査読が要件化を推奨した回帰テスト）。
