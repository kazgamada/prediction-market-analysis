# Polymarket Copytrader 運用マニュアル

最終更新: 2026-05-21
対象: 運用者 (= ユーザー本人)
前提: 本書は Phase 1 (執行レイヤ) が実装済み、Paper trading 開始可能な状態を前提とする。実装要件は `docs/requirements/PHASE1_LIVE_EXECUTION.md` 参照。

---

## 0. このマニュアルの使い方

- **初回セットアップ**: §1 を頭から順にやる (約 30 分)
- **毎日**: §2 を 5 分
- **毎週月曜**: §3 を 30 分
- **毎月 1 回**: §4 を 1〜2 時間
- **異常があった時**: §6 (シナリオ別対処) を引く
- **設定値の意味**: §7 (リスク管理) と §8 (用語集)
- **困ったら**: §9 (FAQ) → §10 (緊急時)

ブラウザだけで完結する設計。CLI / SSH は緊急時以外不要。

---

## 1. 初期セットアップ (一度だけ、約 30 分)

### 1.1 必要なもの

| 項目 | 用途 | 入手先 |
|---|---|---|
| Polygon (USDC) 残高 | 発注の元手 | 取引所から Polygon ネットワークに送金 |
| Polygon (MATIC) 残高 | ガス代 | 同上、$10 分もあれば十分 |
| Polygon RPC HTTP / WS エンドポイント | indexer 用 | Alchemy / Infura / QuickNode の無料枠で OK |
| Polymarket CLOB API key | 発注用 | https://polymarket.com → Settings → API Keys |
| Polymarket トレーダー秘密鍵 | 発注署名用 | 専用のホットウォレットを作成 (MetaMask 等) |
| Telegram bot token | 通知用 | @BotFather で `/newbot` |
| Telegram chat ID | 通知先 | bot に何かメッセージ送信後 `https://api.telegram.org/bot<TOKEN>/getUpdates` で取得 |

**安全のため**: トレーダー用秘密鍵は **新規ウォレット** を使い、生活用ウォレットと分離。最初は $100 だけ送金。

### 1.2 Fly.io secrets 設定

Fly.io ダッシュボード (https://fly.io/apps/prediction-market-analysis/secrets) で以下を全て入力:

```
DATABASE_URL              (Fly Postgres から自動)
POLYGON_RPC_HTTP          https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY
POLYGON_RPC_WS            wss://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY
CLOB_API_KEY              Polymarket から
CLOB_API_SECRET           同上
CLOB_API_PASSPHRASE       同上
TRADER_PRIVATE_KEY        0x...
TRADER_ADDRESS            0x...
TELEGRAM_BOT_TOKEN        @BotFather から
TELEGRAM_CHAT_ID          自分の chat ID
TELEGRAM_ADMIN_USER_IDS   自分の user ID (複数可カンマ区切り)
```

保存すると Fly が自動でマシンを再起動。約 2〜5 分待つ。

### 1.3 Ops ページで起動確認

ブラウザで `https://prediction-market-analysis.fly.dev` → サイドバー → `Ops` を開く。

確認:
- ✅ **cursor block**: 数値が表示され、updated が「数分前」になっている
- ✅ **trades (1h)**: 0 でないこと（市場が動いていれば 10 以上）
- ✅ **dead-letters**: 0 が理想 (10 件未満なら様子見)
- ✅ **last risk**: 「clean」または無害な kind
- ✅ **git_sha** が最新の deploy 番号と一致

1 つでも欠けたら §9 FAQ を参照。

### 1.4 settings 初期値の挿入

Ops ページの **Settings overrides** から、または DB に対して以下を一括実行:

```sql
\i docs/manual/INITIAL_SEED.sql
```

(SQL ファイルは要件定義書 §10 と同一)

完了したら Ops ページで Settings 一覧に 30 件出ていることを確認。

### 1.5 Watchlist 初期登録

Strategy ページで **Phase 0 を実行** を 1 回回す:
- window: 30 日
- top N: 10
- copy $: 50
- delays: 30,60,120

実行後、Execute ページ → Jobs タブで status=COMPLETED を待つ (約 5〜15 分)。

完了したら Execute ページ → Watchlist タブに上位 10 wallet が **自動で追加** されている (auto_rotate が有効なので)。または手動で 0x... を入力して Add。

### 1.6 Paper trading 開始

Ops ページの Settings で:
```
execution_enabled = false
```
であることを確認。これで Phase A (Paper) モード。

Execute ページ上部の Kill Switch が **🟢 LIVE** になっていることを確認 (`kill_switch_on=false`)。

→ これでセットアップ完了。以降は §2 の日次運用へ。

---

## 2. 日次運用 (毎朝、約 5 分)

### 2.1 朝のチェックリスト

毎朝、`Home` を開いて以下を 30 秒で目視:

| チェック項目 | OK の基準 | NG なら |
|---|---|---|
| 累積 PnL (左上) | 緑 (+) のまま | §6.2 「DD が大きい」 |
| 勝率 | 55% 以上 | §6.5 「勝率が下がった」 |
| 最大 DD | -10% 以下 (黄色まで) | §6.2 |
| USDC 残高 | $500 以上 | §6.6 「残高低下」 |
| 今日 PnL | 緑 or 軽微なマイナス | -3% 超なら警戒、-5% で halt |
| **Indexer lag タイル** (右下) | 赤線越えてない | §6.4 「indexer 停止」 |
| **DD gauge タイル** | 緑ゾーン | 黄なら警戒、赤なら手動 halt |
| **受信シグナル タイル** | ✅ が多数 | ❌ や ⏭ ばかりなら §6.3 |

### 2.2 Telegram 通知の確認

毎朝 9:00 JST に Telegram で **日次サマリー** が届く:
```
[Daily Summary]
Date: 2026-05-21
Phase: B Micro (Day 18/28)
Yesterday PnL: +$8.20
Total (phase): +$72.40
Open positions: 7 ($3,210)
USDC: $8,432 / MATIC: 12.4
Status: 🟢 LIVE
```

届かない / 数値が変な場合は §6.7 「Telegram 通知が来ない」。

### 2.3 異常を見つけたら

迷ったら **kill switch を ON** にする (Execute ページ右上トグル or Telegram で `/halt`)。  
止まっていれば資金は減らない。原因究明は止めてから。

---

## 3. 週次運用 (毎週月曜、約 30 分)

### 3.1 Phase 0 結果のレビュー

Strategy ページ → 「Recent Phase 0 runs」を確認。

- 直近 7 件すべて status=COMPLETED → 自動 cron が回ってる ✅
- FAILED が混じってる → Ops ページの Risk events / Recent jobs を確認

### 3.2 戦略マトリクスのチェック

Strategy ページ中央の **市場×戦略 heatmap** を見て:

- 全体的に緑 → 順調、現戦略を継続
- まだら模様 → 市場別に戦略を変えるべきかも (§3.5 参照)
- 赤が増えてきた → edge 劣化、Phase 0 で window を変えて再評価

### 3.3 Top 10 equity 確認

右下の Top 10 equity overlay で:

- 全 10 本がジリ上げ → 本物の edge
- 1〜2 本だけ突出、他は横ばい → 過学習リスク。並び替えを Sharpe に切替えてもう一度評価
- 全体が水平化 → edge 喪失。Watchlist 全入れ替えを検討

### 3.4 Watchlist の手動調整

`auto_rotate_enabled=true` なら自動だが、週次で人間も確認:

Execute ページ → Watchlist タブで:

- active=false な wallet が増えてないか確認
- 新規 wallet を手動で追加したい場合は address を入力 → Add

### 3.5 戦略パラメータ調整 (必要なら)

Ops ページ → Settings で以下を調整する場合は **理由を残してから** ボタン:

| 変更したくなる時 | キー | 例 |
|---|---|---|
| 1 trade あたりサイズを増やす | `copy_size_usdc` | `10` → `20` |
| copy 遅延を変える | `copy_delay_seconds` | `30` → `60` |
| 採用 wallet 数を増やす | `auto_rotate_top_n` | `15` → `25` |
| リスクを緩める (非推奨) | `halt_daily_pnl_pct` | `-5` → `-7` |

**変更は週次レビュー時のみ**。毎日いじると過剰反応で edge を壊す。

---

## 4. 月次運用 (毎月 1 回、約 1〜2 時間)

### 4.1 大きな数字の振り返り

Home ページのスクリーンショットを取り、前月と比較:

- 累積 PnL の伸び率
- 最大 DD
- 勝率
- Sharpe (Execute ページ上部)
- 月内の Telegram alert 件数

### 4.2 Phase 昇格判断

Execute ページの Rollout 進行ステッパーを確認。

**昇格条件 (5/7 → 7/7 になった時)** & **停止条件 (0 ヒット)** が揃ったら:

1. Telegram で `/status` を打って数値を再確認
2. Execute ページの「→ X 昇格」ボタンが活性化していれば押す (確認 prompt あり)
3. settings.rollout_phase が更新され、size limits が新フェーズの値に
4. Telegram に [Phase Promote] 通知が届く

**逆に降格すべき場合**: 停止条件 🛑 が頻発しているなら「← 降格」ボタンで前フェーズへ。降格は **恥ではなく安全策**。

### 4.3 撤退判断

以下のどれか 1 つでも該当したら撤退検討:

- 過去 1 ヶ月 連続赤字
- 最大 DD が許容範囲 (20%) を超えた
- backtest vs 実績の乖離が 40% 超
- Polymarket の流動性が極端に落ちた (24h vol 半減等)

撤退手順:
1. kill switch ON
2. 既存ポジションを Execute ページの手動 order タブで段階的に清算
3. Settings で `execution_enabled=false`
4. USDC を本ウォレットへ送金

### 4.4 secrets ローテーション (3 ヶ月に 1 回)

- CLOB API key を再発行 → Fly secrets 更新
- TRADER_PRIVATE_KEY は変更しないが、残高を増やす際は別途新ウォレットを検討

---

## 5. ページ別ガイド

### 5.1 Home ページ

12 のタイルで全体を俯瞰。各タイルの **ⓘ アイコンにホバー** すると詳細マニュアル。

- 上段 4 タイル: Wallet equity / Drawdown / Replay heatmap / Top10 戦略
- 中段 4 タイル: 市場×戦略 matrix / シグナル時間帯 / DD gauge / Latency
- 下段 4 タイル: Position exposure / Watchlist Top5 / 受信シグナル / Indexer lag

各タイルのタイトルをクリック → 詳細ページへ遷移。

### 5.2 Strategy ページ

**目的**: edge を検証する画面。週次レビューで開く。

- 上左: Phase 0 を実行 (手動 backtest トリガー)
- 上右: 5 つの KPI (sim 総数 / 黒字 / ベスト / ワースト / 中央値)
- 中左: マーケット一覧 (流動性スナップショット)
- 中右: 市場×戦略 heatmap (色付け指標切替可能)
- 下左: ROI × Sharpe scatter
- 下中: Top 10 equity overlay (並び替え可能)
- 下右: Recent Phase 0 runs

### 5.3 Execute ページ

**目的**: 実運用画面。日次で開く。

- 上: ステータスバー (USDC / MATIC / オープン / 今日 PnL / Sharpe / phase 累計 / Kill Switch)
- 中左: リスク (gauge + 4 progress)
- 中央: 実行レイヤ (Positions / Signals / Fills タブ)
- 中右: 管理オペレーション (Watchlist / Jobs / 手動 order タブ)
- 下左: Rollout 進行 (stepper + 4 ボタン)
- 下中: 昇格条件 7 件
- 下右: 停止条件 7 件

### 5.4 Ops ページ

**目的**: 障害対応 / 設定変更。何かおかしい時のみ開く。

- 上: ステータスバー (cursor / trades / dead-letters / last risk)
- 左: Build / Env / Cursors / Dead-letters
- 中: Settings overrides (JSON 編集)
- 右: Recent jobs / Risk events タブ

---

## 6. シナリオ別対処

### 6.1 「Kill switch が勝手に発動した」

1. Execute ページ → 停止条件 タブを開く
2. 🛑 が出てる行を確認 (どの条件にヒットしたか)
3. 原因別の対処:
   - **日次 PnL < -5%**: 既に halted。今日は諦めて明日まで放置。原因を `audit_log` で深掘り
   - **連敗 ≥ 5**: 戦略劣化中。Phase 0 を再実行して edge を再評価
   - **単一 market > 25%**: 既存ポジを手動で部分清算 → 自動的に解除
   - **indexer lag > 120s**: Ops ページで cursor を確認、Fly の indexer マシンを再起動
   - **USDC < $500**: 入金
   - **MATIC < 1.0**: MATIC 入金
4. 解決後、Execute ページ → 上部の Kill Switch トグルを LIVE に戻す
5. Telegram に "/resume" でも OK

### 6.2 「DD が許容を超えそう」

Home の Drawdown タイルでオレンジ線 (-15%) に近づいている:

- -10% 接近: kill switch は触らず、まず Strategy ページで edge 確認
- -12% 超: 自動で size 半減が走っている (連敗 size 半減ロジック)
- -15% 超: kill switch 自動 ON。手動 halt は不要

### 6.3 「シグナルが受信されない / 受信されてもスキップされる」

Execute ページ → シグナル タブを見る:

- **何も来ない** → indexer 停止疑い。§6.4 へ
- **❌ rejected** が多い → CLOB API key 不正、または流動性不足
- **⏭ skipped (リスク上限)** が多い → 設定が厳しすぎ。停止条件タブで何にヒットしてるか確認

### 6.4 「Indexer が止まった」

Home の Indexer lag タイル、または Ops の cursor で確認。

1. Fly.io ダッシュボード → Machines → `indexer` マシンの状態確認
2. state=stopped なら → Start ボタン
3. state=started でも更新止まってる → Restart
4. それでも復活しない → Ops の dead-letters を確認、Polygon RPC ノード切替を検討

### 6.5 「勝率が下がってきた」

- 1 日だけの低下 → 様子見 (ノイズの可能性)
- 3 日連続 → edge 劣化のサイン
- 1 週間連続 → Phase 0 を回して戦略再評価。Watchlist 大幅入れ替え

### 6.6 「USDC 残高が低くなった」

- $500 で停止条件ヒット → 取引所から Polygon USDC を入金
- 入金後、kill switch が自動解除されない場合は手動で LIVE に戻す

### 6.7 「Telegram 通知が来ない」

1. Telegram で bot に `/status` を送る → 返答あるか確認
2. 返答なし → BOT_TOKEN / CHAT_ID 確認、Fly secrets 再設定
3. 返答あるが朝のサマリーが来ない → scheduled_jobs テーブルで `nightly_summary` が enabled か確認

### 6.8 「新しい wallet を追加したい」

1. Execute ページ → Watchlist タブ
2. address (0x...) を入力 → note (任意) → Add
3. すぐ反映、次の signal から copy 対象に

または auto_rotate に任せる (毎晩自動)。

### 6.9 「特定の wallet を一時的に止めたい」

1. Execute ページ → Watchlist タブで該当 wallet を見つける
2. address をコピー
3. (現状は UI から direct toggle 未実装の場合) Ops ページ → Settings 経由で `auto_rotate_blacklist` キーに追加

### 6.10 「Phase 昇格条件を全部満たした」

Execute ページの Rollout 進行で:
- 昇格条件 7/7 (全 ✅)
- 停止条件 0 ヒット (全 🟢)

→ 「→ X 昇格」ボタンが活性化 (青)。

1. Telegram で `/status` 念のため確認
2. ボタンをクリック → 確認 dialog で OK
3. 自動で:
   - settings.rollout_phase 更新
   - copy_size_usdc が新フェーズのデフォルト値に
   - Telegram alert
   - audit_log に記録

**昇格後 1 週間は size を最小に保ち、慣らし運転** することを推奨。

---

## 7. リスク管理の基本

### 7.1 停止条件と上限の違い

- **停止条件 (halt)**: 1 件でもヒット → **全自動発注停止**。kill switch 自動 ON
- **上限 (limit)**: 1 件超過 → **新規発注 skip** (既存ポジは維持)

停止条件は致命的、上限は preventive。

### 7.2 Phase 別のリスク設定

| 設定 | Phase A (Paper) | Phase B (Micro) | Phase C (Small) | Phase D (Scale) |
|---|---|---|---|---|
| copy_size_usdc | 0 (paper) | 10 | 50 | 250 |
| limit_daily_trades | 1000 | 100 | 200 | 500 |
| halt_daily_pnl_pct | (n/a) | -5 | -5 | -7 |
| halt_weekly_pnl_pct | (n/a) | -8 | -8 | -10 |

Phase 昇格時、執行レイヤが自動で上記値に書き換える。

### 7.3 「リスクを緩めたい」誘惑への対応

実運用で勝率が下がると「halt 閾値を緩めれば...」と思いがち。**やってはいけない**。

正しい対応:
1. まず Strategy ページで edge を再検証
2. edge が消えてるなら戦略変更 (delay 変える、size 変える、wallet 入れ替える)
3. それでも結果が悪ければ降格 or 撤退

閾値を緩めるのは「過去の自分のリスク評価が間違っていた」と確信できる時だけ。

### 7.4 「自律」と「監視」のバランス

完全に自律ではない。必須の人間判断:
- 週次レビューでの Watchlist 確認
- 月次の Phase 昇格判断
- Telegram alert への即応 (5 分以内目標)
- 撤退判断

放置可能な範囲:
- 日々の signal 受信 → 発注
- 毎晩の Phase 0 自動再評価
- 自動 watchlist promotion/demotion

---

## 8. 用語集

| 用語 | 意味 |
|---|---|
| Phase 0 | オフライン edge 検証。実発注なし、過去データから「儲かるか」をシミュ |
| Phase A〜D | 段階的ロールアウト。Paper → Micro → Small → Scale |
| Copy trade | 別のウォレットの約定を遅延付きで真似する取引 |
| Edge | 期待値プラスの優位性。これが無い copy は損失 |
| Signal | copy 元 wallet の約定検知イベント |
| Drawdown (DD) | 過去ピークからの落ち込み % |
| Sharpe ratio | (リターン − 無リスク利率) / 標準偏差。リスク調整後リターン |
| Slippage | 期待価格と実約定価格の差 |
| Kill switch | 全自動発注を即停止するマスタースイッチ |
| CLOB | Central Limit Order Book。Polymarket の発注インターフェイス |
| Indexer | Polygon ブロックチェーンを監視して trade を DB に取り込むプロセス |
| Dead-letter | RPC エラーで処理失敗した chunk。後で再試行する用 |
| Cursor | indexer の進捗。「ここまで処理した」記録 |
| Backfill | 過去データを取り込む処理 |
| Resolve | 予測市場が確定して 0 or 1 USDC に決まること |
| Gamma API | Polymarket の市場メタデータ + 解決結果 API |

---

## 9. FAQ

### Q1. 初日からいくら入金すべき?

A. **$100** から。Phase A (Paper) は実発注しないので残高無関係だが、Phase B 移行直後は最小ロット ($10/trade) で月 $100 程度の動き。検証用には $100 で十分。

### Q2. どれくらいで収益が出ますか?

A. **Phase 0 で +ROI が出るまで** + **Phase A〜B 検証 (約 2 ヶ月)** が前提。最短でも 3 ヶ月、現実的には 6 ヶ月。「確実に」「短期で」を期待するアプリではない。

### Q3. Polymarket の手数料は?

A. taker 1〜2% 程度。Phase 0 backtest にも反映済 (`fee_calc.py`)。

### Q4. 複数の wallet を copy しても良い?

A. 推奨。1 つだけだとそのウォレットが劣化したら即終了。15 件くらい分散すると安定。

### Q5. 損失が出たら税金は?

A. 日本居住者は雑所得。Polygon 上の transactions を CSV エクスポートして年末に集計 (Etherscan API 等で自動化可)。本マニュアルの範囲外。

### Q6. 「自律運用」は週何時間?

A. 日次 5 分 + 週次 30 分 + 月次 1〜2h = **月 5〜6 時間**。Telegram alert への即応含む。

### Q7. 24 時間 365 日稼働しないとダメ?

A. Polymarket は土日も米国時間も動く。Fly.io 上で稼働してれば自動。停電 / メンテで停止しても kill switch が自動 ON になるので致命傷にはならない。

### Q8. backtest と実績の乖離が出る理由は?

A. (1) slippage、(2) Polymarket の流動性不足、(3) 自分の発注で市場を動かしてしまう、(4) edge の劣化、のどれか。20% 未満なら許容、30% 超えたら警戒、40% で撤退。

---

## 10. 緊急時対応

### 10.1 「資金が急減している、止めたい」

1. **Telegram で `/halt`** (最短)
2. または Execute ページの Kill Switch トグル ON
3. または Fly.io ダッシュボードで `worker` マシンを Stop

どれか 1 つで全発注停止。

### 10.2 「kill switch を ON にしても発注が続いている」

worker が暴走している可能性 (シグナル受信ループのバグ)。

1. Fly.io ダッシュボード → `worker` マシン → Stop
2. 復旧は Ops ページ + Telegram で原因究明後

### 10.3 「Web UI に繋がらない」

1. ブラウザを変える / シークレットウィンドウ
2. それでもダメ → Fly.io ダッシュボード → `web` マシン状態確認
3. state=stopped → Start
4. それでもダメ → Telegram で `/status` (bot は別マシンなので生きてる可能性)

### 10.4 「秘密鍵を漏らしてしまった」

1. **即 Telegram で `/halt`**
2. 取引所アプリで新ウォレット作成、現ウォレットの残額を **即出金**
3. Fly secrets で TRADER_PRIVATE_KEY / TRADER_ADDRESS を新ウォレットに置換
4. Polymarket で CLOB API key を再発行 (古いキーで発注されないため)
5. Fly secrets 更新 → 再デプロイ

### 10.5 連絡先

- GitHub Issue: https://github.com/kazgamada/prediction-market-analysis/issues
- Telegram bot 経由で `/status` 等のヘルスチェック

---

## 11. このマニュアルの更新

- 新機能追加時: 本書の該当章を **同時更新**
- 運用中の発見 / 改善 Tips: §6 (シナリオ別) に追記
- ユーザー (= あなた) 自身のメモ: `docs/manual/PERSONAL_NOTES.md` (gitignore 対象、本リポには含めない)
