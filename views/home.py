"""
HOME / OVERVIEW page.
High-level landing page: platform intro, database coverage KPIs, charts, nav cards.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd

from components.page_header import page_header
from components.metric_cards import kpi_row
from components.filter_summary import filter_summary_bar
from components.charts import (
    phase_bar, area_chart, bar_chart, donut_chart,
)
from components.chart_tile import chart_tile
from components.alerts import no_data_callout
from utils.filters import FilterState
from utils.formatting import fmt_number, fmt_median
from data.repository import (
    get_overview_kpis,
    get_trials_by_phase,
    get_trials_over_time,
    get_top_sponsors,
    get_top_conditions,
    get_top_interventions,
)
from config.settings import PAGES


_NAV_CSS = """
<style>
.nav-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 10px; }
.nav-card {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 16px 18px;
    transition: box-shadow .15s;
}
.nav-card:hover { box-shadow: 0 4px 12px rgba(37,99,235,.12); border-color: #93C5FD; }
.nav-card .nav-icon { font-size: 1.5rem; }
.nav-card .nav-title { font-weight: 600; font-size: .9rem; color: #1E40AF; margin-top: 4px; }
.nav-card .nav-desc  { font-size: .78rem; color: #6B7280; margin-top: 3px; }
</style>
"""


def render(filters: FilterState) -> None:
    page_header(
        title="Clinical Trials Intelligence Platform",
        subtitle="Competitive landscape, pipeline intelligence, endpoint benchmarking, PRO analytics, and safety analysis.",
        icon="⚗️",
    )
    filter_summary_bar(filters)

    ind = filters.indication_name

    with st.spinner("Loading overview…"):
        kpis = get_overview_kpis(filters)

    # ── KPI Row ───────────────────────────────────────────────────────────────
    st.markdown("### Database Coverage")
    kpi_row([
        {"label": "Total Trials",        "value": kpis["total_trials"],       "icon": "🧪"},
        {"label": "Active Trials",        "value": kpis["active_trials"],       "icon": "🔵"},
        {"label": "Completed Trials",     "value": kpis["completed_trials"],    "icon": "✅"},
        {"label": "Trials with Results",  "value": kpis["trials_with_results"], "icon": "📋"},
    ])
    st.markdown("<br>", unsafe_allow_html=True)
    kpi_row([
        {"label": "Unique Sponsors",     "value": kpis["unique_sponsors"],    "icon": "🏢"},
        {"label": "Unique Drugs",        "value": kpis["unique_drugs"],       "icon": "💊"},
        {"label": "Unique Conditions",   "value": kpis["unique_conditions"],  "icon": "🔬"},
        {"label": "Trials with PROs",    "value": kpis["trials_with_pros"],   "icon": "👤"},
    ])
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts Row 1 ─────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        phase_df = get_trials_by_phase(filters)
        if phase_df.empty:
            no_data_callout("phase distribution")
        else:
            chart_tile(phase_bar(phase_df, x="phase", y="trial_count",
                                 title="Trial Count by Phase"))

    with col2:
        time_df = get_trials_over_time(filters)
        if time_df.empty:
            no_data_callout("trial timeline")
        else:
            time_df["year"] = pd.to_datetime(time_df["year"]).dt.year
            chart_tile(area_chart(time_df, x="year", y="trial_count",
                                  title="Trials First Posted per Year"))

    # ── Charts Row 2 ─────────────────────────────────────────────────────────
    col3, col4 = st.columns(2)

    with col3:
        sp_df = get_top_sponsors(filters, limit=15)
        if sp_df.empty:
            no_data_callout("sponsors")
        else:
            chart_tile(bar_chart(sp_df.head(12), x="sponsor", y="trial_count",
                                 orientation="h", title="Top Sponsors by Trial Count"))

    with col4:
        cond_df = get_top_conditions(filters, limit=15)
        if cond_df.empty:
            no_data_callout("conditions")
        else:
            chart_tile(bar_chart(cond_df.head(12), x="condition", y="trial_count",
                                 orientation="h", title="Top MeSH Conditions"))

    # ── Top Interventions ─────────────────────────────────────────────────────
    intv_df = get_top_interventions(filters, limit=20)
    if not intv_df.empty:
        chart_tile(bar_chart(intv_df.head(15), x="intervention", y="trial_count",
                             orientation="h", title="Top Drug Interventions by Trial Count"))
    else:
        no_data_callout("interventions")

    # ── Navigation Cards ──────────────────────────────────────────────────────
    st.markdown("<hr style='margin:28px 0 16px 0;border-color:#E5E7EB;'>",
                unsafe_allow_html=True)
    st.markdown("### Explore Platform Modules")
    st.markdown(_NAV_CSS, unsafe_allow_html=True)

    nav_pages = [p for p in PAGES if p["key"] != "home"]
    # Render 3-per-row
    for i in range(0, len(nav_pages), 3):
        row_pages = nav_pages[i: i + 3]
        cols = st.columns(len(row_pages))
        for col, p in zip(cols, row_pages):
            with col:
                st.markdown(
                    f"""
                    <div class="nav-card">
                        <div class="nav-icon">{p['icon']}</div>
                        <div class="nav-title">{p['label']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
