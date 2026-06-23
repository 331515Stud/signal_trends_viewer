import streamlit as st

THEMES = {
    "dark": {
        "bg": "#0e1117",
        "paper": "#1e1e1e",
        "text": "#fafafa",
        "grid": "#333333",
        "line_colors": ["#ff6b6b", "#ffd93d", "#6bcb77", "#4d96ff", "#ff6b9d", "#c678dd"],
        "cursor": "green",
        "sidebar_bg": "#1a1a2e",
        "hover_bg": "#2a2a2a",
        "hover_text": "#ffffff",
    },
    "light": {
        "bg": "#ffffff",
        "paper": "#f5f5f5",
        "text": "#212121",
        "grid": "#cccccc",
        "line_colors": ["#b71c1c", "#e65100", "#1b5e20", "#0d47a1", "#880e4f", "#4a148c"],
        "cursor": "#00c853",
        "sidebar_bg": "#e8eaf6",
        "hover_bg": "#ffffff",
        "hover_text": "#212121",
    },
}


def get_theme():
    return THEMES[st.session_state.theme]
