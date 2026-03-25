"""
REPORTED OUTCOMES page.
Posted outcomes and endpoint categories analysis.
"""
from __future__ import annotations
import streamlit as st

from components.page_header import page_header
from components.filter_summary import filter_summary_bar
from components.charts import bar_chart, donut_chart, funnel_chart
from components.chart_tile import chart_tile
from components.alerts import no_data_callout, filter_required_callout
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from data.repository import (
    get_reported_outcome_categories,
    get_reported_outcome_type_dist,
    get_top_outcome_titles,
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
        cat_df     = get_reported_outcome_categories(filters)
        type_df    = get_reported_outcome_type_dist(filters)
        top_df     = get_top_outcome_titles(filters, limit=25)
        funnel_df  = get_reported_pro_funnel(filters)

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
        if type_df.empty:
            no_data_callout("outcome types")
        else:
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(donut_chart(type_df, "outcome_type", "outcome_count",
                                       title="Outcome Type Distribution"))
            with c2:
                chart_tile(bar_chart(type_df, "outcome_type", "trial_count",
                                     title="Trials per Outcome Type"))

    with tab3:
        if top_df.empty:
            no_data_callout("outcome titles")
        else:
            chart_tile(bar_chart(top_df.head(20), "title", "trial_count",
                                 orientation="h", title="Top 20 Reported Outcome Titles"))
            ag_table(top_df, height=400, key="ro_top_table")
            csv_download_button(top_df, "top_outcomes.csv")

    with tab4:
        if not funnel_df.empty:
            chart_tile(funnel_chart(funnel_df, y="stage", x="trial_count",
                                    title="Planned vs Reported PRO Funnel"))
            c1, c2 = st.columns(2)
            for _, row in funnel_df.iterrows():
                with (c1 if row["stage"] == "Planned PROs" else c2):
                    st.metric(row["stage"], int(row["trial_count"]))
        else:
            no_data_callout("PRO funnel")
