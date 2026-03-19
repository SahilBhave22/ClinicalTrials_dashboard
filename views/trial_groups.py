"""
TRIAL GROUPS page.
Protocol arms, design groups, result groups.
"""
from __future__ import annotations
import streamlit as st

from components.page_header import page_header
from components.filter_summary import filter_summary_bar
from components.charts import bar_chart, donut_chart
from components.chart_tile import chart_tile
from components.alerts import no_data_callout
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from data.repository import (
    get_trial_groups,
    get_result_groups,
    get_groups_per_trial_dist,
)


def render(filters: FilterState) -> None:
    page_header(
        title="Trial Groups",
        subtitle="Protocol arms, design groups, and result groups: intervention mapping and group structure.",
        icon="👥",
        breadcrumb="Home > Trial Groups",
    )
    filter_summary_bar(filters)

    tab1, tab2, tab3 = st.tabs(
        ["📐 Design Groups", "📋 Result Groups", "📊 Groups per Trial"]
    )

    with tab1:
        with st.spinner("Loading design groups…"):
            dg_df = get_trial_groups(filters)
        if dg_df.empty:
            no_data_callout("design groups")
        else:
            gt_agg = (
                dg_df.groupby("group_type").size().reset_index(name="count")
                .sort_values("count", ascending=False)
            )
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(donut_chart(gt_agg, "group_type", "count",
                                       title="Group Type Distribution"))
            with c2:
                intv_agg = (
                    dg_df.groupby("intervention_name").size().reset_index(name="group_count")
                    .sort_values("group_count", ascending=False).head(15)
                )
                chart_tile(bar_chart(intv_agg, "intervention_name", "group_count",
                                     orientation="h", title="Top Interventions in Groups"))
            st.markdown("##### Design Groups Table")
            ag_table(dg_df, height=450, key="dg_table")
            csv_download_button(dg_df, "design_groups.csv")

    with tab2:
        with st.spinner("Loading result groups…"):
            rg_df = get_result_groups(filters)
        if rg_df.empty:
            no_data_callout("result groups")
        else:
            with_drug = rg_df["brand_name"].notna().sum()
            st.metric("Result Groups with Drug Linkage", f"{with_drug:,}")
            ag_table(rg_df, height=500, key="rg_table")
            csv_download_button(rg_df, "result_groups.csv")

    with tab3:
        with st.spinner("Loading group distribution…"):
            dist_df = get_groups_per_trial_dist(filters)
        if dist_df.empty:
            no_data_callout("groups per trial distribution")
        else:
            chart_tile(bar_chart(dist_df, "groups_per_trial", "trial_count",
                                 title="Distribution: Design Groups per Trial"))
