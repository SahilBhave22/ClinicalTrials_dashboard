"""
Clinical Trials Intelligence Platform — Main Entry Point.

Run with:
    streamlit run app.py
"""
import base64
from pathlib import Path
from PIL import Image
import streamlit as st
from streamlit_option_menu import option_menu

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

# ── Nav items: (label, page_key, group) ───────────────────────────────────────
NAV_ITEMS = [
    ("Home",         "home",              0),
    ("Disease",      "landscape",         1),
    ("Pipeline",     "pipeline",          1),
    ("Drug Detail",  "drug_detail",       2),
    ("Sponsors",     "sponsor_benchmark", 2),
    ("Trial Design", "trial_design",      3),
    ("Endpoints",    "planned_endpoints", 3),
    ("Outcomes",     "reported_outcomes", 4),
    ("Scores",       "outcome_scores",    4),
    ("PRO Overview", "pro_overview",      5),
    ("PRO Domains",  "pro_domains",       5),
    ("Trial Groups", "trial_groups",      5),
    ("Safety",       "safety_analysis",   6),
    ("Ask the Data", "ask_the_data",      7),
]

_NAV_LABELS = [label for label, _, _ in NAV_ITEMS]
_NAV_KEYS   = [key   for _, key, _ in NAV_ITEMS]
_NAV_ICONS  = [
    "house", "activity", "graph-up", "capsule", "building",
    "clipboard-check", "bullseye", "bar-chart-line", "123",
    "person-check", "grid", "collection", "shield-exclamation", "chat-dots",
]
_valid_keys = set(_NAV_KEYS)

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

/* ── Stick the very first block (our nav) to the top ────────────────────── */
section[data-testid="stMain"] div.block-container > div:first-child {
    position: sticky;
    top: 0;
    z-index: 999;
    background: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    box-shadow: 0 1px 4px rgba(0,0,0,.06);
    margin-left:  -1rem;
    margin-right: -1rem;
    padding-left:  1rem;
    padding-right: 1rem;
    overflow: visible;
}

/* ── Hide scrollbar on the nav iframe (webkit) ───────────────────────────── */
section[data-testid="stMain"] div.block-container > div:first-child iframe {
    overflow-x: auto;
}
.nav-pills::-webkit-scrollbar { display: none; }

/* ── Main content spacing ────────────────────────────────────────────────── */
.block-container {
    padding-top: 0 !important;
    padding-bottom: 3rem !important;
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

# ── Resolve initial page from URL (used only when session has no nav state) ───
# Deep-links like ?nav=landscape will correctly initialize the nav on first load.
# Once the user navigates within the session, option_menu's own session_state
# takes over and the URL param is only kept in sync for bookmarking.
_qp_nav      = st.query_params.get("nav", "home")
_qp_page     = _qp_nav if _qp_nav in _valid_keys else "home"
_default_idx = _NAV_KEYS.index(_qp_page)

# ── Top navigation ────────────────────────────────────────────────────────────
# option_menu is a Streamlit widget: clicking it triggers a rerun (same session),
# NOT a browser page reload.  This is what keeps session_state — and therefore
# all sidebar filter values — alive across page changes.
selected = option_menu(
    menu_title="Apperture Clinical Trials Dashboard",
    options=_NAV_LABELS,
    icons=_NAV_ICONS,
    default_index=_default_idx,
    orientation="horizontal",
    key="main_nav",
    styles={
        "container": {
            "padding": "0",
            "background-color": "#FFFFFF",
            "border": "none",
            "margin": "0",
            "font-family": "'DM Sans', system-ui, sans-serif",
        },
        # Target Bootstrap's .nav-pills on the <ul> to enforce single-line scroll
        "nav-pills": {
            "flex-wrap": "nowrap",
            "overflow-x": "auto",
            "overflow-y": "hidden",
            "-ms-overflow-style": "none",
            "scrollbar-width": "none",
        },
        "menu-title": {
            "font-size": "1.1rem",
            "font-weight": "700",
            "color": "#0F4C81",
            "padding": "0 16px 0 40px",
            "border-right": "1px solid #E2E8F0",
            "white-space": "nowrap",
            "letter-spacing": "0.04em",
            "flex-shrink": "0",
            "font-family": "'DM Sans', system-ui, sans-serif",
            "background-image": _LOGO_URI,
            "background-repeat": "no-repeat",
            "background-size": "28px 28px",
            "background-position": "left center",
        },
        "icon": {
            "font-size": "0.70rem",
            "color": "#9CA3AF",
        },
        "nav-link": {
            "font-size": "0.78rem",
            "font-weight": "500",
            "color": "#6B7280",
            "padding": "10px 8px",
            "border-radius": "0",
            "border-bottom": "2px solid transparent",
            "white-space": "nowrap",
            "letter-spacing": "0.01em",
            "flex-shrink": "0",
            "--hover-color": "#F8FAFC",
            "font-family": "'DM Sans', system-ui, sans-serif",
        },
        "nav-link-selected": {
            "background-color": "#E8F0FB",
            "color": "#0F4C81",
            "font-weight": "600",
            "border-bottom": "2px solid #0F4C81",
        },
    },
)

current_page = _NAV_KEYS[_NAV_LABELS.index(selected)]

# Keep URL in sync for bookmarking — does NOT trigger a browser reload
if st.query_params.get("nav") != current_page:
    st.query_params["nav"] = current_page

# ── Sidebar filters (unchanged; sidebar is filters only) ─────────────────────
from components.filters import render_sidebar
filters = render_sidebar()

# ── Route to pages ────────────────────────────────────────────────────────────
if current_page == "home":
    from views.home import render
    render(filters)

elif current_page == "landscape":
    from views.landscape import render
    render(filters)

elif current_page == "pipeline":
    from views.pipeline_landscape import render
    render(filters)

elif current_page == "drug_detail":
    from views.drug_detail import render
    render(filters)

elif current_page == "sponsor_benchmark":
    from views.sponsor_benchmark import render
    render(filters)

elif current_page == "trial_design":
    from views.trial_design import render
    render(filters)

elif current_page == "planned_endpoints":
    from views.planned_endpoints import render
    render(filters)

elif current_page == "reported_outcomes":
    from views.reported_outcomes import render
    render(filters)

elif current_page == "outcome_scores":
    from views.outcome_scores import render
    render(filters)

elif current_page == "pro_overview":
    from views.pro_overview import render
    render(filters)

elif current_page == "pro_domains":
    from views.pro_domains import render
    render(filters)

elif current_page == "trial_groups":
    from views.trial_groups import render
    render(filters)

elif current_page == "safety_analysis":
    from views.safety_analysis import render
    render(filters)

elif current_page == "ask_the_data":
    from views.ask_the_data import render
    render(filters)
