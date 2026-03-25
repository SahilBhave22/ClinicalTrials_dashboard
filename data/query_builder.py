"""
SQL WHERE-clause builder.

Translates a FilterState into parameterised SQL fragments that can be
injected into any query.

Design rules:
  - NEVER concatenate user-provided strings directly into SQL.
  - All values go through :param_name bind params.
  - List params use :p_0, :p_1 … expansion (pg8000 compatible).
  - The base NCT-ID set is derived from the global indication / atc_class
    filters via the drugs DB and public.drug_trials.
"""
from __future__ import annotations

from typing import List, Optional, Tuple
import streamlit as st

from utils.filters import FilterState
from config.settings import (
    DRUG_INDICATIONS_TABLE,
    DRUG_CLASSES_TABLE,
    DRUGS_BRAND_COL,
    DRUGS_INDICATION_COL,
    DRUGS_ATC_COL,
    BROWSE_CONDITIONS_TABLE,
    BROWSE_CONDITIONS_MESH_TERM,
    BROWSE_CONDITIONS_MESH_TYPE,
    BROWSE_CONDITIONS_MESH_LIST,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _list_clause(col: str, values: List[str], params: dict, prefix: str) -> str:
    """Return `col IN (:p0, :p1, …)` fragment and populate params."""
    if not values:
        return ""
    placeholders = ", ".join(f":{prefix}_{i}" for i in range(len(values)))
    for i, v in enumerate(values):
        params[f"{prefix}_{i}"] = v
    return f"{col} IN ({placeholders})"


# ── Drugs DB helpers ──────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def resolve_brand_names(atc_class: Optional[str]) -> List[str]:
    """
    Query drugs_db to get brand_names matching the atc_class filter.

    NOTE: The global indication_name filter now uses ctgov.browse_conditions (AACT DB)
    and is applied as a JOIN in nct_subquery_clause — it does NOT resolve brand names
    from drug_indications. Only atc_class drives brand-name resolution here.

    Returns empty list if atc_class is not set (means "no ATC restriction").
    """
    if not atc_class:
        return []

    from data.db import query_drugs  # local import to avoid circular

    sql = f"""
        SELECT DISTINCT {DRUGS_BRAND_COL} AS brand_name
        FROM {DRUG_CLASSES_TABLE}
        WHERE {DRUGS_ATC_COL} = :atc_class
          AND {DRUGS_BRAND_COL} IS NOT NULL
        LIMIT 2000
    """
    df = query_drugs(sql, {"atc_class": atc_class})
    if df.empty:
        return []
    return df["brand_name"].dropna().tolist()


@st.cache_data(ttl=600, show_spinner=False)
def resolve_brand_names_from_drug_indication(drug_indication: str) -> List[str]:
    """
    Query drugs_db to get brand_names for the downstream drug_indication filter
    (Sponsor/Drug sidebar tab). Uses public.drug_indications.
    """
    if not drug_indication:
        return []

    from data.db import query_drugs  # local import to avoid circular

    sql = f"""
        SELECT DISTINCT {DRUGS_BRAND_COL} AS brand_name
        FROM {DRUG_INDICATIONS_TABLE}
        WHERE {DRUGS_INDICATION_COL} = :drug_indication
          AND {DRUGS_BRAND_COL} IS NOT NULL
        LIMIT 2000
    """
    df = query_drugs(sql, {"drug_indication": drug_indication})
    if df.empty:
        return []
    return df["brand_name"].dropna().tolist()


@st.cache_data(ttl=600, show_spinner=False)
def resolve_nct_ids(brand_names: tuple[str, ...]) -> List[str]:
    """
    Given a tuple of brand names (hashable for caching), return all nct_ids
    in public.drug_trials that match.
    Returns empty list when brand_names is empty (means "no global filter").
    """
    if not brand_names:
        return []

    from data.db import query_aact  # local import
    placeholders = ", ".join(f":bn_{i}" for i in range(len(brand_names)))
    params = {f"bn_{i}": bn for i, bn in enumerate(brand_names)}
    sql = f"""
        SELECT DISTINCT nct_id
        FROM public.drug_trials
        WHERE brand_name IN ({placeholders})
    """
    df = query_aact(sql, params)
    if df.empty:
        return []
    return df["nct_id"].tolist()


# ── Core builder ──────────────────────────────────────────────────────────────

class QueryBuilder:
    """
    Builds reusable SQL WHERE-clause fragments for a given FilterState.

    Usage:
        qb = QueryBuilder(filters)
        nct_clause, params = qb.nct_clause("s")         # study alias
        brand_clause, _    = qb.brand_clause("dt")      # drug_trials alias
        extra_clause, _    = qb.study_filters_clause("s")
        # merge params dicts, combine clauses with AND
    """

    def __init__(self, filters: FilterState):
        self.filters = filters
        self._brand_names: Optional[List[str]] = None
        self._nct_ids: Optional[List[str]] = None

    # ── Derived brand names ───────────────────────────────────────────────────

    @property
    def brand_names(self) -> List[str]:
        if self._brand_names is None:
            if self.filters._resolved_brand_names:
                self._brand_names = self.filters._resolved_brand_names
            else:
                self._brand_names = resolve_brand_names(
                    self.filters.atc_class_name,
                )
        return self._brand_names

    @property
    def nct_ids(self) -> List[str]:
        if self._nct_ids is None:
            if not self.brand_names and not self.filters.has_global_filter():
                self._nct_ids = []
            else:
                self._nct_ids = resolve_nct_ids(tuple(self.brand_names))
        return self._nct_ids

    def has_global_filter(self) -> bool:
        return self.filters.has_global_filter()

    # ── NCT-ID clause ─────────────────────────────────────────────────────────

    def nct_clause(self, alias: str = "s") -> Tuple[str, dict]:
        """
        Delegates to nct_subquery_clause for consistency.
        Kept for backward compatibility with any direct callers.
        """
        return self.nct_subquery_clause(alias)

    def nct_subquery_clause(self, alias: str = "s") -> Tuple[str, dict]:
        """
        Subquery variant — always scopes to public.drug_trials.

        Indication (indication_name) is now a ctgov.browse_conditions mesh_term.
        It is applied as a JOIN on drug_trials, NOT via brand-name resolution.
        ATC class (atc_class_name) still resolves to brand_names via drug_classes.

        Scenarios:
        - No global filter        → all drug_trials
        - indication only         → drug_trials JOIN browse_conditions mesh-list
        - atc_class only          → drug_trials WHERE brand_name IN (atc brands)
        - both                    → drug_trials JOIN browse_conditions AND brand IN (atc brands)
        - atc set but no brands   → empty set (atc class has no matching drugs)
        """
        indication  = self.filters.indication_name   # browse_conditions mesh_term
        brand_names = self.brand_names               # from atc_class only

        if not self.filters.has_global_filter():
            # No global filter — scope to all drug_trials
            return (
                f"{alias}.nct_id IN (SELECT DISTINCT nct_id FROM public.drug_trials)",
                {},
            )

        # ATC class is set but resolved to zero brands → empty result
        if self.filters.atc_class_name and not brand_names:
            return f"{alias}.nct_id IN (SELECT NULL WHERE FALSE)", {}

        params: dict = {}
        where_parts: list[str] = []
        join_clause = ""

        # ATC-derived brand restriction
        if brand_names:
            bn_frag = _list_clause("dt.brand_name", brand_names, params, "bn")
            where_parts.append(bn_frag)

        # Indication restriction via browse_conditions
        if indication:
            join_clause = (
                f"JOIN {BROWSE_CONDITIONS_TABLE} bc ON bc.nct_id = dt.nct_id"
            )
            where_parts.append(f"bc.{BROWSE_CONDITIONS_MESH_TYPE} = '{BROWSE_CONDITIONS_MESH_LIST}'")
            where_parts.append(f"bc.{BROWSE_CONDITIONS_MESH_TERM} = :bc_indication")
            params["bc_indication"] = indication

        where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        clause = f"""
            {alias}.nct_id IN (
                SELECT DISTINCT dt.nct_id
                FROM public.drug_trials dt
                {join_clause}
                {where_sql}
            )
        """
        return clause, params

    # ── Brand-name clause ─────────────────────────────────────────────────────

    def brand_clause(self, alias: str = "dt", col: str = "brand_name") -> Tuple[str, dict]:
        """Filter a drug_trials-style table by resolved brand names."""
        brand_names = self.brand_names
        combined = list(set(brand_names + self.filters.brand_name))
        if not combined:
            return "", {}
        params: dict = {}
        clause = _list_clause(f"{alias}.{col}", combined, params, "bn")
        return clause, params

    # ── Study-level downstream filters ───────────────────────────────────────

    def study_type_clause(self, alias: str = "s") -> Tuple[str, dict]:
        if not self.filters.study_type:
            return "", {}
        params: dict = {}
        clause = _list_clause(f"{alias}.study_type", self.filters.study_type, params, "sty")
        return clause, params

    def study_filters_clause(self, alias: str = "s") -> Tuple[str, dict]:
        """
        Returns a WHERE fragment for study-level downstream filters:
        phase, overall_status, enrollment range, has_results.
        """
        parts: list[str] = []
        params: dict = {}

        if self.filters.phase:
            c = _list_clause(f"{alias}.phase", self.filters.phase, params, "ph")
            if c:
                parts.append(c)

        if self.filters.overall_status:
            c = _list_clause(
                f"{alias}.overall_status", self.filters.overall_status, params, "st"
            )
            if c:
                parts.append(c)

        if self.filters.enrollment_min is not None:
            parts.append(f"{alias}.enrollment >= :enr_min")
            params["enr_min"] = self.filters.enrollment_min

        if self.filters.enrollment_max is not None:
            parts.append(f"{alias}.enrollment <= :enr_max")
            params["enr_max"] = self.filters.enrollment_max

        if self.filters.has_results is True:
            parts.append(f"{alias}.results_first_submitted_date IS NOT NULL")
        elif self.filters.has_results is False:
            parts.append(f"{alias}.results_first_submitted_date IS NULL")

        clause = " AND ".join(parts)
        return clause, params

    def sponsor_clause(self, alias: str = "sp") -> Tuple[str, dict]:
        if not self.filters.sponsor:
            return "", {}
        params: dict = {}
        clause = _list_clause(f"{alias}.name", self.filters.sponsor, params, "sp")
        return clause, params

    def sponsor_agency_class_clause(self, alias: str = "sp") -> Tuple[str, dict]:
        if not self.filters.sponsor_agency_class:
            return "", {}
        params: dict = {}
        clause = _list_clause(
            f"{alias}.agency_class", self.filters.sponsor_agency_class, params, "sac"
        )
        return clause, params

    def country_clause(self, alias: str = "c") -> Tuple[str, dict]:
        if not self.filters.country:
            return "", {}
        params: dict = {}
        clause = _list_clause(f"{alias}.name", self.filters.country, params, "co")
        return clause, params

    def endpoint_category_clause(self, alias: str = "oc") -> Tuple[str, dict]:
        if not self.filters.endpoint_category:
            return "", {}
        params: dict = {}
        clause = _list_clause(f"{alias}.outcome_category", self.filters.endpoint_category, params, "ec")
        return clause, params

    def pro_instrument_clause(self, alias: str = "pro") -> Tuple[str, dict]:
        if not self.filters.pro_instrument:
            return "", {}
        params: dict = {}
        clause = _list_clause(
            f"{alias}.instrument_name", self.filters.pro_instrument, params, "pi"
        )
        return clause, params

    def ae_clause(self, alias: str = "re") -> Tuple[str, dict]:
        parts: list[str] = []
        params: dict = {}
        if self.filters.ae_organ_system:
            c = _list_clause(
                f"{alias}.organ_system", self.filters.ae_organ_system, params, "aos"
            )
            if c:
                parts.append(c)
        if self.filters.ae_term:
            c = _list_clause(
                f"{alias}.adverse_event_term", self.filters.ae_term, params, "aet"
            )
            if c:
                parts.append(c)
        return " AND ".join(parts), params

    def study_scope_clause(self, alias: str = "s") -> Tuple[str, dict]:
        """
        Combined WHERE fragment applying ALL active sidebar filters as nct_id
        subquery constraints. Use this instead of nct_subquery_clause so that
        phase, status, enrollment, has_results, sponsor, and country filters
        are respected in every query.

        Domain-specific filters (pro_instrument, endpoint_category, ae_*) must
        be applied separately in the functions that query those specific tables.
        """
        parts: list[str] = []
        params: dict = {}

        # 1. Global nct_id scope (brand / indication via drug_trials)
        nct_clause, nct_p = self.nct_subquery_clause(alias)
        parts.append(nct_clause)
        params.update(nct_p)

        # 1b. Specific brand name selection (sidebar "Drug (Brand Name)" multiselect).
        #     nct_subquery_clause above scopes to ALL brands in the indication/atc class.
        #     This intersects that scope down to only the user-selected drug(s).
        if self.filters.brand_name:
            dbn_p: dict = {}
            dbn_in = _list_clause("dt2.brand_name", self.filters.brand_name, dbn_p, "dbn")
            parts.append(
                f"{alias}.nct_id IN "
                f"(SELECT DISTINCT dt2.nct_id FROM public.drug_trials dt2 WHERE {dbn_in})"
            )
            params.update(dbn_p)

        # 1c. Drug indication downstream filter (Sponsor/Drug tab).
        #     Resolves brand_names from public.drug_indications, then scopes via drug_trials.
        if self.filters.drug_indication:
            di_brands = resolve_brand_names_from_drug_indication(self.filters.drug_indication)
            if di_brands:
                di_p: dict = {}
                di_in = _list_clause("dt3.brand_name", di_brands, di_p, "di")
                parts.append(
                    f"{alias}.nct_id IN "
                    f"(SELECT DISTINCT dt3.nct_id FROM public.drug_trials dt3 WHERE {di_in})"
                )
                params.update(di_p)
            else:
                # Selected drug indication has no matching brands → empty result
                parts.append(f"{alias}.nct_id IN (SELECT NULL WHERE FALSE)")

        # 2. Study type
        if self.filters.study_type:
            sty_p: dict = {}
            sty_in = _list_clause("s2.study_type", self.filters.study_type, sty_p, "sty")
            parts.append(
                f"{alias}.nct_id IN "
                f"(SELECT s2.nct_id FROM ctgov.studies s2 WHERE {sty_in})"
            )
            params.update(sty_p)

        # 3. Phase
        if self.filters.phase:
            ph_p: dict = {}
            ph_in = _list_clause("s2.phase", self.filters.phase, ph_p, "ph")
            parts.append(
                f"{alias}.nct_id IN "
                f"(SELECT s2.nct_id FROM ctgov.studies s2 WHERE {ph_in})"
            )
            params.update(ph_p)

        # 4. Overall status
        if self.filters.overall_status:
            os_p: dict = {}
            os_in = _list_clause("s2.overall_status", self.filters.overall_status, os_p, "os")
            parts.append(
                f"{alias}.nct_id IN "
                f"(SELECT s2.nct_id FROM ctgov.studies s2 WHERE {os_in})"
            )
            params.update(os_p)

        # 5. Enrollment range
        if self.filters.enrollment_min is not None:
            parts.append(
                f"{alias}.nct_id IN "
                f"(SELECT s2.nct_id FROM ctgov.studies s2 WHERE s2.enrollment >= :enr_min)"
            )
            params["enr_min"] = self.filters.enrollment_min
        if self.filters.enrollment_max is not None:
            parts.append(
                f"{alias}.nct_id IN "
                f"(SELECT s2.nct_id FROM ctgov.studies s2 WHERE s2.enrollment <= :enr_max)"
            )
            params["enr_max"] = self.filters.enrollment_max

        # 6. Has results
        if self.filters.has_results is True:
            parts.append(
                f"{alias}.nct_id IN "
                f"(SELECT s2.nct_id FROM ctgov.studies s2 "
                f"WHERE s2.results_first_submitted_date IS NOT NULL)"
            )
        elif self.filters.has_results is False:
            parts.append(
                f"{alias}.nct_id IN "
                f"(SELECT s2.nct_id FROM ctgov.studies s2 "
                f"WHERE s2.results_first_submitted_date IS NULL)"
            )

        # 7. Sponsor name (lead only)
        if self.filters.sponsor:
            sp_p: dict = {}
            sp_in = _list_clause("sp2.name", self.filters.sponsor, sp_p, "sph")
            parts.append(
                f"{alias}.nct_id IN "
                f"(SELECT sp2.nct_id FROM ctgov.sponsors sp2 "
                f"WHERE {sp_in} AND sp2.lead_or_collaborator = 'lead')"
            )
            params.update(sp_p)

        # 7b. Sponsor agency class (lead only)
        if self.filters.sponsor_agency_class:
            sac_p: dict = {}
            sac_in = _list_clause(
                "sp3.agency_class", self.filters.sponsor_agency_class, sac_p, "sac"
            )
            parts.append(
                f"{alias}.nct_id IN "
                f"(SELECT sp3.nct_id FROM ctgov.sponsors sp3 "
                f"WHERE {sac_in} AND sp3.lead_or_collaborator = 'lead')"
            )
            params.update(sac_p)

        # 8. Country
        if self.filters.country:
            co_p: dict = {}
            co_in = _list_clause("c2.name", self.filters.country, co_p, "coh")
            parts.append(
                f"{alias}.nct_id IN "
                f"(SELECT c2.nct_id FROM ctgov.countries c2 "
                f"WHERE {co_in} AND c2.removed IS NOT TRUE)"
            )
            params.update(co_p)

        return QueryBuilder.combine(parts), params

    # ── AE-specific CTE scope ─────────────────────────────────────────────────

    def ae_scope_cte(self) -> tuple[str, dict]:
        """
        Build a ``WITH scope_nct AS (...)`` CTE that computes the valid nct_id
        set for adverse-event queries using a single JOIN-based pass rather than
        chaining 10 nested IN subqueries.

        Returns:
            cte_sql : the full ``WITH scope_nct AS (...)`` SQL string.
                      Empty string when no filters are active (caller should
                      skip the JOIN too).
            params  : bind-parameter dict for use with the CTE.

        Usage in a query::

            cte_sql, params = qb.ae_scope_cte()
            scope_join = "JOIN scope_nct ON scope_nct.nct_id = re.nct_id" if cte_sql else ""
            sql = f"{cte_sql} SELECT ... FROM ctgov.reported_events re {scope_join} ..."
        """
        params: dict = {}
        where_parts: list[str] = []
        join_parts: list[str] = []

        # ── Global scope: drug_trials (limits to known drug trials) ───────────
        indication = self.filters.indication_name
        brand_names = self.brand_names

        # ATC class set but resolved to zero brands → empty result set
        if self.filters.atc_class_name and not brand_names:
            return "WITH scope_nct AS (SELECT nct_id FROM ctgov.studies WHERE FALSE)", {}

        # ATC → brand filter on drug_trials
        if brand_names:
            bn_frag = _list_clause("dt.brand_name", brand_names, params, "bn")
            where_parts.append(bn_frag)

        # Indication → browse_conditions JOIN
        if indication:
            join_parts.append(
                f"JOIN {BROWSE_CONDITIONS_TABLE} bc ON bc.nct_id = dt.nct_id"
            )
            where_parts.append(
                f"bc.{BROWSE_CONDITIONS_MESH_TYPE} = '{BROWSE_CONDITIONS_MESH_LIST}'"
            )
            where_parts.append(f"bc.{BROWSE_CONDITIONS_MESH_TERM} = :bc_indication")
            params["bc_indication"] = indication

        # Direct brand-name sidebar filter (further narrows drug_trials)
        if self.filters.brand_name:
            dbn_frag = _list_clause("dt.brand_name", self.filters.brand_name, params, "dbn")
            where_parts.append(dbn_frag)

        # Drug indication sidebar filter → resolves to additional brand restriction
        if self.filters.drug_indication:
            di_brands = resolve_brand_names_from_drug_indication(self.filters.drug_indication)
            if not di_brands:
                return "WITH scope_nct AS (SELECT nct_id FROM ctgov.studies WHERE FALSE)", {}
            di_frag = _list_clause("dt.brand_name", di_brands, params, "di")
            where_parts.append(di_frag)

        # ── Study-level filters (on ctgov.studies alias s) ────────────────────
        if self.filters.study_type:
            sty_frag = _list_clause("s.study_type", self.filters.study_type, params, "sty")
            where_parts.append(sty_frag)

        if self.filters.phase:
            ph_frag = _list_clause("s.phase", self.filters.phase, params, "ph")
            where_parts.append(ph_frag)

        if self.filters.overall_status:
            os_frag = _list_clause("s.overall_status", self.filters.overall_status, params, "os")
            where_parts.append(os_frag)

        if self.filters.enrollment_min is not None:
            where_parts.append("s.enrollment >= :enr_min")
            params["enr_min"] = self.filters.enrollment_min
        if self.filters.enrollment_max is not None:
            where_parts.append("s.enrollment <= :enr_max")
            params["enr_max"] = self.filters.enrollment_max

        if self.filters.has_results is True:
            where_parts.append("s.results_first_submitted_date IS NOT NULL")
        elif self.filters.has_results is False:
            where_parts.append("s.results_first_submitted_date IS NULL")

        # ── Sponsor filters (single JOIN covering both name + agency_class) ───
        if self.filters.sponsor or self.filters.sponsor_agency_class:
            join_parts.append(
                "JOIN ctgov.sponsors sp ON sp.nct_id = s.nct_id"
                " AND sp.lead_or_collaborator = 'lead'"
            )
            if self.filters.sponsor:
                sp_frag = _list_clause("sp.name", self.filters.sponsor, params, "sph")
                where_parts.append(sp_frag)
            if self.filters.sponsor_agency_class:
                sac_frag = _list_clause(
                    "sp.agency_class", self.filters.sponsor_agency_class, params, "sac"
                )
                where_parts.append(sac_frag)

        # ── Country filter ────────────────────────────────────────────────────
        if self.filters.country:
            join_parts.append(
                "JOIN ctgov.countries c ON c.nct_id = s.nct_id"
                " AND c.removed IS NOT TRUE"
            )
            co_frag = _list_clause("c.name", self.filters.country, params, "coh")
            where_parts.append(co_frag)

        joins_sql = "\n        ".join(join_parts)
        where_sql = (
            "WHERE " + "\n          AND ".join(where_parts) if where_parts else ""
        )

        cte_sql = f"""WITH scope_nct AS (
        SELECT DISTINCT s.nct_id
        FROM ctgov.studies s
        JOIN public.drug_trials dt ON dt.nct_id = s.nct_id
        {joins_sql}
        {where_sql}
    )"""
        return cte_sql, params

    # ── Utility: combine clauses ──────────────────────────────────────────────

    @staticmethod
    def combine(clauses: list[str]) -> str:
        """Join non-empty clause strings with AND."""
        return " AND ".join(c for c in clauses if c and c.strip())

    @staticmethod
    def merge_params(*param_dicts: dict) -> dict:
        """Merge multiple param dicts into one."""
        out: dict = {}
        for d in param_dicts:
            out.update(d)
        return out

    def where(self, clause: str) -> str:
        """Prepend WHERE if clause is non-empty."""
        return f"WHERE {clause}" if clause.strip() else ""
