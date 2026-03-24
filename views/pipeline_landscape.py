"""
PIPELINE LANDSCAPE page.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd

from components.page_header import page_header
from components.metric_cards import kpi_row
from components.filter_summary import filter_summary_bar
from components.charts import (
    bar_chart, treemap_chart, donut_chart, heatmap_chart,
)
from components.chart_tile import chart_tile
from components.alerts import no_data_callout, pipeline_data_note
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from services.pipeline_analysis import sponsor_indication_pivot
from data.repository import (
    get_pipeline_kpis,
    get_pipeline_by_sponsor,
    get_pipeline_by_indication,
    get_pipeline_top_interventions,
    get_pipeline_sponsor_indication_heatmap,
    get_pipeline_pro_usage,
    get_pipeline_trials_table,
)


def render(filters: FilterState) -> None:
    page_header(
        title="Pipeline Landscape",
        subtitle="Investigational asset landscape: sponsor activity, indication coverage, and pipeline PRO usage.",
        icon="🔬",
        breadcrumb="Home > Pipeline Landscape",
    )
    filter_summary_bar(filters)
    pipeline_data_note()

    ind = filters.indication_name
    sponsors = tuple(filters.sponsor)

    with st.spinner("Loading pipeline data…"):
        kpis = get_pipeline_kpis(ind, sponsors)

    # ── KPIs ──────────────────────────────────────────────────────────────────
    kpi_row([
        {"label": "Pipeline Trials",        "value": kpis["pipeline_trials"],    "icon": "🔬"},
        {"label": "Unique Assets",           "value": kpis["unique_assets"],      "icon": "💊"},
        {"label": "Active Sponsors",         "value": kpis["active_sponsors"],    "icon": "🏢"},
        {"label": "Indications Covered",     "value": kpis["indications_covered"],"icon": "🎯"},
        {"label": "With Planned PROs",       "value": kpis["with_pros"],          "icon": "👤"},
    ])
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🏢 By Sponsor", "🎯 By Indication", "💊 Interventions",
        "🗺️ Sponsor × Indication", "👤 PRO Usage"
    ])

    with tab1:
        sp_df = get_pipeline_by_sponsor(ind, sponsors, limit=20)
        if sp_df.empty:
            no_data_callout("pipeline sponsors")
        else:
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(bar_chart(sp_df, "sponsor", "pipeline_trials",
                                     orientation="h", title="Pipeline Trials by Sponsor"))
            with c2:
                chart_tile(bar_chart(sp_df, "sponsor", "unique_assets",
                                     orientation="h", title="Unique Assets by Sponsor"))
            csv_download_button(sp_df, "pipeline_sponsors.csv")

    with tab2:
        ind_df = get_pipeline_by_indication(ind, sponsors, limit=25)
        if ind_df.empty:
            no_data_callout("indications")
        else:
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(bar_chart(ind_df, "condition", "trial_count",
                                     orientation="h", title="Pipeline Trials by Indication"))
            with c2:
                chart_tile(treemap_chart(ind_df, path=["condition"],
                                         values="trial_count", title="Indication Treemap"))

    with tab3:
        intv_df = get_pipeline_top_interventions(ind, sponsors, limit=25)
        if intv_df.empty:
            no_data_callout("pipeline interventions")
        else:
            chart_tile(bar_chart(intv_df, "intervention", "trial_count",
                                 orientation="h", title="Top Pipeline Interventions"))
            csv_download_button(intv_df, "pipeline_interventions.csv")

    with tab4:
        heat_df = get_pipeline_sponsor_indication_heatmap(ind, sponsors)
        if not heat_df.empty:
            pivot = sponsor_indication_pivot(heat_df)
            if not pivot.empty:
                chart_tile(heatmap_chart(pivot, title="Sponsor × Indication Pipeline Heatmap",
                                         x_label="Indication", y_label="Sponsor"))
        else:
            no_data_callout("heatmap")

    with tab5:
        pro_df = get_pipeline_pro_usage(ind, sponsors, limit=20)
        if pro_df.empty:
            no_data_callout("pipeline PROs")
        else:
            chart_tile(bar_chart(pro_df, "instrument_name", "trial_count",
                                 orientation="h", title="Pipeline PRO Instrument Usage"))

    # ── Trial Table ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Pipeline Trial Details")
    trials_df = get_pipeline_trials_table(ind)
    if filters.sponsor:
        trials_df = trials_df[trials_df["sponsor_name"].isin(filters.sponsor)]
    if not trials_df.empty:
        ag_table(trials_df, height=420, key="pipeline_table")
        csv_download_button(trials_df, "pipeline_trials.csv")
