"""
OUTCOME SCORE ANALYSIS page.
Lets users select two trials and compare their numeric outcome measurements side-by-side.
"""
from __future__ import annotations

import streamlit as st

from components.alerts import filter_required_callout
from components.metric_cards import kpi_row
from components.page_header import page_header
from components.filter_summary import filter_summary_bar
from components.tables import csv_download_button
from config.settings import COLORS
from data.repository import get_trials_with_outcomes, get_outcome_data_for_trial
from utils.filters import FilterState

_TRIAL_LIST_COLS = {
    "nct_id": "Trial ID",
    "brief_title": "Title",
    "lead_sponsor": "Sponsor",
    "phase": "Phase",
    "overall_status": "Status",
    "enrollment": "Enrollment",
}

_OUTCOME_COLS = {
    "outcome_title": "Outcome",
    "units": "Units",
    "param_type": "Measure",
    "param_value_num": "Value",
    "group_name": "Group",
}


def _slot_card(slot: str, nct_id: str | None, color: str) -> None:
    """Render a styled slot status card."""
    has_trial = bool(nct_id)
    border_color = color if has_trial else "#E5E7EB"
    bg_color = f"{color}0D" if has_trial else "white"
    nct_display = nct_id if has_trial else "&mdash;"
    nct_color = color if has_trial else "#D1D5DB"
    subtitle = (
        '<div style="font-size:12px;color:#9CA3AF;margin-top:2px;">No trial loaded</div>'
        if not has_trial else ""
    )
    html = (
        f'<div style="background:{bg_color};border:2px solid {border_color};'
        f'border-radius:12px;padding:16px 20px;min-height:80px;">'
        f'<span style="font-size:11px;font-weight:700;color:{color};'
        f'text-transform:uppercase;letter-spacing:0.06em;">Trial {slot}</span>'
        f'<div style="font-size:20px;font-weight:700;color:{nct_color};'
        f'font-family:monospace;margin-top:6px;">{nct_display}</div>'
        f'{subtitle}</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _selection_bar(selected_nct: str | None) -> None:
    """Render the action bar between the table and the slot cards."""
    if selected_nct:
        html = (
            f'<div style="background:#F0F9FF;border:1.5px solid {COLORS["secondary"]};'
            f'border-radius:10px;padding:12px 18px;display:flex;align-items:center;gap:12px;">'
            f'<span style="font-size:13px;color:#1A1A2E;">Selected:</span>'
            f'<span style="font-family:monospace;font-weight:700;font-size:14px;'
            f'color:{COLORS["primary"]};">{selected_nct}</span>'
            f'<span style="font-size:13px;color:#6B7280;margin-left:4px;">— choose a slot below</span>'
            f'</div>'
        )
    else:
        html = (
            '<div style="background:#F8FAFC;border:1.5px dashed #D1D5DB;'
            'border-radius:10px;padding:12px 18px;">'
            '<span style="font-size:13px;color:#9CA3AF;">'
            '↑  Click a row in the table above to select a trial, then load it into Trial A or B below.'
            '</span></div>'
        )
    st.markdown(html, unsafe_allow_html=True)


def _placeholder_panel(slot: str, color: str) -> None:
    html = (
        f'<div style="border:2px dashed {color}33;border-radius:12px;'
        f'padding:48px 24px;text-align:center;background:#F8FAFC;">'
        f'<span style="font-size:32px;">🔬</span>'
        f'<p style="color:#6B7280;font-size:14px;margin-top:8px;">'
        f'Load a trial into slot <strong>{slot}</strong> using the controls above.'
        f'</p></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _outcome_panel(slot: str, nct_id: str, color: str) -> None:
    html = (
        f'<div style="background:{color}15;border-left:4px solid {color};'
        f'border-radius:8px;padding:10px 16px;margin-bottom:12px;">'
        f'<span style="font-weight:700;color:{color};font-size:14px;">'
        f'Trial {slot} — {nct_id}</span></div>'
    )
    st.markdown(html, unsafe_allow_html=True)
    with st.spinner(f"Loading outcome data for {nct_id}…"):
        df = get_outcome_data_for_trial(nct_id)
    if df.empty:
        st.info("No numeric outcome measurements found for this trial.")
        return
    display = df.rename(columns=_OUTCOME_COLS)
    st.dataframe(display, use_container_width=True, hide_index=True)
    csv_download_button(display, filename=f"outcomes_{nct_id}.csv")


def render(filters: FilterState) -> None:
    page_header(
        title="Outcome Score Analysis",
        subtitle="Select two trials to compare their numeric outcome measurements side-by-side.",
        icon="📈",
        breadcrumb="Home > Outcome Scores",
    )
    filter_summary_bar(filters)

    if not filters.has_any_filter():
        filter_required_callout(
            "Please select at least one filter in the sidebar "
            "(indication, drug class, sponsor, phase, etc.) to view outcome data."
        )
        return

    # ── session state ─────────────────────────────────────────────────────────
    for key, default in [
        ("os_trial_a", None),
        ("os_trial_b", None),
        ("os_selected_nct", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # ── fetch trial list ──────────────────────────────────────────────────────
    with st.spinner("Loading trials with outcome data…"):
        trials_df = get_trials_with_outcomes(filters)

    if trials_df.empty:
        st.warning("No trials with numeric outcome measurements match the current filters.")
        return

    # ── KPI ───────────────────────────────────────────────────────────────────
    kpi_row([{"label": "Trials with Outcome Data", "value": len(trials_df), "icon": "📊"}])

    # ── trial list ────────────────────────────────────────────────────────────
    st.markdown(
        "<p style='color:#6B7280;font-size:13px;margin:12px 0 4px;'>"
        "Step 1 — Click a row to select a trial.</p>",
        unsafe_allow_html=True,
    )

    display_df = trials_df.rename(columns=_TRIAL_LIST_COLS)
    event = st.dataframe(
        display_df,
        selection_mode="single-row",
        on_select="rerun",
        use_container_width=True,
        hide_index=True,
        key="os_trial_list",
    )

    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        st.session_state["os_selected_nct"] = trials_df.iloc[selected_rows[0]]["nct_id"]

    # ── step 2: action bar ────────────────────────────────────────────────────
    st.markdown(
        "<p style='color:#6B7280;font-size:13px;margin:16px 0 6px;'>"
        "Step 2 — Load the selected trial into a comparison slot.</p>",
        unsafe_allow_html=True,
    )

    selected_nct: str | None = st.session_state["os_selected_nct"]
    _selection_bar(selected_nct)

    st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)

    trial_a: str | None = st.session_state["os_trial_a"]
    trial_b: str | None = st.session_state["os_trial_b"]

    slot_col_a, slot_col_b = st.columns(2)

    with slot_col_a:
        _slot_card("A", trial_a, COLORS["primary"])
        load_col, clear_col = st.columns([3, 1])
        with load_col:
            load_a = st.button(
                f"{'↙ Load into' if selected_nct else 'Load into'} Trial A",
                key="os_load_a",
                use_container_width=True,
                disabled=not selected_nct,
                type="primary" if selected_nct else "secondary",
            )
        with clear_col:
            if trial_a and st.button("✕ Clear", key="os_clear_a", use_container_width=True):
                st.session_state["os_trial_a"] = None
                st.rerun()
        if load_a and selected_nct:
            st.session_state["os_trial_a"] = selected_nct
            st.rerun()

    with slot_col_b:
        _slot_card("B", trial_b, COLORS["accent"])
        load_col, clear_col = st.columns([3, 1])
        with load_col:
            load_b = st.button(
                f"{'↙ Load into' if selected_nct else 'Load into'} Trial B",
                key="os_load_b",
                use_container_width=True,
                disabled=not selected_nct,
                type="primary" if selected_nct else "secondary",
            )
        with clear_col:
            if trial_b and st.button("✕ Clear", key="os_clear_b", use_container_width=True):
                st.session_state["os_trial_b"] = None
                st.rerun()
        if load_b and selected_nct:
            st.session_state["os_trial_b"] = selected_nct
            st.rerun()

    # ── comparison panels ─────────────────────────────────────────────────────
    st.markdown(
        f'<h3 style="color:{COLORS["primary"]};margin-top:32px;">Side-by-Side Comparison</h3>',
        unsafe_allow_html=True,
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if trial_a:
            _outcome_panel("A", trial_a, COLORS["primary"])
        else:
            _placeholder_panel("A", COLORS["primary"])
    with col_b:
        if trial_b:
            _outcome_panel("B", trial_b, COLORS["accent"])
        else:
            _placeholder_panel("B", COLORS["accent"])
