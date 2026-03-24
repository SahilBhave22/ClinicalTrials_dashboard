"""
Clinical Trials Intelligence Platform — Main Entry Point.

Run with:
    streamlit run app.py
"""
import base64
import importlib
from pathlib import Path
from PIL import Image
import streamlit as st

# ── Logo — loaded once at startup ─────────────────────────────────────────────
_LOGO_PATH  = Path(__file__).parent / "assets" / "logos" / "APP_logo1.png"
_LOGO_IMAGE = Image.open(_LOGO_PATH)
_LOGO_B64   = base64.b64encode(_LOGO_PATH.read_bytes()).decode()
_LOGO_URI   = f"url('data:image/png;base64,{_LOGO_B64}')"

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Clinical Trials Intelligence Platform",
    page_icon=_LOGO_IMAGE,
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "Clinical Trials Intelligence Platform v1.0 — Apperture Analytics",
    },
)

# ── Background data preload (starts once per process on first page load) ──────
from utils.preloader import start_background_preload
start_background_preload()

# ── Page registry: (tab label, module path) ───────────────────────────────────
PAGE_MAP = [
    ("🏠 Home",          "views.home"),
    ("💬 Ask the Data",  "views.ask_the_data"),
    ("📈 Pipeline",      "views.pipeline_landscape"),
    ("💊 Drug Detail",   "views.drug_detail"),
    ("🏢 Sponsors",      "views.sponsor_benchmark"),
    ("📋 Trial Design",  "views.trial_design"),
    ("🎯 Endpoints",     "views.planned_endpoints"),
    ("📊 Outcomes",      "views.reported_outcomes"),
    ("🔢 Scores",        "views.outcome_scores"),
    ("👤 PRO Overview",  "views.pro_overview"),
    ("🗂️ Trial Groups",  "views.trial_groups"),
    ("🛡️ Safety",        "views.safety_analysis"),
]

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', system-ui, sans-serif; }
.stApp { background: #F8FAFC; }

/* ── Hide default Streamlit chrome ──────────────────────────────────────── */
header[data-testid="stHeader"]  { display: none !important; }
#MainMenu                        { visibility: hidden !important; }
footer                           { visibility: hidden !important; }
[data-testid="stDeployButton"]   { display: none !important; }
[data-testid="stToolbar"]        { display: none !important; }

/* ── Main content spacing ────────────────────────────────────────────────── */
.block-container {
    padding-top: 0 !important;
    padding-bottom: 3rem !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
    max-width: 100% !important;
}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0B1929 0%, #0F4C81 100%);
    color: white;
}
section[data-testid="stSidebar"] .stMarkdown h3,
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] label { color: #E2E8F0 !important; }

section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stMultiSelect label,
section[data-testid="stSidebar"] .stSlider label,
section[data-testid="stSidebar"] .stCheckbox label,
section[data-testid="stSidebar"] .stRadio label {
    color: #FFFFFF !important; font-size: 13px; font-weight: 500;
}

section[data-testid="stSidebar"] .stSelectbox > div > div,
section[data-testid="stSidebar"] .stMultiSelect > div > div {
    background-color: rgba(255,255,255,0.95) !important;
    color: #1A1A2E !important;
    border: 1px solid rgba(255,255,255,0.3) !important;
    border-radius: 8px !important;
}

section[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] span,
section[data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] span { color: #1A1A2E !important; }

section[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] {
    background-color: #0F4C81 !important;
    color: white !important;
    border-radius: 6px !important;
    display: inline-flex !important;
    align-items: center !important;
    gap: 2px !important;
}

/* Tag label text */
section[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] span:first-child {
    color: white !important;
}

/* Close (×) button — visible white icon on dark navy tag */
section[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] [role="button"],
section[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] span[role="button"] {
    color: rgba(255,255,255,0.85) !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 16px !important;
    height: 16px !important;
    border-radius: 50% !important;
    flex-shrink: 0 !important;
    background: rgba(255,255,255,0.15) !important;
    margin-left: 2px !important;
}
section[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] [role="button"]:hover,
section[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] span[role="button"]:hover {
    background: rgba(255,255,255,0.30) !important;
    color: white !important;
}

/* SVG icon inside the close button */
section[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] [role="button"] svg,
section[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] span[role="button"] svg {
    fill: white !important;
    width: 10px !important;
    height: 10px !important;
}

section[data-testid="stSidebar"] .stButton > button {
    background-color: rgba(255,255,255,0.15) !important;
    color: #FFFFFF !important;
    border: 1px solid rgba(255,255,255,0.3) !important;
    border-radius: 8px !important;
    font-weight: 500;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background-color: rgba(255,255,255,0.25) !important;
    border: 1px solid rgba(255,255,255,0.5) !important;
}

section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.15) !important; }

/* ── Sidebar expanders ───────────────────────────────────────────────────── */
section[data-testid="stSidebar"] .streamlit-expanderHeader { color: #E2E8F0 !important; font-weight: 500; }

/* Expander container — transparent so sidebar gradient shows through */
section[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: transparent !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    border-radius: 8px !important;
}

/* Header row (button) — keep dark background, white text in all states */
section[data-testid="stSidebar"] [data-testid="stExpander"] summary,
section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderToggleIcon"],
section[data-testid="stSidebar"] details summary {
    background: transparent !important;
    color: #E2E8F0 !important;
}

section[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
    background: rgba(255,255,255,0.08) !important;
}

/* The toggle arrow icon */
section[data-testid="stSidebar"] [data-testid="stExpander"] summary svg {
    fill: #E2E8F0 !important;
    stroke: #E2E8F0 !important;
}

/* Expander content area — keep transparent so gradient shows */
section[data-testid="stSidebar"] [data-testid="stExpander"] > div:last-child,
section[data-testid="stSidebar"] details > div {
    background: transparent !important;
    color: #E2E8F0 !important;
}

/* ── Column grid: tighter gap + equal-height rows ────────────────────────── */
[data-testid="stHorizontalBlock"] {
    gap: 0.6rem !important;
    align-items: stretch !important;
}
[data-testid="stColumn"] {
    display: flex !important;
    flex-direction: column !important;
    min-width: 0;
}
[data-testid="stColumn"] > [data-testid="stVerticalBlock"] {
    flex: 1 !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-start !important;
}
[data-testid="stVerticalBlock"] > .element-container {
    margin-bottom: 0.5rem !important;
}

/* ── Tab navigation ──────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0px; background: white; border-radius: 12px; padding: 4px; border: 1px solid #E5E7EB;
}
.stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 8px 20px; font-weight: 500; font-size: 14px; }
.stTabs [aria-selected="true"] { background: #0F4C81 !important; color: white !important; }

/* ── Charts & tables ─────────────────────────────────────────────────────── */
div[data-testid="stDataFrame"] { border: 1px solid #E5E7EB; border-radius: 8px; }
.stPlotlyChart {
    background: white; border-radius: 12px; border: 1px solid #E5E7EB;
    padding: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

/* ── Chart tile header ───────────────────────────────────────────────────── */
.chart-tile-header { padding: 4px 4px 8px 4px; }
.chart-tile-title  { font-size: 0.92rem; font-weight: 700; color: #0F4C81; line-height: 1.3; }
.chart-tile-subtitle { font-size: 0.78rem; color: #6B7280; margin-top: 2px; }

/* ── Headings ────────────────────────────────────────────────────────────── */
h1, h2, h3 { color: #0F4C81; }

/* ── Metric override ─────────────────────────────────────────────────────── */
[data-testid="stMetricValue"] { font-size: 1.6rem !important; }

/* ── Download buttons ────────────────────────────────────────────────────── */
.stDownloadButton > button {
    background: #0F4C81 !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
}
</style>
""", unsafe_allow_html=True)

# ── Auth gate ─────────────────────────────────────────────────────────────────
_USERNAME = "admin"
_PASSWORD = "password#1234"

_login_slot = st.empty()

if not st.session_state.get("authenticated", False):
    with _login_slot.container():
        st.markdown(f"""
        <style>
        section[data-testid="stSidebar"] {{ display: none !important; }}
        .block-container {{ padding-top: 0 !important; }}

        /* Card: style the middle column's vertical block */
        div[data-testid="stMainBlockContainer"]
            div[data-testid="stHorizontalBlock"]
            > div[data-testid="stColumn"]:nth-child(2)
            > div[data-testid="stVerticalBlock"] {{
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 16px;
                box-shadow: 0 4px 32px rgba(15,76,129,0.12);
                padding: 40px 36px 36px !important;
                margin-top: 80px;
        }}

        /* Sign in button */
        div[data-testid="stMainBlockContainer"] .stButton > button {{
            background: #0F4C81 !important;
            color: white !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            font-size: 15px !important;
            height: 44px !important;
            letter-spacing: 0.01em;
            margin-top: 4px;
        }}
        div[data-testid="stMainBlockContainer"] .stButton > button:hover {{
            background: #0D3F6E !important;
        }}
        </style>

        <div style="height:0"></div>
        """, unsafe_allow_html=True)

        _, col, _ = st.columns([1, 1.4, 1])
        with col:
            st.markdown(f"""
            <div style="text-align:center; margin-bottom:24px;">
                <img src="data:image/png;base64,{_LOGO_B64}"
                     style="height:52px; margin-bottom:18px; display:block; margin-left:auto; margin-right:auto;">
                <div style="font-size:21px; font-weight:700; color:#0F4C81; margin-bottom:5px; letter-spacing:-0.01em;">
                    Clinical Trials Intelligence Platform
                </div>
                <div style="font-size:14px; color:#6B7280;">
                    Sign in to continue
                </div>
            </div>
            <hr style="border:none; border-top:1px solid #E5E7EB; margin:0 0 20px 0;">
            """, unsafe_allow_html=True)

            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", placeholder="Enter your password", type="password")

            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

            if st.button("Sign in", use_container_width=True):
                if username == _USERNAME and password == _PASSWORD:
                    st.session_state["authenticated"] = True
                    st.session_state.pop("_login_attempted", None)
                    st.rerun()
                else:
                    st.session_state["_login_attempted"] = True
                    st.rerun()

            if st.session_state.get("_login_attempted", False):
                st.error("Incorrect username or password.")

    st.stop()

# ── Sidebar filters ───────────────────────────────────────────────────────────
from components.filters import render_sidebar
filters = render_sidebar()

# ── Tab navigation + routing ──────────────────────────────────────────────────
FILTER_REQUIRED = {
    "views.outcome_scores",
    "views.safety_analysis",
    "views.trial_groups",
}

tabs = st.tabs([label for label, _ in PAGE_MAP])

for tab, (_, module_path) in zip(tabs, PAGE_MAP):
    with tab:
        if module_path in FILTER_REQUIRED and not filters.has_any_filter():
            st.markdown(
                """
                <div style="text-align:center;padding:60px 20px;">
                  <div style="font-size:48px;margin-bottom:16px;">🔍</div>
                  <h3 style="color:#0F4C81;font-weight:700;">Filter Required</h3>
                  <p style="color:#6B7280;font-size:15px;max-width:420px;margin:0 auto;">
                    Please select at least one filter in the sidebar
                    (indication, drug class, sponsor, phase, etc.)
                    to load this tab.
                  </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            try:
                module = importlib.import_module(module_path)
                module.render(filters)
            except Exception as e:
                st.error(f"Error loading {module_path}: {e}")
                st.exception(e)
