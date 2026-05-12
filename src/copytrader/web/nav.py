"""サイドバーの自動ナビ (英語メニュー) にホバー説明を付けるヘルパー。

Streamlit が `app.py` と `pages/*.py` のファイル名から自動生成する
サイドバーリンク (Status / Watchlist / ...) に、ホバー時の小窓 tooltip
を JS 注入で追加する。`<a>` の `title` 属性なのでマウスを外せば消える。

合わせて、各ページから到達するこの関数で `start_background_warmer()` を
呼び出し、ページ表示用キャッシュを温める daemon thread を起動する。
"""

from __future__ import annotations

import json

import streamlit.components.v1 as components

from copytrader.web.cache import start_background_catchup, start_background_warmer

_TIPS: dict[str, str] = {
    "app": "ホーム — シークレット設定の状態と Phase ガイド。最初に開く画面。",
    "Status": "現在の取り込み件数・シグナル・発注・オープンポジション・直近のリスクイベント一覧。Backfill 進捗もここで見える。",
    "Watchlist": "監視対象ウォレットの追加・削除。ここに入ったウォレットの取引が monitor で追跡される。",
    "Rank": "過去 trade からウォレット別 PnL / 勝率を集計し上位を抽出。Top N を watchlist に自動投入できる。",
    "Replay": "選択ウォレットの過去シグナルを遅延別に再現発注し PnL を比較。Phase 0 の edge 検証用。",
    "Inspect": "1 ウォレットを深掘り。トークン別の取引数・PnL・ネット保有量・最終取引時刻。",
    "Actions": "Backfill / Markets sync / Reconcile / Poll など、ワンショットの保守運用ジョブ。",
}


def render_sidebar_menu_help() -> None:
    """サイドバー自動ナビの各リンクにホバー説明を注入する。各ページから呼ぶ。

    副作用としてページキャッシュ warmer を 1 度だけ起動する。
    """
    start_background_warmer()
    start_background_catchup()
    payload = json.dumps(_TIPS, ensure_ascii=False)
    components.html(
        f"""
<script>
(function() {{
  const tips = {payload};
  function apply() {{
    try {{
      const doc = window.parent.document;
      const links = doc.querySelectorAll('[data-testid="stSidebarNav"] a, [data-testid="stSidebarNavItems"] a');
      links.forEach(function(a) {{
        const txt = (a.textContent || '').trim();
        const tip = tips[txt] || tips[txt.toLowerCase()];
        if (tip) {{
          a.setAttribute('title', tip);
          a.style.cursor = 'help';
        }}
      }});
    }} catch (e) {{ /* cross-frame access guarded */ }}
  }}
  apply();
  try {{
    const obs = new MutationObserver(apply);
    obs.observe(window.parent.document.body, {{ childList: true, subtree: true }});
  }} catch (e) {{}}
}})();
</script>
""",
        height=0,
    )
