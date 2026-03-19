"""
Active filter summary bar — rendered at the top of every page.
"""
from __future__ import annotations
import streamlit as st
from utils.filters import FilterState


_CSS = """
<style>
/* ── Filter bar container ─────────────────────────────────────────────────── */
.fbar {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 10px;
    padding: 9px 14px;
    margin-bottom: 18px;
    box-shadow: 0 1px 4px rgba(0,0,0,.05);
    font-family: 'DM Sans', system-ui, sans-serif;
}

/* ── Left label ───────────────────────────────────────────────────────────── */
.fbar-header {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #9CA3AF;
    white-space: nowrap;
    padding-right: 12px;
    border-right: 1px solid #E5E7EB;
    flex-shrink: 0;
    line-height: 1;
    align-self: center;
}

/* ── Empty state ──────────────────────────────────────────────────────────── */
.fbar-empty {
    font-size: 0.82rem;
    color: #9CA3AF;
    font-style: italic;
    display: flex;
    align-items: center;
    gap: 6px;
}

/* ── Chips wrapper ────────────────────────────────────────────────────────── */
.fbar-chips {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    flex: 1;
}

/* ── Individual chip ──────────────────────────────────────────────────────── */
.fchip {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    border-radius: 7px;
    padding: 5px 11px 5px 9px;
    border: 1px solid transparent;
    line-height: 1;
    max-width: 240px;
    white-space: nowrap;
}

/* Global filters — Indication & Drug Class */
.fchip-global {
    background: #F5F3FF;
    border-color: #C4B5FD;
}
.fchip-global .fchip-icon  { color: #7C3AED; }
.fchip-global .fchip-label { color: #6D28D9; }
.fchip-global .fchip-val   { color: #4C1D95; }

/* Downstream filters */
.fchip-standard {
    background: #EBF4FB;
    border-color: #A8DADC;
}
.fchip-standard .fchip-icon  { color: #2E86AB; }
.fchip-standard .fchip-label { color: #0F4C81; }
.fchip-standard .fchip-val   { color: #0B1929; }

/* ── Chip parts ───────────────────────────────────────────────────────────── */
.fchip-icon {
    font-size: 0.90rem;
    line-height: 1;
    flex-shrink: 0;
    display: flex;
    align-items: center;
}
.fchip-body {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
}
.fchip-label {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    line-height: 1;
    white-space: nowrap;
}
.fchip-val {
    font-size: 0.80rem;
    font-weight: 600;
    line-height: 1.2;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 180px;
}

/* ── Count badge ──────────────────────────────────────────────────────────── */
.fbar-badge {
    margin-left: auto;
    flex-shrink: 0;
    background: #0F4C81;
    color: #FFFFFF;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 3px 9px;
    border-radius: 999px;
    white-space: nowrap;
    line-height: 1.4;
    align-self: center;
}
</style>
"""

# icon + chip-type for every label produced by active_filter_summary()
_FILTER_META: dict[str, tuple[str, str]] = {
    "Indication":        ("🧬", "global"),
    "Drug Class":        ("💊", "global"),
    "Drug":              ("🔬", "standard"),
    "Sponsor":           ("🏢", "standard"),
    "Phase":             ("⚗️",  "standard"),
    "Status":            ("📊", "standard"),
    "Country":           ("🌍", "standard"),
    "Enrollment":        ("👥", "standard"),
    "Has Results":       ("📋", "standard"),
    "Endpoint Category": ("🎯", "standard"),
    "PRO Instrument":    ("📝", "standard"),
    "PRO Domain":        ("📐", "standard"),
}


def filter_summary_bar(filters: FilterState) -> None:
    """Render the active-filter chip bar below the page header."""
    # Always inject CSS (idempotent — browser deduplicates identical <style> blocks)
    st.markdown(_CSS, unsafe_allow_html=True)

    active = filters.active_filter_summary()

    if not active:
        st.markdown(
            '<div class="fbar">'
            '  <div class="fbar-header">🔍&nbsp;Filters</div>'
            '  <span class="fbar-empty">No filters active &mdash; showing all available data</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    chips_html = ""
    for label, val in active.items():
        icon, chip_type = _FILTER_META.get(label, ("🔷", "standard"))
        # Truncate long values for display; keep full value in title for tooltip
        display_val = val if len(val) <= 36 else val[:33] + "…"
        chips_html += (
            f'<span class="fchip fchip-{chip_type}">'
            f'  <span class="fchip-icon">{icon}</span>'
            f'  <span class="fchip-body">'
            f'    <span class="fchip-label">{label}</span>'
            f'    <span class="fchip-val" title="{val}">{display_val}</span>'
            f'  </span>'
            f'</span>'
        )

    n = len(active)
    plural = "filter" if n == 1 else "filters"
    badge = f'<span class="fbar-badge">{n}&nbsp;{plural} active</span>'

    st.markdown(
        f'<div class="fbar">'
        f'  <div class="fbar-header">🔍&nbsp;Filters</div>'
        f'  <div class="fbar-chips">{chips_html}</div>'
        f'  {badge}'
        f'</div>',
        unsafe_allow_html=True,
    )
