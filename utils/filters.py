"""
Filter state management: dataclass + Streamlit session_state helpers.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional
import json
from pathlib import Path
import streamlit as st


@dataclass
class FilterState:
    # ── Primary global filters (indication = browse_conditions mesh_term) ───────
    indication_name: Optional[str] = None   # ctgov.browse_conditions mesh_term
    atc_class_name:  Optional[str] = None   # drug_classes ATC code

    # ── Downstream filters ────────────────────────────────────────────────────
    sponsor:               List[str] = field(default_factory=list)
    sponsor_agency_class:  List[str] = field(default_factory=list)  # ctgov.sponsors.agency_class
    brand_name:            List[str] = field(default_factory=list)
    drug_indication:       Optional[str] = None   # drug_indications.indication_name (Sponsor/Drug tab)
    study_type:         List[str] = field(default_factory=list)
    phase:              List[str] = field(default_factory=list)
    overall_status:     List[str] = field(default_factory=list)
    country:            List[str] = field(default_factory=list)
    endpoint_category:  List[str] = field(default_factory=list)
    outcome_type:       List[str] = field(default_factory=list)
    pro_instrument:     List[str] = field(default_factory=list)
    pro_domain:         List[str] = field(default_factory=list)
    ae_organ_system:    List[str] = field(default_factory=list)
    ae_term:            List[str] = field(default_factory=list)
    has_results:        Optional[bool] = None
    enrollment_min:     Optional[int] = None
    enrollment_max:     Optional[int] = None

    # ── Per-user data restrictions (set once at login, never cleared by sidebar) ─
    allowed_indications: Optional[List[str]] = None   # None = no restriction
    allowed_atc_classes: Optional[List[str]] = None   # None = no restriction

    # ── Derived / cached (resolved at query time) ─────────────────────────────
    _resolved_brand_names: List[str] = field(default_factory=list)

    def has_global_filter(self) -> bool:
        return bool(self.indication_name or self.atc_class_name)

    def has_any_filter(self) -> bool:
        return (
            self.has_global_filter()
            or bool(self.sponsor or self.sponsor_agency_class
                    or self.brand_name or self.drug_indication
                    or self.study_type or self.phase
                    or self.overall_status or self.country
                    or self.endpoint_category or self.outcome_type
                    or self.pro_instrument or self.pro_domain
                    or self.ae_organ_system or self.ae_term
                    or self.has_results is not None
                    or self.enrollment_min is not None
                    or self.enrollment_max is not None)
        )

    def active_filter_summary(self) -> dict[str, str]:
        """Return dict of {label: value} for currently active filters."""
        out: dict[str, str] = {}
        if self.indication_name:
            out["Indication"] = self.indication_name
        if self.atc_class_name:
            out["Drug Class"] = self.atc_class_name
        if self.sponsor:
            out["Sponsor"] = ", ".join(self.sponsor)
        if self.sponsor_agency_class:
            out["Agency Class"] = ", ".join(self.sponsor_agency_class)
        if self.brand_name:
            out["Drug"] = ", ".join(self.brand_name)
        if self.drug_indication:
            out["Drug Indication"] = self.drug_indication
        if self.study_type:
            out["Study Type"] = ", ".join(self.study_type)
        if self.phase:
            out["Phase"] = ", ".join(self.phase)
        if self.overall_status:
            out["Status"] = ", ".join(self.overall_status)
        if self.country:
            out["Country"] = ", ".join(self.country)
        if self.endpoint_category:
            out["Endpoint Category"] = ", ".join(self.endpoint_category)
        if self.pro_instrument:
            out["PRO Instrument"] = ", ".join(self.pro_instrument)
        if self.pro_domain:
            out["PRO Domain"] = ", ".join(self.pro_domain)
        if self.has_results is not None:
            out["Has Results"] = "Yes" if self.has_results else "No"
        if self.enrollment_min or self.enrollment_max:
            lo = self.enrollment_min or 0
            hi = self.enrollment_max or "∞"
            out["Enrollment"] = f"{lo}–{hi}"
        return out


# ── Catalog helpers (no DB, cached for process lifetime) ─────────────────────

@lru_cache(maxsize=1)
def _load_full_indication_list() -> tuple[str, ...]:
    """Return all available indications from the static catalog."""
    try:
        data = json.loads(
            Path("catalogs/condition_sponsor_values.json").read_text(encoding="utf-8")
        )
        return tuple(
            sorted([v.strip() for v in data.get("condition_values", "").split("|") if v.strip()])
        )
    except Exception:
        return ()


@lru_cache(maxsize=1)
def _load_full_atc_class_list() -> tuple[str, ...]:
    """Return all available ATC drug classes from the static catalog."""
    try:
        data = json.loads(
            Path("catalogs/condition_sponsor_values.json").read_text(encoding="utf-8")
        )
        return tuple(
            sorted([v.strip() for v in data.get("drug_class_values", "").split("|") if v.strip()])
        )
    except Exception:
        return ()


SESSION_KEY = "filter_state"


def get_filters() -> FilterState:
    """Retrieve current FilterState from session_state (create default if absent).

    If a user_access config is in session state, the restriction fields on the
    FilterState are always synced from it so they can never be cleared by accident.
    """
    if SESSION_KEY not in st.session_state:
        st.session_state[SESSION_KEY] = FilterState()
    fs: FilterState = st.session_state[SESSION_KEY]

    # Re-sync user restrictions from session state on every access.
    # Supports both inclusion lists (disease_areas) and exclusion lists (disease_areas_exclude).
    # If both are supplied, the inclusion list takes precedence.
    ua = st.session_state.get("user_access", {})

    disease_areas         = ua.get("disease_areas")
    disease_areas_exclude = ua.get("disease_areas_exclude")
    if disease_areas is not None:
        fs.allowed_indications = disease_areas
    elif disease_areas_exclude is not None:
        excl = {e.lower() for e in disease_areas_exclude}
        fs.allowed_indications = [i for i in _load_full_indication_list() if i.lower() not in excl]
    else:
        fs.allowed_indications = None

    drug_classes         = ua.get("drug_classes")
    drug_classes_exclude = ua.get("drug_classes_exclude")
    if drug_classes is not None:
        fs.allowed_atc_classes = drug_classes
    elif drug_classes_exclude is not None:
        excl = {e.lower() for e in drug_classes_exclude}
        fs.allowed_atc_classes = [c for c in _load_full_atc_class_list() if c.lower() not in excl]
    else:
        fs.allowed_atc_classes = None

    return fs


def set_filters(fs: FilterState) -> None:
    """Persist FilterState to session_state."""
    st.session_state[SESSION_KEY] = fs


def reset_downstream_filters() -> None:
    """Clear all downstream filters but keep global indication/atc_class."""
    fs = get_filters()
    fs.sponsor               = []
    fs.sponsor_agency_class  = []
    fs.brand_name            = []
    fs.drug_indication       = None
    fs.study_type            = []
    fs.phase                 = []
    fs.overall_status        = []
    fs.country           = []
    fs.endpoint_category = []
    fs.outcome_type      = []
    fs.pro_instrument    = []
    fs.pro_domain        = []
    fs.ae_organ_system   = []
    fs.ae_term           = []
    fs.has_results       = None
    fs.enrollment_min    = None
    fs.enrollment_max    = None
    set_filters(fs)
