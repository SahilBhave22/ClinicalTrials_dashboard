"""
Sidebar filter UI components.

Renders the global filters (indication_name, atc_class_name) and all
downstream filters whose option lists are constrained by the global selection.
"""
from __future__ import annotations

import json
from pathlib import Path
import streamlit as st

from utils.filters import FilterState, get_filters, set_filters
from data.repository import (
    get_filter_options,
    get_indication_options,
    get_atc_class_options,
)
from config.settings import APP_TITLE, APP_ICON


# ── Fallback values from catalog JSON ────────────────────────────────────────

def _load_catalog_fallback() -> tuple[list[str], list[str]]:
    """Load indication / atc_class values from the drugs catalog JSON as fallback."""
    try:
        catalog_path = Path("catalogs/drugs_schema_catalog.json")
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        indications = [
            v.strip() for v in data.get("drug_indication_values", "").split(",") if v.strip()
        ]
        atc_classes = [
            v.strip() for v in data.get("drug_class_values", "").split(",") if v.strip()
        ]
        return sorted(indications), sorted(atc_classes)
    except Exception:
        return [], []


@st.cache_data(ttl=3600, show_spinner=False)
def _get_indication_list() -> list[str]:
    opts = get_indication_options()
    if opts:
        return opts
    fallback_ind, _ = _load_catalog_fallback()
    return fallback_ind


@st.cache_data(ttl=3600, show_spinner=False)
def _get_atc_class_list() -> list[str]:
    opts = get_atc_class_options()
    if opts:
        return opts
    _, fallback_atc = _load_catalog_fallback()
    return fallback_atc


# ── Global filter clear helper ────────────────────────────────────────────────

def _do_clear_filter(clear_ind: bool = False, clear_atc: bool = False) -> None:
    """
    Clear one or both global filters, reset all downstream filters,
    and wipe the corresponding widget session_state keys so widgets
    re-render with empty values on the next run.
    """
    fs = get_filters()

    if clear_ind:
        fs.indication_name = None
        st.session_state["sb_indication"] = ""
    if clear_atc:
        fs.atc_class_name = None
        st.session_state["sb_atc"] = ""

    # Always reset downstream when a global filter is cleared
    fs.sponsor               = []
    fs.sponsor_agency_class  = []
    fs.brand_name            = []
    fs.drug_indication       = None
    fs.study_type            = []
    fs.phase                 = []
    fs.overall_status        = []
    fs.country               = []
    fs.endpoint_category     = []
    fs.outcome_type          = []
    fs.pro_instrument        = []
    fs.pro_domain            = []
    fs.ae_organ_system       = []
    fs.ae_term               = []
    fs.has_results           = None
    fs.enrollment_min        = None
    fs.enrollment_max        = None
    fs._resolved_brand_names = []

    # Wipe downstream widget keys so they re-render empty
    for key in ("ms_study_type", "ms_phase", "ms_status", "ms_sponsor", "ms_agency_class",
                "ms_brand", "ms_drug_ind",
                "ms_epcat", "ms_pro_inst", "ms_pro_dom", "ms_country"):
        st.session_state.pop(key, None)
    st.session_state["sel_results"] = "Any"
    st.session_state["ni_enr_min"]  = 0
    st.session_state["ni_enr_max"]  = 0

    set_filters(fs)


# ── Global filter change callback ─────────────────────────────────────────────

def _on_global_filter_change() -> None:
    """
    Called by on_change when the user explicitly changes a global selectbox.
    Resets all downstream filters so they are re-scoped to the new global selection.
    Only fires on real user interaction — NOT on reruns triggered by tab switches.
    """
    fs = get_filters()
    new_ind = st.session_state.get("sb_indication") or None
    new_atc = st.session_state.get("sb_atc") or None

    if new_ind == fs.indication_name and new_atc == fs.atc_class_name:
        return  # No actual change, nothing to reset

    fs.indication_name       = new_ind
    fs.atc_class_name        = new_atc
    fs.sponsor               = []
    fs.sponsor_agency_class  = []
    fs.brand_name            = []
    fs.drug_indication       = None
    fs.study_type            = []
    fs.phase                 = []
    fs.overall_status        = []
    fs.country               = []
    fs.endpoint_category     = []
    fs.outcome_type          = []
    fs.pro_instrument        = []
    fs.pro_domain            = []
    fs.ae_organ_system       = []
    fs.ae_term               = []
    fs.has_results           = None
    fs.enrollment_min        = None
    fs.enrollment_max        = None
    fs._resolved_brand_names = []
    set_filters(fs)


# ── Main sidebar renderer ─────────────────────────────────────────────────────

def render_sidebar() -> FilterState:
    """
    Render the full sidebar filter panel.
    Returns the current (updated) FilterState.
    """
    fs = get_filters()

    with st.sidebar:
        # ── Sidebar header (filters only) ─────────────────────────────────────
        st.markdown(
            "<h3 style='color:#E2E8F0;margin:4px 0 2px 0;font-size:1rem;font-weight:700;'>"
            "⚙️ Filters</h3>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<hr style='margin:6px 0 14px 0; border-color:rgba(255,255,255,0.15);'>",
            unsafe_allow_html=True,
        )

        # ── GLOBAL FILTERS ────────────────────────────────────────────────────
        st.markdown("#### 🌐 Global Filters")
        st.caption("These filters drive all pages. Indication uses MeSH conditions (browse_conditions); Drug Class uses ATC codes.")

        indication_opts = [""] + _get_indication_list()
        atc_opts        = [""] + _get_atc_class_list()

        prev_ind = fs.indication_name or ""
        prev_atc = fs.atc_class_name or ""

        ind_col, ind_clear = st.columns([5, 1])
        with ind_col:
            sel_ind = st.selectbox(
                "Indication (Disease Area)",
                options=indication_opts,
                index=indication_opts.index(prev_ind) if prev_ind in indication_opts else 0,
                help="MeSH mesh-list condition from ctgov.browse_conditions. Scopes all pages to trials with this condition that are also in drug_trials.",
                key="sb_indication",
                on_change=_on_global_filter_change,
            )
        with ind_clear:
            st.markdown("<div style='margin-top:26px'></div>", unsafe_allow_html=True)
            if prev_ind:
                st.button("✕", key="btn_clear_ind", help="Clear Indication filter",
                          use_container_width=True,
                          on_click=_do_clear_filter, kwargs={"clear_ind": True})

        atc_col, atc_clear = st.columns([5, 1])
        with atc_col:
            sel_atc = st.selectbox(
                "Drug Class (ATC)",
                options=atc_opts,
                index=atc_opts.index(prev_atc) if prev_atc in atc_opts else 0,
                help="Filters all data to trials associated with this drug class. "
                     "Independent of Indication.",
                key="sb_atc",
                on_change=_on_global_filter_change,
            )
        with atc_clear:
            st.markdown("<div style='margin-top:26px'></div>", unsafe_allow_html=True)
            if prev_atc:
                st.button("✕", key="btn_clear_atc", help="Clear Drug Class filter",
                          use_container_width=True,
                          on_click=_do_clear_filter, kwargs={"clear_atc": True})

        # Re-read fs after potential on_change reset, then sync widget values
        fs = get_filters()
        fs.indication_name = sel_ind or None
        fs.atc_class_name  = sel_atc or None

        # ── Downstream filter options (constrained by global) ──────────────
        opts = get_filter_options(fs.indication_name, fs.atc_class_name)

        st.markdown("<hr style='margin:12px 0;border-color:rgba(255,255,255,0.15);'>", unsafe_allow_html=True)
        st.markdown("#### 🔽 Downstream Filters")

        with st.expander("Trial Attributes", expanded=True):
            fs.study_type = st.multiselect(
                "Study Type",
                options=opts.get("study_types", []),
                default=[t for t in fs.study_type if t in opts.get("study_types", [])],
                key="ms_study_type",
            )
            fs.phase = st.multiselect(
                "Phase",
                options=opts.get("phases", []),
                default=[p for p in fs.phase if p in opts.get("phases", [])],
                key="ms_phase",
            )
            fs.overall_status = st.multiselect(
                "Status",
                options=opts.get("statuses", []),
                default=[s for s in fs.overall_status if s in opts.get("statuses", [])],
                key="ms_status",
            )
            has_results_options = {"Any": None, "Has Results": True, "No Results": False}
            hr_label = {None: "Any", True: "Has Results", False: "No Results"}[fs.has_results]
            fs.has_results = has_results_options[
                st.selectbox("Results Posted", list(has_results_options.keys()),
                             index=list(has_results_options.keys()).index(hr_label),
                             key="sel_results")
            ]

        with st.expander("Sponsor / Drug"):
            fs.sponsor = st.multiselect(
                "Sponsor",
                options=opts.get("sponsors", []),
                default=[s for s in fs.sponsor if s in opts.get("sponsors", [])],
                key="ms_sponsor",
            )
            fs.sponsor_agency_class = st.multiselect(
                "Agency Class",
                options=opts.get("agency_classes", []),
                default=[a for a in fs.sponsor_agency_class if a in opts.get("agency_classes", [])],
                key="ms_agency_class",
                help="Lead sponsor organisation type: INDUSTRY, FED, OTHER_GOV, INDIV.",
            )
            fs.brand_name = st.multiselect(
                "Drug (Brand Name)",
                options=opts.get("brands", []),
                default=[b for b in fs.brand_name if b in opts.get("brands", [])],
                key="ms_brand",
            )
            # Drug Indication — from public.drug_indications, scoped by brands in scope.
            # This is a downstream filter distinct from the global MeSH Indication filter.
            drug_ind_opts = [""] + opts.get("drug_indications", [])
            prev_drug_ind = fs.drug_indication or ""
            sel_drug_ind = st.selectbox(
                "Drug Indication (Label)",
                options=drug_ind_opts,
                index=drug_ind_opts.index(prev_drug_ind) if prev_drug_ind in drug_ind_opts else 0,
                help="Filter by the labeled indication from the drugs database (drug_indications table).",
                key="ms_drug_ind",
            )
            fs.drug_indication = sel_drug_ind or None

        with st.expander("Enrollment"):
            enr_min = st.number_input(
                "Min Enrollment", min_value=0, value=fs.enrollment_min or 0,
                step=10, key="ni_enr_min",
            )
            enr_max = st.number_input(
                "Max Enrollment", min_value=0, value=fs.enrollment_max or 0,
                step=10, key="ni_enr_max",
            )
            fs.enrollment_min = int(enr_min) if enr_min > 0 else None
            fs.enrollment_max = int(enr_max) if enr_max > 0 else None

        with st.expander("Endpoints / Outcomes"):
            fs.endpoint_category = st.multiselect(
                "Endpoint Category",
                options=opts.get("categories", []),
                default=[c for c in fs.endpoint_category if c in opts.get("categories", [])],
                key="ms_epcat",
            )

        with st.expander("PRO"):
            fs.pro_instrument = st.multiselect(
                "PRO Instrument",
                options=opts.get("pro_instruments", []),
                default=[p for p in fs.pro_instrument if p in opts.get("pro_instruments", [])],
                key="ms_pro_inst",
            )
            fs.pro_domain = st.multiselect(
                "PRO Domain",
                options=opts.get("domains", []),
                default=[d for d in fs.pro_domain if d in opts.get("domains", [])],
                key="ms_pro_dom",
            )

        with st.expander("Geography"):
            fs.country = st.multiselect(
                "Country",
                options=opts.get("countries", []),
                default=[c for c in fs.country if c in opts.get("countries", [])],
                key="ms_country",
            )

        st.markdown("<hr style='margin:12px 0;border-color:rgba(255,255,255,0.15);'>", unsafe_allow_html=True)
        st.button("🔄 Reset All Filters", use_container_width=True, key="btn_reset",
                  on_click=_do_clear_filter, kwargs={"clear_ind": True, "clear_atc": True})

    set_filters(fs)
    return fs
