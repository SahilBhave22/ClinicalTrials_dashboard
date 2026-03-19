"""
Callout / alert banner components.
"""
from __future__ import annotations
import streamlit as st


def info_callout(message: str, title: str = "Note") -> None:
    st.info(f"**{title}** — {message}")


def warning_callout(message: str, title: str = "Warning") -> None:
    st.warning(f"**{title}** — {message}")


def danger_callout(message: str, title: str = "Important") -> None:
    st.error(f"**{title}** — {message}")


def score_comparability_warning() -> None:
    warning_callout(
        "Outcome scores shown here may use different units, parameter types, or "
        "measurement timepoints across trials. Direct numerical comparisons are "
        "interpretively limited. Use filters to restrict to a single endpoint "
        "category and unit type before drawing conclusions.",
        title="Score Comparability Caution",
    )


def ae_interpretation_warning() -> None:
    warning_callout(
        "Adverse event frequencies reflect reporting from individual trials, "
        "which vary in design, population, duration, and follow-up. "
        "Cross-trial comparisons should account for these differences. "
        "Only groups where subjects_affected > 0 are shown.",
        title="Safety Interpretation Note",
    )


def no_data_callout(context: str = "current filters") -> None:
    st.info(
        f"No data available for the {context}. "
        "Try adjusting your filters or broadening the selection."
    )


def pipeline_data_note() -> None:
    info_callout(
        "Pipeline data is sourced from onco_pipeline_trials and reflects "
        "investigational assets in the oncology pipeline. "
        "Sponsor and indication coverage may be incomplete for very early-stage assets.",
        title="Pipeline Data Note",
    )
