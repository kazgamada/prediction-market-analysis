# Polymarket Copytrader 完全再構築 要件定義書

最終更新: 2026-05-12
対象: 現リポジトリ `prediction-market-analysis`（中身は `polymarket-copytrader`）
方針: 現状の実装を破棄し、スクラッチから作り直す。本書はその設計の前提と要件を確定するためのもの。

---

## 0. このドキュメントのゴール

1. 現行実装で発生したトラブルを **網羅的に棚卸し**、再発させない設計制約として固定する。
2. 「Phase 0（オフライン edge 検証）」が **1 回もまともに完遂できていない** という事実を直視し、最短で edge の有無を判定できる構成に再設計する。
3. 実装着手前に、ユーザー（運用者）と Claude の間で **スコープ / 非スコープ / 完了条件** を合意するためのインプットとする。

> 着手承認は本書のレビュー後に行う。本書が確定するまで一切のコード変更を行わない。

---

## 1. 背景: これまでのトラブル全リスト

### 1.1 プロジェクトの経緯

- 元々 `Jon-Becker/prediction-market-analysis` を fork した **オフライン分析ツール** だった。
- 途中で Render に乗せようとして preDeployCommand / startup-download で詰まり、最終的に `0accd98` で startup-download を撤去。
- `53c1d47` でリポジトリを **リセット**、`22bffaa` で **polymarket-copytrader にピボット**。
- 以降 Fly.io デプロイを軸に開発しているが、indexer / backfill / 監視プロセスが **一度も安定稼働していない**。

### 1.2 トラブル分類表（git log 由来）

各項目は「何が起きたか → なぜ起きたか → 再構築で潰す方法」を後段の設計要件に反映する。

| # | 領域 | 症状（コミット） | 根本原因 |
|---|------|------------------|----------|
| T1 | チェーン RPC | per-chunk 失敗で iter_logs ごと停止（`e4c08fb`） | 1 chunk の失敗が全体停止を引き起こす設計。skip / retry 戦略がない。 |
| T2 | チェーン RPC | CTF Exchange V1 のアドレスを叩いていた（`75789ce`） | コントラクトアドレスがハードコード & V2 移行を追えていない。 |
| T3 | チェーン RPC | RPC API key が例外メッセージに露出（`fe6ed48`） | エラー整形なし。シークレットがログに混入。 |
| T4 | チェーン RPC | JSON-RPC エラー本文が見えずデバッグ不能（`a0c50c4`） | error body を捨てていた。 |
| T5 | Indexer | バックフィルが「終わらない」（`e2f9ec9`） | 全期間を無条件に走査。recent N days の窓を持たない。 |
| T6 | Indexer | カーソルが過去に巻き戻り進捗が消える（`9ad9932`） | カーソル更新が monotonic でなく、レース・例外で巻き戻る。 |
| T7 | Indexer | PostgreSQL の 65535 パラメータ上限で INSERT 失敗（`071fbb4`） | 1 INSERT の行数 × カラム数の見積もりなし。 |
| T8 | Indexer | バックフィルが遅すぎる（`ca98214`） | DB commit が 1 行単位 / RPC 並列度が 1。 |
| T9 | Indexer | カーソルが過去に張り付き永遠に追いつかない（`2a73f74`） | 「recent_floor まで一気にジャンプ」する初回ブートストラップがなかった。 |
| T10 | Monitor プロセス | 個別タスクが落ちると monitor 全体が死ぬ（`e7bbdb2`） | タスクスーパーバイザ不在。例外で main loop 終了。 |
| T11 | Monitor プロセス | monitor 単独運用で catchup が走らず、web 側に fallback 実装（`5a8d142`, `248e39b`） | プロセス境界の役割分担が曖昧。fallback が二重実装を生んでいる。 |
| T12 | Fly.io | release_command が Postgres 未 attach で失敗しデプロイ完了せず（`fa65243`） | Fly Postgres attach の順序と migration 実行タイミングを混在。 |
| T13 | Fly.io | machine が auto-stop で catchup スレッドごと殺される（`248e39b`） | 長時間ジョブを web プロセスのバックグラウンドスレッドに依存。 |
| T14 | Fly.io | `[[services]]` 旧構文でデプロイ失敗（`5c710d4`） | Fly 設定の追従漏れ。 |
| T15 | Fly.io | app 名不一致で deploy 失敗（`2816dc7`） | リポ名と Fly app 名のずれ。 |
| T16 | Docker | README.md が build context に無くてビルド失敗（`436a8f6`） | .dockerignore / build 指定の食い違い。 |
| T17 | DB 接続 | `postgres://` を SQLAlchemy が拒否（`f63c0cd`） | スキーマ正規化なし。Fly が出す URL 形式と未整合。 |
| T18 | Web UI | 「Run backfill」ボタンが反応しない（`5206547`） | 同期実行で Streamlit のリランがブロック。 |
| T19 | Web UI | live log が画面に流れない / 進捗が見えない（`8556cb1`, `e6e5c34`, `e7a4023`） | ログ収集・flush・表示の仕組みがその場しのぎ。 |
| T20 | Web UI | ページ遷移でジョブが消える（`bf7a0de`） | ジョブが Streamlit セッションに紐付いていた。 |
| T21 | 観測性 | 何が起きているか外から見えない（`f9e413e`, `68d3b32`） | health / self-test エンドポイントを後付けで継ぎ足し。 |
| T22 | スコープ | Phase 0 を 1 度も完走できないまま UI 改修（tooltip / page cache / state 永続化等）が先行 | Phase 0 完了条件が定量化されていない。 |

### 1.3 ここから読み取れる「設計上の禁じ手」

- **長時間ジョブを web プロセスに同居させる**（Streamlit + バックグラウンドスレッド）。
- **単一プロセスにすべての責務を持たせる**（indexer・catchup・UI を 1 個に詰め込む）。
- **カーソルや状態を「メモリ + ad-hoc」で管理する**。永続化と monotonic 保証が無いと必ず巻き戻る。
- **エラーを握りつぶす or 全捨てる**。中庸（per-unit skip + dead-letter）を持たないと T1 / T6 / T10 を再発する。
- **コントラクトアドレス / RPC URL / DB URL をハードコードする**。
- **デプロイ後の確認手段を後付けする**。最初から `/healthz` `/api/status` 相当を作る。

---

## 2. 再構築のゴールと非ゴール

### 2.1 ゴール（このリビルドで達成すること）

- G1. **Phase 0 を 1 サイクル完走できる**。すなわち「過去 30〜90 日の OrderFilled を取り込み → ウォレットランキングを出し → 上位 N に遅延コピーした場合の期待値を replay でレポートする」までを、ボタン 1 つもしくは 1 コマンドで完了できる。
- G2. **観測可能であること**。任意の瞬間に「いまどこまで取り込めているか / 直近何件取れているか / RPC 健全性はどうか」が 1 画面で分かる。
- G3. **障害が起きても自己復旧する**。RPC chunk 失敗・カーソル巻き戻り・プロセス再起動で進捗が壊れない。
- G4. **本番（Fly.io）でブラウザ完結**で動かせる。ターミナルからの介入なしでバックフィル開始 / 停止 / 再実行ができる（CLAUDE.md §0.1）。

### 2.2 非ゴール（今回は作らない）

- 自動発注（Phase 4 の live モード）。スコープは Phase 0〜2（read-only ライブ監視）まで。
- 複数チェーン対応。Polygon Mainnet + Polymarket CTF Exchange V2 のみ。
- Kalshi など他予測市場。
- 高度な ML / 価格モデル。あくまで「上位ウォレット模倣 + 遅延 + サイズキャップ」のシンプルな統計検証。
- 課金 / マルチテナント / ユーザー登録。運用者 1 名想定、認証は単一パスワードのみ。

---

## 3. 設計原則（CLAUDE.md §0 を踏襲）

D1. **観測 → 仮説 → 修正の順**を構造で強制する。ジョブ実行・RPC 呼び出し・DB 書き込みのすべてに「いま何件 / 最後にいつ成功したか」が記録される。
D2. **責務分離 (1 プロセス = 1 責務)**。`web`（UI）/ `indexer`（取り込み）/ `worker`（分析・replay）を別プロセスにする。web が長時間ジョブを抱えない。
D3. **状態は DB に一元化**。カーソル・ジョブ進捗・ジョブログ・risk_event を Postgres に書く。プロセス内メモリで保持しない。
D4. **idempotent と monotonic**。INSERT は ON CONFLICT、カーソルは `GREATEST(current, new)` 更新、ジョブは同一 idempotency key で再投入可。
D5. **失敗の粒度を分ける**。chunk 単位の失敗は skip + retry queue。プロセス全体は落とさない。
D6. **設定は環境変数 + DB 設定テーブル**。コントラクトアドレス・RPC URL・しきい値は再デプロイなしで切り替え可能。
D7. **ブラウザ完結デプロイ**。Fly.io への変更は Web UI / GitHub / Vercel ダッシュボード相当の操作のみで完結する。CLI 手順書は補助。
D8. **最小実装**。Phase 0 完走に不要なものは作らない（page cache warmer, tooltip 改修, state 永続化 UI 等は後回し）。

---

## 4. システム構成

### 4.1 物理構成（Fly.io）

```
┌─────────────────────────────────────────────────┐
│  Fly app: polymarket-copytrader                 │
│                                                 │
│  process: web        (Streamlit, 常時 1 台)     │
│  process: indexer    (RPC backfill + WS stream) │
│  process: worker     (rank / replay / poller)   │
│                                                 │
│  attached: Fly Postgres (managed)               │
└─────────────────────────────────────────────────┘
```

- web は **読み取り中心**。ジョブの起動は DB に「job request」を INSERT するだけ。
- indexer と worker は **常駐**。`auto_stop_machines='off'` + `min_machines_running=1`。
- migration はデプロイ時 release 相当ではなく、各プロセス起動時に `alembic upgrade head` を一度だけ実行（advisory lock で多重実行防止）。

### 4.2 論理コンポーネント

| コンポーネント | 責務 | 失敗時挙動 |
|----------------|------|------------|
| `chain.client` | Polygon RPC への呼び出し。chunk 分割・並列・retry・rate limit。 | chunk 単位で失敗 → dead-letter テーブルに移動。プロセスは継続。 |
| `chain.contracts` | CTF Exchange V2 / USDC / CTF ERC1155 のアドレスとイベント定義。DB で上書き可。 | 不明アドレスは起動時に拒否（fail-fast）。 |
| `indexer.backfill` | 指定ブロック範囲を取り込む。カーソルは `cursors` テーブル。 | 中断しても次回は `MAX(cursor, recent_floor)` から再開。 |
| `indexer.stream` | WS で最新ブロックを subscribe。停止しても backfill が catchup。 | WS 切断 → 指数バックオフ再接続。10 分復帰しなければ alert。 |
| `analysis.rank` | 過去 N 日のウォレット PnL を集計し、しきい値で上位を返す。 | DB クエリのみ。失敗は job 単位で記録。 |
| `analysis.replay` | 上位ウォレットに遅延コピーした場合の損益を再現。 | 同上。 |
| `monitor.watchlist` | watchlist 上のウォレットの新規約定を `signal` として保存。 | 同上。 |
| `web` | 状況閲覧 + ジョブ起動 + watchlist 編集。長時間処理は持たない。 | UI 単独で落ちても indexer / worker に影響なし。 |
| `worker` | job_queue を polling で実行（rank / replay / reconcile / poll）。 | 1 ジョブの失敗はそのジョブだけ FAILED。 |
| `health` | `/healthz`（liveness）`/readyz`（DB / RPC self-test）。 | UI からも結果を見える化。 |

### 4.3 シーケンス（Phase 0 ハッピーパス）

1. ユーザーが web で「Phase 0 を実行」を押す。
2. web が `jobs` に `kind=phase0` を INSERT。
3. worker が pick up し、依存ジョブを enqueue: `backfill(last_30d)` → `rank(window=30)` → `replay(window=30, delays=[30,60,120])`。
4. 各ジョブの状態（PENDING / RUNNING / SUCCEEDED / FAILED）と progress（取り込み済みブロック / 件数）は `jobs` と `job_logs` に書く。
5. web は `jobs` を 2 秒 polling で表示。完了後、`replay_report` の結果テーブルを表示。

---

## 5. データモデル（最小セット）

```
cursors            (name PK, last_block, last_block_at, updated_at)
blocks_seen        (block_number PK, log_count, fetched_at)   -- chunk 進捗
trades             (tx_hash, log_index PK, ts, maker, taker, token_id, side, price, size_usdc, ...)
wallets            (address PK, first_seen, last_seen, trade_count, gross_volume_usdc)
wallet_stats_daily (address, date PK, trades, volume_usdc, realized_pnl_usdc, win_rate)
watchlist          (address PK, note, added_at, active)
signals            (id, address, token_id, side, size_usdc, ts, source)
positions          (token_id PK, size, avg_price, last_reconciled_at)
orders             (id, token_id, side, size, price, status, last_polled_at)
risk_events        (id, kind, severity, message, ts)
jobs               (id, kind, status, params_json, progress_json, error_text, created_at, started_at, finished_at, idempotency_key UNIQUE)
job_logs           (id, job_id, ts, level, message)
rpc_dead_letters   (id, kind, request_json, error_text, ts, retries)
settings           (key PK, value_json, updated_at)  -- コントラクトアドレス等の上書き
```

- すべてのテーブルに `created_at` / `updated_at` を持たせる。
- 大量 INSERT は `executemany` + chunk 上限 = `floor(65535 / カラム数) - 安全マージン` を計算するヘルパに集約（T7 再発防止）。

---

## 6. 機能要件

### 6.1 取り込み（indexer）

- F1. 過去 N 日（デフォルト 30、最大 90）の OrderFilled を取り込めること。N は UI から変更可能。
- F2. 初回起動時、カーソルが古ければ `recent_floor = head - N days` まで **同期的に** ジャンプし、その後 stream で前進（T9 対策）。
- F3. RPC chunk は `[block_lo, block_hi]` の単位で並列実行。1 chunk の失敗は dead-letter に積み、他は継続（T1 対策）。
- F4. dead-letter は worker が 1 分おきに retry。3 回失敗で `risk_event` に上げて止める。
- F5. カーソルは `cursors.last_block = GREATEST(current, new)` で更新（T6 対策）。
- F6. CTF Exchange V2 のアドレスとイベント ABI は `settings` テーブルで上書き可能。デフォルト値は constants にハードコードしつつ、起動時に DB 値で上書き（T2 対策）。
- F7. RPC エラーは API key を redact してログ・例外メッセージに整形（T3 対策）、JSON-RPC body は保持（T4 対策）。

### 6.2 分析（worker）

- F8. `rank` ジョブ: window（日数）/ min_trades / min_volume を引数に上位ウォレット一覧を返す。
- F9. `replay` ジョブ: 上位ウォレット集合に対し、delays（秒）/ copy_usd / slippage を引数に PnL を出す。
- F10. `inspect` ジョブ: 任意アドレスのトークン別 PnL を返す。
- F11. すべての分析結果は `job.progress_json` / 専用結果テーブルに保存し、UI から後で再表示可。

### 6.3 監視（monitor / watchlist）

- F12. watchlist のウォレットが新規約定したら `signals` に記録（Phase 1）。
- F13. watchlist の追加・削除は UI から可能。バリデーション（チェックサムアドレス）必須。
- F14. 監視 WS が 10 分以上復帰しなければ `risk_event` を上げ、UI に赤帯で表示。

### 6.4 UI（Streamlit）

- F15. トップに 1 画面で **Status**: 最終取り込みブロック / そこから現在 head までの遅延 / 直近 1 時間の trade 件数 / dead-letter 件数 / RPC self-test の結果。
- F16. 「Phase 0 を実行」ボタン 1 つで F1〜F11 を順次実行（ジョブを enqueue するだけ）。
- F17. job 一覧 + 個別ジョブの live log を表示。ジョブ詳細はページ遷移しても継続（job は worker 側で走っているため）。
- F18. watchlist 編集 UI（追加・削除・無効化）。
- F19. 設定 UI: window / min_trades / min_volume / delays / copy_usd を `settings` テーブルに保存。
- F20. 単一パスワード認証（`WEB_PASSWORD` env）。未設定なら起動を拒否（fail-fast）。

### 6.5 観測性（必須）

- F21. `/healthz`: プロセス生存。常時 200。
- F22. `/readyz`: DB ping + 最新 RPC self-test 結果（30 秒キャッシュ）。
- F23. UI に「診断」ページ: cursor 値 / 最新 N ジョブ / dead-letter / settings の現在値 / git SHA / build 時刻 を表示。
- F24. 重要イベント（cursor 巻き戻り検知 / WS 切断 / dead-letter 急増）は Telegram に通知（任意）。

---

## 7. 非機能要件

| カテゴリ | 要件 |
|----------|------|
| 性能 | 過去 30 日分の OrderFilled 取り込みが **連続稼働で 2 時間以内** に完了すること。 |
| 耐障害 | 任意のタイミングで indexer / worker / web を kill しても、再起動で進捗が継続すること。 |
| セキュリティ | API key / private key を例外・ログ・UI に露出しない。Fly secrets で管理。 |
| 機密 | RLS 相当の制御は単一テナント前提なので不要だが、`WEB_PASSWORD` で UI 全体を保護。 |
| 観測性 | F21〜F23 を満たすこと。 |
| デプロイ | main へ push → GitHub Actions or Fly auto-deploy → 5 分以内に反映。release_command は使わない。 |
| ロールバック | 直前の good commit に main を戻して push すれば自動でロールバックされること。 |

---

## 8. 運用要件（CLAUDE.md §0 準拠）

- O1. 修正は main 直プッシュを基本（蟻地獄回避ルール §0.2）。
- O2. デプロイ・環境変数・ロールバックは **ブラウザのみで完結** することを README に明記。CLI 手順は補助。
- O3. 障害時はまず `/readyz` と UI の診断ページを開くフローを明文化。
- O4. 同じ箇所を 3 回直してダメなら全戻し（§0.5）。

---

## 9. テスト戦略（最小）

| レイヤ | 内容 |
|--------|------|
| unit | `chain.client` の chunk 分割 / retry / API key redact、`indexer.decoder` のイベントデコード、`cursors` の monotonic 更新、INSERT chunk 計算ヘルパ。 |
| integration | sqlite or テスト用 postgres で `backfill → rank → replay` を 1 サイクル流す e2e（モック RPC）。 |
| smoke (本番) | デプロイ直後に `/readyz` を curl し、`status=ok` を確認するだけの GitHub Actions。 |

CI で必須にするのは unit + integration のみ。本番 smoke は post-deploy ジョブ。

---

## 10. 移行・廃棄方針

- 旧 `prediction-market-analysis`（Render / FastAPI / React）コードはすでに `0accd98` で実質剥がされている。**復活させない**。
- 現リポジトリの `src/copytrader/` は **全削除して書き直す**。テストも刷新。
- 既存 Fly app `prediction-market-analysis` は **そのまま使い回す**（app 名変更はコストが大きいので保留）。fly.toml の app 名は変えない。
- DB は移行不要（Phase 0 の検証データは捨てて良い）。新 schema を alembic で 0 から作る。

---

## 11. ロードマップ（最短ルート）

| Step | 内容 | 完了条件 |
|------|------|----------|
| S0 | 本書のレビュー & 確定 | ユーザー承認 |
| S1 | スケルトン再構築（3 プロセス分離 + alembic 0 から） | docker compose up でローカル 3 プロセスが起動し、`/readyz` が 200 |
| S2 | indexer MVP（F1〜F7） | 過去 7 日分が 30 分以内に取り込める。dead-letter が DB に積まれる |
| S3 | worker MVP（F8〜F11） | Phase 0 ジョブが 1 コマンドで完走し replay レポートが出る |
| S4 | UI MVP（F15〜F20） | Web から Phase 0 ボタン 1 つで S2+S3 が走る |
| S5 | Fly.io 移行 | ブラウザのみで本番デプロイ・ロールバックできる。`/readyz` が緑 |
| S6 | Phase 0 本番計測 | 過去 30 日で edge があるか / 撤退かを判定 |

S6 で **edge が出なければ撤退**。S3 以降の UI 改修・Telegram 通知・Phase 1 以降は一切やらない。

---

## 12. 明確化したいオープン質問（ユーザーに確認したい）

着手前に確定したい論点。実装承認時に合わせて回答をもらう。

- Q1. 撤退ライン: Phase 0 で「edge あり」と判断する数値基準（例: 30 日 replay で年率換算 +X% 以上 / Sharpe Y 以上）を、いま事前に決めるか、結果を見てから決めるか。
- Q2. 監視ウォレット数の上限: rank の `watchlist-top` は実運用で 10 / 50 / 100 のどれを想定するか。RPC コストに直結する。
- Q3. RPC プロバイダ: 引き続き Alchemy / QuickNode どちらをデフォルトにするか。無料枠の rate limit を超える前提なら有料プラン契約のタイミングを決めたい。
- Q4. 通知: Telegram は最初から入れるか、Phase 0 完走後でよいか。
- Q5. 旧 git 履歴の扱い: 現リポジトリで作り直すか、新規リポジトリに切り出して `polymarket-copytrader` 単独リポ化するか。

---

## 13. 受け入れ条件（このリビルドが「完了」と言える状態）

- A1. `git clone` → `docker compose up` で 3 プロセスが起動し、`/readyz` が 200。
- A2. ローカルで Phase 0 ジョブが 1 コマンドで完走し、replay レポートが UI に表示される。
- A3. Fly.io 本番でも A2 と同じ操作がブラウザのみで完了する。
- A4. indexer / worker / web を任意のタイミングで kill しても、再起動で進捗が継続する（手動テストで確認）。
- A5. §1.2 のトラブル T1〜T22 すべてに対応する unit / integration テスト or 構造的予防策がコードに入っている。
- A6. README が「セットアップ・運用・障害対応」をブラウザ完結ベースで記述している。

以上。
