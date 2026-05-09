"""サイドバーに各ページの解説 (メニュー説明) を表示するヘルパー。

Streamlit の自動ナビゲーションはファイル名から生成されるリンクのみで、
ホバー解説を持たない。代替として、サイドバー直下に各ページの 1 行解説を
出して "メニューにホバーで解説" の代わりとする。
"""

from __future__ import annotations

import streamlit as st

_MENU: tuple[tuple[str, str, str], ...] = (
    ("Home", "ホーム",
     "シークレット設定の状態と Phase ガイド。最初に開く画面。"),
    ("Status", "ステータス",
     "現在の取り込み件数・シグナル・発注・オープンポジション・直近のリスクイベント一覧。"),
    ("Watchlist", "ウォッチリスト",
     "監視対象ウォレットの追加・削除。ここに入ったウォレットの取引が monitor で追跡される。"),
    ("Rank", "ランキング",
     "過去 trade からウォレット別 PnL/勝率を集計し上位を抽出。Top N を watchlist に自動投入できる。"),
    ("Replay", "リプレイ検証",
     "選択ウォレットの過去シグナルを遅延別に再現発注し PnL を比較。Phase 0 の edge 検証用。"),
    ("Inspect", "ウォレット詳細",
     "1 ウォレットを深掘り。トークン別の取引数・PnL・ネット保有量・最終取引時刻。"),
    ("Actions", "アクション",
     "Backfill / Markets sync / Reconcile / Poll など、ワンショットの保守運用ジョブ。"),
)


def render_sidebar_menu_help() -> None:
    """サイドバーにメニュー解説を表示する。各ページから呼び出す。"""
    with st.sidebar:
        st.markdown("### メニュー解説")
        for _, label, desc in _MENU:
            st.markdown(f"**{label}** — {desc}")
        st.caption(
            "各ページ内のフォーム項目・ボタンにマウスを合わせると、"
            "個別のヘルプ (?) が表示されます。"
        )
