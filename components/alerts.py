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


def filter_required_callout(message: str = "Please select at least one filter to view this page.") -> None:
    st.markdown(
        f"""
        <div style="text-align:center;padding:60px 20px;">
          <div style="font-size:48px;margin-bottom:16px;">🔎</div>
          <h3 style="color:#0F4C81;font-weight:700;">Filter Required</h3>
          <p style="color:#6B7280;font-size:15px;max-width:420px;margin:0 auto;">
            {message}
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def pipeline_data_note() -> None:
    info_callout(
        "Pipeline data is sourced from onco_pipeline_trials and reflects "
        "investigational assets in the oncology pipeline. "
        "Sponsor and indication coverage may be incomplete for very early-stage assets.",
        title="Pipeline Data Note",
    )
