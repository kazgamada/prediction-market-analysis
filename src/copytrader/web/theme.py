"""Shared dark-theme CSS + Plotly layout helpers.

Design:
- Page background: pure black (#000000)
- LIVE charts (real-time data): black plot area, white/cyan/yellow/red/green text
- STATIC charts (backtest snapshots): white plot area, dark text
- Tiles: very dark grey with subtle cyan border
"""
from __future__ import annotations

# Color palette
BG_BLACK = "#000000"
TILE_BG = "#0a0d12"
TILE_BORDER = "#1a2230"
TEXT_PRIMARY = "#fafafa"
TEXT_DIM = "#7a8499"
TEXT_GRID = "#1f2937"
ACCENT_CYAN = "#3aa3ff"
ACCENT_YELLOW = "#ffd166"
ACCENT_GREEN = "#22c55e"
ACCENT_RED = "#ef4444"
ACCENT_BLUE = "#60a5fa"

STATIC_BG = "#ffffff"
STATIC_TEXT = "#1a1a1a"
STATIC_GRID = "#e5e7eb"

# Plotly layouts
LIVE_AXIS = dict(
    color=TEXT_DIM,
    gridcolor=TEXT_GRID,
    zerolinecolor=TEXT_GRID,
    linecolor=TEXT_GRID,
)
LIVE_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor=TILE_BG,
    font=dict(color=TEXT_PRIMARY, size=9, family="sans serif"),
    xaxis=LIVE_AXIS,
    yaxis=LIVE_AXIS,
    margin=dict(t=4, b=4, l=4, r=4),
    showlegend=False,
)

STATIC_AXIS = dict(
    color=STATIC_TEXT,
    gridcolor=STATIC_GRID,
    zerolinecolor=STATIC_GRID,
    linecolor=STATIC_GRID,
)
STATIC_LAYOUT = dict(
    paper_bgcolor=STATIC_BG,
    plot_bgcolor=STATIC_BG,
    font=dict(color=STATIC_TEXT, size=9, family="sans serif"),
    xaxis=STATIC_AXIS,
    yaxis=STATIC_AXIS,
    margin=dict(t=4, b=4, l=4, r=4),
    showlegend=False,
)

# Plotly color sequences
LIVE_PALETTE = [
    ACCENT_CYAN, ACCENT_YELLOW, ACCENT_GREEN, ACCENT_RED,
    ACCENT_BLUE, "#a78bfa", "#fb7185", "#34d399",
]
STATIC_PALETTE = [
    "#1f77b4", "#d62728", "#2ca02c", "#9467bd",
    "#ff7f0e", "#17becf", "#e377c2", "#8c564b",
]

# Global CSS injected at the top of every page
GLOBAL_CSS = """
<style>
/* === Page === */
.stApp, [data-testid="stAppViewContainer"], section.main, [data-testid="stMain"] {
  background-color: #000000 !important;
}
[data-testid="stHeader"] {
  background-color: rgba(0,0,0,0.5) !important;
}
[data-testid="stSidebar"] {
  background-color: #050708 !important;
  border-right: 1px solid #1a2230;
}
[data-testid="stSidebarNav"] a {
  color: #b3bccc !important;
  font-size: 0.85rem !important;
}
[data-testid="stSidebarNav"] a:hover {
  background-color: #0f1623 !important;
  color: #3aa3ff !important;
}
[data-testid="stSidebarNav"] [aria-current="page"] {
  background-color: #0f1623 !important;
  color: #3aa3ff !important;
}

.block-container {
  padding-top: 0.6rem !important;
  padding-bottom: 0.4rem !important;
  max-width: 100% !important;
}

/* === Typography === */
h1, h2, h3, h4, h5, h6, p, span, div {
  color: #e6e6e6;
}
h1 { font-size: 1.2rem !important; padding: 0 !important; margin: 0 0 0.3rem 0 !important; color: #fafafa !important; }
h2 { font-size: 1.0rem !important; padding: 0 !important; margin: 0.2rem 0 !important; }
h3, h4, h5 { padding: 0 !important; margin: 0.2rem 0 !important; color: #cbd5e1 !important; }
h5 { font-size: 0.85rem !important; }
small, .stCaption, [data-testid="stCaptionContainer"] { color: #6b7785 !important; }
hr { margin: 0.3rem 0 !important; border-color: #1a2230 !important; }

/* === Metrics === */
[data-testid="stMetric"] {
  padding: 0.3rem 0.5rem !important;
  background-color: #0a0d12 !important;
  border: 1px solid #1a2230 !important;
  border-radius: 6px !important;
}
[data-testid="stMetricLabel"] {
  font-size: 0.7rem !important;
  color: #7a8499 !important;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
[data-testid="stMetricValue"] {
  font-size: 1.1rem !important;
  color: #fafafa !important;
  font-weight: 600;
}
[data-testid="stMetricDelta"] {
  font-size: 0.7rem !important;
}
[data-testid="stMetricDelta"] svg { width: 0.7rem !important; }

/* === Containers (tiles) === */
[data-testid="stVerticalBlockBorderWrapper"] {
  background-color: #0a0d12 !important;
  border: 1px solid #1a2230 !important;
  border-radius: 8px !important;
  padding: 0.4rem 0.6rem !important;
}

/* === DataFrames === */
.stDataFrame, [data-testid="stDataFrame"] {
  background-color: #0a0d12 !important;
  font-size: 0.75rem !important;
}
.stDataFrame [data-testid="stTable"] {
  background-color: #0a0d12 !important;
}
.stDataFrame thead { color: #7a8499 !important; }
.stDataFrame tbody td { color: #e6e6e6 !important; }

/* === Buttons === */
.stButton button {
  background-color: #0f1623 !important;
  color: #fafafa !important;
  border: 1px solid #2a3445 !important;
  font-size: 0.78rem !important;
  padding: 0.2rem 0.6rem !important;
}
.stButton button:hover {
  background-color: #1a2638 !important;
  border-color: #3aa3ff !important;
  color: #3aa3ff !important;
}
.stButton button[kind="primary"] {
  background-color: #1e40af !important;
  border-color: #3aa3ff !important;
}
.stButton button[kind="primary"]:hover {
  background-color: #2563eb !important;
}

/* === Inputs === */
input, textarea, .stNumberInput input, .stTextInput input,
.stTextArea textarea, .stSelectbox div[role="button"] {
  background-color: #0a0d12 !important;
  color: #fafafa !important;
  border: 1px solid #2a3445 !important;
  font-size: 0.78rem !important;
}

/* === Tabs === */
.stTabs [data-baseweb="tab-list"] {
  background-color: transparent !important;
  border-bottom: 1px solid #1a2230 !important;
  gap: 0;
}
.stTabs [data-baseweb="tab"] {
  background-color: transparent !important;
  color: #7a8499 !important;
  padding: 0.3rem 0.8rem !important;
  font-size: 0.78rem !important;
}
.stTabs [aria-selected="true"] {
  color: #3aa3ff !important;
  border-bottom: 2px solid #3aa3ff !important;
}

/* === Radio === */
.stRadio > div { gap: 0.5rem !important; }
.stRadio label {
  font-size: 0.75rem !important;
  color: #b3bccc !important;
}

/* === Progress === */
.stProgress > div > div > div { height: 6px !important; }
.stProgress > div > div { background-color: #1a2230 !important; }

/* === Page link === */
.stPageLink a {
  padding: 0 !important;
  font-size: 0.85rem !important;
  color: #3aa3ff !important;
}
.stPageLink a:hover { color: #60a5fa !important; }

/* === Alerts (toast / success / error) === */
.stAlert, [data-testid="stNotification"] {
  background-color: #0a0d12 !important;
  border: 1px solid #1a2230 !important;
}

/* === Code blocks === */
code, .stCode {
  background-color: #050708 !important;
  color: #ffd166 !important;
  border: 1px solid #1a2230 !important;
  font-size: 0.72rem !important;
}

/* === Toggle === */
.stCheckbox label, .stToggle label { color: #cbd5e1 !important; }

/* === Help tooltip (browser native title) === */
.help-tip-icon {
  cursor: help;
  color: #3aa3ff;
  font-weight: bold;
  font-size: 0.85rem;
  margin-left: 0.2rem;
}
.help-tip-icon:hover { color: #60a5fa; }

/* === JSON viewer === */
[data-testid="stJson"] { background-color: #050708 !important; }
</style>
"""


def inject_theme() -> None:
    """Call this at the top of every page (after st.set_page_config)."""
    import streamlit as st
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
