"""
TRIAL DESIGN page.
Benchmark design patterns: allocation, intervention model, arms, eligibility.
"""
from __future__ import annotations
import streamlit as st

from components.page_header import page_header
from components.filter_summary import filter_summary_bar
from components.charts import bar_chart, donut_chart, grouped_bar
from components.chart_tile import chart_tile
from components.alerts import no_data_callout
from components.tables import csv_download_button
from utils.filters import FilterState
from services.trial_design_analysis import (
    allocation_summary,
    intervention_model_summary,
    primary_purpose_summary,
)
from data.repository import (
    get_trial_design_metrics,
    get_arms_distribution,
    get_eligibility_distribution,
)


def render(filters: FilterState) -> None:
    page_header(
        title="Trial Design",
        subtitle="Benchmark trial design patterns: allocation method, intervention model, arms count, and eligibility.",
        icon="📐",
        breadcrumb="Home > Trial Design",
    )
    filter_summary_bar(filters)

    with st.spinner("Loading trial design data…"):
        design_df  = get_trial_design_metrics(filters)
        arms_df    = get_arms_distribution(filters)
        elig_df    = get_eligibility_distribution(filters)

    if design_df.empty:
        no_data_callout("trial design data")
        return

    alloc_df  = allocation_summary(design_df)
    model_df  = intervention_model_summary(design_df)
    purpose_df = primary_purpose_summary(design_df)

    # ── Row 1 ──────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        if not alloc_df.empty:
            chart_tile(donut_chart(alloc_df, "allocation", "trial_count",
                                   title="Allocation Method"))
    with c2:
        if not model_df.empty:
            chart_tile(bar_chart(model_df, "intervention_model", "trial_count",
                                 orientation="h", title="Intervention Model"))
    with c3:
        if not purpose_df.empty:
            chart_tile(donut_chart(purpose_df, "primary_purpose", "trial_count",
                                   title="Primary Purpose"))

    # ── Arms distribution ──────────────────────────────────────────────────
    st.markdown("---")
    if not arms_df.empty:
        chart_tile(bar_chart(arms_df, "number_of_arms", "trial_count",
                             title="Number of Arms / Groups per Trial"))

    # ── Eligibility ────────────────────────────────────────────────────────
    st.markdown("---")
    if not elig_df.empty:
        c1, c2 = st.columns(2)
        with c1:
            gender_agg = (
                elig_df.groupby("gender")["trial_count"]
                .sum().reset_index()
                .sort_values("trial_count", ascending=False)
            )
            chart_tile(donut_chart(gender_agg, "gender", "trial_count",
                                   title="Gender Eligibility"))
        with c2:
            import pandas as pd
            age_data = {
                "Age Group": ["Adult", "Child", "Older Adult"],
                "trial_count": [
                    elig_df["adult"].sum(),
                    elig_df["child"].sum(),
                    elig_df["older_adult"].sum(),
                ],
            }
            age_df = pd.DataFrame(age_data)
            chart_tile(bar_chart(age_df, "Age Group", "trial_count",
                                 title="Eligible Age Groups"))
        csv_download_button(elig_df.drop(columns=["adult","child","older_adult"], errors="ignore"),
                             "eligibility.csv")
