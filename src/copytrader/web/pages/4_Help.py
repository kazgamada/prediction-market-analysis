"""Help — abbreviation glossary callable from UI.

Mirror of USER_MANUAL.md §0.5 略号・専門用語ミニ早見表.
更新時は両方を同期させること (本ページと docs/manual/USER_MANUAL.md)。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from copytrader.web.auth import require_password
from copytrader.web.theme import (
    ACCENT_CYAN, ACCENT_GREEN, ACCENT_RED, ACCENT_YELLOW,
    LIVE_LAYOUT, LIVE_PALETTE, STATIC_LAYOUT, STATIC_PALETTE,
    TILE_BG, inject_theme,
)

st.set_page_config(page_title="Help", layout="wide",
                   initial_sidebar_state="collapsed")
require_password()

inject_theme()

st.markdown(
    "# Help — 略号・専門用語一覧　"
    "<small style='font-size:0.7rem;color:#888;'>UI 上の略語をここで引ける</small>",
    unsafe_allow_html=True,
)

st.markdown(
    "アプリ画面・本マニュアルで頻出する略号を 9 カテゴリで網羅。"
    "**略号 / フルスペル / 日本語 / 補足** の 4 列。",
)

GLOSSARY = {
    "💰 お金": [
        ("PnL", "Profit and Loss",
         "損益", "日次 PnL = 今日の利益/損失。Profit (利益) と Loss (損失) の合算"),
        ("DD", "Drawdown",
         "ドローダウン (最高益からの下落%)",
         "例: ピーク $1,000 → $900 に下落 = DD -10%"),
        ("ROI", "Return On Investment",
         "投資収益率 (%)", "利益 ÷ 元本"),
        ("Sharpe", "Sharpe Ratio",
         "シャープ・レシオ (リスク調整後リターン)",
         "(リターン − 無リスク利率) ÷ 標準偏差。> 1.0 で優秀。命名: W.F. Sharpe"),
        ("USDC", "USD Coin",
         "ユーエスディーコイン (米ドル建てステーブルコイン)",
         "1 USDC ≈ 1 米ドル。Circle 社発行"),
        ("MATIC", "(固有名詞 - Polygon Network token)",
         "マティック (Polygon ガス代用トークン)",
         "発注ごとに微量消費"),
        ("USD", "United States Dollar",
         "米ドル", "$ 記号で表記"),
        ("bps", "basis points",
         "ベーシスポイント", "1 bps = 0.01%。100 bps = 1%"),
    ],
    "📈 取引": [
        ("edge", "trading edge",
         "(取引上の) 優位性",
         "期待値プラスの優位性。これが無い copy は損失要因"),
        ("signal", "trading signal",
         "取引シグナル", "コピー元 wallet の約定検知イベント"),
        ("copy trade", "copy trade / copy trading",
         "コピー取引",
         "別ウォレットの約定を遅延付きで真似する取引手法"),
        ("slippage", "price slippage",
         "スリッページ (価格のずれ)",
         "想定価格と実約定価格のずれ %。delay が長いほど大きい"),
        ("fill", "order fill",
         "フィル (約定)", "発注が市場と成立。partial fill = 部分約定"),
        ("delay", "execution delay",
         "遅延 (発注までの待ち時間, 秒)",
         "signal 検知から発注までの間隔"),
        ("halt", "trading halt",
         "取引停止", "全自動発注の停止状態。kill switch ON と同義"),
        ("kill switch", "emergency kill switch",
         "緊急停止スイッチ", "全発注を即止めるマスタースイッチ"),
        ("backtest", "backtesting",
         "バックテスト (過去データ検証)",
         "過去データで戦略を仮想実行"),
        ("paper trading", "paper trading",
         "ペーパートレード (仮想取引)",
         "実発注せずシグナル受信のみ。Phase A で実施"),
        ("wallet", "wallet",
         "ウォレット (口座)", "Polygon 上のアカウント。0x... のアドレス"),
        ("watchlist", "watchlist",
         "ウォッチリスト (監視対象一覧)",
         "copy 対象として登録した wallet の集合"),
        ("smart money", "smart money",
         "スマートマネー (上手な投資家)",
         "過去成績の良い wallet。copy 対象候補"),
    ],
    "⚙️ システム": [
        ("indexer", "blockchain event indexer",
         "ブロックチェーン イベント インデクサー",
         "ブロックチェーンを監視して取引データを DB に取り込む裏方"),
        ("cursor", "indexer cursor",
         "(インデクサー) 進捗カーソル",
         "「ここまで処理した」記録。ブロック番号で表される"),
        ("lag", "indexer lag",
         "遅れ秒数", "最新ブロックから何秒遅れて処理しているか"),
        ("CLOB", "Central Limit Order Book",
         "セントラル・リミット・オーダー・ブック",
         "Polymarket の取引所。注文板 + マッチングエンジン"),
        ("RPC", "Remote Procedure Call",
         "リモート・プロシージャ・コール",
         "ブロックチェーンノードへのアクセス方式"),
        ("WS", "WebSocket",
         "ウェブソケット (双方向リアルタイム通信)",
         "RPC の一種。リアルタイム購読向け"),
        ("HTTP", "HyperText Transfer Protocol",
         "ハイパーテキスト転送プロトコル", "Web の標準通信"),
        ("API", "Application Programming Interface",
         "アプリケーション・プログラミング・インターフェース",
         "外部サービスへの呼び出し窓口"),
        ("DB", "Database",
         "データベース", "本プロジェクトでは PostgreSQL"),
        ("dead-letter", "dead-letter queue (DLQ)",
         "デッドレターキュー",
         "処理失敗した RPC chunk を後で再試行するための一時保管"),
        ("chunk", "data chunk",
         "チャンク (データの塊)",
         "indexer が一度に処理するブロック範囲 (デフォルト 1000)"),
        ("migration", "database migration",
         "DB マイグレーション", "テーブル構造変更を Alembic で管理"),
        ("idempotent", "idempotent operation",
         "冪等 (べきとう)",
         "同じ操作を何度しても結果が変わらない性質。二重発注防止"),
    ],
    "🎚 Phase": [
        ("Phase 0", "Phase Zero",
         "オフライン edge 検証",
         "実発注なし、過去データで「儲かるか」をシミュ"),
        ("Phase A", "Phase A — Paper Trading",
         "ペーパートレード (4 週)",
         "実発注なし、シグナルだけ受信して仮想発注 / size $0"),
        ("Phase B", "Phase B — Micro Live",
         "マイクロ実発注 (4 週)",
         "$10/trade で本物の発注、検証スタート"),
        ("Phase C", "Phase C — Small Live",
         "スモール実発注 (8 週)",
         "$50/trade、本格運用準備"),
        ("Phase D", "Phase D — Scale",
         "スケール本番 (継続)", "$250/trade〜、本番稼働"),
    ],
    "🛒 発注": [
        ("size", "trade size",
         "サイズ (1 取引あたりの金額)", "単位 USDC"),
        ("BUY / B", "BUY (buy order)",
         "買い注文", "「Yes」または「対象が起きる」に賭ける"),
        ("SELL / S", "SELL (sell order)",
         "売り注文", "「No」または「対象が起きない」に賭ける"),
        ("TIF", "Time In Force",
         "注文有効期限種別", "注文がいつまで生きるかの設定"),
        ("GTC", "Good Till Cancelled",
         "キャンセルまで有効", "通常はこれを使う"),
        ("IOC", "Immediate Or Cancel",
         "即時 or キャンセル",
         "即約定可能な部分だけ約定、残りはキャンセル"),
        ("FOK", "Fill Or Kill",
         "全量 or 全キャンセル", "全量約定できないなら全キャンセル"),
        ("p50", "50th percentile (median)",
         "中央値", "データを並べて真ん中の値"),
        ("p95", "95th percentile",
         "95 パーセンタイル", "下位 95% を含む値。外れ値の影響"),
        ("0x...", "hexadecimal prefix",
         "ウォレットアドレス",
         "Polygon/Ethereum 共通。'0x' + 16進40文字"),
        ("token_id", "Polymarket token ID",
         "トークン ID", "Polymarket の各 outcome の数値識別子"),
        ("market", "prediction market",
         "予測市場",
         "1 件の予測対象 (例: 米大統領 2028 — Dem)"),
        ("outcome", "market outcome",
         "結果 (Yes / No)", "予測市場が最終的にどちらに決着したか"),
        ("resolve", "market resolution",
         "市場解決 (確定)", "予測市場が確定して 0 or 1 USDC に"),
        ("liquidity", "market liquidity",
         "流動性", "取引量。低いと slippage 悪化"),
        ("OI", "Open Interest",
         "未決済建玉総額", "その市場に建っている総 USDC"),
        ("vol", "volume",
         "出来高", "一定期間の取引総額。24h vol = 24 時間出来高"),
    ],
    "🚦 アイコン": [
        ("✅", "filled", "約定成功", "シグナルが市場と成立"),
        ("⏳", "pending", "待機中", "delay 経過中"),
        ("❌", "rejected", "発注失敗", "CLOB rejected"),
        ("⏭", "skipped", "スキップ", "リスク上限ヒット"),
        ("🟢", "live", "正常稼働中", "LIVE 状態"),
        ("🛑", "halted", "全停止中", "HALTED 状態"),
        ("⚠", "warning", "警告", "条件超過"),
        ("●", "current", "現在", "ステッパー内の現在位置"),
    ],
    "⛓ ブロックチェーン": [
        ("Polygon", "Polygon PoS",
         "ポリゴン (Ethereum レイヤー2)",
         "Polymarket はここで動いている"),
        ("Ethereum", "Ethereum",
         "イーサリアム", "大本のブロックチェーン"),
        ("PoS", "Proof of Stake",
         "プルーフ・オブ・ステーク (権威証明)",
         "Polygon の合意アルゴリズム"),
        ("gas", "gas fee",
         "ガス代 (取引手数料)",
         "tx 1 件あたりの計算料金。MATIC で支払う"),
        ("block", "block",
         "ブロック",
         "ブロックチェーンの記録単位。Polygon は約 2 秒に 1 ブロック"),
        ("tx", "transaction",
         "トランザクション (取引)", "ブロックチェーン上の 1 件の処理"),
        ("OrderFilled", "OrderFilled event",
         "(CTF Exchange の) 約定イベント", "Polymarket の約定通知"),
        ("CTF", "Conditional Token Framework",
         "コンディショナル・トークン・フレームワーク",
         "Polymarket の取引対象トークン規格"),
    ],
    "🛠 DevOps": [
        ("CI", "Continuous Integration",
         "継続的統合", "テスト自動実行 (GitHub Actions)"),
        ("CD", "Continuous Deployment",
         "継続的デプロイ", "自動デプロイ"),
        ("PR", "Pull Request",
         "プルリクエスト", "コード変更の提案単位"),
        ("CLI", "Command Line Interface",
         "コマンドラインインターフェース", "ターミナルでの操作"),
        ("SSH", "Secure Shell",
         "セキュアシェル", "暗号化通信プロトコル"),
        ("UI", "User Interface", "ユーザーインターフェース", "画面"),
        ("e2e", "end-to-end",
         "エンド・ツー・エンド", "全体通しのテスト"),
        ("DoD", "Definition of Done",
         "完了の定義", "「終わった」と判断する基準"),
        ("JST", "Japan Standard Time",
         "日本標準時", "UTC+9"),
        ("UTC", "Coordinated Universal Time",
         "協定世界時", "世界標準時刻、時差なし"),
        ("JSON", "JavaScript Object Notation",
         "ジェイソン", "データ形式"),
        ("SQL", "Structured Query Language",
         "エスキューエル", "DB の操作言語"),
        ("DDL", "Data Definition Language",
         "データ定義言語", "SQL のうち CREATE TABLE 等"),
    ],
}

search = st.text_input("🔍 検索 (略号 / 英語 / 日本語、部分一致)",
                       placeholder="例: PnL、Sharpe、シグナル、CLOB").strip().lower()

SETUP_TAB_LABEL = "🚀 初期設定"

SETUP_STEPS = [
    (
        "Step 0 — Deploy 検証 (今日〜数日)",
        """
**目的**: 全 17 PR の deploy が走り、システムが裏で動き始めている確認。

**チェックリスト**:
- ✅ GitHub Actions の `Deploy to Fly.io #N` が ✅
- ✅ Ops ページの `git_sha` が最新
- ✅ **migration が走った** (Ops で cursors / dead-letters が表示される)
- ✅ **scheduler が動いている** (Ops → Recent jobs に `gamma_resolve_fetch` が出現)
- ✅ **indexer 稼働** (cursor block が更新され続け、trades 1h > 0)
- ✅ **risk evaluator 動作** (Execute のリスクゲージが正常表示)
- ✅ **Home/Strategy/Execute/Ops** が全部開ける
""",
    ),
    (
        "Step 1 — 外部準備 (1〜2 週間)",
        """
**目的**: 実発注に必要な外部サービスの登録 + Fly secrets 投入。

**必要なもの**:
1. **Polymarket CLOB API key** — https://polymarket.com → Settings → Developer → API Keys。3 つの値 (key / secret / passphrase) 取得
2. **Polygon トレーダーウォレット** — MetaMask で **新規ウォレット作成** (生活用と分離)
   - 秘密鍵をエクスポート (`TRADER_PRIVATE_KEY`)
   - 公開アドレス (`TRADER_ADDRESS`)
3. **USDC + MATIC 入金** — 取引所から Polygon ネットワークでウォレットへ:
   - USDC: $100 (Phase B 検証用に $200 推奨)
   - MATIC: $5 程度
4. **Telegram bot 作成** — @BotFather に `/newbot` → token 取得
   - `https://api.telegram.org/bot<TOKEN>/getUpdates` で chat_id 取得
   - 自分の user_id を `TELEGRAM_ADMIN_USER_IDS` に

**Fly secrets 投入** (Fly.io ダッシュボード → Secrets):
```
CLOB_API_KEY, CLOB_API_SECRET, CLOB_API_PASSPHRASE
TRADER_PRIVATE_KEY, TRADER_ADDRESS
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ADMIN_USER_IDS
```

保存すると Fly が自動再起動。

**動作確認**:
- Telegram で `/status` → 返答あり → bot 接続 OK
- Ops ページで cursor / trades が引き続き動いている
""",
    ),
    (
        "Step 2 — edge 検証 (2〜4 週間)",
        """
**目的**: Phase 0 を毎晩自動実行し、edge が **本当に存在するか** を見極める。撤退判断もここで。

**何もしなくても自動で動くもの**:
- 毎晩 18:00 UTC `nightly_phase0` job が走る
- 毎時 `gamma_resolve_fetch` で resolved market を取り込む
- 毎晩 19:00 `watchlist_rotate` で auto promote/demote

**初日にやること**:
1. Strategy ページで `Run` を 1 回手動実行 (window=30, top_n=10)
2. 数分〜十数分待って status=SUCCEEDED 確認
3. Strategy ページの KPI が表示される

**毎日チェック (3 分)**:
- Strategy ページの KPI:
  - **黒字率** > 50% か (赤いほど edge 薄い)
  - **中央値 ROI** > +3% か
  - **ベスト** が突出してないか (= 過学習サイン)

**2〜4 週間後の判断**:

| 状況 | 判断 |
|---|---|
| 中央値 ROI > +5%、黒字率 > 60%、Top10 全部右肩上がり | ✅ **Phase A へ進む** |
| 中央値 ROI 0〜+3%、ばらつき大 | ⚠ もう 2 週観察 |
| 中央値 ROI < 0 が 2 週続く | 🛑 **撤退**。実発注しない |

**この時点で watchlist が空なら**: Strategy の上位 wallet 一覧から 10〜15 件を Execute → Watchlist で手動登録。
""",
    ),
    (
        "Step A — Phase A Paper Trading ($0/trade, 4 週間)",
        """
**目的**: 実発注なしで「もし発注してたら」のシミュレーション。

**準備**:
1. Ops → Settings で `execution_enabled = false` を確認 (デフォルト)
2. Execute → Watchlist に **active wallet 10〜15 件**

**毎日 (5 分)**:
- Home の KPI を確認 (Indexer lag、受信シグナル、DD gauge)
- Execute → シグナル tab: watchlist の wallet が約定すると signal 行が出現
  - `⏭ skipped` reason="paper" になる
- Telegram の朝サマリー (9:00 JST) を確認

**週次 (30 分)**:
- Strategy ページで Phase 0 結果を見る
- backtest predicted vs paper-mode signals 件数を比較
- latency p95 を確認

**4 週間後の昇格条件**:
- 経過 ≥ 28 日
- 累積 paper ROI ≥ +3%
- 最大 DD ≤ -8%
- 勝率 ≥ 52%
- backtest 乖離 ≤ 20%
- Latency p95 ≤ 3000ms
- **kill switch を 1 回手動 ON/OFF してテスト**
""",
    ),
    (
        "Step B — Phase B Micro Live ($10/trade, 4 週間)",
        """
**目的**: 本物のお金で動かす最初のフェーズ。

**昇格手順**:
1. Execute ページで昇格条件全 ✅ + 停止条件 0 ヒット 確認
2. Telegram `/status` で念のため確認
3. 「→ B 昇格」ボタンクリック
4. 自動的に `execution_enabled=true`, `copy_size_usdc=10`, Telegram 通知

**運用 4 週間**:
- 日次: Home + Telegram (3 分)
- 週次: Strategy + Execute レビュー (30 分)
- **異常時**: Telegram `/halt` (即停止)

**典型的なトラブルと対処**:

| 症状 | 対処 |
|---|---|
| latency p95 > 3 秒 | RPC ノード切替 |
| slippage > 1% 多発 | `limit_slippage_bps` を 100→50 に絞る |
| Watchlist wallet 突然パフォーマンス低下 | auto_rotate が deactivate するのを待つ |
| 連敗 3 回 | 自動 size 半減 ($10→$5)、24h でリセット |
| dead-letters > 100 件 | RPC 不調、Ops で確認 |
| kill switch 発動 | 停止条件タブで原因確認、解決後手動 OFF |

**昇格条件 (Phase C へ)**:
- B で 28 日以上稼働
- 累計 ROI ≥ +3% (paper 予測の 70% 以上)
- 最大 DD ≤ 8%
- 勝率 ≥ 52%
""",
    ),
    (
        "Step C — Phase C Small Live ($50/trade, 8 週間)",
        """
**目的**: 本格運用へのスケールアップ。月次レビュー導入。

**昇格時**:
- USDC を **$500 以上** に入金
- 「→ C 昇格」ボタン → `copy_size_usdc = 50` 自動更新

**運用 8 週間**:
- 日次 / 週次は変わらず
- **月次レビュー (1〜2 時間) を追加**:
  - 月初に Home / Strategy / Execute のスクショ保存
  - 前月との比較
  - watchlist の入れ替え方針見直し
  - settings パラメータ調整可否判断

**昇格条件 (Phase D へ)**:
- C で 56 日以上稼働 (約 2 ヶ月)
- 累計 ROI ≥ +8%
- 月次 Sharpe ≥ 0.8
- 最大 DD ≤ 10%
""",
    ),
    (
        "Step D — Phase D Scale ($250+/trade, 継続)",
        """
**目的**: フル運用。資金を 5% ずつ拡大しながら継続。

**昇格時**:
- USDC を **$2,500+** に入金
- `copy_size_usdc = 250`
- 「→ D 昇格」

**運用ルール**:
- 日次 / 週次 / 月次を継続
- **四半期 (3 ヶ月) ごと**:
  - secrets ローテーション (CLOB key 再発行)
  - 戦略の根本見直し (新しい wallet 母集団、新しい delay 設定)
- **常時**:
  - `copy_size_usdc` は **資金の 5% を超えない** (Kelly 上限)
  - 残高が増えたら段階的に size 拡大 (例: $1k→50 / $5k→250 / $20k→1000)

**撤退判定 (継続評価)**:
- 任意の 1 ヶ月で連続赤字 → 警戒
- 任意の 1 ヶ月で DD > 15% → 一時 Halt + 原因調査
- 3 ヶ月連続赤字 → Phase C へ降格 or 撤退
""",
    ),
    (
        "⚠ やってはいけないこと",
        """
| やってはいけない | なぜ |
|---|---|
| 停止条件の閾値を緩める | 過去の自分の安全設定を裏切る = 破産への直行便 |
| size を急に 2x にする | リスクが指数的に増える。**5% ずつ** |
| kill switch 中に手動発注を乱発 | 自動システムの判断と矛盾 |
| Phase A をスキップして B へ直行 | backtest と実発注の乖離を見ずに本番 |
| Watchlist を 1 件に絞る | 単一 wallet 劣化で即終了 |
| 「もうそろそろ大丈夫」で監視を止める | 暴落は監視してない時に来る |
| 秘密鍵を生活用ウォレットと共有 | 漏洩時の被害が連鎖 |
| settings.execution_enabled を Step A 前に true にする | paper 検証を飛ばして本番 |
""",
    ),
    (
        "🎯 今すぐの 3 アクション",
        """
**deploy が green なら、今日中にこの 3 つを終わらせる**:

1. **Step 0 確認**: GitHub Actions で Deploy が green、Ops で git_sha が最新を確認
2. **Step 1 開始**: Polymarket CLOB key を取得して Fly secrets に投入 (15 分)
3. **Step 2 起動**: Strategy ページで `Run` を 1 回手動実行 → 結果を見る

**3 つすべて今日中に終わる作業です。**

完了したら 2 週間の検証期間 (Step 2)、その間アプリは自動で回ります。
2 週間後に edge が確認できれば Phase A → B → C → D と段階的に進む。

**正式運用 (Phase D) までの想定期間: 4.5〜6 ヶ月**
""",
    ),
]

tab_labels = [SETUP_TAB_LABEL] + list(GLOSSARY.keys())
tabs = st.tabs(tab_labels)

# Setup tab (first)
with tabs[0]:
    st.markdown(
        "**Phase 0 (実装完了) → Phase A → B → C → D (正式運用) の段階別ロードマップ。**"
        "各ステップを expander で展開して詳細確認。",
    )
    if search:
        # Filter steps by title or body keyword match
        matched = [
            (t, b) for t, b in SETUP_STEPS
            if search in t.lower() or search in b.lower()
        ]
        if not matched:
            st.info(f"「{search}」に該当する setup ステップはありません。")
        for title, body in matched:
            with st.expander(title, expanded=True):
                st.markdown(body)
    else:
        for i, (title, body) in enumerate(SETUP_STEPS):
            # First 2 steps + immediate action expanded by default
            expanded = (
                title.startswith("Step 0")
                or title.startswith("Step 1")
                or title.startswith("🎯")
            )
            with st.expander(title, expanded=expanded):
                st.markdown(body)

# Glossary tabs (rest)
for (label, items), tab in zip(GLOSSARY.items(), tabs[1:], strict=False):
    with tab:
        rows = items
        if search:
            rows = [
                r for r in items
                if any(search in str(c).lower() for c in r)
            ]
        if not rows:
            st.info(f"「{search}」に該当する用語はこのカテゴリにはありません。")
            continue
        df = pd.DataFrame(rows,
                          columns=["略号 / 用語", "フルスペル", "日本語", "補足"])
        st.dataframe(df, use_container_width=True, hide_index=True, height=420)

if search:
    total_hits = sum(
        1 for items in GLOSSARY.values() for r in items
        if any(search in str(c).lower() for c in r)
    )
    st.caption(f"「{search}」: 全カテゴリで {total_hits} 件ヒット")

st.divider()
st.markdown(
    "### 詳しい資料  \n"
    "- [📖 USER_MANUAL.md (運用マニュアル全文)]"
    "(https://github.com/kazgamada/prediction-market-analysis/blob/main/docs/manual/USER_MANUAL.md)  \n"
    "- [📐 PHASE1_LIVE_EXECUTION.md (実装要件定義書)]"
    "(https://github.com/kazgamada/prediction-market-analysis/blob/main/docs/requirements/PHASE1_LIVE_EXECUTION.md)  \n"
    "- [🔧 INITIAL_SEED.sql (初期 settings 投入 SQL)]"
    "(https://github.com/kazgamada/prediction-market-analysis/blob/main/docs/manual/INITIAL_SEED.sql)  \n"
    "- [📚 REBUILD.md (元の要件定義)]"
    "(https://github.com/kazgamada/prediction-market-analysis/blob/main/docs/requirements/REBUILD.md)"
)

st.caption(
    "本ページの内容は USER_MANUAL.md §0.5 と完全同期。"
    "更新時は両方の修正が必要。"
)
