"""
Sidebar filter UI components.

Renders the global filters (indication_name, atc_class_name) and all
downstream filters whose option lists are constrained by the global selection.
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from data.repository import (
    get_atc_class_options,
    get_filter_options,
    get_indication_options,
)
from utils.filters import (
    FilterState,
    get_filters,
    set_filters,
    get_unique_display_labels,
)

_DOWNSTREAM_WIDGET_KEYS = (
    "ms_study_type",
    "ms_phase",
    "ms_status",
    "ms_sponsor",
    "ms_agency_class",
    "ms_brand",
    "ms_drug_ind",
    "ms_epcat",
    "ms_pro_inst",
    "ms_pro_dom",
    "ms_country",
)
_DRAFT_GLOBALS_KEY = "_sidebar_draft_globals"
_HAS_RESULTS_OPTIONS = {"Any": None, "Has Results": True, "No Results": False}


def _load_condition_sponsor_catalog() -> dict:
    """Load condition/sponsor/drug-class values from the condition_sponsor catalog."""
    try:
        path = Path("catalogs/condition_sponsor_values.json")
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


@st.cache_data(show_spinner=False)
def _load_static_filter_values() -> dict:
    """Load pre-set filter values (study types, phases, statuses, countries, etc.)."""
    try:
        path = Path("catalogs/filter_static_values.json")
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_indication_list() -> list[str]:
    """
    Return unique human-readable disease labels for the Condition dropdown.
    Sourced from disease_bucket_mapping.json (2939 labels covering 6298 raw
    condition names). Falls back to the raw condition catalog, then DB.
    """
    labels = get_unique_display_labels()
    if labels:
        return labels
    # fallback: raw names from the condition catalog
    data = _load_condition_sponsor_catalog()
    values = [v.strip() for v in data.get("condition_values", "").split("|") if v.strip()]
    if values:
        return sorted(values)
    return get_indication_options()


def _get_atc_class_list() -> list[str]:
    """Return ATC drug class list from catalog (instant). DB enrichment skipped."""
    data = _load_condition_sponsor_catalog()
    values = [v.strip() for v in data.get("drug_class_values", "").split("|") if v.strip()]
    if values:
        return sorted(values)
    return get_atc_class_options()


def _get_sponsor_list() -> list[str]:
    """Return sponsor list from catalog (instant)."""
    data = _load_condition_sponsor_catalog()
    return sorted([v.strip() for v in data.get("sponsor_values", "").split("|") if v.strip()])


def _get_static_opts() -> dict:
    """
    Return filter options entirely from static catalogs, without a DB call.
    Used when no global filter is active.
    """
    sv = _load_static_filter_values()
    return {
        "sponsors": _get_sponsor_list(),
        "study_types": sv.get("study_types", []),
        "phases": sv.get("phases", []),
        "statuses": sv.get("overall_statuses", []),
        "countries": sv.get("countries", []),
        "agency_classes": sv.get("agency_classes", []),
        "categories": sv.get("endpoint_categories", []),
        "pro_instruments": sv.get("pro_instruments", []),
        "domains": sv.get("pro_domains", []),
        "brands": [],
        "drug_indications": [],
    }


def _clear_downstream_widget_state(reset_to_empty: bool = True) -> None:
    """Reset downstream widget state for either a fresh draft or applied rehydrate."""
    if reset_to_empty:
        empty_values = {
            "ms_study_type": [],
            "ms_phase": [],
            "ms_status": [],
            "ms_sponsor": [],
            "ms_agency_class": [],
            "ms_brand": [],
            "ms_drug_ind": "",
            "ms_epcat": [],
            "ms_pro_inst": [],
            "ms_pro_dom": [],
            "ms_country": [],
        }
        for key, value in empty_values.items():
            st.session_state[key] = value
    else:
        for key in _DOWNSTREAM_WIDGET_KEYS:
            st.session_state.pop(key, None)
    st.session_state["sel_results"] = "Any"
    st.session_state["ni_enr_min"] = 0
    st.session_state["ni_enr_max"] = 0


def _apply_sidebar_filters() -> None:
    """Commit the current sidebar widget selections into the applied FilterState."""
    fs = get_filters()
    fs.indication_name = st.session_state.get("sb_indication") or None
    fs.atc_class_name = st.session_state.get("sb_atc") or None
    fs.study_type = list(st.session_state.get("ms_study_type", []))
    fs.phase = list(st.session_state.get("ms_phase", []))
    fs.overall_status = list(st.session_state.get("ms_status", []))
    fs.sponsor = list(st.session_state.get("ms_sponsor", []))
    fs.sponsor_agency_class = list(st.session_state.get("ms_agency_class", []))
    fs.brand_name = list(st.session_state.get("ms_brand", []))
    fs.drug_indication = st.session_state.get("ms_drug_ind") or None
    fs.endpoint_category = list(st.session_state.get("ms_epcat", []))
    fs.pro_instrument = list(st.session_state.get("ms_pro_inst", []))
    fs.pro_domain = list(st.session_state.get("ms_pro_dom", []))
    fs.country = list(st.session_state.get("ms_country", []))
    fs.has_results = _HAS_RESULTS_OPTIONS.get(st.session_state.get("sel_results", "Any"))
    fs.enrollment_min = None
    fs.enrollment_max = None
    fs._resolved_brand_names = []
    set_filters(fs)
    st.session_state[_DRAFT_GLOBALS_KEY] = (fs.indication_name, fs.atc_class_name)


def _sidebar_has_pending_changes(fs: FilterState) -> bool:
    """Return True when current widget selections differ from applied filters."""
    return any((
        (st.session_state.get("sb_indication") or None) != fs.indication_name,
        (st.session_state.get("sb_atc") or None) != fs.atc_class_name,
        list(st.session_state.get("ms_study_type", [])) != fs.study_type,
        list(st.session_state.get("ms_phase", [])) != fs.phase,
        list(st.session_state.get("ms_status", [])) != fs.overall_status,
        list(st.session_state.get("ms_sponsor", [])) != fs.sponsor,
        list(st.session_state.get("ms_agency_class", [])) != fs.sponsor_agency_class,
        list(st.session_state.get("ms_brand", [])) != fs.brand_name,
        (st.session_state.get("ms_drug_ind") or None) != fs.drug_indication,
        list(st.session_state.get("ms_epcat", [])) != fs.endpoint_category,
        list(st.session_state.get("ms_pro_inst", [])) != fs.pro_instrument,
        list(st.session_state.get("ms_pro_dom", [])) != fs.pro_domain,
        list(st.session_state.get("ms_country", [])) != fs.country,
        _HAS_RESULTS_OPTIONS.get(st.session_state.get("sel_results", "Any")) != fs.has_results,
    ))


def _do_clear_filter(clear_ind: bool = False, clear_atc: bool = False) -> None:
    """
    Clear one or both global filters, reset all downstream filters, and wipe the
    corresponding widget session_state keys so widgets re-render empty.
    """
    fs = get_filters()

    if clear_ind:
        fs.indication_name = None
        st.session_state["sb_indication"] = ""
    if clear_atc:
        fs.atc_class_name = None
        st.session_state["sb_atc"] = ""

    fs.sponsor = []
    fs.sponsor_agency_class = []
    fs.brand_name = []
    fs.drug_indication = None
    fs.study_type = []
    fs.phase = []
    fs.overall_status = []
    fs.country = []
    fs.endpoint_category = []
    fs.outcome_type = []
    fs.pro_instrument = []
    fs.pro_domain = []
    fs.ae_organ_system = []
    fs.ae_term = []
    fs.has_results = None
    fs.enrollment_min = None
    fs.enrollment_max = None
    fs._resolved_brand_names = []

    _clear_downstream_widget_state()
    st.session_state.pop("_pending_sb_indication", None)
    st.session_state.pop("_pending_sb_atc", None)
    st.session_state[_DRAFT_GLOBALS_KEY] = (fs.indication_name, fs.atc_class_name)
    set_filters(fs)


def _on_global_filter_change() -> None:
    """
    When a global filter changes, clear downstream widget + applied state and
    immediately apply the new global value so every page reflects it without
    requiring a separate "Apply Filters" click.
    """
    new_ind = st.session_state.get("sb_indication") or None
    new_atc = st.session_state.get("sb_atc") or None
    prev_ind, prev_atc = st.session_state.get(
        _DRAFT_GLOBALS_KEY,
        (get_filters().indication_name, get_filters().atc_class_name),
    )

    if new_ind == prev_ind and new_atc == prev_atc:
        return

    _clear_downstream_widget_state()
    st.session_state[_DRAFT_GLOBALS_KEY] = (new_ind, new_atc)

    # Immediately persist global filter change into FilterState so the page
    # updates on this rerun without requiring an explicit Apply click.
    fs = get_filters()
    fs.indication_name = new_ind
    fs.atc_class_name = new_atc
    fs.sponsor = []
    fs.sponsor_agency_class = []
    fs.brand_name = []
    fs.drug_indication = None
    fs.study_type = []
    fs.phase = []
    fs.overall_status = []
    fs.country = []
    fs.endpoint_category = []
    fs.outcome_type = []
    fs.pro_instrument = []
    fs.pro_domain = []
    fs.ae_organ_system = []
    fs.ae_term = []
    fs.has_results = None
    fs.enrollment_min = None
    fs.enrollment_max = None
    fs._resolved_brand_names = []
    set_filters(fs)


def render_sidebar() -> FilterState:
    """
    Render the full sidebar filter panel.
    Returns the currently applied FilterState.
    """
    fs = get_filters()

    if "_pending_sb_indication" in st.session_state:
        st.session_state["sb_indication"] = st.session_state.pop("_pending_sb_indication")
    if "_pending_sb_atc" in st.session_state:
        st.session_state["sb_atc"] = st.session_state.pop("_pending_sb_atc")

    with st.sidebar:
        st.markdown(
            "<h3 style='color:#E2E8F0;margin:4px 0 2px 0;font-size:1rem;font-weight:700;'>"
            "Filters</h3>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<hr style='margin:6px 0 14px 0; border-color:rgba(255,255,255,0.15);'>",
            unsafe_allow_html=True,
        )

        st.markdown("#### Global Filters")
        st.caption("Drug class and Condition filters")

        allowed_indications = fs.allowed_indications
        allowed_atc_classes = fs.allowed_atc_classes

        if allowed_indications is not None:
            # allowed_indications already holds display labels — use directly.
            indication_opts = [""] + sorted(allowed_indications)
        else:
            indication_opts = [""] + _get_indication_list()
        if "sb_indication" not in st.session_state:
            st.session_state["sb_indication"] = fs.indication_name or ""

        sel_ind = st.selectbox(
            "Condition (Disease Area)",
            options=indication_opts,
            help=(
                "Select a disease area to scope all pages to trials matching that "
                "condition. One display label may cover several raw condition names."
            ),
            key="sb_indication",
            on_change=_on_global_filter_change,
        )

        if allowed_atc_classes is not None:
            atc_opts = [""] + allowed_atc_classes
        else:
            atc_opts = [""] + _get_atc_class_list()
        if "sb_atc" not in st.session_state:
            st.session_state["sb_atc"] = fs.atc_class_name or ""

        sel_atc = st.selectbox(
            "Drug Class (ATC)",
            options=atc_opts,
            help="Filters all data to trials associated with this drug class. Independent of Indication.",
            key="sb_atc",
            on_change=_on_global_filter_change,
        )

        draft_indication = sel_ind or None
        draft_atc_class = sel_atc or None

        if draft_indication or draft_atc_class:
            opts = get_filter_options(draft_indication, draft_atc_class)
        else:
            opts = _get_static_opts()

        st.markdown("<hr style='margin:12px 0;border-color:rgba(255,255,255,0.15);'>", unsafe_allow_html=True)
        st.markdown("#### Downstream Filters")

        # Initialise widget session-state keys from FilterState only when absent.
        # Using setdefault avoids conflicting with values already written by
        # _clear_downstream_widget_state or _apply_sidebar_filters.
        st.session_state.setdefault("ms_study_type",   [t for t in fs.study_type          if t in opts.get("study_types",   [])])
        st.session_state.setdefault("ms_phase",        [p for p in fs.phase               if p in opts.get("phases",        [])])
        st.session_state.setdefault("ms_status",       [s for s in fs.overall_status      if s in opts.get("statuses",      [])])
        st.session_state.setdefault("ms_sponsor",      [s for s in fs.sponsor             if s in opts.get("sponsors",      [])])
        st.session_state.setdefault("ms_agency_class", [a for a in fs.sponsor_agency_class if a in opts.get("agency_classes", [])])
        st.session_state.setdefault("ms_brand",        [b for b in fs.brand_name          if b in opts.get("brands",        [])])
        st.session_state.setdefault("ms_drug_ind",     fs.drug_indication or "")
        st.session_state.setdefault("ms_epcat",        [c for c in fs.endpoint_category   if c in opts.get("categories",    [])])
        st.session_state.setdefault("ms_pro_inst",     [p for p in fs.pro_instrument      if p in opts.get("pro_instruments", [])])
        st.session_state.setdefault("ms_pro_dom",      [d for d in fs.pro_domain          if d in opts.get("domains",       [])])
        st.session_state.setdefault("ms_country",      [c for c in fs.country             if c in opts.get("countries",     [])])
        st.session_state.setdefault("sel_results",
            {None: "Any", True: "Has Results", False: "No Results"}[fs.has_results])

        with st.expander("Trial Attributes", expanded=False):
            st.multiselect(
                "Study Type",
                options=opts.get("study_types", []),
                key="ms_study_type",
                on_change=_apply_sidebar_filters,
            )
            st.multiselect(
                "Phase",
                options=opts.get("phases", []),
                key="ms_phase",
                on_change=_apply_sidebar_filters,
            )
            st.multiselect(
                "Status",
                options=opts.get("statuses", []),
                key="ms_status",
                on_change=_apply_sidebar_filters,
            )
            st.selectbox(
                "Results Posted",
                list(_HAS_RESULTS_OPTIONS.keys()),
                key="sel_results",
                on_change=_apply_sidebar_filters,
            )

        with st.expander("Sponsor / Drug"):
            st.multiselect(
                "Sponsor",
                options=opts.get("sponsors", []),
                key="ms_sponsor",
                on_change=_apply_sidebar_filters,
            )
            st.multiselect(
                "Agency Class",
                options=opts.get("agency_classes", []),
                key="ms_agency_class",
                help="Lead sponsor organisation type: INDUSTRY, FED, OTHER_GOV, INDIV.",
                on_change=_apply_sidebar_filters,
            )
            st.multiselect(
                "Drug (Brand Name)",
                options=opts.get("brands", []),
                key="ms_brand",
                on_change=_apply_sidebar_filters,
            )
            drug_ind_opts = [""] + opts.get("drug_indications", [])
            st.selectbox(
                "Drug Indication (Label)",
                options=drug_ind_opts,
                help="Filter by the labeled indication from the drugs database (drug_indications table).",
                key="ms_drug_ind",
                on_change=_apply_sidebar_filters,
            )

        with st.expander("Endpoints / Outcomes"):
            st.multiselect(
                "Endpoint Category",
                options=opts.get("categories", []),
                key="ms_epcat",
                on_change=_apply_sidebar_filters,
            )

        with st.expander("PRO"):
            st.multiselect(
                "PRO Instrument",
                options=opts.get("pro_instruments", []),
                key="ms_pro_inst",
                on_change=_apply_sidebar_filters,
            )
            st.multiselect(
                "PRO Domain",
                options=opts.get("domains", []),
                key="ms_pro_dom",
                on_change=_apply_sidebar_filters,
            )

        with st.expander("Geography"):
            st.multiselect(
                "Country",
                options=opts.get("countries", []),
                key="ms_country",
                on_change=_apply_sidebar_filters,
            )

        if _sidebar_has_pending_changes(fs):
            st.caption("You have unapplied filter changes.")

        st.markdown("<hr style='margin:12px 0;border-color:rgba(255,255,255,0.15);'>", unsafe_allow_html=True)
        st.button(
            "Apply Filters",
            use_container_width=True,
            type="primary",
            key="btn_apply_filters",
            on_click=_apply_sidebar_filters,
        )
        st.button(
            "Reset All Filters",
            use_container_width=True,
            key="btn_reset",
            on_click=_do_clear_filter,
            kwargs={"clear_ind": True, "clear_atc": True},
        )

    st.session_state[_DRAFT_GLOBALS_KEY] = (draft_indication, draft_atc_class)
    return get_filters()
