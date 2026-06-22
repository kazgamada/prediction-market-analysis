"""管理者 > AI設定（OpenRouter API キー入力 + モデル選択 + コスト集計）。

AUDIT.md 共通機能要件（AIモデル選択）に対応する管理者専用ページ。
画面構成は上から:
  1. OpenRouter API キー入力フォーム（モデル選択窓のすぐ上）
  2. モデル選択 UI（プルダウン + 選択中バッジ + 単価表示）
  3. コスト集計（過去30日: USD / 円換算・モデル別内訳）
"""
from __future__ import annotations

from decimal import Decimal

import streamlit as st

from copytrader.ai.app_settings import (
    OPENROUTER_API_KEY,
    mask_secret,
    masked_view,
    set_app_setting,
)
from copytrader.ai.openrouter import (
    FALLBACK_MODELS,
    fetch_models,
    get_selected_config,
    save_selected_config,
)
from copytrader.ai.usage import cost_summary
from copytrader.config import settings
from copytrader.db.engine import get_session
from copytrader.db.models import AdminAuditLog
from copytrader.web.auth import current_user, require_admin
from copytrader.web.sidebar import render_sidebar

st.set_page_config(page_title="AI設定", layout="wide",
                   initial_sidebar_state="expanded")
require_admin()
render_sidebar()

# 管理者ページ共通: 全面黒背景 + 選択中モデルバッジ
st.markdown("""
<style>
.stApp { background: #000 !important; color: #fff !important; }
.model-badge {
    display: inline-block; background: #2563eb; color: #fff;
    padding: 0.15rem 0.6rem; border-radius: 0.5rem;
    font-size: 0.8rem; font-weight: 700; margin-left: 0.4rem;
}
</style>""", unsafe_allow_html=True)

st.markdown("## 🤖 AI設定")
st.caption("OpenRouter 経由で利用する AI モデルを管理します。設定は管理者のみ変更できます。")


def _audit(action: str, detail: dict) -> None:
    user = current_user()
    with get_session() as s:
        s.add(AdminAuditLog(
            actor_id=user.id,
            action=action,
            target_type="app_settings",
            target_id=OPENROUTER_API_KEY if "setting" in action else "openrouter_config",
            detail=detail,
        ))


# ---------------------------------------------------------------------------
# 1. OpenRouter API キー（モデル選択窓のすぐ上）
# ---------------------------------------------------------------------------
st.markdown("### 🔑 OpenRouter API キー")

view = masked_view(OPENROUTER_API_KEY)
if view["isEmpty"]:
    src = "環境変数" if (settings.openrouter_api_key or settings.anthropic_api_key) else "なし"
    st.info(f"DB 未設定（現在のフォールバック元: {src}）。"
            "下のフォームから入力すると DB に保存され、環境変数より優先されます。")
else:
    st.success(f"設定済み: `{view['maskedValue']}`")

with st.container(border=True):
    with st.form("openrouter_api_key_form", clear_on_submit=True):
        new_key = st.text_input(
            "OpenRouter API キー",
            type="password",
            placeholder="sk-or-v1-...",
            help="https://openrouter.ai/keys で取得したキーを入力。保存後は再マスク表示に戻ります。",
        )
        col_save, col_del = st.columns([1, 1])
        save_clicked = col_save.form_submit_button("💾 保存", type="primary",
                                                   use_container_width=True)
        delete_clicked = col_del.form_submit_button("🗑 削除（env に戻す）",
                                                    use_container_width=True)

    if save_clicked:
        if not new_key.strip():
            st.warning("API キーを入力してください。")
        else:
            set_app_setting(
                OPENROUTER_API_KEY, new_key,
                updated_by=current_user().id,
                description="OpenRouter API key (admin-managed)",
            )
            _audit("admin.setting_updated", {"key": OPENROUTER_API_KEY,
                                             "masked": mask_secret(new_key)})
            st.toast("OpenRouter API キーを保存しました", icon="✅")
            st.rerun()

    if delete_clicked:
        set_app_setting(OPENROUTER_API_KEY, "", updated_by=current_user().id)
        _audit("admin.setting_updated", {"key": OPENROUTER_API_KEY, "deleted": True})
        st.toast("API キーを削除しました（環境変数フォールバックに戻ります）", icon="🗑")
        st.rerun()

# ---------------------------------------------------------------------------
# 2. モデル選択 UI
# ---------------------------------------------------------------------------
st.markdown("### 🧠 AIモデル選択")

selected = get_selected_config()
if selected is not None:
    st.markdown(
        f"現在の選択モデル: <span class='model-badge'>{selected.model_name}</span>"
        f"<code style='margin-left:0.5rem;color:#9aa7bd;'>{selected.model_id}</code>",
        unsafe_allow_html=True,
    )
else:
    st.caption("モデル未選択（解決順: 環境変数 OPENROUTER_MODEL → DB 選択モデル）。")

with st.spinner("OpenRouter モデル一覧を取得中..."):
    models = fetch_models()

if not models:
    # OpenRouter へ到達できない場合は最小フォールバック一覧で UI を維持する
    models = FALLBACK_MODELS
    st.warning("OpenRouter からモデル一覧を取得できませんでした。"
               "オフライン候補を表示しています（ネットワーク許可後に最新化されます）。")

if not models:
    st.error("利用可能なモデルがありません。")
else:
    labels = [f"{m.name}  ({m.model_id})" for m in models]
    default_idx = 0
    if selected is not None:
        for i, m in enumerate(models):
            if m.model_id == selected.model_id:
                default_idx = i
                break
    choice = st.selectbox(
        f"モデルを選択（全 {len(models)} 件）",
        options=range(len(models)),
        format_func=lambda i: labels[i],
        index=default_idx,
    )
    chosen = models[choice]

    is_current = selected is not None and chosen.model_id == selected.model_id
    badge = "<span class='model-badge'>選択中</span>" if is_current else ""
    st.markdown(f"**{chosen.name}** {badge}", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("コンテキスト長",
              f"{chosen.context_length:,}" if chosen.context_length else "—")

    def _per_mtok(price: Decimal | None) -> str:
        if price is None:
            return "—"
        return f"${(price * Decimal(1_000_000)):.4f}"

    c2.metric("プロンプト単価 / 1M tok", _per_mtok(chosen.prompt_price))
    c3.metric("補完単価 / 1M tok", _per_mtok(chosen.completion_price))

    if st.button("✅ このモデルを使用する", type="primary",
                 disabled=is_current, key="_use_model"):
        save_selected_config(chosen, updated_by=current_user().id)
        _audit("admin.model_selected", {"model_id": chosen.model_id,
                                        "model_name": chosen.name})
        st.toast(f"モデルを {chosen.name} に設定しました", icon="🤖")
        st.rerun()

# ---------------------------------------------------------------------------
# 3. コスト集計（過去30日）
# ---------------------------------------------------------------------------
st.markdown("### 💰 AI コスト（過去30日）")

try:
    summary = cost_summary(days=30)
    jpy = summary.total_cost_usd * Decimal(str(settings.usd_jpy_rate))
    m1, m2, m3 = st.columns(3)
    m1.metric("合計コスト (USD)", f"${summary.total_cost_usd:,.4f}")
    m2.metric("合計コスト (円換算)", f"¥{jpy:,.1f}",
              help=f"為替 {settings.usd_jpy_rate} 円/USD で換算")
    m3.metric("合計トークン", f"{summary.total_tokens:,}")

    if summary.by_model:
        st.markdown("#### モデル別内訳")
        st.dataframe(
            [
                {
                    "モデル": r["model_id"],
                    "コスト(USD)": f"${r['cost_usd']:,.4f}",
                    "トークン": f"{r['tokens']:,}",
                    "呼び出し": r["calls"],
                }
                for r in summary.by_model
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("まだ AI 使用ログがありません（AI 呼び出し後に集計されます）。")
except Exception as e:  # noqa: BLE001
    st.caption(f"⚠️ コスト集計を取得できませんでした: {str(e)[:80]}")
