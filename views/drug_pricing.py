"""
DRUG PRICING page.
Annual cost trends and WAC unit price history scoped by the active filters.
"""
from __future__ import annotations
import plotly.express as px
import streamlit as st

from components.page_header import page_header
from components.metric_cards import kpi_row
from components.filter_summary import filter_summary_bar
from components.charts import bar_chart
from components.chart_tile import chart_tile
from components.alerts import no_data_callout, filter_required_callout
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from utils.formatting import fmt_number
from data.repository import (
    get_pricing_kpis,
    get_annual_cost_per_brand_over_time,
    get_annual_cost_by_drug_class,
    get_wac_price_history,
    get_annual_pricing_raw,
)
from config.settings import CATEGORICAL_PALETTE
from services.ai_summary import build_drug_pricing_context, generate_summary, filter_hash


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_currency(value: float | None) -> str:
    """Format a dollar value as $1.2M, $450K, or $1,234."""
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:,.0f}"


def _fmt_pct_change(pct: float | None) -> str:
    """Format a percentage change with sign."""
    if pct is None:
        return ""
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}% YoY"


# ── Multi-brand chart helpers (not in shared helpers — pricing-specific) ──────

_CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans, system-ui, sans-serif", size=12, color="#1A1A2E"),
    height=380,
    hoverlabel=dict(bgcolor="white", font_size=12),
    legend=dict(
        orientation="h",
        yanchor="bottom", y=1.02,
        xanchor="right", x=1,
        font=dict(size=10),
        tracegroupgap=2,
        itemsizing="constant",
    ),
)

_XAXIS = dict(showgrid=False, showline=True, linecolor="#E5E7EB",
              tickfont=dict(size=11), automargin=True)
_YAXIS = dict(showgrid=True, gridcolor="#F3F4F6", gridwidth=1,
              showline=True, linecolor="#E5E7EB", tickfont=dict(size=11),
              automargin=True)


def _apply_layout(fig, overrides: dict) -> None:
    """Merge _CHART_LAYOUT with overrides (overrides win) and apply once."""
    fig.update_layout(**{**_CHART_LAYOUT, **overrides})


def _cost_per_brand_step_chart(df) -> object:
    """Step-line chart showing annual cost over time with one line per brand."""
    import plotly.graph_objects as go
    if df.empty:
        fig = go.Figure()
        _apply_layout(fig, {"title": dict(text="Annual Cost Over Time per Drug",
                                          font=dict(size=14, color="#0F4C81"))})
        return fig

    fig = px.line(
        df,
        x="quarter_start",
        y="total_cost",
        color="brand_name",
        line_shape="hv",
        color_discrete_sequence=CATEGORICAL_PALETTE,
        labels={
            "quarter_start": "Quarter",
            "total_cost":    "Annual Cost ($)",
            "brand_name":    "Drug",
        },
    )
    fig.update_traces(line_width=2.5)
    _apply_layout(fig, {
        "height": 440,
        "margin": dict(l=40, r=160, t=50, b=40),
        "legend": dict(
            orientation="v",
            yanchor="top",  y=1,
            xanchor="left", x=1.02,
            font=dict(size=10),
            tracegroupgap=2,
            itemsizing="constant",
        ),
        "title": dict(text="Annual Cost Over Time per Drug",
                      font=dict(size=14, color="#0F4C81")),
    })
    fig.update_xaxes(**_XAXIS)
    fig.update_yaxes(**_YAXIS, tickprefix="$")
    return fig


def _wac_line_chart(df) -> object:
    """Multi-brand WAC unit price line chart."""
    import plotly.graph_objects as go
    if df.empty:
        fig = go.Figure()
        _apply_layout(fig, {"title": dict(text="WAC Unit Price History",
                                          font=dict(size=14, color="#0F4C81"))})
        return fig

    fig = px.line(
        df,
        x="wac_unit_effective_date",
        y="wac_unit_price",
        color="brand_name",
        color_discrete_sequence=CATEGORICAL_PALETTE,
        labels={
            "wac_unit_effective_date": "Effective Date",
            "wac_unit_price":          "WAC Unit Price ($)",
            "brand_name":              "Brand",
            "ndc":                     "NDC",
        },
        hover_data=["ndc"],
    )
    fig.update_traces(line_width=2, mode="lines+markers", marker_size=4)
    _apply_layout(fig, {
        "margin": dict(l=40, r=160, t=50, b=40),
        "legend": dict(
            orientation="v",
            yanchor="top",  y=1,
            xanchor="left", x=1.02,
            font=dict(size=10),
            tracegroupgap=2,
            itemsizing="constant",
        ),
        "title": dict(text="WAC Unit Price History", font=dict(size=14, color="#0F4C81")),
    })
    fig.update_xaxes(**_XAXIS)
    fig.update_yaxes(**_YAXIS, tickprefix="$")
    return fig


# ── Main render ───────────────────────────────────────────────────────────────

def render(filters: FilterState) -> None:
    page_header(
        title="Drug Pricing",
        subtitle="Annual cost trends and WAC unit price history for the active filter scope.",
        icon="💰",
        breadcrumb="Home > Drug Pricing",
    )
    filter_summary_bar(filters)

    # Always load KPIs — they show database-wide counts even without a filter.
    with st.spinner("Loading pricing data…"):
        kpis = get_pricing_kpis(filters)

    if kpis["unique_drugs"] == 0:
        no_data_callout("pricing data for the current filters")
        return

    # ── KPI row ───────────────────────────────────────────────────────────────
    latest_qtr_label = kpis["latest_quarter"] or "—"
    pct_delta = _fmt_pct_change(kpis["price_change_pct"])

    kpi_row([
        {"label": "Unique Drugs",      "value": fmt_number(kpis["unique_drugs"]),    "icon": "💊"},
        {"label": "Dosage Forms",      "value": fmt_number(kpis["dosage_forms"]),    "icon": "🧪"},
        {"label": "Unique Diseases",   "value": fmt_number(kpis["unique_diseases"]), "icon": "🔬"},
        {
            "label": f"Avg Annual Cost ({latest_qtr_label})",
            "value": _fmt_currency(kpis["latest_avg_cost"]),
            "icon": "💰",
            **({"delta": pct_delta} if pct_delta else {}),
        },
    ])
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts + table: require at least one active filter ────────────────────
    if not filters.has_any_filter():
        filter_required_callout(
            "Select at least one filter in the sidebar to view pricing charts and data."
        )
        return

    with st.spinner("Loading pricing charts…"):
        brand_cost_df  = get_annual_cost_per_brand_over_time(filters)
        drug_class_df  = get_annual_cost_by_drug_class(filters)
        wac_df         = get_wac_price_history(filters)
        raw_df         = get_annual_pricing_raw(filters)

    # ── Tabs: one chart per tab ───────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Cost Over Time",
        "🏷️ By Drug Class",
        "💲 WAC Price History",
        "📄 Raw Data",
    ])

    with tab1:
        if brand_cost_df.empty:
            no_data_callout("cost-over-time data")
        else:
            chart_tile(
                _cost_per_brand_step_chart(brand_cost_df),
                subtitle="Step-line per drug — quarterly total annual cost",
            )

    with tab2:
        if drug_class_df.empty:
            no_data_callout("drug class data")
        else:
            chart_tile(
                bar_chart(drug_class_df, x="drug_class", y="avg_cost",
                          title="Avg Latest Annual Cost by Drug Class",
                          orientation="h"),
                subtitle="Average annual cost per brand within each ATC class (latest quarter)",
            )

    with tab3:
        if wac_df.empty:
            no_data_callout("WAC price history data")
        else:
            chart_tile(
                _wac_line_chart(wac_df),
                subtitle="Average WAC unit price per brand over time",
            )

    with tab4:
        if raw_df.empty:
            no_data_callout("raw pricing records for the current filters")
        else:
            display_df = raw_df.rename(columns={
                "brand_name":        "Brand Name",
                "disease":           "Disease",
                "dosage_form":       "Dosage Form",
                "quarter_start":     "Quarter Start",
                "total_cost_filled": "Total Annual Cost ($)",
            })
            ag_table(display_df, key="pricing_raw_table")
            csv_download_button(display_df, filename="drug_pricing.csv")

    # ── AI Summary button ──────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    _render_ai_summary(filters, kpis, brand_cost_df, drug_class_df, wac_df)


# ── AI Summary helpers ─────────────────────────────────────────────────────────

def _render_ai_summary(filters, kpis, brand_cost_df, drug_class_df, wac_df):
    """Render the AI Summary button and result card for the Drug Pricing page."""
    _, btn_col = st.columns([4, 1])

    with btn_col:
        if filters.has_any_filter():
            clicked = st.button(
                "🤖 AI Summary",
                use_container_width=True,
                key="pricing_ai_btn",
                help="Generate an AI-powered analyst summary of the current pricing data.",
            )
        else:
            st.caption("Apply a filter to enable AI Summary.")
            clicked = False

    if clicked:
        current_hash = filter_hash(filters)
        if st.session_state.get("pricing_summary_hash") != current_hash:
            with st.spinner("Generating AI summary…"):
                context = build_drug_pricing_context(
                    kpis, brand_cost_df, drug_class_df, wac_df, filters
                )
                summary = generate_summary(context, page_name="Drug Pricing")
            if summary:
                st.session_state["pricing_ai_summary"] = summary
                st.session_state["pricing_summary_hash"] = current_hash

    # Clear cached summary if filters have changed
    current_hash = filter_hash(filters)
    if (
        "pricing_summary_hash" in st.session_state
        and st.session_state["pricing_summary_hash"] != current_hash
    ):
        st.session_state.pop("pricing_ai_summary", None)
        st.session_state.pop("pricing_summary_hash", None)

    if st.session_state.get("pricing_ai_summary"):
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
        st.markdown(st.session_state["pricing_ai_summary"])
        st.markdown("</div>", unsafe_allow_html=True)
