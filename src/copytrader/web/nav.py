"""サイドバーに各ページのメニュー一覧を表示するヘルパー。

メニュー名のみを縦に並べ、ホバー時に説明をネイティブブラウザの
ツールチップ (`<span title="…">`) で表示する。マウスを外すと消える。
"""

from __future__ import annotations

from html import escape

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
    """サイドバーにメニュー一覧 (ホバーで説明表示) を出す。各ページから呼ぶ。"""
    items = "".join(
        '<li style="margin: 2px 0;">'
        f'<span title="{escape(desc, quote=True)}" '
        'style="border-bottom: 1px dotted #888; cursor: help;">'
        f'{escape(label)}'
        '</span>'
        '</li>'
        for _, label, desc in _MENU
    )
    html = (
        '<div style="font-size: 0.9rem;">'
        '<div style="font-weight: 600; margin-bottom: 4px;">メニュー</div>'
        f'<ul style="padding-left: 1.1em; margin: 0;">{items}</ul>'
        '<div style="color: #888; font-size: 0.8rem; margin-top: 6px;">'
        '名前にカーソルを当てると説明が表示されます'
        '</div>'
        '</div>'
    )
    with st.sidebar:
        st.markdown(html, unsafe_allow_html=True)
