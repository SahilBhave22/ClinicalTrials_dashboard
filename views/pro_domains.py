"""
PRO DOMAINS page.
PRO domain / subscale analysis from domain_score_match table.
"""
from __future__ import annotations
import streamlit as st

from components.page_header import page_header
from components.filter_summary import filter_summary_bar
from components.charts import (
    bar_chart, treemap_chart, sunburst_chart, heatmap_chart,
)
from components.chart_tile import chart_tile
from components.alerts import no_data_callout
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from services.pro_analysis import domain_pivot
from data.repository import (
    get_pro_domains,
    get_domain_instrument_heatmap,
    get_domain_by_drug,
)


def render(filters: FilterState) -> None:
    page_header(
        title="PRO Domains",
        subtitle="Patient-reported outcome domain and subscale analysis: instrument coverage, domain distribution, drug associations.",
        icon="🧩",
        breadcrumb="Home > PRO Domains",
    )
    filter_summary_bar(filters)

    with st.spinner("Loading domain data…"):
        domain_df  = get_pro_domains(filters)
        heat_df    = get_domain_instrument_heatmap(filters)
        drug_df    = get_domain_by_drug(filters)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Domain Distribution", "🗺️ Instrument × Domain", "💊 By Drug", "📄 Detail Table"
    ])

    with tab1:
        if domain_df.empty:
            no_data_callout("domain data")
        else:
            dom_agg = (
                domain_df.groupby("domain")["trial_count"]
                .sum().reset_index()
                .sort_values("trial_count", ascending=False)
                .head(20)
            )
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(bar_chart(dom_agg, "domain", "trial_count",
                                     orientation="h", title="Top PRO Domains by Trial Count"))
            with c2:
                chart_tile(treemap_chart(dom_agg, path=["domain"],
                                         values="trial_count",
                                         title="Domain Coverage Treemap"))

    with tab2:
        if heat_df.empty:
            no_data_callout("instrument × domain heatmap")
        else:
            pivot = domain_pivot(heat_df)
            if not pivot.empty:
                chart_tile(heatmap_chart(pivot, title="Instrument × Domain Heatmap",
                                         x_label="Domain", y_label="Instrument"))
            else:
                no_data_callout("heatmap pivot")

    with tab3:
        if drug_df.empty:
            no_data_callout("drug domain data")
        else:
            drug_agg = (
                drug_df.groupby("brand_name")["trial_count"]
                .sum().reset_index()
                .sort_values("trial_count", ascending=False)
                .head(15)
            )
            c1, c2 = st.columns(2)
            with c1:
                chart_tile(bar_chart(drug_agg, "brand_name", "trial_count",
                                     orientation="h", title="Domains by Drug"))
            with c2:
                sun_df = drug_df[drug_df["brand_name"].isin(
                    drug_agg["brand_name"].head(10).tolist()
                )]
                chart_tile(sunburst_chart(sun_df, path=["brand_name", "domain"],
                                          values="trial_count",
                                          title="Drug → Domain Sunburst"))

    with tab4:
        if not domain_df.empty:
            ag_table(domain_df, height=450, key="pro_domains_table")
            csv_download_button(domain_df, "pro_domains.csv")
