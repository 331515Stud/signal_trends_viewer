import streamlit as st


def inject_theme_css(theme):
    st.markdown(f"""
<style>
    .stApp {{ background-color: {theme['bg']}; }}
    .stApp header[data-testid="stHeader"] {{ background-color: {theme['paper']}; }}
    [data-testid="stSidebar"] {{ background-color: {theme['sidebar_bg']}; }}
    [data-testid="stSidebar"] * {{ color: {theme['text']} !important; }}
    h1, h2, h3, h4, h5, h6 {{ color: {theme['text']} !important; }}
    p, span, div, label, li {{ color: {theme['text']} !important; }}
    code {{
        background-color: {theme['paper']} !important;
        color: {theme['text']} !important;
        padding: 2px 6px;
        border: 1px solid {theme['grid']};
        border-radius: 4px;
    }}
    [data-testid="stMetric"] {{
        background-color: {theme['paper']};
        border: 1px solid {theme['grid']};
        padding: 10px; border-radius: 8px;
    }}
    [data-testid="stMetric"] label {{ color: {theme['text']} !important; }}
    [data-testid="stMetric"] [data-testid="stMetricValue"] {{ color: {theme['text']} !important; }}
    [data-testid="stExpander"] {{
        background-color: {theme['paper']};
        border: 1px solid {theme['grid']};
    }}
    [data-testid="stExpander"] * {{ color: {theme['text']} !important; }}
    [data-testid="stExpanderHeader"] {{
        background-color: {theme['paper']} !important;
        color: {theme['text']} !important;
    }}
    .stButton > button {{
        background-color: {theme['paper']}; color: {theme['text']};
        border: 1px solid {theme['grid']};
    }}
    .stButton > button:hover {{
        border-color: {theme['text']};
    }}
    hr {{ border-color: {theme['grid']}; }}
    input, textarea, select {{
        background-color: {theme['bg']} !important;
        color: {theme['text']} !important;
        border-color: {theme['grid']} !important;
    }}
    input:focus, textarea:focus, select:focus {{
        border-color: {theme['text']} !important;
        box-shadow: none !important;
    }}
    [data-testid="stTextInput"] > div > div > input {{
        background-color: {theme['bg']} !important;
        color: {theme['text']} !important;
        border-color: {theme['grid']} !important;
    }}
    [data-testid="stNumberInput"] > div > div > input {{
        background-color: {theme['bg']} !important;
        color: {theme['text']} !important;
        border-color: {theme['grid']} !important;
    }}
    [data-testid="stNumberInput"] button {{
        background-color: {theme['paper']} !important;
        color: {theme['text']} !important;
        border-color: {theme['grid']} !important;
    }}
    [data-testid="stNumberInput"] button:hover {{
        background-color: {theme['grid']} !important;
    }}
    [data-testid="stSelectbox"] > div > div {{
        background-color: {theme['bg']} !important;
        color: {theme['text']} !important;
        border-color: {theme['grid']} !important;
    }}
    [data-testid="stRadio"] > div {{
        color: {theme['text']} !important;
    }}
    [data-testid="stCheckbox"] > div {{
        color: {theme['text']} !important;
    }}
    .stDownloadButton > button {{
        background-color: {theme['paper']}; color: {theme['text']};
        border: 1px solid {theme['grid']};
    }}
    [data-testid="stSidebar"] [data-testid="stExpander"] {{
        background-color: {theme['sidebar_bg']} !important;
    }}
    [data-testid="stSidebar"] [data-testid="stExpanderHeader"] {{
        background-color: {theme['sidebar_bg']} !important;
        color: {theme['text']} !important;
    }}
    [data-testid="stSidebar"] [data-testid="stExpander"] * {{
        color: {theme['text']} !important;
    }}
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {{
        background-color: {theme['sidebar_bg']} !important;
        color: {theme['text']} !important;
    }}
    [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {{
        background-color: {theme['grid']} !important;
    }}
    [data-testid="stFileUploader"] {{
        background-color: {theme['bg']} !important;
        border: 1px solid {theme['grid']} !important;
        border-radius: 8px;
    }}
    [data-testid="stFileUploader"] * {{
        color: {theme['text']} !important;
    }}
    [data-testid="stFileUploader"] section {{
        background-color: {theme['bg']} !important;
        border-color: {theme['grid']} !important;
    }}
    [data-testid="stFileUploader"] section > div {{
        color: {theme['text']} !important;
    }}
    [data-testid="stFileUploader"] button {{
        background-color: {theme['paper']} !important;
        color: {theme['text']} !important;
        border: 1px solid {theme['grid']} !important;
    }}
    [data-testid="stFileUploader"] button:hover {{
        border-color: {theme['text']} !important;
    }}
    [data-testid="stFileUploader"] small {{
        color: {theme['text']} !important;
    }}
</style>
""", unsafe_allow_html=True)
