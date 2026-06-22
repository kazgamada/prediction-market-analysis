# polymarket-copytrader 完成化要件定義書

> 本書は `AUDIT.md` の監査基準に基づき、本リポジトリを「課金ユーザーに提供できる完成状態」へ
> 到達させるための要件をまとめたもの。証拠（ファイルパス + 行番号 + コマンド出力）を伴う。
> 詳細な監査ログは `docs/AUDIT_REPORT.md` を参照。

最終更新: 2026-06-17

---

## 0. スタック注記（AUDIT.md 前提との差異）

`AUDIT.md` は Next.js 14 / TypeScript / Supabase / Stripe を共通前提に書かれているが、
本リポジトリは **Python 3.12 / Streamlit / SQLAlchemy + Alembic / Postgres / Fly.io** で構成された
Polymarket コピートレードボットである。したがって以下のように監査観点を読み替えた。

| AUDIT.md の前提 | 本リポジトリでの対応 |
|---|---|
| `tsc --noEmit` | 該当なし（Python）。代替: import スモークテスト |
| `npm run build` | 該当なし。代替: Docker ビルド（本監査環境では daemon 不在のため未実行・要確認） |
| `npm run lint` | `ruff check src tests` |
| テスト | `pytest`（unit は DB 不要 / integration は Postgres 必須） |
| Supabase / RLS | 該当なし。認証は自前の Streamlit パスワードゲート（後述） |
| Stripe Billing | **未実装。本ツールに課金フローは存在しない**（§7 参照） |
| 共通 UI 規約（左黒/右白サイドバー等） | Streamlit ベースのため Next.js 用 UI 規約は直接適用不可（§6 参照） |

---

## 1. プロダクト概要と現状サマリー

- **目的**: Polymarket の高勝率ウォレットを発見し、その約定を遅延付きで模倣するコピートレードボット。
  Phase 0（オフライン edge 検証）中心の再構築版。
- **構成**: 3 プロセス分離（`web`=Streamlit / `indexer`=Polygon backfill+WS / `worker`=job queue）。
  状態は Postgres に一元化。
- **完成度の所感**: コア（indexer / job queue / PnL / rank / risk / execution scaffolding）は実装済みで
  テストも整備されている。**リリースブロッカーはコード品質ゲートと運用前提（認証・本番設定）に集中**。
- **リリース可否判定**: コード起因の P0〜P3 はすべて修正済み（認証・二重発注・マイグレーション・
  health・backfill・executor・lint 等）。残るは**環境/運用依存**（Docker/Fly 実ビルド・本番 secrets・
  CI 常時化）のみで、これらを満たせば限定リリース可。`WEB_PASSWORD` を必ず設定すること。

---

## 2. 検証ログ（本監査で実行）

`AUDIT.md` Step 2 を本スタックに読み替えて実行した。生ログは `docs/AUDIT_REPORT.md` §2 に転記。

| ゲート | コマンド | 監査時の初期結果 | 修正後 |
|---|---|---|---|
| 依存導入 | `pip install -e ".[dev]"` | OK | OK |
| Lint | `ruff check src tests` | **64 errors（exit 1）** | **All checks passed（exit 0）** |
| Unit テスト | `pytest tests/unit -q` | 42 passed | 42 passed |
| 統合テスト | `pytest -q`（Postgres 16） | **2 failed / 12 errors** | **85 passed**（回帰テスト多数追加） |
| import スモーク | 全モジュール import | 53 OK（`web.app` は DB 接続のため除外） | 同左 |
| 秘密情報 grep | `sk_live` 等 | ハードコード無し（テスト用文字列のみ） | — |
| 依存脆弱性 | `pip-audit` | 5 件すべて venv 同梱 pip のみ（ランタイム依存は健全） | — |
| E2E（web 実起動） | `:8501` + `:8080` 死活 | 8080 無応答（F-2 バグ） | **両ポート 200 / SIGTERM 伝播 OK** |

---

## 3. 本監査で修正した課題（P1）

実装済み。詳細は `docs/AUDIT_REPORT.md` §4。

0. **二重発注の防止（実害バグ / P0・敵対的査読で検出）**
   indexer の catchup ループと live WS stream が同一 OrderFilled ログを観測すると、1 つのコピー元
   トレードから signals が 2 行生成され、コピー注文が 2 回発生する（二重支出）。`maybe_record_signal`
   に DB レベルの重複排除が無く、`persist.py` のコメントが約束していた「executor の de-dup」は
   実在しなかった。→ `signals` に originating trade identity（`tx_hash`, `log_index`）を追加し
   （migration `0003`）、部分 unique index + `ON CONFLICT DO NOTHING` で**レースセーフに冪等化**。
   回帰テスト `tests/integration/test_signal_dedup.py`（3 本）を追加。

6. **backfill カーソルの取りこぼし防止（実害バグ / P1・敵対的査読を起点に検出）**
   `iter_logs` は並行実行のチャンクを**完了順（ブロック順でない）**に yield するが、旧実装は
   チャンクごとにカーソルを単調前進させていた。このためクラッシュ時に下位チャンクを取りこぼし、
   また失敗チャンクを飛ばして上位チャンクがカーソルを進めると当該範囲が二度と再走査されなかった。
   → カーソルを「`from_block` から連続して完了した区間の末尾」= 真の low-water mark に変更
   （`backfill.py`）。失敗/未到着チャンクが frontier を堰き止め、次 catchup で再走査される（冪等）。
   liveness 優先の dead-letter 設計は維持。回帰テスト `tests/integration/test_backfill_cursor.py`（4 本）。

1. **マイグレーション自己修復の本番クラッシュ（実害バグ / P1）**
   `src/copytrader/db/engine.py` の `_clear_stale_alembic_state` が DROP するテーブルを
   ハードコード列挙しており、`0002`（phase1）で追加された `market_resolutions` 等が漏れていた。
   結果、phase1 テーブルを持つ本番 DB が stale stamp を抱えた状態で起動すると、自己修復の
   再マイグレーションが `relation "market_resolutions" already exists` でクラッシュし **起動不能**。
   → DROP 対象を `Base.metadata.sorted_tables` から導出し、将来のマイグレーション追加にも
   自動追従する構造に変更。

1b. **ヘルスサーバが起動直後に死ぬ（実害バグ / P1）**
   `src/copytrader/runtime/web_main.py` が Streamlit へ `os.execvp` で**プロセス置換**しており、
   バックグラウンド（daemon）の health スレッドを道連れに kill していた。結果 UI 起動後は
   `:8080` の `/healthz` `/readyz`（`fly.toml` の web サービス・README の死活確認）が**永久に無応答**。
   設計意図（「migration がクラッシュしても /readyz が応答する」）が成立していなかった。
   → 子プロセス起動（`subprocess.Popen`）+ SIGTERM/SIGINT 転送に変更。親（health スレッド）を
   生かしたまま UI を動かす。E2E で両ポート同時応答とグレースフル停止を実証。

2. **Lint 64 件（P1 / 品質ゲート）**
   未使用 import・import 順序・未使用ループ変数等。`ruff --fix` + Streamlit ページの
   意図的な遅延 import への `# noqa: E402` 整理で解消。

7. **追加で全 P0〜P3 のコード課題を解消（敵対的査読由来 + 残課題）**
   - **A-1（P0 認証）**: `require_password()` を**セッション維持型パスワードゲート**に再実装
     （`WEB_PASSWORD` 設定時のみ要求 / 定数時間比較 / `session_state` 保持で再認証回避）。
     未設定時は開放（dev）。`.env.example` も実態に合わせ更新。
   - **E-6（P1 executor）**: `_recover_stale_executing` で executions 行の無い stale EXECUTING のみ
     PENDING に戻す（行があれば不介入＝二重発注不可）。halt を **pause** 化（claim せず PENDING 保持）。
   - **E-8（P2 Position）**: flat 後の再建玉を新規 open 扱いに（side/avg リセット）。査読の「PK に
     side 追加」案は close セマンティクスを壊すため不採用。
   - **E-9（P2 jobs lease）**: `heartbeat_at`（migration 0004）追加。log/progress 書込で beat 更新、
     失効判定を `COALESCE(heartbeat_at, started_at)` 基準にして長時間ジョブの誤殺を防止。
   - **E-10（P3 FK）**: migration 0005 で signal→execution→trade_pnl を `ON DELETE CASCADE` 化。
   - **D-1（P3 残高）**: `balance_client`（USDC/MATIC を RPC 取得）+ `balance_refresh` ジョブを実装。
     risk のガードを「None=未取得→halt せず / 実値=0 含め floor 判定」に修正（安全側へ）。
   - 各々に回帰テスト追加（executor 4 / position 2 / heartbeat 3 / auth・balance unit 3）。

3. **統合テストの time-bomb（P2 / テスト健全性）**
   `tests/integration/test_rank_streaming.py` が `ts=datetime(2026,5,12)` を絶対値で seed し、
   `window_days` の相対ウィンドウ（`now()-window`）から外れて常時失敗していた。
   → seed を `now()` 基準に変更。

4. **マイグレーションテストの stale 断定（P2）**
   `test_migration_self_heal.py` が `ver == "0001"` を断定していたが head は `0002`。
   → head を動的に取得して比較。

5. **統合テストの分離破壊（P2）**
   `tests/integration/conftest.py` の `fresh_db` が TRUNCATE のみで、スキーマを破壊する
   自己修復テストの後続が ERROR 連鎖していた。→ 各テスト前に `run_migrations()` で head を
   保証し、`Base.metadata` 由来の全テーブルを TRUNCATE する方式に変更。

---

## 4. 残課題ロードマップ

> コード起因の P0〜P3 はすべて修正済み（§3）。残るは**デプロイ環境/運用に依存し、
> 本リポジトリのコード変更では完結しない**項目のみ。

### 環境・運用（要確認 / 要作業）

- **B-1. Docker ビルドの CI 検証（対応済み・実ビルドは要外部実行）** — `ci.yml` に `docker-build`
  ジョブを追加し、push/PR ごとに本番イメージのビルドを検証するようにした（GitHub runner で実行）。
  本監査環境ではレジストリ pull がネットワークポリシーで 403 となり実ビルド完走は不可だったが、
  Dockerfile のパース・COPY 対象の存在・`pip install -e .`・3 ランタイム entrypoint の import は
  ローカル検証済み。実ビルド完走の最終確認は CI（外部）に委譲。
- **B-2. 本番環境変数の充足確認** — `POLYGON_RPC_HTTP/WS`、`DATABASE_URL`、（実行時）
  `CLOB_API_KEY/SECRET/PASSPHRASE`・`TRADER_PRIVATE_KEY`、`TELEGRAM_*` の Fly.io secrets 設定。
  完全リストは §8。

### 運用（推奨）

- 統合テストは既に CI（`ci.yml`、Postgres サービス + alembic + pytest）で push/PR ごとに実行
  されている（当初の「CI で回っていない可能性」は誤りで、実際は回っている。time-bomb は
  トリガー日以降 CI を赤にしていたはずで、§3 の修正で再び green になる）。
- `web.app` がモジュール import 時に DB 接続する設計（import スモークで顕在化）。
  Streamlit の実行モデル上は許容だが、テスト容易性のため遅延化を検討（任意）。
- `balance_refresh` ジョブを scheduler（`scheduled_jobs`）に登録し定期実行（execution 有効時）。

> その他のコード課題（A-1/E-1/E-5〜E-10/F-1/F-2/D-1）は §3 ですべて修正済み。

---

## 4.5 共通機能要件: AIモデル選択（OpenRouter）

AUDIT.md に新規追加された「共通機能要件(全ツール必須・AIモデル選択)」を、本スタック
（Streamlit / SQLAlchemy + Alembic / Postgres）向けに読み替えて実装した。Next.js の
API Route / Supabase RLS は、それぞれ Python サービス層関数 / アプリ層 `require_admin()`
ゲートに対応づけた。

### 実装サマリー

- **DB**: `alembic/versions/0009_ai_model_settings.py` で `app_settings` / `openrouter_config`
  / `ai_usage_log` の3テーブルを追加。`openrouter_config.is_selected` は部分一意インデックス
  （`WHERE is_selected`）で「選択は常に高々1件」を担保（AUDIT の「トリガーで1件制約」の代替）。
- **API キー入力（A-1）**: 管理者ページ `pages/admin_ai_settings.py` に
  「🔑 OpenRouter API キー」フォームを設置。`type="password"`・保存/削除ボタン・トースト・
  マスク表示（`sk-or-v1-••••••••xxxx`）。値は `app_settings`（`updated_by` で監査）に永続化。
- **モデル選択（A-2）**: OpenRouter `/models` を1時間キャッシュで取得し、プルダウン + 選択中
  バッジ（`#2563eb`）+ コンテキスト長・プロンプト/補完単価を表示。「このモデルを使用する」で
  `openrouter_config` に保存。到達不可時は最小フォールバック一覧で UI を維持。
- **ユーザー側制限（B）**: モデル選択 UI は管理者メニュー配下のみ。ユーザー設定画面
  （`settings_notifications` / `settings_billing`）にモデル選択は存在せず、`profiles`/`users` に
  `ai_model` 等のカラムも持たない。`resolve_model()` はユーザー ID を引数に取らない。
- **解決順（F）**: `ai/resolve_model.py` が API キーを **DB(`app_settings.openrouter_api_key`)
  → env `OPENROUTER_API_KEY` → env `ANTHROPIC_API_KEY`** の順、モデルを **env `OPENROUTER_MODEL`
  （強制上書き）→ DB 選択モデル** の順で解決。キーが OpenRouter 系に無ければ provider を
  `anthropic` にフォールバック。キーはサーバ側のみで参照（クライアント非公開）。
- **使用量ログ / コスト表示（E）**: `ai/usage.py` の `log_usage()` がトークン数・推定コストを
  `ai_usage_log` に記録。`cost_summary(days)` が過去N日の合計（USD・円換算）・トークン・
  モデル別内訳を返し、管理者ページの「💰 AI コスト（過去30日）」に表示。

### GAP 分析（AUDIT.md H）

| 機能 | 着手前 | 実装後 | 工数 |
|---|---|---|---|
| 管理者UIでの API キー入力・保存（`app_settings`） | 未（AI連携自体が皆無） | 実装済（`admin_ai_settings.py` + `app_settings`） | 0.5d |
| OpenRouter API 連携・モデル一覧取得（1h キャッシュ） | 未 | 実装済（`ai/openrouter.py`、フォールバック付き） | 0.5d |
| 管理者モデル選択 UI（色付きバッジ・単価表示） | 未 | 実装済 | 0.5d |
| 選択モデルの DB 保存・取得（1件制約） | 未 | 実装済（部分一意 index） | 0.25d |
| ユーザー側モデル選択の削除/禁止 | 該当なし（元から無し） | 維持（管理者専用） | 0d |
| AI 使用量ログ記録 | 未 | 実装済（`ai/usage.py`） | 0.25d |
| 管理者ダッシュボードへのコスト表示 | 未 | 実装済（CostSummary 相当） | 0.25d |
| 既存 AI 呼び出しの OpenRouter 移行 | 既存 AI 呼び出しが0件 | 解決層（`resolve_model`）を整備し将来の呼び出しに備え済 | 0d |

> 補足: 本リポジトリには既存の AI 呼び出しが1件も無かったため「移行（F）」は対象ゼロ。
> 将来 AI 機能を追加する際は `resolve_model()` + `log_usage()` を経由する規約とする。

---

## 4.6 認証の統合ログインページ化（運営者の管理者表示・認証画面の常時表示）

### 背景（不具合）
- 旧来は「`WEB_PASSWORD` 設定 **かつ users 空**」のときだけ単一パスワードゲートが出る設計で、
  ① 一度でもユーザー行ができるとゲートが無効化され**認証画面が出ない**、
  ② パスワードのみログインは `_current_user` を作らず**管理者メニューが永久に出ない**、
  という2問題があった。

### 対応
- `web/auth_tokens.py`（新規）+ `login_tokens` テーブル（alembic 0010）でワンタイム
  トークン（マジックリンク / パスワードリセット）を実装。生トークンは SHA-256 ハッシュで保存。
- `_show_login_form()` を**統合ログインページ**に刷新。タブ構成:
  - **ログイン**（メール/パスワード）
  - **新規登録**（メール+パスワード8文字以上）
  - **マジックリンク**（パスワード不要・未登録は自動作成）
  - **パスワード再設定**（リセットリンク送信 → `?action=reset&token=` で新PW設定）
  - OIDC 設定時は上部に **Google ログイン**ボタン
- `require_login()` で `?action=magic|reset&token=` のクエリを処理（マジックリンク消費→ログイン、
  リセット→新PWフォーム）。レガシー単一ゲートは **DB 接続不可時のみの緊急フォールバック**に降格し、
  通常は統合ログインを常時表示（①を解消）。
- 許可リスト（`ADMIN_EMAILS` / 既定 `kazgamada@gmail.com`）のメールは
  `_promote_if_admin()` により **全ログイン経路（パスワード/OAuth/マジックリンク/新規登録）で
  admin に自動昇格**（②を解消）。
- メールは既存 Resend 基盤（`email/client.py`）を利用（`RESEND_API_KEY` 未設定時は fail-soft）。
  リンク URL は `APP_BASE_URL` から生成。

### 検証
- 統合テスト `tests/integration/test_auth_flows.py`（7件）: トークンの往復/ワンタイム/期限切れ/
  用途不一致、新規登録の admin 昇格・バリデーション・重複、パスワード更新。
- 実機: 新規登録タブで `kazgamada@gmail.com` を登録 → 自動 admin 昇格 → 管理者メニュー表示を確認。

---

## 5. E2E / 手動確認チェックリスト

`AUDIT.md` Step 2.5 のうち、ローカル Postgres + web 実起動で検証できた範囲は本監査で実施済み
（`docs/AUDIT_REPORT.md` §3）: Streamlit `:8501` 応答 / health `:8080` 応答 / SIGTERM 伝播。
外部 RPC/CLOB・本番配信に依存する以下は人間による手動確認項目。

- [x] web 実起動で `/readyz`（health, internal 8080）が 200（migration/db 状態込み）を返す ※監査で確認
- [x] Streamlit UI（8501）が起動応答する ※監査で確認（`WEB_PASSWORD` 設定時もログインゲート付きで起動確認）
- [ ] Fly.io 本番デプロイ後にも上記 2 ポートが応答する（本番環境での再確認）
- [ ] `WEB_PASSWORD` を設定し、ログインゲートが本番で機能する
- [ ] indexer が Polygon RPC に接続し backfill が進む（`Jobs` ページの live log）
- [ ] Phase 0 を 1 周実行し result JSON が出る（README 手順）
- [ ] kill switch ON/OFF が execution layer に反映される
- [ ] Telegram 通知（設定時）が届く

---

## 6. UI 規約（Streamlit 文脈での読み替え）

`AUDIT.md` の共通 UI 規約（左カラム黒/右カラム白、ページ内タブ全廃、`config/navigation.ts` 等）は
Next.js 前提であり、Streamlit のマルチページ（`web/pages/*.py`）には直接適用できない。
本ツールは既にダークテーマ（`web/theme.py`）とページ分割（Strategy / Execute / Ops / Help）を
持つ。共通 UI パッケージ化はポートフォリオ全体の Next.js 系ツールとは別軸で扱うべきで、
**本リポジトリは UI 規約 GAP の対象外**と判断する（要ポートフォリオ横断での合意）。

---

## 7. Billing（Stripe）について

本ツールに課金・サブスク機能は存在せず、Stripe 連携も無い（grep で `stripe` 不検出）。
`AUDIT.md` の共通 Billing 要件は SaaS 提供形態を採る場合にのみ適用される。
コピートレードボットを「課金ユーザーに提供」する形態（SaaS 化）を採るなら Billing は
新規の大型要件となるため、別 Phase として切り出すこと。現 Phase 0/1 のスコープ外。

---

## 8. 必要環境変数 完全リスト

コード内の `os.environ[...]` / `settings.*`（`config.py`）と `.env.example` を突合。

| 変数 | 必須度 | 用途 | 取得場所 |
|---|---|---|---|
| `DATABASE_URL` | 必須 | Postgres 接続（`postgres://` も自動正規化） | Fly Postgres / Supabase 等 |
| `POLYGON_RPC_HTTP` | 必須 | Polygon backfill | Alchemy / QuickNode / Infura |
| `POLYGON_RPC_WS` | 必須 | Polygon WS ストリーム | 同上 |
| `WEB_PASSWORD` | 要判断 | Web UI ゲート（セッション維持型パスワードゲート実装済み。本番では必ず設定すること） | 任意設定 |
| `INDEXER_WINDOW_DAYS` | 任意 | backfill 期間（既定 30 / 最大 90） | — |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 任意 | 通知 | BotFather |
| `CLOB_API_KEY` / `SECRET` / `PASSPHRASE` | 実行時必須 | CLOB 発注（execution layer） | Polymarket CLOB |
| `TRADER_PRIVATE_KEY` | 実行時必須 | 署名鍵（**秘匿必須**） | 自ウォレット |
| `GIT_SHA` / `BUILD_TIME` | 任意 | 診断ページ表示 | CI 注入 |

---

## 9. ゼロから動かす手順（要約）

```sh
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env   # POLYGON_RPC_* と DATABASE_URL を設定
# Postgres を用意し
DATABASE_URL=... .venv/bin/alembic upgrade head
docker compose up -d   # web / indexer / worker
open http://localhost:8501
```

テスト: `DATABASE_URL=...test .venv/bin/alembic upgrade head && .venv/bin/pytest -q`
（unit のみなら DB 不要: `pytest tests/unit -q`）

---

## 10. 要確認リスト（外部依存・本リポジトリのコードでは閉じない事項）

- **B-2. 本番 secrets の設定** — Fly.io に `WEB_PASSWORD`（必須化）、`POLYGON_RPC_HTTP/WS`、
  `DATABASE_URL`、（execution 有効時）`CLOB_*`・`TRADER_PRIVATE_KEY`・`TRADER_ADDRESS`、
  `TELEGRAM_*` を設定する（人手・本番環境アクセスが必要）。完全リストは §8。
- Docker 実ビルドの最終確認は `ci.yml` の `docker-build` ジョブ（GitHub runner）に委譲済み
  （本監査環境はレジストリ pull がネットワーク制限で不可）。
- 解決済み（参考）: CI は DB 付き統合テストを実行している（`ci.yml`）。Web UI 認証は
  セッション維持型ゲートとして再有効化済み（`WEB_PASSWORD` 設定で有効）。`.env.example` も是正済み。
