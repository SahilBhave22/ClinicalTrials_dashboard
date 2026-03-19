"""
SAFETY ANALYSIS page.
Adverse events: terms, organ systems, drug linkage, frequency analysis.
"""
from __future__ import annotations
import streamlit as st

from components.page_header import page_header
from components.metric_cards import kpi_row
from components.filter_summary import filter_summary_bar
from components.charts import bar_chart, donut_chart, treemap_chart, heatmap_chart
from components.chart_tile import chart_tile
from components.alerts import ae_interpretation_warning, no_data_callout
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from utils.formatting import fmt_number
from services.safety_analysis import top_ae_terms, add_incidence_column
from data.repository import (
    get_adverse_event_summary,
    get_top_adverse_events,
    get_ae_by_organ_system,
    get_ae_by_drug,
    get_ae_detail_table,
)


def render(filters: FilterState) -> None:
    page_header(
        title="Safety Analysis",
        subtitle="Adverse event reporting: terms, organ systems, drug associations, and incidence analysis.",
        icon="🛡️",
        breadcrumb="Home > Safety Analysis",
    )
    filter_summary_bar(filters)
    ae_interpretation_warning()

    # ── Organ system / AE term filters ────────────────────────────────────────
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        organ_system_filter = st.text_input(
            "Filter by Organ System (optional)", placeholder="e.g. Gastrointestinal disorders",
            key="ae_organ_filter",
        )
    with col_f2:
        ae_term_filter = st.text_input(
            "Filter by AE Term (optional)", placeholder="e.g. Nausea",
            key="ae_term_filter",
        )

    os_val  = organ_system_filter.strip() or None
    aet_val = ae_term_filter.strip() or None

    with st.spinner("Loading safety data…"):
        kpis_data   = get_adverse_event_summary(filters)
        top_ae_df   = get_top_adverse_events(filters, limit=25)
        organ_df    = get_ae_by_organ_system(filters)
        drug_ae_df  = get_ae_by_drug(filters, limit=20)

    # ── KPIs ──────────────────────────────────────────────────────────────────
    kpi_row([
        {"label": "Trials with AEs",      "value": kpis_data["trials_with_ae"],        "icon": "🧪"},
        {"label": "AE Records",           "value": kpis_data["total_ae_records"],       "icon": "📋"},
        {"label": "Unique AE Terms",      "value": kpis_data["unique_ae_terms"],        "icon": "🔬"},
        {"label": "Organ Systems",        "value": kpis_data["unique_organ_systems"],   "icon": "🫀"},
        {"label": "Total Subjects Affected","value": kpis_data["total_subjects_affected"],"icon": "👥"},
    ])
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "🔢 Top AE Terms", "🫀 Organ Systems", "💊 By Drug", "📄 Detail Table"
    ])

    with tab1:
        if top_ae_df.empty:
            no_data_callout("adverse event terms")
        else:
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(bar_chart(top_ae_df.head(15), "adverse_event_term", "trial_count",
                                     orientation="h",
                                     title="Top AE Terms by Trial Count"))
            with c2:
                chart_tile(bar_chart(top_ae_df.head(15), "adverse_event_term", "total_affected",
                                     orientation="h",
                                     title="Top AE Terms by Subjects Affected"))
            ag_table(top_ae_df, height=350, key="ae_top_table")
            csv_download_button(top_ae_df, "top_ae_terms.csv")

    with tab2:
        if organ_df.empty:
            no_data_callout("organ system data")
        else:
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(bar_chart(organ_df, "organ_system", "trial_count",
                                     orientation="h",
                                     title="AE Trials by Organ System"))
            with c2:
                chart_tile(treemap_chart(organ_df, path=["organ_system"],
                                         values="total_affected",
                                         title="Subjects Affected by Organ System"))
            csv_download_button(organ_df, "organ_systems.csv")

    with tab3:
        if drug_ae_df.empty:
            no_data_callout("drug AE data")
        else:
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(bar_chart(drug_ae_df, "brand_name", "trial_count",
                                     orientation="h",
                                     title="AE Trials by Drug"))
            with c2:
                chart_tile(bar_chart(drug_ae_df, "brand_name", "unique_terms",
                                     orientation="h",
                                     title="Unique AE Terms per Drug"))
            csv_download_button(drug_ae_df, "drug_ae_summary.csv")

    with tab4:
        st.markdown("##### Adverse Event Detail Table")
        st.caption(
            "Shows trials, AE terms, organ systems, subjects affected/at risk, "
            "drug linkage via drug_result_groups."
        )
        with st.spinner("Loading AE detail…"):
            detail_df = get_ae_detail_table(filters, os_val, aet_val)
        if detail_df.empty:
            no_data_callout("adverse event detail")
        else:
            detail_df = add_incidence_column(detail_df)
            ag_table(detail_df, height=500, key="ae_detail_table")
            csv_download_button(detail_df, "ae_detail.csv")
