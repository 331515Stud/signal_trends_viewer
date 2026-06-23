import streamlit as st

from adapters.file_loader import detect_columns
from ui.themes import get_theme
from ui.styles import inject_theme_css
from ui.sidebar import render_sidebar
from ui.trend_charts import render_trend_charts
from ui.oscillogram import render_oscillograms

st.set_page_config(page_title="Signal Trends Viewer", page_icon="⚡", layout="wide")

if "cursor_x" not in st.session_state:
    st.session_state.cursor_x = None
if "df" not in st.session_state:
    st.session_state.df = None
if "selected_file" not in st.session_state:
    st.session_state.selected_file = None
if "theme" not in st.session_state:
    st.session_state.theme = "dark"
if "signal_idx" not in st.session_state:
    st.session_state.signal_idx = 0
if "step_size" not in st.session_state:
    st.session_state.step_size = 1
if "open_meta_keys" not in st.session_state:
    st.session_state.open_meta_keys = set()
if "open_meta_data" not in st.session_state:
    st.session_state.open_meta_data = {}
if "active_session_name" not in st.session_state:
    st.session_state.active_session_name = None
if "active_dataset_name" not in st.session_state:
    st.session_state.active_dataset_name = None

render_sidebar()

theme = get_theme()
inject_theme_css(theme)

st.title("\U0001f4c8 Signal Trends Viewer")

active = st.session_state.get("active_session_name")
active_ds = st.session_state.get("active_dataset_name")
if active:
    label = f"\U0001f50a {active}"
    if active_ds:
        label = f"{active_ds} / {active}"
    is_dark = st.session_state.theme == "dark"
    bg = "#1a3a2a" if is_dark else "#e8f5e9"
    color = "#4CAF50" if is_dark else "#2e7d32"
    border = "#4CAF50" if is_dark else "#66bb6a"
    st.markdown(
        f'<div style="background:{bg};border:1px solid {border};'
        f'border-radius:6px;padding:6px 10px;margin-bottom:8px;'
        f'font-size:0.85em;color:{color};">{label}</div>',
        unsafe_allow_html=True,
    )

if st.session_state.df is not None:
    df = st.session_state.df
    ts_col, x, rms_cols, signal_cols = detect_columns(df)

    selected_x, y_cache = render_trend_charts(df, x, rms_cols, theme)

    if selected_x is not None:
        st.session_state.cursor_x = selected_x
        st.rerun()

    render_oscillograms(df, x, signal_cols, theme)

else:
    st.info("\U0001f449 Выберите сессию в дереве датасетов")
