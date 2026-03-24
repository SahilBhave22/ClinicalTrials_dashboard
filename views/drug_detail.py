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
    bar_chart, heatmap_chart,
)
from components.chart_tile import chart_tile
from components.alerts import no_data_callout
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from data.repository import (
    get_overview_kpis,
    get_drug_trials,
    get_drug_brand_names,
    get_drug_classes,
    get_drug_phase_brand_heatmap,
)
from services.ai_summary import (
    build_drug_detail_context,
    generate_summary,
    filter_hash,
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
        kpis          = get_overview_kpis(filters)
        trials_df     = get_drug_trials(filters)
        brands_df     = get_drug_brand_names(filters)
        classes_df    = get_drug_classes(filters)
        phase_heat_df = get_drug_phase_brand_heatmap(filters)

    if kpis["total_trials"] == 0:
        no_data_callout("trials for the current filters")
        return

    # ── KPIs ──────────────────────────────────────────────────────────────────
    kpi_row([
        {"label": "Total Trials",  "value": kpis["total_trials"],        "icon": "🧪"},
        {"label": "Completed",     "value": kpis["completed_trials"],    "icon": "✅"},
        {"label": "With Results",  "value": kpis["trials_with_results"], "icon": "📋"},
        {"label": "Brand Names",   "value": len(brands_df),              "icon": "💊"},
        {"label": "Drug Classes",  "value": len(classes_df),             "icon": "🏷️"},
    ])
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(
        ["💊 Brand Names / Drugs", "📊 Phase & Design", "🏷️ Drug Classes", "📄 Trial List"]
    )

    with tab1:
        if brands_df.empty:
            no_data_callout("brand names")
        else:
            chart_tile(bar_chart(brands_df, "brand_name", "trial_count",
                                 orientation="h",
                                 title="Brand Names — Trial Counts"))

    with tab2:
        if phase_heat_df.empty:
            no_data_callout("phase data")
        else:
            chart_tile(heatmap_chart(phase_heat_df,
                                     title="Phase × Brand Name — Trial Counts",
                                     x_label="Brand Name",
                                     y_label="Phase"))

    with tab3:
        _NULL_LIKE = {"null", "none", "n/a", "na", "unknown", "not specified", "missing", ""}
        classes_df = classes_df[
            classes_df["drug_class"].notna() &
            ~classes_df["drug_class"].str.strip().str.lower().isin(_NULL_LIKE)
        ]
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

    # ── AI Summary button ──────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    _render_ai_summary(filters, kpis, brands_df, classes_df, phase_heat_df, trials_df)


# ── AI Summary helpers ─────────────────────────────────────────────────────────

def _render_ai_summary(filters, kpis, brands_df, classes_df, phase_heat_df, trials_df):
    """Render the AI Summary button and result card."""
    _, btn_col = st.columns([4, 1])

    with btn_col:
        if filters.has_any_filter():
            clicked = st.button(
                "🤖 AI Summary",
                use_container_width=True,
                key="drug_ai_btn",
                help="Generate an AI-powered analyst summary of the current drug portfolio data.",
            )
        else:
            st.caption("Apply a filter to enable AI Summary.")
            clicked = False

    if clicked:
        current_hash = filter_hash(filters)
        # Only call the API if filters have changed since last generation
        if st.session_state.get("drug_summary_hash") != current_hash:
            with st.spinner("Generating AI summary…"):
                context = build_drug_detail_context(
                    kpis, brands_df, classes_df, phase_heat_df, trials_df, filters
                )
                summary = generate_summary(context, page_name="Drug Detail")
            if summary:
                st.session_state["drug_ai_summary"] = summary
                st.session_state["drug_summary_hash"] = current_hash

    # Clear cached summary if filters no longer match (user changed filters without re-clicking)
    current_hash = filter_hash(filters)
    if (
        "drug_summary_hash" in st.session_state
        and st.session_state["drug_summary_hash"] != current_hash
    ):
        st.session_state.pop("drug_ai_summary", None)
        st.session_state.pop("drug_summary_hash", None)

    # Render the summary card if one exists
    if st.session_state.get("drug_ai_summary"):
        st.markdown(
            """
            <div style="
                background: white;
                border: 1px solid #E5E7EB;
                border-left: 4px solid #0F4C81;
                border-radius: 12px;
                padding: 24px 28px;
                margin: 8px 0 24px 0;
                box-shadow: 0 1px 3px rgba(0,0,0,0.06);
            ">
            <div style="
                font-size: 11px;
                color: #6B7280;
                font-weight: 600;
                letter-spacing: 0.05em;
                text-transform: uppercase;
                margin-bottom: 16px;
            ">
                🤖 AI Generated &nbsp;·&nbsp; GPT-4o &nbsp;·&nbsp; Based on current filters
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(st.session_state["drug_ai_summary"])
        st.markdown("</div>", unsafe_allow_html=True)
