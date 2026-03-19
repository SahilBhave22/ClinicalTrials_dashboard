"""
PRO OVERVIEW page.
Planned and reported PRO instrument usage analysis.
"""
from __future__ import annotations
import streamlit as st

from components.page_header import page_header
from components.metric_cards import kpi_row
from components.filter_summary import filter_summary_bar
from components.charts import bar_chart, stacked_bar, donut_chart, funnel_chart
from components.chart_tile import chart_tile
from components.alerts import no_data_callout
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from services.pro_analysis import (
    aggregate_pro_usage,
    top_instruments,
    planned_vs_reported_pivot,
)
from data.repository import (
    get_pro_usage,
    get_pro_by_sponsor,
    get_pro_by_phase,
    get_reported_pro_funnel,
)


def render(filters: FilterState) -> None:
    page_header(
        title="PRO Overview",
        subtitle="Patient-reported outcome instrument adoption: planned vs reported, by sponsor, and by phase.",
        icon="👤",
        breadcrumb="Home > PRO Overview",
    )
    filter_summary_bar(filters)

    with st.spinner("Loading PRO data…"):
        raw_df     = get_pro_usage(filters)
        sp_df      = get_pro_by_sponsor(filters, limit=15)
        phase_df   = get_pro_by_phase(filters)
        funnel_df  = get_reported_pro_funnel(filters)

    agg_df  = aggregate_pro_usage(raw_df)
    top_df  = top_instruments(agg_df, n=15)
    pivot_df = planned_vs_reported_pivot(raw_df)

    # ── KPIs ──────────────────────────────────────────────────────────────────
    # Use funnel_df for trial counts — it queries COUNT(DISTINCT nct_id) directly,
    # avoiding double-counting trials that use multiple PRO instruments.
    planned_n = reported_n = 0
    if not funnel_df.empty:
        planned_rows  = funnel_df[funnel_df["stage"] == "Planned PROs"]
        reported_rows = funnel_df[funnel_df["stage"] == "Reported PROs"]
        planned_n  = int(planned_rows["trial_count"].iloc[0])  if not planned_rows.empty  else 0
        reported_n = int(reported_rows["trial_count"].iloc[0]) if not reported_rows.empty else 0
    unique_instr = len(agg_df) if not agg_df.empty else 0

    kpi_row([
        {"label": "Unique PRO Instruments", "value": unique_instr,  "icon": "📋"},
        {"label": "Trials with Planned PRO","value": planned_n,     "icon": "📝"},
        {"label": "Trials with Reported PRO","value": reported_n,   "icon": "✅"},
    ])
    st.markdown("<br>", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Instrument Frequency", "📋 Planned vs Reported",
        "🏢 By Sponsor", "📐 By Phase"
    ])

    with tab1:
        if top_df.empty:
            no_data_callout("PRO instruments")
        else:
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(bar_chart(top_df, "instrument_name", "total",
                                     orientation="h", title="Top PRO Instruments (Total)"))
            with c2:
                chart_tile(donut_chart(top_df.head(10), "instrument_name", "total",
                                       title="Instrument Share (Top 10)"))
            csv_download_button(top_df, "pro_instruments.csv")

    with tab2:
        if not funnel_df.empty:
            chart_tile(funnel_chart(funnel_df, y="stage", x="trial_count",
                                    title="Planned → Reported PRO Funnel"))
        if not pivot_df.empty:
            chart_tile(stacked_bar(pivot_df.head(60), "instrument_name", "trial_count",
                                   "stage", title="Planned vs Reported by Instrument"))

    with tab3:
        if sp_df.empty:
            no_data_callout("sponsor PRO data")
        else:
            # sponsor_total is COUNT(DISTINCT nct_id) per sponsor from the SQL CTE —
            # deduplicates trials that appear under multiple instruments.
            sp_agg = (
                sp_df.drop_duplicates("sponsor")[["sponsor", "sponsor_total"]]
                .rename(columns={"sponsor_total": "trial_count"})
                .sort_values("trial_count", ascending=False).head(15)
            )
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(bar_chart(sp_agg, "sponsor", "trial_count",
                                     orientation="h", title="PRO Adoption by Sponsor"))
            with c2:
                from services.analytics import pivot_heatmap
                from components.charts import heatmap_chart
                sp_top15 = sp_agg["sponsor"].head(12).tolist()
                sp_heat = sp_df[sp_df["sponsor"].isin(sp_top15)]
                pivot = pivot_heatmap(sp_heat, "sponsor", "instrument_name", "trial_count")
                if not pivot.empty:
                    chart_tile(heatmap_chart(pivot, title="Sponsor × Instrument Heatmap",
                                             x_label="Instrument", y_label="Sponsor"))

    with tab4:
        if phase_df.empty:
            no_data_callout("phase PRO data")
        else:
            chart_tile(bar_chart(phase_df, "phase", "pro_trials",
                                 title="Trials with Planned PROs by Phase"))

    # ── Full table ────────────────────────────────────────────────────────────
    st.markdown("---")
    if not agg_df.empty:
        st.markdown("#### PRO Instrument Details")
        ag_table(agg_df, height=350, key="pro_overview_table")
        csv_download_button(agg_df, "pro_overview.csv")
