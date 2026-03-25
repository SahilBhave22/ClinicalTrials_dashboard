"""
OUTCOME SCORE ANALYSIS page.
Temporarily disabled while performance issues are being addressed.
"""
from __future__ import annotations

import streamlit as st

from components.page_header import page_header
from components.filter_summary import filter_summary_bar
from utils.filters import FilterState


def render(filters: FilterState) -> None:
    page_header(
        title="Outcome Score Analysis",
        subtitle="Numeric outcome measurements: score distributions, drug comparisons, and result-group analysis.",
        icon="📈",
        breadcrumb="Home > Outcome Scores",
    )
    filter_summary_bar(filters)
    st.info("This page is currently a work in progress.")
