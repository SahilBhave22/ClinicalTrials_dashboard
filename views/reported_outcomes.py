"""
REPORTED OUTCOMES page.
Posted outcomes and endpoint categories analysis.
"""
from __future__ import annotations
import streamlit as st

from components.page_header import page_header
from components.filter_summary import filter_summary_bar
from components.charts import bar_chart, donut_chart, funnel_chart, heatmap_chart
from components.chart_tile import chart_tile
from components.alerts import no_data_callout, filter_required_callout
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from data.repository import (
    get_reported_outcome_categories,
    get_outcome_type_category_heatmap,
    get_reported_pro_funnel,
)


def render(filters: FilterState) -> None:
    page_header(
        title="Reported Outcomes",
        subtitle="Analysis of posted result outcomes: category distributions, types, and top reported endpoints.",
        icon="📊",
        breadcrumb="Home > Reported Outcomes",
    )
    filter_summary_bar(filters)

    if not filters.has_any_filter():
        filter_required_callout(
            "Please select at least one filter in the sidebar "
            "(indication, drug class, sponsor, phase, etc.) to view the charts."
        )
        return

    with st.spinner("Loading reported outcome data…"):
        cat_df      = get_reported_outcome_categories(filters)
        heatmap_df  = get_outcome_type_category_heatmap(filters)
        funnel_df   = get_reported_pro_funnel(filters)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Categories", "📋 Outcome Types", "🔢 Top Outcomes", "👤 PRO Funnel"
    ])

    with tab1:
        if cat_df.empty:
            no_data_callout("outcome categories")
        else:
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(bar_chart(cat_df, "category", "outcome_count",
                                     orientation="h", title="Outcomes by Category"))
            with c2:
                chart_tile(donut_chart(cat_df, "category", "trial_count",
                                       title="Trials per Category"))
            csv_download_button(cat_df, "outcome_categories.csv")

    with tab2:
        if heatmap_df.empty:
            no_data_callout("outcome types")
        else:
            chart_tile(heatmap_chart(
                heatmap_df,
                title="Outcome Type × Category (Unique Trials)",
                x_label="Outcome Category",
                y_label="Outcome Type",
            ))

    with tab3:
        if cat_df.empty:
            no_data_callout("outcome categories")
        else:
            top10 = cat_df.sort_values("trial_count", ascending=False).head(10)
            chart_tile(bar_chart(top10, "category", "trial_count",
                                 orientation="h", title="Top 10 Outcome Categories"))
            ag_table(cat_df, height=400, key="ro_top_table")
            csv_download_button(cat_df, "top_outcome_categories.csv")

    with tab4:
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
