"""
DRUG DETAIL page.
Drill into a drug portfolio scoped by the active global filters.
"""
from __future__ import annotations
import streamlit as st

from components.page_header import page_header
from components.metric_cards import kpi_row
from components.filter_summary import filter_summary_bar
from components.charts import (
    phase_bar, bar_chart,
)
from components.chart_tile import chart_tile
from components.alerts import no_data_callout
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from data.repository import (
    get_overview_kpis,
    get_drug_trials,
    get_drug_conditions,
    get_drug_classes,
    get_drug_phase_mix,
)


def render(filters: FilterState) -> None:
    page_header(
        title="Drug Detail",
        subtitle="Trial portfolio, conditions studied, and drug classes for the active filter scope.",
        icon="💊",
        breadcrumb="Home > Drug Detail",
    )
    filter_summary_bar(filters)

    with st.spinner("Loading drug data…"):
        kpis       = get_overview_kpis(filters)
        trials_df  = get_drug_trials(filters)
        phase_df   = get_drug_phase_mix(filters)
        cond_df    = get_drug_conditions(filters)
        classes_df = get_drug_classes(filters)

    if kpis["total_trials"] == 0:
        no_data_callout("trials for the current filters")
        return

    # ── KPIs ──────────────────────────────────────────────────────────────────
    kpi_row([
        {"label": "Total Trials",      "value": kpis["total_trials"],        "icon": "🧪"},
        {"label": "Completed",         "value": kpis["completed_trials"],    "icon": "✅"},
        {"label": "With Results",      "value": kpis["trials_with_results"], "icon": "📋"},
        {"label": "Conditions Studied","value": len(cond_df),                "icon": "🔬"},
        {"label": "Drug Classes",      "value": len(classes_df),             "icon": "💊"},
    ])
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📊 Phase & Design", "🔬 Conditions", "💊 Drug Classes", "📄 Trial List"]
    )

    with tab1:
        if not phase_df.empty:
            chart_tile(phase_bar(phase_df, "phase", "trial_count",
                                 title="Phase Mix"))

    with tab2:
        if cond_df.empty:
            no_data_callout("conditions")
        else:
            chart_tile(bar_chart(cond_df, "condition", "trial_count",
                                 orientation="h",
                                 title="Top Conditions Studied"))

    with tab3:
        if classes_df.empty:
            no_data_callout("drug classes")
        else:
            chart_tile(bar_chart(classes_df, "drug_class", "brand_count",
                                 orientation="h",
                                 title="ATC Drug Classes — Brands per Class"))

    with tab4:
        if trials_df.empty:
            no_data_callout("trial list")
        else:
            ag_table(trials_df, height=460, key="drug_trials_table")
            csv_download_button(trials_df, filename="drug_detail_trials.csv")
