"""
DISEASE / COMPETITIVE LANDSCAPE page.
"""
from __future__ import annotations
import streamlit as st

from components.page_header import page_header
from components.metric_cards import kpi_row
from components.filter_summary import filter_summary_bar
from components.charts import (
    phase_bar, bar_chart, status_bar, area_chart,
    donut_chart, treemap_chart,
)
from components.chart_tile import chart_tile
from components.alerts import no_data_callout
from components.tables import csv_download_button, styled_table
from utils.filters import FilterState
from utils.formatting import fmt_number, fmt_pct
from data.repository import (
    get_landscape_kpis,
    get_trials_by_phase,
    get_sponsor_share,
    get_status_distribution,
    get_country_distribution,
    get_top_interventions,
    get_trials_over_time,
)


def render(filters: FilterState) -> None:
    page_header(
        title="Disease / Competitive Landscape",
        subtitle="Analyze the competitive trial landscape within the selected indication and drug class context.",
        icon="🗺️",
        breadcrumb="Home > Disease Landscape",
    )
    filter_summary_bar(filters)

    ind = filters.indication_name
    atc = filters.atc_class_name

    if not ind and not atc:
        st.info("**Tip:** Select an Indication or Drug Class in the sidebar to focus the landscape view.")

    with st.spinner("Loading landscape data…"):
        kpis = get_landscape_kpis(filters)

    # ── KPIs ──────────────────────────────────────────────────────────────────
    kpi_row([
        {"label": "Total Trials",        "value": kpis["total_trials"],       "icon": "🧪"},
        {"label": "Active Trials",       "value": kpis["active_trials"],      "icon": "🔵"},
        {"label": "Completed",           "value": kpis["completed_trials"],   "icon": "✅"},
        {"label": "% Completed",         "value": f"{kpis['pct_completed']}%","icon": "📊", "fmt": False},
        {"label": "With Results",        "value": kpis["with_results"],       "icon": "📋"},
        {"label": "Median Enrollment",   "value": kpis["median_enrollment"],  "icon": "👥"},
    ])
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📊 Phase & Status", "🏢 Sponsors", "🌍 Geography", "📈 Timeline"]
    )

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            phase_df = get_trials_by_phase(filters)
            if not phase_df.empty:
                chart_tile(phase_bar(phase_df, "phase", "trial_count", "Trials by Phase"))
        with c2:
            status_df = get_status_distribution(filters)
            if not status_df.empty:
                chart_tile(status_bar(status_df, "status", "trial_count", "Trials by Status"))

    with tab2:
        sp_df = get_sponsor_share(filters, limit=15)
        if sp_df.empty:
            no_data_callout("sponsors")
        else:
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(bar_chart(sp_df, "sponsor", "trial_count",
                                     orientation="h", title="Sponsor Trial Count"))
            with c2:
                chart_tile(donut_chart(sp_df.head(10), "sponsor", "trial_count",
                                       title="Sponsor Share (Top 10)"))
            csv_download_button(sp_df, "sponsor_share.csv", "⬇ Download Sponsor Data")

    with tab3:
        country_df = get_country_distribution(filters, limit=20)
        if country_df.empty:
            no_data_callout("geography")
        else:
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(bar_chart(country_df, "country", "trial_count",
                                     orientation="h", title="Top Countries"))
            with c2:
                chart_tile(treemap_chart(country_df, path=["country"],
                                         values="trial_count", title="Country Treemap"))

    with tab4:
        time_df = get_trials_over_time(filters)
        if not time_df.empty:
            import pandas as pd
            time_df["year"] = pd.to_datetime(time_df["year"]).dt.year
            chart_tile(area_chart(time_df, "year", "trial_count",
                                  title="Trials First Posted per Year"))

    # ── Intervention frequency ────────────────────────────────────────────────
    st.markdown("---")
    intv_df = get_top_interventions(filters, limit=20)
    if not intv_df.empty:
        chart_tile(bar_chart(intv_df, "intervention", "trial_count",
                             orientation="h", title="Top Drug Interventions in Context"))
        csv_download_button(intv_df, "interventions.csv")
    else:
        no_data_callout("interventions")
