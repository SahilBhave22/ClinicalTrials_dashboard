"""
SPONSOR BENCHMARK page.
Compare sponsor trial activity, phase mix, PRO adoption, endpoint usage.
"""
from __future__ import annotations
import streamlit as st

from components.page_header import page_header
from components.filter_summary import filter_summary_bar
from components.charts import (
    bar_chart, stacked_bar, grouped_bar, heatmap_chart,
)
from components.chart_tile import chart_tile
from components.alerts import no_data_callout, filter_required_callout
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from services.analytics import pivot_heatmap
from data.repository import (
    get_sponsor_trial_counts,
    get_sponsor_phase_mix,
    get_sponsor_pro_adoption,
    get_sponsor_endpoint_usage,
)


def render(filters: FilterState) -> None:
    page_header(
        title="Sponsor Benchmark",
        subtitle="Compare sponsor trial portfolios, phase distribution, PRO adoption rates, and endpoint focus.",
        icon="🏢",
        breadcrumb="Home > Sponsor Benchmark",
    )
    filter_summary_bar(filters)

    if not filters.has_any_filter():
        filter_required_callout(
            "Please select at least one filter in the sidebar "
            "(indication, drug class, sponsor, phase, etc.) to view the charts."
        )
        return

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Trial Counts", "📐 Phase Mix", "👤 PRO Adoption", "🎯 Endpoint Usage"
    ])

    with tab1:
        counts_df = get_sponsor_trial_counts(filters, limit=20)
        if counts_df.empty:
            no_data_callout("sponsor trial counts")
        else:
            c1, c2 = st.columns([3, 2])
            with c1:
                chart_tile(bar_chart(counts_df, "sponsor", "total_trials",
                                     orientation="h", title="Total Trials per Sponsor"))
            with c2:
                import pandas as pd
                melted = pd.melt(
                    counts_df[["sponsor", "active_trials", "completed_trials"]],
                    id_vars="sponsor",
                    var_name="status",
                    value_name="trial_count",
                )
                melted["status"] = melted["status"].map(
                    {"active_trials": "Active", "completed_trials": "Completed"}
                )
                chart_tile(stacked_bar(melted, "sponsor", "trial_count", "status",
                                       title="Active vs Completed"))
            csv_download_button(counts_df, "sponsor_counts.csv")

    with tab2:
        phase_df = get_sponsor_phase_mix(filters, limit=15)
        if phase_df.empty:
            no_data_callout("sponsor phase mix")
        else:
            chart_tile(stacked_bar(phase_df, "sponsor", "trial_count", "phase",
                                   title="Phase Mix by Sponsor"))

    with tab3:
        pro_df = get_sponsor_pro_adoption(filters, limit=15)
        if pro_df.empty:
            no_data_callout("PRO adoption data")
        else:
            chart_tile(bar_chart(pro_df, "sponsor", "pct_with_pro",
                                 orientation="h",
                                 title="% Trials with Planned PROs by Sponsor"))
            st.markdown("##### PRO Adoption Details")
            ag_table(pro_df, height=320, key="sp_pro_table")
            csv_download_button(pro_df, "sponsor_pro_adoption.csv")

    with tab4:
        ep_df = get_sponsor_endpoint_usage(filters, limit=10)
        if ep_df.empty:
            no_data_callout("endpoint usage")
        else:
            pivot = pivot_heatmap(ep_df, "sponsor", "category", "trial_count")
            if not pivot.empty:
                chart_tile(heatmap_chart(pivot,
                                         title="Endpoint Category Usage by Sponsor",
                                         x_label="Category", y_label="Sponsor"))
            st.markdown("##### Endpoint Usage Data")
            ag_table(ep_df, height=300, key="sp_ep_table")
