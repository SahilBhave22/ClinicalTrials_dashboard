"""
OUTCOME SCORE ANALYSIS page.
Numeric outcome measurements: box plots, score by drug, result-group comparisons.
"""
from __future__ import annotations
import streamlit as st

from components.page_header import page_header
from components.filter_summary import filter_summary_bar
from components.charts import box_plot, bar_chart, scatter_chart
from components.chart_tile import chart_tile
from components.alerts import (
    score_comparability_warning,
    warning_callout,
    no_data_callout,
)
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from services.outcome_analysis import (
    flag_baseline_rows,
    unit_consistency_check,
    is_comparable,
    prepare_boxplot_data,
    score_summary_by_group,
)
from data.repository import get_outcome_scores, get_score_by_drug


def render(filters: FilterState) -> None:
    page_header(
        title="Outcome Score Analysis",
        subtitle="Numeric outcome measurements: score distributions, drug comparisons, and result-group analysis.",
        icon="📈",
        breadcrumb="Home > Outcome Scores",
    )
    filter_summary_bar(filters)
    score_comparability_warning()

    cat_opts = filters.endpoint_category

    # ── Controls ──────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        selected_cats = st.multiselect(
            "Filter by Endpoint Category",
            options=cat_opts or ["OS", "PFS", "ORR", "CR", "DOR", "PRO", "Other"],
            default=cat_opts or [],
            key="os_cats",
        )
    with c2:
        exclude_baseline = st.checkbox(
            "Exclude Baseline Timepoints", value=True, key="os_excl_baseline"
        )
    with c3:
        group_by = st.selectbox(
            "Group By", options=["brand_name", "category"], key="os_groupby"
        )

    with st.spinner("Loading score data…"):
        df = get_outcome_scores(filters, selected_cats, exclude_baseline)

    if df.empty:
        no_data_callout("outcome scores")
        return

    df = flag_baseline_rows(df)

    # ── Comparability check ───────────────────────────────────────────────────
    if not is_comparable(df):
        unit_map = unit_consistency_check(df)
        units_str = "; ".join(
            f"{cat}: [{', '.join(u[:3])}]" for cat, u in unit_map.items()
        )
        warning_callout(
            f"Multiple units detected across categories — direct comparison not valid. "
            f"Units found: {units_str}",
            title="Mixed Units Detected",
        )

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["📦 Box Plots", "📊 Summary by Drug", "📄 Raw Scores"])

    with tab1:
        plot_df = prepare_boxplot_data(df, group_col=group_by)
        if plot_df.empty:
            no_data_callout("box plot data")
        else:
            top_groups = (
                plot_df.groupby(group_by)["param_value_num"]
                .median().nlargest(15).index.tolist()
            )
            plot_df_top = plot_df[plot_df[group_by].isin(top_groups)]
            chart_tile(box_plot(plot_df_top, x=group_by, y="param_value_num",
                                color="category" if "category" in plot_df_top.columns else None,
                                title=f"Score Distribution by {group_by.replace('_',' ').title()}",
                                points="outliers"))
            if df["units"].nunique() > 1:
                st.caption(f"⚠️ Units vary across rows ({df['units'].nunique()} unique). "
                           "Filter to one category for valid comparison.")

    with tab2:
        for cat in (selected_cats if selected_cats else ["All"]):
            with st.expander(f"Category: {cat}", expanded=(len(selected_cats or []) <= 2)):
                summary_df = get_score_by_drug(filters, cat)
                if not summary_df.empty:
                    chart_tile(bar_chart(summary_df, "brand_name", "median_score",
                                        orientation="h",
                                        title=f"Median Score — {cat}"))
                    ag_table(summary_df, height=250, key=f"score_sum_{cat}")
                else:
                    no_data_callout(f"{cat} score summary")

    with tab3:
        display_cols = [
            "nct_id", "brand_name", "category", "outcome_title",
            "param_value_num", "units", "param_type", "classification",
        ]
        show_cols = [c for c in display_cols if c in df.columns]
        st.markdown(f"**{len(df):,} rows** — showing up to 500")
        ag_table(df[show_cols].head(500), height=500, key="os_raw_table")
        csv_download_button(df[show_cols], "outcome_scores.csv")
