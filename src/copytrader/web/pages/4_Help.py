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

tab_labels = list(GLOSSARY.keys())
tabs = st.tabs(tab_labels)

for (label, items), tab in zip(GLOSSARY.items(), tabs, strict=False):
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
