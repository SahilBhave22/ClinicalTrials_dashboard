# Design System & UI Standards

This project is a **Streamlit analytics dashboard**. All UI work must follow the design system defined below. Do not deviate from colours, typography, spacing, or component patterns without being explicitly asked.

---

## Stack

- **Framework**: Streamlit (`st.set_page_config(layout="wide", initial_sidebar_state="expanded")`)
- **Charts**: Plotly Express / Plotly Graph Objects via reusable helpers
- **Styling**: Inline CSS injected via `st.markdown(..., unsafe_allow_html=True)` at app startup

---

## Typography

- Typeface: **DM Sans** (Google Fonts), applied globally via `@import` in the startup CSS block.
- Apply to: `html, body, [class*="css"]`
- All Plotly charts must set `font_family="DM Sans, system-ui, sans-serif"` in their layout.

---

## Colour Palette

Always import colours from a central `config/settings.py` — never hardcode hex values in view files.

```python
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
```

Page background: `#F8FAFC`. All `h1`/`h2`/`h3` headings: `#0F4C81`.

---

## Global CSS (injected once in `app.py`)

```css
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', system-ui, sans-serif; }
.stApp { background: #F8FAFC; }

/* Sidebar */
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
    background-color: #0F4C81 !important; color: white !important; border-radius: 6px !important;
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
section[data-testid="stSidebar"] .streamlit-expanderHeader { color: #E2E8F0 !important; font-weight: 500; }

/* Tab navigation */
.stTabs [data-baseweb="tab-list"] {
    gap: 0px; background: white; border-radius: 12px; padding: 4px; border: 1px solid #E5E7EB;
}
.stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 8px 20px; font-weight: 500; font-size: 14px; }
.stTabs [aria-selected="true"] { background: #0F4C81 !important; color: white !important; }

/* Charts & tables */
div[data-testid="stDataFrame"] { border: 1px solid #E5E7EB; border-radius: 8px; }
.stPlotlyChart {
    background: white; border-radius: 12px; border: 1px solid #E5E7EB;
    padding: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
h1, h2, h3 { color: #0F4C81; }

/* Download button */
.stDownloadButton > button { background: #0F4C81; color: white; border: none; border-radius: 8px; }
```

---

## App Structure

```
app.py                  ← page config, global CSS, sidebar, tab router
config/settings.py      ← COLORS and all constants
components/
    metric_cards.py     ← metric_row(), section_header()
    filters.py          ← render_sidebar_filters()
    tables.py           ← show_table()
utils/
    charts.py           ← all Plotly helpers
    filters.py          ← get_filter_options(), apply_filters(), init_filters(), reset_filters()
    formatting.py       ← fmt_number(), fmt_pct()
views/
    <page>.py           ← one file per tab, each exposes render()
```

### Tab navigation pattern

```python
PAGE_MAP = {"🏠 Home": home_module, "📊 Analytics": analytics_module, ...}
tabs = st.tabs(list(PAGE_MAP.keys()))
for tab, (label, module) in zip(tabs, PAGE_MAP.items()):
    with tab:
        try:
            module.render()
        except Exception as e:
            st.error(f"Error loading {label}: {e}")
            st.exception(e)
```

### Sidebar structure

```python
with st.sidebar:
    # 1. Logo / branding header (centred, white text)
    # 2. st.markdown("---")
    # 3. render_sidebar_filters(repo)
    # 4. st.markdown("---")
    # 5. Footer (muted, 11px, centred): "Demo Mode · v1.0.0"
```

---

## Component Patterns

### KPI metric cards — `metric_row(metrics, columns)`

```python
# Each metric dict: {"label": str, "value": str|int|float, "icon": str, "delta": str (optional)}
# Renders a white card per metric, laid out in st.columns(columns)
```

Card HTML template:
```html
<div style="background:white; border:1px solid #E5E7EB; border-radius:12px;
            padding:20px 24px; text-align:center; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
  <div style="font-size:13px; color:#6B7280; font-weight:500;
              letter-spacing:0.03em; text-transform:uppercase;">
      {icon} {label}
  </div>
  <div style="font-size:32px; font-weight:700; color:#0F4C81; margin-top:4px; line-height:1.1;">
      {value}
  </div>
  <!-- optional delta -->
  <div style="font-size:12px; color:#2A9D8F; margin-top:4px;">{delta}</div>
</div>
```

### Section headers — `section_header(title, subtitle="")`

```html
<div style="margin:28px 0 12px 0;">
  <h3 style="color:#0F4C81; font-weight:700; margin-bottom:2px; font-size:20px;">{title}</h3>
  <p style="color:#6B7280; font-size:14px; margin:0;">{subtitle}</p>
</div>
```

### Data tables — `show_table(df, title, key, max_rows=500, download=True)`

- `st.dataframe(df, use_container_width=True, hide_index=True, key=key)`
- Show `(1,234 rows — showing first 500)` note when truncated.
- Always include a **📥 Download CSV** button beneath.

---

## Chart Helpers (`utils/charts.py`)

All helpers call `apply_style(fig)` which sets:

```python
_LAYOUT_DEFAULTS = dict(
    font_family   = "DM Sans, system-ui, sans-serif",
    font_color    = "#1A1A2E",
    paper_bgcolor = "rgba(0,0,0,0)",
    plot_bgcolor  = "rgba(0,0,0,0)",
    margin        = dict(l=40, r=20, t=40, b=40),
    hoverlabel    = dict(bgcolor="white", font_size=12),
    legend        = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
# x-axis: showgrid=False, linecolor="#E5E7EB"
# y-axis: showgrid=True, gridcolor="#F3F4F6", linecolor="#E5E7EB"
```

Implement these helpers, all using `COLORS["chart_sequence"]`:
`bar_chart`, `line_chart`, `area_chart`, `pie_chart` (hole=0.45), `scatter_chart`, `box_chart`, `treemap_chart`, `sunburst_chart`, `heatmap_chart` (Blues scale), `funnel_chart`.

---

## Sidebar Filters — Cascading Pattern

Filter state lives entirely in `st.session_state.filters` (a plain dict initialised by `init_filters()`).

**Cascade rule:**
1. Render **top-level independent filters** first (their options come from static lookup dicts, not the DB). This updates `f["category"]` / `f["type"]` in session state immediately.
2. Call `get_filter_options(repo, f)` *after* those widgets to compute narrowed downstream options.
3. Render all remaining cascading filters using the narrowed options.

This ensures downstream dropdowns reflect the current top-level selection on the same Streamlit rerun — not one rerun behind.

```python
def _safe_default(current: list, available: list) -> list:
    """Drop previously-selected values no longer present in available options."""
    avail_set = set(available)
    return [v for v in current if v in avail_set]
```

Always include a full-width `🔄 Reset All Filters` button at the bottom, calling `reset_filters()` then `st.rerun()`. Wrap secondary filters in `st.expander("More filters", expanded=False)`.

---

## Formatting Rules

| Type | Format | Null |
|---|---|---|
| Integer counts | `1,234` (thousands sep) | `—` |
| Percentages | `12.3%` (1 decimal) | `—` |
| Floats | `1,234.56` | `—` |
| Status/phase strings | Title-cased via mapping dict | raw value as fallback |

---

## Layout Conventions

- Two-column chart rows: `col1, col2 = st.columns(2)`
- KPI rows: `st.columns(N)` where N = number of metrics
- Always pass `use_container_width=True` to `st.plotly_chart`
- Section spacing: 28px top margin, 12px below header before first chart
- Each view file exposes exactly one `render()` function; no global side-effects at import time
