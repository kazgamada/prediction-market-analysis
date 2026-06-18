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
- **リリース可否判定**: 現時点では **不可**。P0（Web UI 認証無効）と、本監査で修正した
  品質ゲート（lint・テスト）の green 化が前提。本書の P0/P1 を消化すれば限定リリース可。

---

## 2. 検証ログ（本監査で実行）

`AUDIT.md` Step 2 を本スタックに読み替えて実行した。生ログは `docs/AUDIT_REPORT.md` §2 に転記。

| ゲート | コマンド | 監査時の初期結果 | 修正後 |
|---|---|---|---|
| 依存導入 | `pip install -e ".[dev]"` | OK | OK |
| Lint | `ruff check src tests` | **64 errors（exit 1）** | **All checks passed（exit 0）** |
| Unit テスト | `pytest tests/unit -q` | 42 passed | 42 passed |
| 統合テスト | `pytest -q`（Postgres 16） | **2 failed / 12 errors** | **66 passed** |
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

## 4. 残課題ロードマップ（未対応 / 要判断）

### P0（リリース前に必須・要ユーザー判断）

- **A-1. Web UI の認証が無効化されている** 🔴
  - 証拠: `src/copytrader/web/auth.py:9-10` — `require_password()` が `return` のみの no-op。
    コメントに「頻繁な再認証要求を避けるため無効化」とある。
  - 影響: Fly.io の公開 URL（`fly.toml` の `http_service`）に到達できれば誰でも UI を操作可能。
    本ツールは kill switch・手動 order・watchlist 編集など **資金移動につながる操作** を持つため、
    無認証公開は重大なアクセス制御欠如。
  - 推奨対応: パスワードゲートの再有効化（セッション維持で再認証頻度を下げる実装）か、
    Fly.io 側のネットワーク制限（Tailscale / basic auth proxy / IP allowlist）。
    `.env.example` / README は依然 `WEB_PASSWORD` を案内しており実態と乖離している点も是正。
  - **意図的に無効化された挙動のため、再有効化の方式は本書では実装せず要ユーザー判断とする。**

### P1（リリース前に必須）

- **E-6. executor のクラッシュ復旧 / halt セマンティクス（要設計判断・未実装）** — ①claim 後〜CLOB
  完了前のクラッシュで signal が EXECUTING のまま滞留し再処理されない。②halt 中は signal を
  SKIPPED で破棄する実装だが Help ページの「溜まった signal」=保留と矛盾（`executor.py:54-98`）。
  > 資金経路（執行）の復旧ロジックと halt 方針の確定を伴い、誤修正は二重発注/取りこぼしを生むため、
  > 証拠付きで報告し未実装とした（推測で実装しない原則）。要ユーザー判断。
  > なお E-7（backfill 取りこぼし）は §3 で修正済み。
- **B-1. Docker / Fly.io ビルドの実証** — 本監査環境では Docker daemon 不在のため
  `docker build` を未実行。CI（`.github/workflows`）でのビルド成功を要確認。
- **B-2. 本番環境変数の充足確認** — `POLYGON_RPC_HTTP/WS`、`DATABASE_URL`、（実行時）
  `CLOB_API_KEY/SECRET/PASSPHRASE`・`TRADER_PRIVATE_KEY`、`TELEGRAM_*` の Fly.io secrets 設定。
  完全リストは §8。

### P2（リリース後 2 週間以内）

- 統合テストを CI で常時実行（Postgres サービスコンテナ）。現状 time-bomb が
  すり抜けていた事実は「DB 付きテストが CI で回っていない可能性」を示唆 → 要確認。
- `web.app` がモジュール import 時に DB 接続する設計（import スモークで顕在化）。
  Streamlit の実行モデル上は許容だが、テスト容易性のため遅延化を検討。

### P3（改善余地）

- `risk/evaluator.py:178` の TODO（USDC/MATIC 残高フック、PR #4 連携）。
- パフォーマンス・デッドコード整理は現時点で顕著な問題なし。

---

## 5. E2E / 手動確認チェックリスト

`AUDIT.md` Step 2.5 のうち、ローカル Postgres + web 実起動で検証できた範囲は本監査で実施済み
（`docs/AUDIT_REPORT.md` §3）: Streamlit `:8501` 応答 / health `:8080` 応答 / SIGTERM 伝播。
外部 RPC/CLOB・本番配信に依存する以下は人間による手動確認項目。

- [x] web 実起動で `/readyz`（health, internal 8080）が 200（migration/db 状態込み）を返す ※監査で確認
- [x] Streamlit UI（8501）が起動応答する ※監査で確認（認証 P0 対応は別途）
- [ ] Fly.io 本番デプロイ後にも上記 2 ポートが応答する（本番環境での再確認）
- [ ] 認証（P0 対応後）が機能する
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
| `WEB_PASSWORD` | 要判断 | Web UI ゲート（**現在 no-op**、P0 A-1） | 任意設定 |
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

## 10. 要確認リスト（推測で埋めていない事項）

- CI（GitHub Actions）で integration テスト（DB 付き）が実際に回っているか
- Docker / Fly.io 本番ビルドが現行コードで成功するか
- Web UI 認証無効化が意図通り（運用上許容される閉域配置か）
- `WEB_PASSWORD` を fail-fast にする README/`.env.example` の記述を実態に合わせるか
