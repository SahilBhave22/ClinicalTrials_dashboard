"""
MARKET ACCESS page.
Formulary tier and utilization-management requirement data for 2025 and 2026
across six major US payers, scoped by the active brand/drug filters.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.page_header import page_header
from components.metric_cards import kpi_row
from components.filter_summary import filter_summary_bar
from components.alerts import no_data_callout, filter_required_callout
from utils.filters import FilterState
from utils.formatting import fmt_number
from data.repository import get_ma_kpis, get_ma_tier_grid, get_ma_req_grid
from services.ai_summary import build_market_access_context, generate_summary, filter_hash


# ── Ordered payer columns ─────────────────────────────────────────────────────
_PAYERS      = ["Aetna", "Cigna", "UnitedHealthcare", "Kaiser", "OptumRx", "Anthem"]
_TIER_COLS   = ["aetna_tier", "cigna_tier", "united_tier", "kaiser_tier", "optum_tier", "anthem_tier"]
_REQ_COLS    = ["aetna_req",  "cigna_req",  "united_req",  "kaiser_req",  "optum_req",  "anthem_req"]

# ── Shared Plotly layout defaults ─────────────────────────────────────────────
_BASE_LAYOUT = dict(
    font=dict(family="DM Sans, system-ui, sans-serif", size=12, color="#1A1A2E"),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    hoverlabel=dict(bgcolor="white", font_size=12),
)

# ── Discrete 5-band tier colorscale (0=NC … 4=Tier4+) ────────────────────────
# Each band occupies 1/5 of the [0, 5] z-range.
_TIER_COLORSCALE = [
    [0 / 5, "#9CA3AF"], [1 / 5, "#9CA3AF"],   # 0 = Not Covered  (gray)
    [1 / 5, "#2A9D8F"], [2 / 5, "#2A9D8F"],   # 1 = Tier 1       (teal)
    [2 / 5, "#2E86AB"], [3 / 5, "#2E86AB"],   # 2 = Tier 2       (blue)
    [3 / 5, "#F18F01"], [4 / 5, "#F18F01"],   # 3 = Tier 3       (amber)
    [4 / 5, "#E76F51"], [5 / 5, "#E76F51"],   # 4 = Tier 4+      (coral)
]


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _parse_tier(val) -> tuple[int, str]:
    """Map a raw tier cell value to (numeric_z_for_colorscale, display_label)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0, "NC"
    s = str(val).strip()
    if s == "" or s.upper() in {"NC", "N/A", "NOT COVERED"}:
        return 0, "NC"
    try:
        n = int(float(s))
        return min(n, 4), str(n) if n <= 4 else "4+"
    except ValueError:
        # Non-numeric text (e.g. "NF", "EX") — treat as not covered
        return 0, s[:4]


def _tier_chart(df: pd.DataFrame, year: int) -> go.Figure:
    """
    Categorical heatmap: drugs on rows, payers on columns.
    Each cell is coloured by tier (discrete palette) and annotated with the tier value.
    """
    brands = df["brand_name"].tolist()

    z, text = [], []
    for _, row in df.iterrows():
        z_row, t_row = [], []
        for col in _TIER_COLS:
            num, label = _parse_tier(row.get(col))
            z_row.append(num)
            t_row.append(label)
        z.append(z_row)
        text.append(t_row)

    height = max(420, len(brands) * 28 + 160)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=_PAYERS,
        y=brands,
        text=text,
        texttemplate="%{text}",
        textfont=dict(color="white", size=12, family="DM Sans, system-ui, sans-serif"),
        colorscale=_TIER_COLORSCALE,
        zmin=0,
        zmax=5,
        colorbar=dict(
            title=dict(text="Tier", font=dict(size=12), side="right"),
            tickvals=[0.5, 1.5, 2.5, 3.5, 4.5],
            ticktext=["NC", "Tier 1", "Tier 2", "Tier 3", "Tier 4+"],
            lenmode="fraction",
            len=0.55,
            thickness=14,
        ),
        hovertemplate="%{y}<br>%{x}: <b>%{text}</b><extra></extra>",
    ))
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(
            text=f"Formulary Tiers by Drug & Payer ({year})",
            font=dict(size=14, color="#0F4C81"),
        ),
        height=height,
        margin=dict(l=180, r=100, t=60, b=40),
        xaxis=dict(
            side="top",
            tickfont=dict(size=12),
            showgrid=False,
            linecolor="#E5E7EB",
        ),
        yaxis=dict(
            autorange="reversed",
            tickfont=dict(size=11),
            showgrid=False,
            linecolor="#E5E7EB",
        ),
    )
    return fig


def _req_chart(df: pd.DataFrame, req_type: str, year: int) -> go.Figure:
    """
    Grid-style checkbox chart: drugs on rows, payers on columns.
    Green cell (✓) = payer applies the selected requirement (PA / QL / SP).
    White cell = no requirement. Cell gaps render as a visible grid.
    """
    brands = df["brand_name"].tolist()
    rt = req_type.upper()

    z, text = [], []
    for _, row in df.iterrows():
        z_row, t_row = [], []
        for col in _REQ_COLS:
            raw = row.get(col)
            val = str(raw).upper() if pd.notna(raw) else ""
            has_it = rt in val
            z_row.append(1 if has_it else 0)
            t_row.append("✓" if has_it else "")
        z.append(z_row)
        text.append(t_row)

    height = max(420, len(brands) * 30 + 160)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=_PAYERS,
        y=brands,
        text=text,
        texttemplate="%{text}",
        textfont=dict(color="white", size=16, family="DM Sans, system-ui, sans-serif"),
        colorscale=[[0, "#FFFFFF"], [1, "#2A9D8F"]],   # white = no req, green = req present
        zmin=0,
        zmax=1,
        showscale=False,
        xgap=3,   # gap between columns → forms vertical grid lines
        ygap=3,   # gap between rows    → forms horizontal grid lines
        hovertemplate="%{y}<br>%{x}: <b>" + req_type + " %{text}</b><extra></extra>",
    ))
    fig.update_layout(
        **{**_BASE_LAYOUT, "paper_bgcolor": "#E5E7EB"},
        title=dict(
            text=f"{req_type} Requirement by Drug & Payer ({year})",
            font=dict(size=14, color="#0F4C81"),
        ),
        height=height,
        margin=dict(l=180, r=40, t=60, b=40),
        xaxis=dict(
            side="top",
            tickfont=dict(size=12),
            showgrid=False,
            linecolor="#E5E7EB",
        ),
        yaxis=dict(
            autorange="reversed",
            tickfont=dict(size=11),
            showgrid=False,
            linecolor="#E5E7EB",
        ),
    )
    return fig


# ── Main render ───────────────────────────────────────────────────────────────

def render(filters: FilterState) -> None:
    page_header(
        title="Market Access",
        subtitle="Formulary tier and utilization-management requirements across 6 major US payers (2025 & 2026).",
        icon="🏥",
        breadcrumb="Home > Market Access",
    )
    filter_summary_bar(filters)

    # ── Year selector ─────────────────────────────────────────────────────────
    year = st.radio(
        "Formulary Year",
        options=[2025, 2026],
        horizontal=True,
        index=0,
        key="ma_year_selector",
    )

    # ── KPI row — always shown ────────────────────────────────────────────────
    with st.spinner("Loading market access data…"):
        kpis = get_ma_kpis(filters, year=year)

    if kpis["total_drugs"] == 0:
        no_data_callout("market access data for the current filters")
        return

    kpi_row([
        {"label": "Drugs Tracked",        "value": fmt_number(kpis["total_drugs"]), "icon": "💊"},
        {"label": "With Prior Auth (PA)",  "value": f"{kpis['pa_pct']:.1f}%",        "icon": "📋"},
        {"label": "With Qty Limits (QL)",  "value": f"{kpis['ql_pct']:.1f}%",        "icon": "⚖️"},
        {"label": "With Specialty (SP)",   "value": f"{kpis['sp_pct']:.1f}%",        "icon": "🏥"},
        {"label": "Payers Covered",        "value": "6",                             "icon": "🏛️"},
    ])
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts: require at least one active filter ────────────────────────────
    if not filters.has_any_filter():
        filter_required_callout(
            "Select at least one filter in the sidebar to view market access charts."
        )
        return

    with st.spinner("Loading market access charts…"):
        tier_df = get_ma_tier_grid(filters, year=year)
        req_df  = get_ma_req_grid(filters, year=year)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab1, tab2 = st.tabs([
        "🎨 Formulary Tiers",
        "✅ Access Requirements",
    ])

    # ── Tab 1: Colour-coded tier grid ─────────────────────────────────────────
    with tab1:
        if tier_df.empty:
            no_data_callout("formulary tier data for the current filters")
        else:
            n = len(tier_df)
            st.caption(
                f"Showing {n} drug{'s' if n != 1 else ''} — "
                "each cell shows the formulary tier assigned by that payer. "
                "**NC** = Not Covered / not on formulary."
            )
            st.plotly_chart(
                _tier_chart(tier_df, year),
                use_container_width=True,
                key="ma_tier_chart",
            )

    # ── Tab 2: PA / QL / SP checkbox grid ────────────────────────────────────
    with tab2:
        if req_df.empty:
            no_data_callout("access requirement data for the current filters")
        else:
            req_type = st.radio(
                "Requirement type",
                options=["PA", "QL", "SP"],
                format_func=lambda x: {
                    "PA": "PA — Prior Authorization",
                    "QL": "QL — Quantity Limit",
                    "SP": "SP — Specialty Pharmacy",
                }[x],
                horizontal=True,
                key="ma_req_type",
            )
            n = len(req_df)
            st.caption(
                f"Showing {n} drug{'s' if n != 1 else ''} — "
                f"**✓** = payer applies **{req_type}** requirement for that drug. "
                f"Empty cell = no {req_type} requirement."
            )
            st.plotly_chart(
                _req_chart(req_df, req_type, year),
                use_container_width=True,
                key="ma_req_chart",
            )

    # ── AI Summary button ──────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    _render_ai_summary(filters, kpis, tier_df, req_df, year)


# ── AI Summary helpers ─────────────────────────────────────────────────────────

def _render_ai_summary(filters, kpis, tier_df, req_df, year):
    """Render the AI Summary button and result card for the Market Access page."""
    _, btn_col = st.columns([4, 1])

    with btn_col:
        if filters.has_any_filter():
            clicked = st.button(
                "🤖 AI Summary",
                use_container_width=True,
                key="ma_ai_btn",
                help="Generate an AI-powered analyst summary of the current market access data.",
            )
        else:
            st.caption("Apply a filter to enable AI Summary.")
            clicked = False

    if clicked:
        current_hash = filter_hash(filters)
        if st.session_state.get("ma_summary_hash") != current_hash:
            with st.spinner("Generating AI summary…"):
                context = build_market_access_context(kpis, tier_df, req_df, year, filters)
                summary = generate_summary(context, page_name="Market Access")
            if summary:
                st.session_state["ma_ai_summary"] = summary
                st.session_state["ma_summary_hash"] = current_hash

    # Clear cached summary if filters have changed
    current_hash = filter_hash(filters)
    if (
        "ma_summary_hash" in st.session_state
        and st.session_state["ma_summary_hash"] != current_hash
    ):
        st.session_state.pop("ma_ai_summary", None)
        st.session_state.pop("ma_summary_hash", None)

    if st.session_state.get("ma_ai_summary"):
        st.markdown(
            """
            <div style="
                background: white;
                border: 1px solid #E5E7EB;
                border-left: 4px solid #0F4C81;
                border-radius: 12px;
                padding: 24px 28px;
                margin: 8px 0 24px 0;
                box-shadow: 0 1px 3px rgba(0,0,0,0.06);
            ">
            <div style="
                font-size: 11px;
                color: #6B7280;
                font-weight: 600;
                letter-spacing: 0.05em;
                text-transform: uppercase;
                margin-bottom: 16px;
            ">
                🤖 AI Generated &nbsp;·&nbsp; GPT-4o &nbsp;·&nbsp; Based on current filters
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(st.session_state["ma_ai_summary"])
        st.markdown("</div>", unsafe_allow_html=True)
