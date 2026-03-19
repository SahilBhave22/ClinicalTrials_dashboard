"""
Application-level configuration constants and theme settings.
"""

# ── App identity ────────────────────────────────────────────────────────────
APP_TITLE       = "Clinical Trials Intelligence Platform"
APP_SHORT_TITLE = "CTIP"
APP_ICON        = "⚗️"
APP_VERSION     = "1.0.0"

# ── Database keys (must match DBS dict in utils/db_conn.py) ─────────────────
DB_AACT   = "aact"
DB_DRUGS  = "drugs"

# ── Drugs DB – table names ────────────────────────────────────────────────────
DRUGS_TABLE            = "public.drugs"            # brand_name, generic_name
DRUG_INDICATIONS_TABLE = "public.drug_indications" # brand_name, indication_name (downstream filter only)
DRUG_CLASSES_TABLE     = "public.drug_classes"     # brand_name, atc_class_name

DRUGS_BRAND_COL      = "brand_name"
DRUGS_INDICATION_COL = "indication_name"
DRUGS_ATC_COL        = "atc_class_name"
DRUGS_GENERIC_COL    = "generic_name"

# ── AACT DB – browse_conditions (global indication source) ───────────────────
# The global "Indication" filter uses ctgov.browse_conditions mesh-list terms,
# NOT drug_indications. drug_indications is used only as a downstream filter.
BROWSE_CONDITIONS_TABLE     = "ctgov.browse_conditions"
BROWSE_CONDITIONS_MESH_TERM = "mesh_term"
BROWSE_CONDITIONS_MESH_TYPE = "mesh_type"
BROWSE_CONDITIONS_MESH_LIST = "mesh-list"

# ── Query limits ─────────────────────────────────────────────────────────────
MAX_TABLE_ROWS     = 500
MAX_NL_ROWS        = 200
FILTER_CACHE_TTL   = 600   # seconds
QUERY_CACHE_TTL    = 300

# ── Design system colour palette ──────────────────────────────────────────────
COLORS = {
    "primary":        "#0F4C81",   # deep navy — headings, active tabs, KPI values, primary buttons
    "secondary":      "#2E86AB",   # medium blue — chart accents
    "accent":         "#F18F01",   # amber — highlights
    "success":        "#2A9D8F",   # teal — positive deltas
    "warning":        "#E9C46A",   # yellow — warning states
    "danger":         "#E76F51",   # coral — errors / terminated states
    "bg_dark":        "#0B1929",   # near-black navy — sidebar gradient top
    "bg_card":        "#FFFFFF",   # card backgrounds
    "text_primary":   "#1A1A2E",   # body text
    "text_secondary": "#6B7280",   # labels, subtitles
    "chart_sequence": [
        "#0F4C81", "#2E86AB", "#2A9D8F", "#F18F01",
        "#E76F51", "#E9C46A", "#457B9D", "#A8DADC",
        "#264653", "#F4A261", "#1D3557", "#6B7280",
    ],
}

# ── Shorthand aliases (for imports in chart/component files) ──────────────────
PRIMARY_COLOR   = COLORS["primary"]
SECONDARY_COLOR = COLORS["secondary"]
SUCCESS_COLOR   = COLORS["success"]
WARNING_COLOR   = COLORS["warning"]
DANGER_COLOR    = COLORS["danger"]
NEUTRAL_COLOR   = COLORS["text_secondary"]

PHASE_COLORS = {
    "EARLY_PHASE1": "#A8DADC",
    "PHASE1":       "#2E86AB",
    "PHASE2":       "#457B9D",
    "PHASE3":       "#0F4C81",
    "PHASE4":       "#1D3557",
    "N/A":          "#6B7280",
}

STATUS_COLORS = {
    "COMPLETED":              "#2A9D8F",
    "RECRUITING":             "#2E86AB",
    "ACTIVE_NOT_RECRUITING":  "#0F4C81",
    "TERMINATED":             "#E76F51",
    "SUSPENDED":              "#E9C46A",
    "WITHDRAWN":              "#6B7280",
    "UNKNOWN":                "#264653",
}

CATEGORICAL_PALETTE = COLORS["chart_sequence"]

# ── Page nav ─────────────────────────────────────────────────────────────────
PAGES = [
    {"label": "Home / Overview",        "icon": "🏠", "key": "home"},
    {"label": "Disease Landscape",      "icon": "🗺️", "key": "landscape"},
    {"label": "Pipeline Landscape",     "icon": "🔬", "key": "pipeline"},
    {"label": "Drug Detail",            "icon": "💊", "key": "drug_detail"},
    {"label": "Sponsor Benchmark",      "icon": "🏢", "key": "sponsor_benchmark"},
    {"label": "Trial Design",           "icon": "📐", "key": "trial_design"},
    {"label": "Planned Endpoints",      "icon": "🎯", "key": "planned_endpoints"},
    {"label": "Reported Outcomes",      "icon": "📊", "key": "reported_outcomes"},
    {"label": "Outcome Scores",         "icon": "📈", "key": "outcome_scores"},
    {"label": "PRO Overview",           "icon": "👤", "key": "pro_overview"},
    {"label": "PRO Domains",            "icon": "🧩", "key": "pro_domains"},
    {"label": "Trial Groups",           "icon": "👥", "key": "trial_groups"},
    {"label": "Safety Analysis",        "icon": "🛡️", "key": "safety_analysis"},
    {"label": "Ask the Data",           "icon": "💬", "key": "ask_the_data"},
]
