"""
REAL WORLD SAFETY page.
Post-market spontaneous adverse event reports from FDA FAERS.
"""
from __future__ import annotations

import streamlit as st

from components.alerts import filter_required_callout, info_callout, no_data_callout
from components.chart_tile import chart_tile
from components.charts import bar_chart, donut_chart, heatmap_chart
from components.filter_summary import filter_summary_bar
from components.page_header import page_header
from components.tables import ag_table, csv_download_button
from data.repository import (
    get_faers_brand_scope,
    get_outcome_brand_heatmap,
    get_outcomes_distribution,
    get_reaction_brand_heatmap,
    get_reactions_by_soc,
    get_top_reactions,
)
from utils.filters import FilterState


def render(filters: FilterState) -> None:
    page_header(
        title="Real World Safety",
        subtitle="Post-market spontaneous safety reports from FDA FAERS.",
        icon="🌐",
        breadcrumb="Home > Real World Safety",
    )
    filter_summary_bar(filters)

    if not filters.has_any_filter():
        filter_required_callout(
            "Select at least one filter in the sidebar to view FAERS charts and data."
        )
        return

    with st.spinner("Resolving drugs..."):
        brands, resolution_note = get_faers_brand_scope(filters)

    if resolution_note:
        info_callout(resolution_note, title="Drug Resolution")

    if not brands:
        no_data_callout("FAERS data for the current filters")
        return

    tab_ae, tab_soc, tab_outcomes = st.tabs([
        "⚠️ Adverse Events",
        "🫀 SOC",
        "📋 Outcomes",
    ])

    with tab_ae:
        with st.spinner("Loading adverse event data..."):
            top_rx_df = get_top_reactions(brands, limit=20)
            heatmap_df = get_reaction_brand_heatmap(brands, limit=10)

        if top_rx_df.empty:
            no_data_callout("reaction data")
        else:
            c1, c2 = st.columns(2)
            with c1:
                pt_bar = bar_chart(
                    top_rx_df,
                    x="pt",
                    y="report_count",
                    title="PT by Case Count",
                )
                pt_bar.update_layout(margin=dict(l=12, r=20, t=65, b=40))
                chart_tile(
                    pt_bar,
                    height=480,
                )
            with c2:
                if heatmap_df.empty:
                    no_data_callout("drug-by-AE heatmap data")
                else:
                    chart_tile(
                        heatmap_chart(
                            heatmap_df,
                            title="Top 10 Drugs × Top 10 AEs by Case Count",
                            x_label="Adverse Event",
                            y_label="Drug",
                            height=420,
                        ),
                        height=480,
                    )
            ag_table(top_rx_df, height=360, key="faers_top_reactions_table")
            csv_download_button(top_rx_df, "top_reactions.csv")

    with tab_soc:
        with st.spinner("Loading SOC data..."):
            soc_df = get_reactions_by_soc(brands)

        if soc_df.empty:
            no_data_callout("SOC data")
        else:
            soc_bar = bar_chart(
                soc_df.head(20),
                x="soc",
                y="report_count",
                title="SOC by Case Count",
            )
            soc_bar.update_layout(margin=dict(l=12, r=20, t=65, b=40))
            chart_tile(
                soc_bar,
                height=480,
            )
            ag_table(soc_df, height=360, key="faers_soc_table")
            csv_download_button(soc_df, "reactions_by_soc.csv")

    with tab_outcomes:
        with st.spinner("Loading outcome data..."):
            outc_df = get_outcomes_distribution(brands)
            heatmap_df = get_outcome_brand_heatmap(brands, limit=10)

        if outc_df.empty:
            no_data_callout("outcome data")
        else:
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(
                    donut_chart(
                        outc_df,
                        names="outcome_label",
                        values="report_count",
                        title="Outcome Distribution",
                    ),
                    height=420,
                )
            with c2:
                if heatmap_df.empty:
                    no_data_callout("outcome-by-drug heatmap data")
                else:
                    chart_tile(
                        heatmap_chart(
                            heatmap_df,
                            title="Top 10 Drugs × Outcomes by Case Count",
                            x_label="Outcome",
                            y_label="Drug",
                            height=420,
                        ),
                        height=420,
                    )
            ag_table(outc_df, height=360, key="faers_outcomes_table")
            csv_download_button(outc_df, "outcomes.csv")
