"""
PLANNED ENDPOINTS page.
Protocol-level design outcomes analysis.
"""
from __future__ import annotations
import streamlit as st

from components.page_header import page_header
from components.filter_summary import filter_summary_bar
from components.charts import bar_chart, donut_chart, stacked_bar
from components.chart_tile import chart_tile
from components.alerts import no_data_callout, filter_required_callout
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from data.repository import (
    get_design_outcome_type_dist,
    get_top_design_endpoints,
    get_planned_pro_usage,
    get_design_outcomes,
)


def render(filters: FilterState) -> None:
    page_header(
        title="Planned Endpoints",
        subtitle="Protocol-level endpoint design: outcome types, most common endpoints, and planned PRO instruments.",
        icon="🎯",
        breadcrumb="Home > Planned Endpoints",
    )
    filter_summary_bar(filters)

    if not filters.has_any_filter():
        filter_required_callout(
            "Please select at least one filter in the sidebar "
            "(indication, drug class, sponsor, phase, etc.) to view the charts."
        )
        return

    with st.spinner("Loading endpoint data…"):
        type_df   = get_design_outcome_type_dist(filters)
        top_ep_df = get_top_design_endpoints(filters, limit=25)
        pro_df    = get_planned_pro_usage(filters)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Outcome Types", "🔢 Top Endpoints", "👤 Planned PROs", "📄 Full Table"
    ])

    with tab1:
        if type_df.empty:
            no_data_callout("outcome type distribution")
        else:
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(donut_chart(type_df, "outcome_type", "endpoint_count",
                                       title="Endpoints by Type"))
            with c2:
                chart_tile(bar_chart(type_df, "outcome_type", "trial_count",
                                     title="Trials with Each Outcome Type"))

    with tab2:
        if top_ep_df.empty:
            no_data_callout("endpoints")
        else:
            chart_tile(bar_chart(top_ep_df.head(20), "outcome_category", "trial_count",
                                 orientation="h", title="Top 20 Planned Endpoint Categories by Frequency"))
            csv_download_button(top_ep_df, "top_endpoints.csv")

    with tab3:
        if pro_df.empty:
            no_data_callout("planned PROs")
        else:
            pro_agg = (
                pro_df.groupby("instrument_name")["trial_count"]
                .sum().reset_index()
                .sort_values("trial_count", ascending=False)
            )
            chart_tile(bar_chart(pro_agg, "instrument_name", "trial_count",
                                 orientation="h", title="Planned PRO Instruments"))
            st.markdown("##### PRO Instrument Usage by Phase")
            chart_tile(stacked_bar(pro_df, "instrument_name", "trial_count", "phase",
                                   title="PRO Instruments by Phase"))

    with tab4:
        full_df = get_design_outcomes(filters)
        if full_df.empty:
            no_data_callout("design outcomes")
        else:
            ag_table(full_df, height=500, key="ep_full_table")
            csv_download_button(full_df, "design_outcomes.csv")
