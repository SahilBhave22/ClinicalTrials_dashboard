"""
PLANNED ENDPOINTS page.
Protocol-level design outcomes analysis.
"""
from __future__ import annotations
import streamlit as st

from components.page_header import page_header
from components.filter_summary import filter_summary_bar
from components.charts import bar_chart, funnel_chart, heatmap_chart
from components.chart_tile import chart_tile
from components.alerts import no_data_callout, filter_required_callout
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from data.repository import (
    get_design_outcome_type_category_heatmap,
    get_top_design_endpoints,
    get_reported_pro_funnel,
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
        heatmap_df = get_design_outcome_type_category_heatmap(filters)
        top_ep_df  = get_top_design_endpoints(filters, limit=10)
        funnel_df  = get_reported_pro_funnel(filters)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Outcome Types", "🔢 Top Endpoints", "👤 Planned PROs", "📄 Full Table"
    ])

    with tab1:
        if heatmap_df.empty:
            no_data_callout("outcome type distribution")
        else:
            chart_tile(heatmap_chart(
                heatmap_df,
                title="Outcome Type × Category (Unique Trials)",
                x_label="Outcome Category",
                y_label="Outcome Type",
            ))

    with tab2:
        if top_ep_df.empty:
            no_data_callout("endpoints")
        else:
            chart_tile(bar_chart(top_ep_df.head(10), "outcome_category", "trial_count",
                                 orientation="h", title="Top 10 Planned Endpoint Categories by Frequency"))
            csv_download_button(top_ep_df, "top_endpoints.csv")

    with tab3:
        if not funnel_df.empty:
            stage_order = {"Planned PROs": 0, "Reported PROs": 1}
            funnel_sorted = funnel_df.sort_values(
                "stage", key=lambda s: s.map(stage_order)
            ).reset_index(drop=True)
            chart_tile(funnel_chart(funnel_sorted, y="stage", x="trial_count",
                                    title="Planned vs Reported PRO Funnel"))
            c1, c2 = st.columns(2)
            for _, row in funnel_sorted.iterrows():
                with (c1 if row["stage"] == "Planned PROs" else c2):
                    st.metric(row["stage"], int(row["trial_count"]))
        else:
            no_data_callout("PRO funnel")

    with tab4:
        full_df = get_design_outcomes(filters)
        if full_df.empty:
            no_data_callout("design outcomes")
        else:
            ag_table(full_df, height=500, key="ep_full_table")
            csv_download_button(full_df, "design_outcomes.csv")
