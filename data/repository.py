"""
All database queries live here. UI/service code calls these functions only.

Optimisation rules enforced:
  - SELECT only required columns
  - Push ALL filters into SQL
  - Aggregate in SQL, not pandas
  - No SELECT *
  - LIMIT on large result sets
  - subjects_affected > 0 enforced on adverse events
  - browse_conditions: always filter mesh_type = 'mesh-list'
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import streamlit as st
import pandas as pd

from data.db import (
    query_aact,
    query_aact_ae,
    query_aact_uncached,
    query_pricing,
    query_drugs,
    query_market_access,
    query_fdaers,
)
from data.query_builder import QueryBuilder, _list_clause
from utils.filters import FilterState
from config.settings import (
    MAX_TABLE_ROWS, ANNUAL_PRICING_TABLE, HISTORICAL_PRICING_TABLE,
    DRUG_CLASSES_TABLE, DRUGS_ATC_COL, DRUGS_BRAND_COL, DRUG_INDICATIONS_TABLE, DRUGS_INDICATION_COL,
    MA_TABLE_2025, MA_TABLE_2026,
)


_MESH_TO_INDICATION_MAP_PATH = (
    Path(__file__).resolve().parent.parent / "catalogs" / "mesh_to_indication_map.json"
)



@lru_cache(maxsize=1)
def _load_mesh_to_indication_map() -> dict[str, list[str]]:
    """Load the pre-built MeSH-to-indication mapping from disk once per process."""
    if not _MESH_TO_INDICATION_MAP_PATH.exists():
        return {}
    return json.loads(_MESH_TO_INDICATION_MAP_PATH.read_text())


@st.cache_data(ttl=600, show_spinner=False)
def _resolve_brands_from_mesh_indication(mesh_term: str) -> list[str]:
    """
    Resolve brand names for a global MeSH condition using the JSON mapping file.

    Steps:
      1. Look up the selected MeSH term in catalogs/mesh_to_indication_map.json
      2. Resolve mapped drug indication labels in public.drug_indications
      3. Return distinct brand names for pricing / market access queries
    """
    if not mesh_term:
        return []

    mesh_map = _load_mesh_to_indication_map()
    matched_indications = mesh_map.get(mesh_term.lower().strip(), [])
    if not matched_indications:
        return []

    sql = f"""
        SELECT DISTINCT {DRUGS_BRAND_COL} AS brand_name
        FROM {DRUG_INDICATIONS_TABLE}
        WHERE LOWER({DRUGS_INDICATION_COL}) = ANY(:indications)
          AND {DRUGS_BRAND_COL} IS NOT NULL
        ORDER BY 1
    """
    df = query_drugs(sql, {"indications": [v.lower() for v in matched_indications]})
    return df["brand_name"].dropna().tolist() if not df.empty else []


@st.cache_data(ttl=600, show_spinner=False)
def _resolve_relevant_brands_for_global_filters(
    indication: str | None,
    atc_class: str | None,
) -> list[str]:
    """
    Resolve the relevant brand set for the selected global filters from the
    drugs-side sources, not from co-enrolled trial rows.

    - indication -> mesh_to_indication_map.json -> public.drug_indications
    - atc_class  -> public.drug_classes
    - both       -> intersection of the two brand sets
    """
    mesh_brands: list[str] | None = None
    atc_brands: list[str] | None = None

    if indication:
        mesh_brands = _resolve_brands_from_mesh_indication(indication)

    if atc_class:
        sql = f"""
            SELECT DISTINCT {DRUGS_BRAND_COL} AS brand_name
            FROM {DRUG_CLASSES_TABLE}
            WHERE {DRUGS_ATC_COL} = :atc_class
              AND {DRUGS_BRAND_COL} IS NOT NULL
            ORDER BY 1
        """
        df = query_drugs(sql, {"atc_class": atc_class})
        atc_brands = df["brand_name"].dropna().tolist() if not df.empty else []

    if mesh_brands is not None and atc_brands is not None:
        atc_set = set(atc_brands)
        return [b for b in mesh_brands if b in atc_set]
    if mesh_brands is not None:
        return mesh_brands
    if atc_brands is not None:
        return atc_brands
    return []


OUTC_LABELS = {
    "DE": "Death",
    "LT": "Life-Threatening",
    "HO": "Hospitalisation",
    "DS": "Disability",
    "CA": "Congenital Anomaly",
    "RI": "Required Intervention",
    "OT": "Other",
}

OCCP_LABELS = {
    "MD": "Physician",
    "PH": "Pharmacist",
    "OT": "Other HCP",
    "LW": "Lawyer",
    "CN": "Consumer",
    "HP": "Health Professional",
}


# ════════════════════════════════════════════════════════════════════════════
#  FILTER OPTIONS  (for sidebar dropdowns – constrained by global filters)
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600, show_spinner=False)
def get_filter_options(indication: str | None, atc_class: str | None) -> dict:
    """
    Return available filter values constrained by the active global filters.
    All values come from the AACT DB, scoped to matching nct_ids.
    """
    # Build a minimal FilterState for the QB
    fs = FilterState(indication_name=indication, atc_class_name=atc_class)
    qb = QueryBuilder(fs)
    nct_clause, nct_params = qb.nct_subquery_clause("s")

    # Sponsors
    sql_sponsors = f"""
        SELECT DISTINCT sp.name
        FROM ctgov.sponsors sp
        JOIN ctgov.studies s ON s.nct_id = sp.nct_id
        WHERE {nct_clause}
          AND sp.lead_or_collaborator = 'lead'
          AND sp.name IS NOT NULL
        ORDER BY sp.name
        LIMIT 500
    """
    # Study types
    sql_study_types = f"""
        SELECT DISTINCT s.study_type
        FROM ctgov.studies s
        WHERE {nct_clause}
          AND s.study_type IS NOT NULL
        ORDER BY s.study_type
    """
    # Phases
    sql_phases = f"""
        SELECT DISTINCT s.phase
        FROM ctgov.studies s
        WHERE {nct_clause}
          AND s.phase IS NOT NULL
        ORDER BY s.phase
    """
    # Statuses
    sql_statuses = f"""
        SELECT DISTINCT s.overall_status
        FROM ctgov.studies s
        WHERE {nct_clause}
          AND s.overall_status IS NOT NULL
        ORDER BY s.overall_status
    """
    # Countries
    sql_countries = f"""
        SELECT DISTINCT c.name
        FROM ctgov.countries c
        JOIN ctgov.studies s ON s.nct_id = c.nct_id
        WHERE {nct_clause}
          AND c.name IS NOT NULL AND c.removed IS NOT TRUE
        ORDER BY c.name
        LIMIT 300
    """
    # Endpoint categories
    sql_categories = f"""
        SELECT DISTINCT oc.outcome_category
        FROM public.drug_trial_outcome_categories oc
        JOIN ctgov.studies s ON s.nct_id = oc.nct_id
        WHERE {nct_clause}
          AND oc.outcome_category IS NOT NULL
        ORDER BY oc.outcome_category
    """
    # PRO instruments
    sql_pro = f"""
        SELECT DISTINCT p.instrument_name
        FROM public.drug_trial_design_outcomes_pro p
        JOIN ctgov.studies s ON s.nct_id = p.nct_id
        WHERE {nct_clause}
          AND p.instrument_name IS NOT NULL
        ORDER BY p.instrument_name
        LIMIT 200
    """
    # PRO domains
    sql_domains = f"""
        SELECT DISTINCT d.criteria
        FROM public.domain_score_match d
        JOIN ctgov.studies s ON s.nct_id = d.nct_id
        WHERE {nct_clause}
          AND d.criteria IS NOT NULL
        ORDER BY d.criteria
        LIMIT 200
    """
    # Sponsor agency classes (lead sponsors only)
    sql_agency_classes = f"""
        SELECT DISTINCT sp.agency_class
        FROM ctgov.sponsors sp
        JOIN ctgov.studies s ON s.nct_id = sp.nct_id
        WHERE {nct_clause}
          AND sp.lead_or_collaborator = 'lead'
          AND sp.agency_class IS NOT NULL
        ORDER BY sp.agency_class
    """

    def _vals(df: pd.DataFrame) -> list:
        if df.empty:
            return []
        return df.iloc[:, 0].dropna().tolist()

    # Brands in scope — computed first so we can use them to scope drug_indications.
    # When the indication is a raw conditions-table name (not in the MeSH map),
    # relevant_brands will be empty; fall back to all brands in the nct_clause scope.
    relevant_brands = _resolve_relevant_brands_for_global_filters(indication, atc_class)
    brands_list: list[str] = []
    if indication or atc_class:
        if relevant_brands:
            brand_params = dict(nct_params)
            brand_in = _list_clause("dt.brand_name", relevant_brands, brand_params, "gfbn")
            sql_brands = f"""
                SELECT DISTINCT dt.brand_name
                FROM public.drug_trials dt
                JOIN ctgov.studies s ON s.nct_id = dt.nct_id
                WHERE {nct_clause}
                  AND {brand_in}
                  AND dt.brand_name IS NOT NULL
                ORDER BY dt.brand_name
                LIMIT 300
            """
            brands_list = _vals(query_aact(sql_brands, brand_params))
        else:
            # Mesh map returned nothing (raw condition name) — scope brands via nct_clause
            sql_brands = f"""
                SELECT DISTINCT dt.brand_name
                FROM public.drug_trials dt
                JOIN ctgov.studies s ON s.nct_id = dt.nct_id
                WHERE {nct_clause}
                  AND dt.brand_name IS NOT NULL
                ORDER BY dt.brand_name
                LIMIT 300
            """
            brands_list = _vals(query_aact(sql_brands, nct_params))
    else:
        sql_brands = f"""
            SELECT DISTINCT dt.brand_name
            FROM public.drug_trials dt
            JOIN ctgov.studies s ON s.nct_id = dt.nct_id
            WHERE {nct_clause}
              AND dt.brand_name IS NOT NULL
            ORDER BY dt.brand_name
            LIMIT 300
        """
        brands_list = _vals(query_aact(sql_brands, nct_params))

    # Drug label indications (DRUGS DB, scoped by brands currently in scope).
    # These populate the downstream "Drug Indication" filter in the Sponsor/Drug tab.
    drug_ind_list: list = []
    if brands_list:
        from data.db import query_drugs
        di_ph = ", ".join(f":di_b_{i}" for i in range(len(brands_list)))
        di_p  = {f"di_b_{i}": b for i, b in enumerate(brands_list)}
        sql_drug_ind = f"""
            SELECT DISTINCT indication_name
            FROM public.drug_indications
            WHERE brand_name IN ({di_ph})
              AND indication_name IS NOT NULL
            ORDER BY indication_name
            LIMIT 300
        """
        drug_ind_list = _vals(query_drugs(sql_drug_ind, di_p))

    return {
        "sponsors":         _vals(query_aact(sql_sponsors,       nct_params)),
        "agency_classes":   _vals(query_aact(sql_agency_classes, nct_params)),
        "study_types":      _vals(query_aact(sql_study_types,    nct_params)),
        "phases":           _vals(query_aact(sql_phases,         nct_params)),
        "statuses":         _vals(query_aact(sql_statuses,       nct_params)),
        "countries":        _vals(query_aact(sql_countries,      nct_params)),
        "categories":       _vals(query_aact(sql_categories,     nct_params)),
        "pro_instruments":  _vals(query_aact(sql_pro,            nct_params)),
        "brands":           brands_list,
        "domains":          _vals(query_aact(sql_domains,        nct_params)),
        "drug_indications": drug_ind_list,
    }


# ════════════════════════════════════════════════════════════════════════════
#  OVERVIEW / HOME KPIs
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def _build_scope_key(filters: FilterState) -> str:
    """Deterministic snapshot key matching scripts/generate_snapshot_sql.py logic."""
    parts = []
    if filters.allowed_indications is not None:
        parts.append("ind:" + "|".join(sorted(filters.allowed_indications)))
    if filters.allowed_atc_classes is not None:
        parts.append("atc:" + "|".join(sorted(filters.allowed_atc_classes)))
    return "__".join(parts) if parts else "global"


def get_overview_kpis(filters: FilterState) -> dict:
    # ── Fast path: no sidebar filters → read from pre-computed snapshot ──────
    if not filters.has_any_filter():
        scope_key = _build_scope_key(filters)
        snap_df = query_aact(
            "SELECT * FROM public.overview_kpis_snapshot "
            "WHERE scope_key = :scope_key ORDER BY refreshed_at DESC LIMIT 1",
            {"scope_key": scope_key},
        )
        if snap_df.empty and scope_key != "global":
            # Snapshot not yet generated for this scope — fall back to global row
            snap_df = query_aact(
                "SELECT * FROM public.overview_kpis_snapshot "
                "WHERE scope_key = 'global' ORDER BY refreshed_at DESC LIMIT 1",
                {},
            )
        if not snap_df.empty:
            row = snap_df.iloc[0]
            return {
                "total_trials":        int(row["total_trials"]        or 0),
                "active_trials":       int(row["active_trials"]       or 0),
                "completed_trials":    int(row["completed_trials"]     or 0),
                "trials_with_results": int(row["trials_with_results"]  or 0),
                "median_enrollment":   float(row["median_enrollment"]  or 0),
                "unique_sponsors":     int(row["unique_sponsors"]      or 0),
                "unique_drugs":        int(row["unique_drugs"]         or 0),
                "unique_conditions":   int(row["unique_conditions"]    or 0),
                "trials_with_pros":    int(row["trials_with_pros"]     or 0),
            }

    # ── Filtered path: run live queries ──────────────────────────────────────
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")

    sql = f"""
        SELECT
            COUNT(DISTINCT s.nct_id)                                          AS total_trials,
            COUNT(DISTINCT CASE WHEN s.overall_status IN
                ('RECRUITING','ACTIVE_NOT_RECRUITING') THEN s.nct_id END)     AS active_trials,
            COUNT(DISTINCT CASE WHEN s.overall_status = 'COMPLETED'
                THEN s.nct_id END)                                            AS completed_trials,
            COUNT(DISTINCT CASE WHEN s.results_first_submitted_date IS NOT NULL
                THEN s.nct_id END)                                            AS trials_with_results,
            PERCENTILE_CONT(0.5) WITHIN GROUP
                (ORDER BY s.enrollment)                                       AS median_enrollment
        FROM ctgov.studies s
        WHERE {scope_clause}
    """
    sql_sponsors = f"""
        SELECT COUNT(DISTINCT sp.name) AS unique_sponsors
        FROM ctgov.sponsors sp
        JOIN ctgov.studies s ON s.nct_id = sp.nct_id
        WHERE {scope_clause}
          AND sp.lead_or_collaborator = 'lead'
    """
    sql_drugs = f"""
        SELECT COUNT(DISTINCT dt.brand_name) AS unique_drugs
        FROM public.drug_trials dt
        JOIN ctgov.studies s ON s.nct_id = dt.nct_id
        WHERE {scope_clause}
    """
    sql_conditions = f"""
        SELECT COUNT(DISTINCT bc.downcase_mesh_term) AS unique_conditions
        FROM ctgov.browse_conditions bc
        JOIN ctgov.studies s ON s.nct_id = bc.nct_id
        WHERE {scope_clause}
          AND bc.mesh_type = 'mesh-list'
    """
    sql_pros = f"""
        SELECT COUNT(DISTINCT p.nct_id) AS trials_with_pros
        FROM public.drug_trial_design_outcomes_pro p
        JOIN ctgov.studies s ON s.nct_id = p.nct_id
        WHERE {scope_clause}
    """

    df       = query_aact(sql,            params)
    sp_df    = query_aact(sql_sponsors,   params)
    dr_df    = query_aact(sql_drugs,      params)
    cond_df  = query_aact(sql_conditions, params)
    pro_df   = query_aact(sql_pros,       params)

    row = df.iloc[0] if not df.empty else {}
    return {
        "total_trials":       int(row.get("total_trials",    0) or 0),
        "active_trials":      int(row.get("active_trials",   0) or 0),
        "completed_trials":   int(row.get("completed_trials",0) or 0),
        "trials_with_results":int(row.get("trials_with_results",0) or 0),
        "median_enrollment":  float(row.get("median_enrollment", 0) or 0),
        "unique_sponsors":    int(sp_df.iloc[0]["unique_sponsors"]   if not sp_df.empty   else 0),
        "unique_drugs":       int(dr_df.iloc[0]["unique_drugs"]      if not dr_df.empty   else 0),
        "unique_conditions":  int(cond_df.iloc[0]["unique_conditions"]if not cond_df.empty else 0),
        "trials_with_pros":   int(pro_df.iloc[0]["trials_with_pros"] if not pro_df.empty  else 0),
    }


@st.cache_data(ttl=300, show_spinner=False)
def get_trials_by_phase(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    sql = f"""
        SELECT
            COALESCE(s.phase, 'N/A') AS phase,
            COUNT(DISTINCT s.nct_id) AS trial_count
        FROM ctgov.studies s
        WHERE {scope_clause}
        GROUP BY 1 ORDER BY 2 DESC
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_trials_over_time(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    sql = f"""
        SELECT
            DATE_TRUNC('year', s.study_first_posted_date) AS year,
            COUNT(DISTINCT s.nct_id)                      AS trial_count
        FROM ctgov.studies s
        WHERE {scope_clause}
          AND s.study_first_posted_date IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_top_sponsors(filters: FilterState, limit: int = 20) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    sql = f"""
        SELECT
            sp.name                  AS sponsor,
            COUNT(DISTINCT sp.nct_id) AS trial_count
        FROM ctgov.sponsors sp
        JOIN ctgov.studies s ON s.nct_id = sp.nct_id
        WHERE {scope_clause}
          AND sp.lead_or_collaborator = 'lead'
          AND sp.name IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_top_conditions(filters: FilterState, limit: int = 20) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    sql = f"""
        SELECT
            bc.mesh_term             AS condition,
            COUNT(DISTINCT bc.nct_id) AS trial_count
        FROM ctgov.browse_conditions bc
        JOIN ctgov.studies s ON s.nct_id = bc.nct_id
        WHERE {scope_clause}
          AND bc.mesh_type = 'mesh-list'
          AND bc.mesh_term IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_top_interventions(filters: FilterState, limit: int = 20) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    sql = f"""
        SELECT
            i.name                   AS intervention,
            COUNT(DISTINCT i.nct_id) AS trial_count
        FROM ctgov.interventions i
        JOIN ctgov.studies s ON s.nct_id = i.nct_id
        WHERE {scope_clause}
          AND i.intervention_type = 'Drug'
          AND i.name IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT {limit}
    """
    return query_aact(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  LANDSCAPE
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_landscape_kpis(filters: FilterState) -> dict:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    where_str = f"WHERE {scope_clause}" if scope_clause else ""

    sql = f"""
        SELECT
            COUNT(DISTINCT s.nct_id)                                        AS total_trials,
            COUNT(DISTINCT CASE WHEN s.overall_status IN
                ('RECRUITING','ACTIVE_NOT_RECRUITING') THEN s.nct_id END)   AS active_trials,
            COUNT(DISTINCT CASE WHEN s.overall_status = 'COMPLETED'
                THEN s.nct_id END)                                          AS completed_trials,
            COUNT(DISTINCT CASE WHEN s.results_first_submitted_date IS NOT NULL
                THEN s.nct_id END)                                          AS with_results,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY s.enrollment)      AS median_enrollment,
            COUNT(DISTINCT sp2.name)                                        AS unique_sponsors
        FROM ctgov.studies s
        LEFT JOIN ctgov.sponsors sp2
               ON sp2.nct_id = s.nct_id AND sp2.lead_or_collaborator = 'lead'
        {where_str}
    """
    df = query_aact(sql, params)
    row = df.iloc[0] if not df.empty else {}
    total = int(row.get("total_trials", 0) or 0)
    completed = int(row.get("completed_trials", 0) or 0)
    return {
        "total_trials":     total,
        "active_trials":    int(row.get("active_trials",   0) or 0),
        "completed_trials": completed,
        "with_results":     int(row.get("with_results",    0) or 0),
        "median_enrollment":float(row.get("median_enrollment", 0) or 0),
        "unique_sponsors":  int(row.get("unique_sponsors", 0) or 0),
        "pct_completed":    round(100.0 * completed / total, 1) if total else 0.0,
    }


@st.cache_data(ttl=300, show_spinner=False)
def get_sponsor_share(filters: FilterState, limit: int = 15) -> pd.DataFrame:
    return get_top_sponsors(filters, limit)


@st.cache_data(ttl=300, show_spinner=False)
def get_status_distribution(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    sql = f"""
        SELECT
            COALESCE(s.overall_status, 'UNKNOWN') AS status,
            COUNT(DISTINCT s.nct_id)               AS trial_count
        FROM ctgov.studies s
        WHERE {scope_clause}
        GROUP BY 1 ORDER BY 2 DESC
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_country_distribution(filters: FilterState, limit: int = 20) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    sql = f"""
        SELECT
            c.name                   AS country,
            COUNT(DISTINCT c.nct_id) AS trial_count
        FROM ctgov.countries c
        JOIN ctgov.studies s ON s.nct_id = c.nct_id
        WHERE {scope_clause}
          AND c.name IS NOT NULL
          AND c.removed IS NOT TRUE
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT {limit}
    """
    return query_aact(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  PIPELINE LANDSCAPE
# ════════════════════════════════════════════════════════════════════════════

def _pipeline_where(
    bucket: str | None,
    sponsors: tuple[str, ...],
    pipeline_classes: tuple[str, ...],
    params: dict,
    base: str = "WHERE TRUE",
) -> str:
    """Build a WHERE clause fragment for pipeline_trials queries."""
    clause = base
    clause += " AND pt.pipeline_class NOT IN ('lifecycle study', 'unclassified')"
    if bucket:
        clause += " AND pt.trial_bucket = :bucket"
        params["bucket"] = bucket
    if sponsors:
        sp_params = {f"_sp{i}": s for i, s in enumerate(sponsors)}
        clause += " AND pt.sponsor_name IN (" + ", ".join(f":_sp{i}" for i in range(len(sponsors))) + ")"
        params.update(sp_params)
    if pipeline_classes:
        pc_params = {f"_pc{i}": c for i, c in enumerate(pipeline_classes)}
        clause += " AND pt.pipeline_class IN (" + ", ".join(f":_pc{i}" for i in range(len(pipeline_classes))) + ")"
        params.update(pc_params)
    return clause


@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_kpis(
    bucket: str | None,
    sponsors: tuple[str, ...] = (),
    pipeline_classes: tuple[str, ...] = (),
) -> dict:
    """Pipeline KPIs from pipeline_trials, filtered by trial_bucket direct match."""
    params: dict = {}
    cond_where = _pipeline_where(bucket, sponsors, pipeline_classes, params)
    sql = f"""
        SELECT
            COUNT(DISTINCT pt.nct_id)            AS pipeline_trials,
            COUNT(DISTINCT pt.intervention_name) AS unique_assets,
            COUNT(DISTINCT pt.sponsor_name)      AS active_sponsors,
            COUNT(DISTINCT pt.trial_bucket)      AS indications_covered
        FROM public.pipeline_trials pt
        {cond_where}
    """
    sql_pros = f"""
        SELECT COUNT(DISTINCT pp.nct_id) AS with_pros
        FROM public.onco_pipeline_design_outcomes_pro pp
        JOIN public.pipeline_trials pt ON pt.nct_id = pp.nct_id
        {cond_where}
    """
    df     = query_aact(sql,      params)
    pro_df = query_aact(sql_pros, params)
    row = df.iloc[0] if not df.empty else {}
    return {
        "pipeline_trials":    int(row.get("pipeline_trials",   0) or 0),
        "unique_assets":      int(row.get("unique_assets",     0) or 0),
        "active_sponsors":    int(row.get("active_sponsors",   0) or 0),
        "indications_covered":int(row.get("indications_covered",0) or 0),
        "with_pros":          int(pro_df.iloc[0]["with_pros"]  if not pro_df.empty else 0),
    }


@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_by_sponsor(
    bucket: str | None,
    sponsors: tuple[str, ...] = (),
    pipeline_classes: tuple[str, ...] = (),
    limit: int = 20,
) -> pd.DataFrame:
    params: dict = {}
    cond_where = _pipeline_where(bucket, sponsors, pipeline_classes, params,
                                  base="WHERE pt.sponsor_name IS NOT NULL")
    sql = f"""
        SELECT
            pt.sponsor_name              AS sponsor,
            COUNT(DISTINCT pt.nct_id)   AS pipeline_trials,
            COUNT(DISTINCT pt.intervention_name) AS unique_assets
        FROM public.pipeline_trials pt
        {cond_where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_by_indication(
    bucket: str | None,
    sponsors: tuple[str, ...] = (),
    pipeline_classes: tuple[str, ...] = (),
    limit: int = 25,
) -> pd.DataFrame:
    params: dict = {}
    cond_where = _pipeline_where(bucket, sponsors, pipeline_classes, params,
                                  base="WHERE pt.trial_bucket IS NOT NULL")
    sql = f"""
        SELECT
            pt.trial_bucket              AS condition,
            COUNT(DISTINCT pt.nct_id)   AS trial_count,
            COUNT(DISTINCT pt.sponsor_name) AS sponsors
        FROM public.pipeline_trials pt
        {cond_where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_top_interventions(
    bucket: str | None,
    sponsors: tuple[str, ...] = (),
    pipeline_classes: tuple[str, ...] = (),
    limit: int = 25,
) -> pd.DataFrame:
    params: dict = {}
    cond_where = _pipeline_where(bucket, sponsors, pipeline_classes, params,
                                  base="WHERE pt.intervention_name IS NOT NULL")
    sql = f"""
        SELECT
            pt.intervention_name         AS intervention,
            COUNT(DISTINCT pt.nct_id)   AS trial_count,
            COUNT(DISTINCT pt.sponsor_name) AS sponsors
        FROM public.pipeline_trials pt
        {cond_where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_sponsor_indication_heatmap(
    bucket: str | None,
    sponsors: tuple[str, ...] = (),
    pipeline_classes: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Return sponsor × bucket counts for heatmap."""
    params: dict = {}
    cond_where = _pipeline_where(
        bucket, sponsors, pipeline_classes, params,
        base="WHERE pt.sponsor_name IS NOT NULL AND pt.trial_bucket IS NOT NULL",
    )
    bare = cond_where.replace("pt.", "")
    sql = f"""
        WITH ranked_sponsors AS (
            SELECT sponsor_name, COUNT(DISTINCT nct_id) AS cnt
            FROM public.pipeline_trials
            {bare}
            GROUP BY 1 ORDER BY 2 DESC LIMIT 15
        ),
        ranked_buckets AS (
            SELECT trial_bucket, COUNT(DISTINCT nct_id) AS cnt
            FROM public.pipeline_trials
            {bare}
            GROUP BY 1 ORDER BY 2 DESC LIMIT 15
        )
        SELECT
            pt.sponsor_name  AS sponsor,
            pt.trial_bucket  AS condition,
            COUNT(DISTINCT pt.nct_id) AS trial_count
        FROM public.pipeline_trials pt
        JOIN ranked_sponsors rs ON rs.sponsor_name = pt.sponsor_name
        JOIN ranked_buckets rb ON rb.trial_bucket = pt.trial_bucket
        {cond_where}
        GROUP BY 1, 2
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_pro_usage(
    bucket: str | None,
    sponsors: tuple[str, ...] = (),
    pipeline_classes: tuple[str, ...] = (),
    limit: int = 20,
) -> pd.DataFrame:
    params: dict = {}
    cond_where = _pipeline_where(bucket, sponsors, pipeline_classes, params)
    cond_where += " AND pp.instrument_name IS NOT NULL"
    sql = f"""
        SELECT
            pp.instrument_name,
            COUNT(DISTINCT pp.nct_id) AS trial_count
        FROM public.onco_pipeline_design_outcomes_pro pp
        JOIN public.pipeline_trials pt ON pt.nct_id = pp.nct_id
        {cond_where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_trials_table(
    bucket: str | None,
    pipeline_classes: tuple[str, ...] = (),
    limit: int = MAX_TABLE_ROWS,
) -> pd.DataFrame:
    params: dict = {}
    cond_where = _pipeline_where(bucket, (), pipeline_classes, params)
    sql = f"""
        SELECT
            pt.nct_id,
            pt.sponsor_name,
            pt.intervention_name,
            pt.trial_bucket,
            pt.pipeline_class,
            s.phase,
            s.overall_status,
            s.enrollment,
            s.start_date,
            s.primary_completion_date
        FROM public.pipeline_trials pt
        LEFT JOIN ctgov.studies s ON s.nct_id = pt.nct_id
        {cond_where}
        ORDER BY s.start_date DESC NULLS LAST
        LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_by_class(
    bucket: str | None,
    sponsors: tuple[str, ...] = (),
    pipeline_classes: tuple[str, ...] = (),
) -> pd.DataFrame:
    params: dict = {}
    cond_where = _pipeline_where(bucket, sponsors, pipeline_classes, params,
                                  base="WHERE pt.pipeline_class IS NOT NULL")
    sql = f"""
        SELECT
            pt.pipeline_class            AS pipeline_class,
            COUNT(DISTINCT pt.nct_id)   AS trial_count,
            COUNT(DISTINCT pt.sponsor_name) AS sponsors
        FROM public.pipeline_trials pt
        {cond_where}
        GROUP BY 1 ORDER BY 2 DESC
    """
    return query_aact(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  DRUG DETAIL
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_drug_trials(filters: FilterState) -> pd.DataFrame:
    from data.query_builder import _list_clause, resolve_brand_names_from_drug_indication

    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")

    # Restrict dt.brand_name to brands actually in scope (same logic as
    # get_drug_brand_names / get_drug_phase_brand_heatmap) so co-enrolled
    # drugs from other classes don't appear as extra rows in the trial list.
    restricted_brands: list[str] = []
    if qb.brand_names:
        restricted_brands.extend(qb.brand_names)
    if filters.brand_name:
        restricted_brands.extend(filters.brand_name)
    if filters.drug_indication:
        di_brands = resolve_brand_names_from_drug_indication(filters.drug_indication)
        restricted_brands.extend(di_brands)
    restricted_brands = list(dict.fromkeys(restricted_brands))

    brand_filter = ""
    if restricted_brands:
        bn_p: dict = {}
        bn_frag = _list_clause("dt.brand_name", restricted_brands, bn_p, "dtbf")
        params.update(bn_p)
        brand_filter = f"AND {bn_frag}"

    sql = f"""
        SELECT
            s.nct_id,
            s.brief_title,
            dt.brand_name,
            s.phase,
            s.overall_status,
            s.enrollment,
            s.start_date,
            s.primary_completion_date,
            s.results_first_submitted_date,
            sp.name AS lead_sponsor
        FROM ctgov.studies s
        JOIN public.drug_trials dt ON dt.nct_id = s.nct_id
        LEFT JOIN ctgov.sponsors sp
               ON sp.nct_id = s.nct_id AND sp.lead_or_collaborator = 'lead'
        WHERE {scope_clause}
          {brand_filter}
        ORDER BY s.start_date DESC NULLS LAST
        LIMIT 500
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_drug_conditions(filters: FilterState, limit: int = 20) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    params["lim"] = limit
    sql = f"""
        SELECT
            bc.mesh_term              AS condition,
            COUNT(DISTINCT bc.nct_id) AS trial_count
        FROM ctgov.browse_conditions bc
        JOIN ctgov.studies s ON s.nct_id = bc.nct_id
        WHERE {scope_clause}
          AND bc.mesh_type = 'mesh-list'
        GROUP BY 1 ORDER BY 2 DESC LIMIT :lim
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_drug_classes(filters: FilterState) -> pd.DataFrame:
    """Return ATC drug class counts for the current filter scope.

    Two-step cross-DB query:
      Step 1 (AACT DB)  — resolve which brand names are actually in scope.
      Step 2 (Drugs DB) — look up ATC classes for those brands.
    """
    from data.db import query_drugs
    from data.query_builder import _list_clause, resolve_brand_names_from_drug_indication
    from config.settings import DRUG_CLASSES_TABLE, DRUGS_BRAND_COL, DRUGS_ATC_COL

    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")

    # Build optional brand restriction (ATC-derived + user-selected + drug-indication).
    restricted_brands: list[str] = []
    if qb.brand_names:
        restricted_brands.extend(qb.brand_names)
    if filters.brand_name:
        restricted_brands.extend(filters.brand_name)
    if filters.drug_indication:
        di_brands = resolve_brand_names_from_drug_indication(filters.drug_indication)
        restricted_brands.extend(di_brands)
    restricted_brands = list(dict.fromkeys(restricted_brands))  # deduplicate, preserve order

    brand_filter = ""
    if restricted_brands:
        bn_p: dict = {}
        bn_frag = _list_clause("dt.brand_name", restricted_brands, bn_p, "dcbf")
        params.update(bn_p)
        brand_filter = f"AND {bn_frag}"

    # Step 1: get brand names that are in scope from AACT DB.
    brands_sql = f"""
        SELECT DISTINCT dt.brand_name
        FROM ctgov.studies s
        JOIN public.drug_trials dt ON dt.nct_id = s.nct_id
        WHERE {scope_clause}
          AND dt.brand_name IS NOT NULL
          {brand_filter}
    """
    brands_df = query_aact(brands_sql, params)
    if brands_df.empty:
        return pd.DataFrame(columns=["drug_class", "brand_count"])

    in_scope_brands = brands_df["brand_name"].dropna().tolist()

    # Step 2: look up ATC classes for those brands from Drugs DB.
    atc_params: dict = {}
    bn_frag2 = _list_clause(DRUGS_BRAND_COL, in_scope_brands, atc_params, "atcbn")
    atc_sql = f"""
        SELECT
            {DRUGS_ATC_COL}                   AS drug_class,
            COUNT(DISTINCT {DRUGS_BRAND_COL}) AS brand_count
        FROM {DRUG_CLASSES_TABLE}
        WHERE {bn_frag2}
          AND {DRUGS_ATC_COL} IS NOT NULL
          AND {DRUGS_ATC_COL} <> ''
        GROUP BY 1 ORDER BY 2 DESC
        LIMIT 10
    """
    return query_drugs(atc_sql, atc_params)


@st.cache_data(ttl=300, show_spinner=False)
def get_drug_phase_mix(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    sql = f"""
        SELECT
            COALESCE(s.phase, 'N/A') AS phase,
            COUNT(DISTINCT s.nct_id) AS trial_count
        FROM ctgov.studies s
        WHERE {scope_clause}
        GROUP BY 1 ORDER BY 2 DESC
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_drug_brand_names(filters: FilterState, limit: int = 30) -> pd.DataFrame:
    """Return brand names and their trial counts, restricted to in-scope brands only."""
    from data.query_builder import _list_clause, resolve_brand_names_from_drug_indication

    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    params["lim"] = limit

    # Build brand restriction so the JOIN with drug_trials only surfaces brands
    # that are actually in scope. Without this, every brand co-enrolled in a
    # scoped trial would appear even if it belongs to a different drug class.
    # Restriction applies when ATC class, explicit brand selection, or drug
    # indication is active. When only indication_name is set the brand list is
    # intentionally unrestricted (indication is condition-level, not drug-level).
    restricted_brands: list[str] = []
    if qb.brand_names:
        restricted_brands.extend(qb.brand_names)
    if filters.brand_name:
        restricted_brands.extend(filters.brand_name)
    if filters.drug_indication:
        di_brands = resolve_brand_names_from_drug_indication(filters.drug_indication)
        restricted_brands.extend(di_brands)
    restricted_brands = list(dict.fromkeys(restricted_brands))  # deduplicate, preserve order

    brand_filter = ""
    if restricted_brands:
        bn_p: dict = {}
        bn_frag = _list_clause("dt.brand_name", restricted_brands, bn_p, "dbf")
        params.update(bn_p)
        brand_filter = f"AND {bn_frag}"

    sql = f"""
        SELECT
            dt.brand_name,
            COUNT(DISTINCT s.nct_id) AS trial_count
        FROM ctgov.studies s
        JOIN public.drug_trials dt ON dt.nct_id = s.nct_id
        WHERE {scope_clause}
          AND dt.brand_name IS NOT NULL
          {brand_filter}
        GROUP BY 1 ORDER BY 2 DESC
        LIMIT :lim
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_drug_phase_brand_heatmap(filters: FilterState, limit: int = 20) -> pd.DataFrame:
    """
    Return a pivoted DataFrame (phase × brand_name) with trial counts.
    Brands are limited to the top `limit` by trial count to keep the chart readable.
    """
    from data.query_builder import _list_clause, resolve_brand_names_from_drug_indication

    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    params["lim"] = limit

    # Same brand restriction logic as get_drug_brand_names — only surface brands
    # that are actually in scope, not every brand co-enrolled in scoped trials.
    restricted_brands: list[str] = []
    if qb.brand_names:
        restricted_brands.extend(qb.brand_names)
    if filters.brand_name:
        restricted_brands.extend(filters.brand_name)
    if filters.drug_indication:
        di_brands = resolve_brand_names_from_drug_indication(filters.drug_indication)
        restricted_brands.extend(di_brands)
    restricted_brands = list(dict.fromkeys(restricted_brands))

    brand_filter = ""
    if restricted_brands:
        bn_p: dict = {}
        bn_frag = _list_clause("dt.brand_name", restricted_brands, bn_p, "hbf")
        params.update(bn_p)
        brand_filter = f"AND {bn_frag}"

    # First fetch the top brands by trial count so we can restrict the heatmap
    top_brands_sql = f"""
        SELECT dt.brand_name
        FROM ctgov.studies s
        JOIN public.drug_trials dt ON dt.nct_id = s.nct_id
        WHERE {scope_clause}
          AND dt.brand_name IS NOT NULL
          {brand_filter}
        GROUP BY 1 ORDER BY COUNT(DISTINCT s.nct_id) DESC
        LIMIT :lim
    """
    top_brands_df = query_aact(top_brands_sql, params)
    if top_brands_df.empty:
        return pd.DataFrame()

    top_brands = top_brands_df["brand_name"].tolist()

    params2: dict = dict(params)
    bn_frag = _list_clause("dt.brand_name", top_brands, params2, "hbm")

    detail_sql = f"""
        SELECT
            COALESCE(s.phase, 'N/A') AS phase,
            dt.brand_name,
            COUNT(DISTINCT s.nct_id) AS trial_count
        FROM ctgov.studies s
        JOIN public.drug_trials dt ON dt.nct_id = s.nct_id
        WHERE {scope_clause}
          AND {bn_frag}
        GROUP BY 1, 2
    """
    long_df = query_aact(detail_sql, params2)
    if long_df.empty:
        return pd.DataFrame()

    pivot = long_df.pivot_table(
        index="phase", columns="brand_name", values="trial_count", fill_value=0
    )
    # Order columns by total trials descending (matches top_brands order)
    col_order = [b for b in top_brands if b in pivot.columns]
    pivot = pivot[col_order]
    return pivot


# ════════════════════════════════════════════════════════════════════════════
#  SPONSOR BENCHMARK
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_sponsor_trial_counts(filters: FilterState, limit: int = 20) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            sp.name                   AS sponsor,
            COUNT(DISTINCT sp.nct_id) AS total_trials,
            COUNT(DISTINCT CASE WHEN s.overall_status IN
                ('RECRUITING','ACTIVE_NOT_RECRUITING') THEN sp.nct_id END) AS active_trials,
            COUNT(DISTINCT CASE WHEN s.overall_status = 'COMPLETED'
                THEN sp.nct_id END)                                        AS completed_trials,
            COUNT(DISTINCT CASE WHEN s.results_first_submitted_date IS NOT NULL
                THEN sp.nct_id END)                                        AS with_results
        FROM ctgov.sponsors sp
        JOIN ctgov.studies s ON s.nct_id = sp.nct_id
        WHERE sp.lead_or_collaborator = 'lead'
          AND sp.name IS NOT NULL
          {scope_where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_sponsor_phase_mix(filters: FilterState, limit: int = 15) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        WITH top_sponsors AS (
            SELECT sp.name, COUNT(DISTINCT sp.nct_id) AS cnt
            FROM ctgov.sponsors sp
            JOIN ctgov.studies s ON s.nct_id = sp.nct_id
            WHERE sp.lead_or_collaborator = 'lead' AND sp.name IS NOT NULL
              {scope_where}
            GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
        )
        SELECT
            sp.name                   AS sponsor,
            COALESCE(s.phase,'N/A')   AS phase,
            COUNT(DISTINCT sp.nct_id) AS trial_count
        FROM ctgov.sponsors sp
        JOIN ctgov.studies s ON s.nct_id = sp.nct_id
        JOIN top_sponsors ts ON ts.name = sp.name
        WHERE sp.lead_or_collaborator = 'lead'
          {scope_where}
        GROUP BY 1, 2
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_sponsor_pro_adoption(filters: FilterState, limit: int = 15) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        WITH trial_pros AS (
            SELECT DISTINCT p.nct_id FROM public.drug_trial_design_outcomes_pro p
        ),
        sponsor_totals AS (
            SELECT sp.name, COUNT(DISTINCT sp.nct_id) AS total
            FROM ctgov.sponsors sp
            JOIN ctgov.studies s ON s.nct_id = sp.nct_id
            WHERE sp.lead_or_collaborator = 'lead' AND sp.name IS NOT NULL
              {scope_where}
            GROUP BY 1
        ),
        sponsor_pros AS (
            SELECT sp.name, COUNT(DISTINCT sp.nct_id) AS pro_count
            FROM ctgov.sponsors sp
            JOIN ctgov.studies s ON s.nct_id = sp.nct_id
            JOIN trial_pros tp ON tp.nct_id = sp.nct_id
            WHERE sp.lead_or_collaborator = 'lead'
              {scope_where}
            GROUP BY 1
        )
        SELECT
            st.name AS sponsor,
            st.total,
            COALESCE(sp2.pro_count, 0) AS pro_trials,
            ROUND(100.0 * COALESCE(sp2.pro_count, 0) / NULLIF(st.total, 0), 1) AS pct_with_pro
        FROM sponsor_totals st
        LEFT JOIN sponsor_pros sp2 ON sp2.name = st.name
        ORDER BY st.total DESC LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_sponsor_endpoint_usage(filters: FilterState, limit: int = 10) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        WITH top_sponsors AS (
            SELECT sp.name, COUNT(DISTINCT sp.nct_id) AS cnt
            FROM ctgov.sponsors sp
            JOIN ctgov.studies s ON s.nct_id = sp.nct_id
            WHERE sp.lead_or_collaborator = 'lead' {scope_where}
            GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
        )
        SELECT
            sp.name               AS sponsor,
            oc.outcome_category   AS category,
            COUNT(DISTINCT oc.nct_id) AS trial_count
        FROM ctgov.sponsors sp
        JOIN ctgov.studies s ON s.nct_id = sp.nct_id
        JOIN public.drug_trial_outcome_categories oc ON oc.nct_id = sp.nct_id
        JOIN top_sponsors ts ON ts.name = sp.name
        WHERE sp.lead_or_collaborator = 'lead'
          AND oc.outcome_category IS NOT NULL
          {scope_where}
        GROUP BY 1, 2
    """
    return query_aact(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  TRIAL DESIGN
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_trial_design_metrics(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            COALESCE(d.allocation, 'N/A')          AS allocation,
            COALESCE(d.intervention_model, 'N/A')  AS intervention_model,
            COALESCE(d.primary_purpose, 'N/A')     AS primary_purpose,
            COUNT(DISTINCT d.nct_id)               AS trial_count
        FROM ctgov.designs d
        JOIN ctgov.studies s ON s.nct_id = d.nct_id
        WHERE d.nct_id IS NOT NULL {scope_where}
        GROUP BY 1, 2, 3
        ORDER BY 4 DESC
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_arms_distribution(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    sql = f"""
        SELECT
            s.number_of_arms,
            COUNT(DISTINCT s.nct_id) AS trial_count
        FROM ctgov.studies s
        WHERE {scope_clause}
          AND s.number_of_arms IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_eligibility_distribution(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            COALESCE(e.gender, 'All')           AS gender,
            e.adult,
            e.child,
            e.older_adult,
            COUNT(DISTINCT e.nct_id)            AS trial_count
        FROM ctgov.eligibilities e
        JOIN ctgov.studies s ON s.nct_id = e.nct_id
        WHERE e.nct_id IS NOT NULL {scope_where}
        GROUP BY 1, 2, 3, 4
        ORDER BY 5 DESC
    """
    return query_aact(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  PLANNED ENDPOINTS (design_outcomes)
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_design_outcomes(filters: FilterState, limit: int = MAX_TABLE_ROWS) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""

    sql = f"""
        SELECT
            do_.outcome_type,
            do_.measure,
            do_.time_frame,
            s.phase,
            COUNT(DISTINCT do_.nct_id) AS trial_count
        FROM ctgov.design_outcomes do_
        JOIN ctgov.studies s ON s.nct_id = do_.nct_id
        WHERE do_.measure IS NOT NULL
          {scope_where}
        GROUP BY 1, 2, 3, 4
        ORDER BY 5 DESC
        LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_design_outcome_type_dist(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            COALESCE(do_.outcome_type, 'other') AS outcome_type,
            COUNT(*)                            AS endpoint_count,
            COUNT(DISTINCT do_.nct_id)          AS trial_count
        FROM ctgov.design_outcomes do_
        JOIN ctgov.studies s ON s.nct_id = do_.nct_id
        WHERE do_.nct_id IS NOT NULL {scope_where}
        GROUP BY 1 ORDER BY 2 DESC
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_design_outcome_type_category_heatmap(filters: FilterState) -> pd.DataFrame:
    """Pivoted DataFrame: rows=outcome_type, cols=outcome_category, values=unique trial count."""
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    ec_clause, ec_p = qb.endpoint_category_clause("dc")
    params.update(ec_p)
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    ec_where = f"AND {ec_clause}" if ec_clause else ""
    sql = f"""
        SELECT
            COALESCE(do_.outcome_type, 'other') AS outcome_type,
            dc.outcome_category,
            COUNT(DISTINCT do_.nct_id)          AS trial_count
        FROM ctgov.design_outcomes do_
        JOIN public.drug_trial_design_outcome_categories dc ON dc.nct_id = do_.nct_id
        JOIN ctgov.studies s ON s.nct_id = do_.nct_id
        WHERE dc.outcome_category IS NOT NULL {scope_where} {ec_where}
        GROUP BY 1, 2
    """
    df = query_aact(sql, params)
    if df.empty:
        return df
    return df.pivot_table(
        index="outcome_type", columns="outcome_category",
        values="trial_count", fill_value=0,
    )


@st.cache_data(ttl=300, show_spinner=False)
def get_planned_pro_usage(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    pi_clause, pi_p = qb.pro_instrument_clause("p")
    params.update(pi_p)
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    pi_where = f"AND {pi_clause}" if pi_clause else ""
    sql = f"""
        SELECT
            p.instrument_name,
            COUNT(DISTINCT p.nct_id) AS trial_count,
            s.phase
        FROM public.drug_trial_design_outcomes_pro p
        JOIN ctgov.studies s ON s.nct_id = p.nct_id
        WHERE p.instrument_name IS NOT NULL {scope_where} {pi_where}
        GROUP BY 1, 3 ORDER BY 2 DESC LIMIT 30
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_top_design_endpoints(filters: FilterState, limit: int = 25) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    ec_clause, ec_p = qb.endpoint_category_clause("dc")
    params.update(ec_p)
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    ec_where = f"AND {ec_clause}" if ec_clause else ""
    sql = f"""
        SELECT
            dc.outcome_category,
            COUNT(DISTINCT dc.nct_id) AS trial_count
        FROM public.drug_trial_design_outcome_categories dc
        JOIN ctgov.studies s ON s.nct_id = dc.nct_id
        WHERE dc.outcome_category IS NOT NULL {scope_where} {ec_where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """
    return query_aact(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  REPORTED OUTCOMES
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_reported_outcome_categories(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    ec_clause, ec_p = qb.endpoint_category_clause("oc")
    params.update(ec_p)
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    ec_where = f"AND {ec_clause}" if ec_clause else ""
    sql = f"""
        SELECT
            oc.outcome_category AS category,
            COUNT(DISTINCT oc.outcome_id) AS outcome_count,
            COUNT(DISTINCT oc.nct_id)     AS trial_count
        FROM public.drug_trial_outcome_categories oc
        JOIN ctgov.studies s ON s.nct_id = oc.nct_id
        WHERE oc.outcome_category IS NOT NULL {scope_where} {ec_where}
        GROUP BY 1 ORDER BY 2 DESC
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_reported_outcome_type_dist(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            COALESCE(o.outcome_type, 'OTHER') AS outcome_type,
            COUNT(DISTINCT o.id)              AS outcome_count,
            COUNT(DISTINCT o.nct_id)          AS trial_count
        FROM ctgov.outcomes o
        JOIN ctgov.studies s ON s.nct_id = o.nct_id
        WHERE o.nct_id IS NOT NULL {scope_where}
        GROUP BY 1 ORDER BY 2 DESC
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_outcome_type_category_heatmap(filters: FilterState) -> pd.DataFrame:
    """Pivoted DataFrame: rows=outcome_type, cols=outcome_category, values=unique trial count."""
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    ec_clause, ec_p = qb.endpoint_category_clause("oc")
    params.update(ec_p)
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    ec_where = f"AND {ec_clause}" if ec_clause else ""
    sql = f"""
        SELECT
            COALESCE(o.outcome_type, 'OTHER') AS outcome_type,
            oc.outcome_category,
            COUNT(DISTINCT o.nct_id)          AS trial_count
        FROM ctgov.outcomes o
        JOIN public.drug_trial_outcome_categories oc
            ON oc.nct_id = o.nct_id AND oc.outcome_id = o.id
        JOIN ctgov.studies s ON s.nct_id = o.nct_id
        WHERE oc.outcome_category IS NOT NULL {scope_where} {ec_where}
        GROUP BY 1, 2
    """
    df = query_aact(sql, params)
    if df.empty:
        return df
    return df.pivot_table(
        index="outcome_type", columns="outcome_category",
        values="trial_count", fill_value=0,
    )


@st.cache_data(ttl=300, show_spinner=False)
def get_top_outcome_titles(filters: FilterState, limit: int = 25) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            o.title,
            o.outcome_type,
            COUNT(DISTINCT o.nct_id) AS trial_count
        FROM ctgov.outcomes o
        JOIN ctgov.studies s ON s.nct_id = o.nct_id
        WHERE o.title IS NOT NULL {scope_where}
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_reported_pro_funnel(filters: FilterState) -> pd.DataFrame:
    """Planned vs reported PRO funnel."""
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    pi_clause, pi_p = qb.pro_instrument_clause("p")
    params.update(pi_p)
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    pi_where = f"AND {pi_clause}" if pi_clause else ""
    sql = f"""
        SELECT
            'Planned PROs'  AS stage,
            COUNT(DISTINCT p.nct_id) AS trial_count
        FROM public.drug_trial_design_outcomes_pro p
        JOIN ctgov.studies s ON s.nct_id = p.nct_id
        WHERE TRUE {scope_where} {pi_where}
        UNION ALL
        SELECT
            'Reported PROs' AS stage,
            COUNT(DISTINCT p.nct_id) AS trial_count
        FROM public.drug_trial_outcomes_pro p
        JOIN ctgov.studies s ON s.nct_id = p.nct_id
        WHERE TRUE {scope_where} {pi_where}
    """
    return query_aact(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  OUTCOME SCORES
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_outcome_scores(filters: FilterState, categories: list,
                        exclude_baseline: bool = True,
                        limit: int = MAX_TABLE_ROWS) -> pd.DataFrame:
    """
    Fetch numeric outcome measurements joined to category and brand name.
    Only rows where param_value_num is not null.
    """
    # Build a FilterState that includes categories for the endpoint_category_clause
    fs_with_cats = FilterState(
        indication_name=filters.indication_name,
        atc_class_name=filters.atc_class_name,
        phase=filters.phase,
        overall_status=filters.overall_status,
        enrollment_min=filters.enrollment_min,
        enrollment_max=filters.enrollment_max,
        has_results=filters.has_results,
        sponsor=filters.sponsor,
        country=filters.country,
        brand_name=filters.brand_name,
        endpoint_category=categories,
    )
    qb = QueryBuilder(fs_with_cats)
    scope_clause, scope_p = qb.study_scope_clause("o")
    cat_clause, cat_p     = qb.endpoint_category_clause("oc")
    combined = QueryBuilder.combine([scope_clause, cat_clause])
    nct_where = f"AND {combined}" if combined else ""
    params = QueryBuilder.merge_params(scope_p, cat_p)

    baseline_filter = """
        AND LOWER(COALESCE(om.classification, '')) NOT IN (
            'baseline','cycle 1 day 1','week 1 day 1','month 1 day 1',
            'day 1','pre-dose','pre-treatment','screening'
        )
    """ if exclude_baseline else ""

    sql = f"""
        SELECT
            om.outcome_id,
            om.title                AS outcome_title,
            om.units,
            om.param_type,
            om.param_value_num,
            om.dispersion_value_num,
            om.classification,
            om.result_group_id,
            oc.outcome_category AS category,
            dt.brand_name,
            o.nct_id
        FROM ctgov.outcome_measurements om
        JOIN ctgov.outcomes o ON o.id::text = om.outcome_id::text
        JOIN public.drug_trial_outcome_categories oc
               ON oc.outcome_id::text = om.outcome_id::text
        JOIN public.drug_trials dt ON dt.nct_id = o.nct_id
        WHERE om.param_value_num IS NOT NULL
          {baseline_filter}
          {nct_where}
        ORDER BY om.param_value_num DESC
        LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_score_by_drug(filters: FilterState, category: str,
                       exclude_baseline: bool = True) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("o")
    nct_where = f"AND {scope_clause}" if scope_clause else ""
    params["cat"] = category
    baseline_filter = """
        AND LOWER(COALESCE(om.classification,'')) NOT IN (
            'baseline','cycle 1 day 1','week 1 day 1','day 1','pre-dose'
        )
    """ if exclude_baseline else ""
    sql = f"""
        SELECT
            dt.brand_name,
            PERCENTILE_CONT(0.5) WITHIN GROUP
                (ORDER BY om.param_value_num) AS median_score,
            AVG(om.param_value_num)           AS mean_score,
            COUNT(*)                          AS n_measurements,
            MIN(om.param_value_num)           AS min_score,
            MAX(om.param_value_num)           AS max_score
        FROM ctgov.outcome_measurements om
        JOIN ctgov.outcomes o ON o.id::text = om.outcome_id::text
        JOIN public.drug_trial_outcome_categories oc
               ON oc.outcome_id::text = om.outcome_id::text
        JOIN public.drug_trials dt ON dt.nct_id = o.nct_id
        WHERE oc.outcome_category = :cat
          AND om.param_value_num IS NOT NULL
          {baseline_filter}
          {nct_where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT 20
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_trials_with_outcomes(filters: FilterState) -> pd.DataFrame:
    """
    Distinct trials that have at least one numeric outcome measurement,
    filtered by the active FilterState. Used for the trial comparison selector.

    Uses EXISTS instead of JOINing through outcome_measurements to avoid
    scanning the full measurements table; results_first_submitted_date IS NOT NULL
    is a cheap indexed pre-filter that eliminates trials without posted results
    before the EXISTS check runs.
    """
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    nct_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            s.nct_id,
            s.brief_title,
            (SELECT sp.name
             FROM ctgov.sponsors sp
             WHERE sp.nct_id = s.nct_id
               AND sp.lead_or_collaborator = 'lead'
             LIMIT 1)        AS lead_sponsor,
            s.phase,
            s.overall_status,
            s.enrollment
        FROM ctgov.studies s
        WHERE s.results_first_submitted_date IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM ctgov.outcomes o
              JOIN ctgov.outcome_measurements om
                ON om.outcome_id::text = o.id::text
              WHERE o.nct_id = s.nct_id
                AND om.param_value_num IS NOT NULL
          )
          {nct_where}
        ORDER BY s.start_date DESC NULLS LAST
        LIMIT 500
    """
    return query_aact(sql, params)


@st.cache_data(ttl=600, show_spinner=False)
def get_outcome_data_for_trial(nct_id: str) -> pd.DataFrame:
    """
    Numeric outcome measurements for a single trial.

    Performance notes:
    - Drive from ctgov.outcomes (small, indexed on nct_id) rather than the huge
      outcome_measurements table.
    - Cast only the integer PK side of each join (o.id::text, rg.id::text) so
      the varchar FK columns (om.outcome_id, om.result_group_id) remain bare and
      the planner can use their indexes.  Casting both sides (the previous
      approach) wraps the FK in a function and forces a sequential scan.
    - TTL raised to 600 s — per-trial data is stable within a session.
    """
    sql = """
        SELECT
            om.title          AS outcome_title,
            om.units,
            om.param_type,
            om.param_value_num,
            rg.title          AS group_name
        FROM ctgov.outcomes o
        JOIN ctgov.outcome_measurements om ON om.outcome_id = o.id
        LEFT JOIN ctgov.result_groups rg   ON om.result_group_id = rg.id
        WHERE o.nct_id = :nct_id
          AND om.param_value_num IS NOT NULL
        ORDER BY om.title, rg.title
    """
    return query_aact(sql, {"nct_id": nct_id})


# ════════════════════════════════════════════════════════════════════════════
#  PRO OVERVIEW
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_pro_usage(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    pi_clause_p, pi_p = qb.pro_instrument_clause("p")
    pi_clause_r, _    = qb.pro_instrument_clause("r")  # same params as pi_clause_p
    params.update(pi_p)
    scope_where  = f"AND {scope_clause}" if scope_clause else ""
    pi_where_p   = f"AND {pi_clause_p}" if pi_clause_p else ""
    pi_where_r   = f"AND {pi_clause_r}" if pi_clause_r else ""
    sql = f"""
        SELECT
            p.instrument_name,
            COUNT(DISTINCT p.nct_id)  AS planned_count,
            0                         AS reported_count
        FROM public.drug_trial_design_outcomes_pro p
        JOIN ctgov.studies s ON s.nct_id = p.nct_id
        WHERE p.instrument_name IS NOT NULL {scope_where} {pi_where_p}
        GROUP BY 1
        UNION ALL
        SELECT
            r.instrument_name,
            0                         AS planned_count,
            COUNT(DISTINCT r.nct_id)  AS reported_count
        FROM public.drug_trial_outcomes_pro r
        JOIN ctgov.studies s ON s.nct_id = r.nct_id
        WHERE r.instrument_name IS NOT NULL {scope_where} {pi_where_r}
        GROUP BY 1
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pro_by_sponsor(filters: FilterState, limit: int = 15) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    pi_clause, pi_p = qb.pro_instrument_clause("p")
    params.update(pi_p)
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    pi_where = f"AND {pi_clause}" if pi_clause else ""
    sql = f"""
        WITH sponsor_totals AS (
            SELECT sp.name AS sponsor,
                   COUNT(DISTINCT p.nct_id) AS sponsor_total
            FROM public.drug_trial_design_outcomes_pro p
            JOIN ctgov.studies s ON s.nct_id = p.nct_id
            JOIN ctgov.sponsors sp ON sp.nct_id = s.nct_id
                   AND sp.lead_or_collaborator = 'lead'
            WHERE p.instrument_name IS NOT NULL {scope_where} {pi_where}
            GROUP BY 1
        )
        SELECT
            sp.name             AS sponsor,
            p.instrument_name,
            COUNT(DISTINCT p.nct_id) AS trial_count,
            st.sponsor_total
        FROM public.drug_trial_design_outcomes_pro p
        JOIN ctgov.studies s ON s.nct_id = p.nct_id
        JOIN ctgov.sponsors sp ON sp.nct_id = s.nct_id
               AND sp.lead_or_collaborator = 'lead'
        JOIN sponsor_totals st ON st.sponsor = sp.name
        WHERE p.instrument_name IS NOT NULL {scope_where} {pi_where}
        GROUP BY 1, 2, st.sponsor_total
        ORDER BY 4 DESC, 3 DESC LIMIT {limit * 5}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pro_by_phase(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    pi_clause, pi_p = qb.pro_instrument_clause("p")
    params.update(pi_p)
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    pi_where = f"AND {pi_clause}" if pi_clause else ""
    sql = f"""
        SELECT
            COALESCE(s.phase,'N/A') AS phase,
            COUNT(DISTINCT p.nct_id) AS pro_trials
        FROM public.drug_trial_design_outcomes_pro p
        JOIN ctgov.studies s ON s.nct_id = p.nct_id
        WHERE TRUE {scope_where} {pi_where}
        GROUP BY 1 ORDER BY 2 DESC
    """
    return query_aact(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  PRO DOMAINS
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_pro_domains(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    pi_clause, pi_p = qb.pro_instrument_clause("d")
    pd_clause, pd_p = qb.pro_domain_clause("d")
    params.update(pi_p)
    params.update(pd_p)
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    pi_where = f"AND {pi_clause}" if pi_clause else ""
    pd_where = f"AND {pd_clause}" if pd_clause else ""
    sql = f"""
        SELECT
            d.criteria         AS domain,
            d.instrument_name,
            COUNT(DISTINCT d.nct_id) AS trial_count,
            COUNT(DISTINCT d.brand_name) AS drug_count
        FROM public.domain_score_match d
        JOIN ctgov.studies s ON s.nct_id = d.nct_id
        WHERE d.criteria IS NOT NULL {scope_where} {pi_where} {pd_where}
        GROUP BY 1, 2
        ORDER BY 3 DESC
        LIMIT 200
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_domain_instrument_heatmap(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    pi_clause, pi_p = qb.pro_instrument_clause("d")
    pd_clause, pd_p = qb.pro_domain_clause("d")
    params.update(pi_p)
    params.update(pd_p)
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    pi_where = f"AND {pi_clause}" if pi_clause else ""
    pd_where = f"AND {pd_clause}" if pd_clause else ""
    sql = f"""
        WITH top_instruments AS (
            SELECT instrument_name, COUNT(DISTINCT nct_id) AS cnt
            FROM public.domain_score_match
            GROUP BY 1 ORDER BY 2 DESC LIMIT 12
        ),
        top_domains AS (
            SELECT criteria, COUNT(DISTINCT nct_id) AS cnt
            FROM public.domain_score_match
            WHERE criteria IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC LIMIT 12
        )
        SELECT
            d.instrument_name,
            d.criteria   AS domain,
            COUNT(DISTINCT d.nct_id) AS trial_count
        FROM public.domain_score_match d
        JOIN ctgov.studies s ON s.nct_id = d.nct_id
        JOIN top_instruments ti ON ti.instrument_name = d.instrument_name
        JOIN top_domains td ON td.criteria = d.criteria
        WHERE d.criteria IS NOT NULL {scope_where} {pi_where} {pd_where}
        GROUP BY 1, 2
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_domain_by_drug(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    pi_clause, pi_p = qb.pro_instrument_clause("d")
    pd_clause, pd_p = qb.pro_domain_clause("d")
    params.update(pi_p)
    params.update(pd_p)
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    pi_where = f"AND {pi_clause}" if pi_clause else ""
    pd_where = f"AND {pd_clause}" if pd_clause else ""
    sql = f"""
        SELECT
            d.brand_name,
            d.criteria   AS domain,
            COUNT(DISTINCT d.nct_id) AS trial_count
        FROM public.domain_score_match d
        JOIN ctgov.studies s ON s.nct_id = d.nct_id
        WHERE d.criteria IS NOT NULL
          AND d.brand_name IS NOT NULL {scope_where} {pi_where} {pd_where}
        GROUP BY 1, 2
        ORDER BY 3 DESC LIMIT 200
    """
    return query_aact(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  TRIAL GROUPS
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_trial_groups(filters: FilterState, limit: int = MAX_TABLE_ROWS) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            dg.nct_id,
            dg.group_type,
            dg.title       AS group_title,
            i.name         AS intervention_name,
            i.intervention_type,
            s.phase,
            s.overall_status
        FROM ctgov.design_groups dg
        JOIN ctgov.design_group_interventions dgi ON dgi.design_group_id = dg.id
        JOIN ctgov.interventions i ON i.id = dgi.intervention_id
        JOIN ctgov.studies s ON s.nct_id = dg.nct_id
        WHERE dg.nct_id IS NOT NULL {scope_where}
        ORDER BY dg.nct_id, dg.group_type
        LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_result_groups(filters: FilterState, limit: int = MAX_TABLE_ROWS) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            rg.nct_id,
            rg.ctgov_group_code,
            rg.result_type,
            rg.title,
            drg.brand_name,
            s.phase,
            s.overall_status
        FROM ctgov.result_groups rg
        JOIN ctgov.studies s ON s.nct_id = rg.nct_id
        LEFT JOIN public.drug_result_groups drg
               ON drg.nct_id = rg.nct_id
               AND drg.result_group_id::text = rg.id::text
        WHERE rg.nct_id IS NOT NULL {scope_where}
        ORDER BY rg.nct_id, rg.ctgov_group_code
        LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_groups_per_trial_dist(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            groups_per_trial,
            COUNT(*) AS trial_count
        FROM (
            SELECT dg.nct_id, COUNT(DISTINCT dg.id) AS groups_per_trial
            FROM ctgov.design_groups dg
            JOIN ctgov.studies s ON s.nct_id = dg.nct_id
            WHERE dg.nct_id IS NOT NULL {scope_where}
            GROUP BY 1
        ) t
        GROUP BY 1 ORDER BY 1
    """
    return query_aact(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  SAFETY / ADVERSE EVENTS
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=900, show_spinner=False)
def get_ae_aggregates(filters: FilterState) -> dict:
    """
    Single-query replacement for the chart datasets used on the safety page:
      get_top_adverse_events  → result["top_ae"]  (DataFrame, top 25 by trial_count)
      get_ae_by_organ_system  → result["organ"]   (DataFrame, top 50 by trial_count)

    Uses one DB round-trip with a shared ae_filtered CTE so reported_events is
    scanned only once per filter combination.
    """
    import json

    _empty: dict = {
        "top_ae": pd.DataFrame(),
        "organ":  pd.DataFrame(),
    }
    if not filters.has_any_filter():
        return _empty

    qb = QueryBuilder(filters)
    cte_sql, params = qb.ae_scope_cte()
    scope_join = "JOIN scope_nct ON scope_nct.nct_id = re.nct_id" if cte_sql else ""

    sql = f"""
        {cte_sql}{"," if cte_sql else "WITH"} ae_filtered AS (
            SELECT re.nct_id, re.adverse_event_term, re.organ_system,
                   re.subjects_affected, re.event_count
            FROM ctgov.reported_events re
            {scope_join}
            WHERE re.subjects_affected > 0
              AND re.adverse_event_term IS NOT NULL
        )
        SELECT 'top_terms' AS _rs, row_to_json(t.*)::text AS data
        FROM (
            SELECT adverse_event_term, organ_system,
                   COUNT(DISTINCT nct_id)  AS trial_count,
                   SUM(subjects_affected)  AS total_affected,
                   SUM(event_count)        AS total_events
            FROM ae_filtered
            GROUP BY 1, 2
            ORDER BY 3 DESC, 4 DESC
            LIMIT 25
        ) t
        UNION ALL
        SELECT 'organ_systems' AS _rs, row_to_json(o.*)::text AS data
        FROM (
            SELECT COALESCE(organ_system, 'Unknown') AS organ_system,
                   COUNT(DISTINCT nct_id)            AS trial_count,
                   COUNT(DISTINCT adverse_event_term) AS unique_terms,
                   SUM(subjects_affected)             AS total_affected
            FROM ae_filtered
            GROUP BY 1
            ORDER BY 2 DESC, 4 DESC
            LIMIT 50
        ) o
    """
    raw = query_aact_ae(sql, params)
    if raw.empty or "_rs" not in raw.columns or "data" not in raw.columns:
        return _empty

    result: dict = dict(_empty)
    for rs, group in raw.groupby("_rs"):
        rows = [json.loads(r) for r in group["data"]]
        if rs == "top_terms":
            result["top_ae"] = pd.DataFrame(rows)
        elif rs == "organ_systems":
            result["organ"] = pd.DataFrame(rows)
    return result


@st.cache_data(ttl=900, show_spinner=False)
def get_adverse_event_summary(filters: FilterState) -> dict:
    """KPIs for the safety page."""
    if not filters.has_any_filter():
        return {
            "trials_with_ae": 0, "total_ae_records": 0,
            "unique_ae_terms": 0, "unique_organ_systems": 0,
            "total_subjects_affected": 0,
        }
    qb = QueryBuilder(filters)
    cte_sql, params = qb.ae_scope_cte()
    scope_join = "JOIN scope_nct ON scope_nct.nct_id = re.nct_id" if cte_sql else ""

    sql = f"""
        {cte_sql}{"," if cte_sql else "WITH"} ae_base AS (
            SELECT re.nct_id, re.adverse_event_term, re.organ_system,
                   re.subjects_affected, re.subjects_at_risk, re.event_count
            FROM ctgov.reported_events re
            {scope_join}
            WHERE re.subjects_affected > 0
              AND re.adverse_event_term IS NOT NULL
        )
        SELECT
            COUNT(DISTINCT re.nct_id)             AS trials_with_ae,
            COUNT(*)                              AS total_ae_records,
            COUNT(DISTINCT re.adverse_event_term) AS unique_ae_terms,
            COUNT(DISTINCT re.organ_system)       AS unique_organ_systems,
            SUM(re.subjects_affected)             AS total_subjects_affected
        FROM ae_base re
    """
    df = query_aact_ae(sql, params)
    row = df.iloc[0] if not df.empty else {}
    return {
        "trials_with_ae":        int(row.get("trials_with_ae",          0) or 0),
        "total_ae_records":      int(row.get("total_ae_records",         0) or 0),
        "unique_ae_terms":       int(row.get("unique_ae_terms",          0) or 0),
        "unique_organ_systems":  int(row.get("unique_organ_systems",     0) or 0),
        "total_subjects_affected": int(row.get("total_subjects_affected",0) or 0),
    }


@st.cache_data(ttl=900, show_spinner=False)
def get_top_adverse_events(filters: FilterState, limit: int = 25) -> pd.DataFrame:
    if not filters.has_any_filter():
        return pd.DataFrame()
    qb = QueryBuilder(filters)
    cte_sql, params = qb.ae_scope_cte()
    scope_join = "JOIN scope_nct ON scope_nct.nct_id = re.nct_id" if cte_sql else ""
    sql = f"""
        {cte_sql}
        SELECT
            re.adverse_event_term,
            re.organ_system,
            COUNT(DISTINCT re.nct_id)  AS trial_count,
            SUM(re.subjects_affected)  AS total_affected,
            SUM(re.event_count)        AS total_events
        FROM ctgov.reported_events re
        {scope_join}
        WHERE re.subjects_affected > 0
          AND re.adverse_event_term IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 3 DESC, 4 DESC
        LIMIT {limit}
    """
    return query_aact_ae(sql, params)


@st.cache_data(ttl=900, show_spinner=False)
def get_ae_by_organ_system(filters: FilterState) -> pd.DataFrame:
    if not filters.has_any_filter():
        return pd.DataFrame()
    qb = QueryBuilder(filters)
    cte_sql, params = qb.ae_scope_cte()
    scope_join = "JOIN scope_nct ON scope_nct.nct_id = re.nct_id" if cte_sql else ""
    sql = f"""
        {cte_sql}
        SELECT
            COALESCE(re.organ_system,'Unknown') AS organ_system,
            COUNT(DISTINCT re.nct_id)           AS trial_count,
            COUNT(DISTINCT re.adverse_event_term) AS unique_terms,
            SUM(re.subjects_affected)            AS total_affected
        FROM ctgov.reported_events re
        {scope_join}
        WHERE re.subjects_affected > 0
        GROUP BY 1 ORDER BY 2 DESC, 4 DESC
        LIMIT 50
    """
    return query_aact_ae(sql, params)


@st.cache_data(ttl=900, show_spinner=False)
def get_ae_by_drug(filters: FilterState, limit: int = 20) -> pd.DataFrame:
    """Adverse events per drug, using drug_result_groups to link drug → result group."""
    if not filters.has_any_filter():
        return pd.DataFrame()
    qb = QueryBuilder(filters)
    cte_sql, params = qb.ae_scope_cte()
    scope_join = "JOIN scope_nct ON scope_nct.nct_id = re.nct_id" if cte_sql else ""
    sql = f"""
        {cte_sql}
        SELECT
            drg.brand_name,
            COUNT(DISTINCT re.nct_id)             AS trial_count,
            COUNT(DISTINCT re.adverse_event_term) AS unique_terms,
            SUM(re.subjects_affected)             AS total_affected
        FROM ctgov.reported_events re
        {scope_join}
        JOIN public.drug_result_groups drg
               ON drg.nct_id = re.nct_id
               AND drg.result_group_id::text = re.result_group_id::text
        WHERE re.subjects_affected > 0
          AND drg.brand_name IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """
    return query_aact_ae(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_ae_detail_table(filters: FilterState,
                         organ_system: str | None = None,
                         ae_term: str | None = None,
                         limit: int = MAX_TABLE_ROWS) -> pd.DataFrame:
    """Full adverse event detail table with drug linkage."""
    if not filters.has_any_filter():
        return pd.DataFrame()
    qb = QueryBuilder(filters)
    cte_sql, params = qb.ae_scope_cte()
    params = dict(params)
    scope_join = "JOIN scope_nct ON scope_nct.nct_id = re.nct_id" if cte_sql else ""

    extra = ""
    if organ_system:
        extra += " AND re.organ_system = :organ_system"
        params["organ_system"] = organ_system
    if ae_term:
        extra += " AND re.adverse_event_term = :ae_term"
        params["ae_term"] = ae_term

    sql = f"""
        {cte_sql}
        SELECT
            re.nct_id,
            re.adverse_event_term,
            re.organ_system,
            re.subjects_affected,
            re.subjects_at_risk,
            re.event_count,
            drg.brand_name,
            sp.name          AS sponsor,
            s.phase,
            s.overall_status
        FROM ctgov.reported_events re
        {scope_join}
        JOIN ctgov.studies s ON s.nct_id = re.nct_id
        LEFT JOIN public.drug_result_groups drg
               ON drg.nct_id = re.nct_id
               AND drg.result_group_id::text = re.result_group_id::text
        LEFT JOIN ctgov.sponsors sp
               ON sp.nct_id = s.nct_id AND sp.lead_or_collaborator = 'lead'
        WHERE re.subjects_affected > 0
          AND re.adverse_event_term IS NOT NULL
          {extra}
        ORDER BY re.subjects_affected DESC
        LIMIT {limit}
    """
    return query_aact_ae(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  DRUGS DB  – indication / atc_class option queries
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def get_indication_options() -> list[str]:
    """
    Returns distinct condition names from ctgov.conditions, scoped to trials
    present in public.drug_trials. These are the options for the global
    Indication filter.
    """
    from config.settings import CONDITIONS_TABLE, CONDITIONS_NAME_COL
    sql = f"""
        SELECT DISTINCT LOWER(c.{CONDITIONS_NAME_COL})
        FROM {CONDITIONS_TABLE} c
        JOIN public.drug_trials dt ON dt.nct_id = c.nct_id
        WHERE c.{CONDITIONS_NAME_COL} IS NOT NULL
        ORDER BY 1
        LIMIT 3000
    """
    df = query_aact(sql)
    if df.empty:
        return []
    return df.iloc[:, 0].dropna().tolist()


@st.cache_data(ttl=3600, show_spinner=False)
def get_atc_class_options() -> list[str]:
    from data.db import query_drugs
    from config.settings import DRUG_CLASSES_TABLE, DRUGS_ATC_COL
    sql = f"""
        SELECT DISTINCT {DRUGS_ATC_COL}
        FROM {DRUG_CLASSES_TABLE}
        WHERE {DRUGS_ATC_COL} IS NOT NULL
        ORDER BY 1
    """
    df = query_drugs(sql)
    if df.empty:
        return []
    return df.iloc[:, 0].dropna().tolist()


@st.cache_data(ttl=600, show_spinner=False)
def get_brand_options_from_drugs(indication: str | None, atc_class: str | None) -> list[str]:
    """
    Return brand names available for the Drug Detail page selector, scoped by
    the active global filters.

    indication is a ctgov.browse_conditions mesh_term (AACT DB) — NOT a
    drug_indications.indication_name value.  When indication is set, brands are
    derived from public.drug_trials JOIN ctgov.browse_conditions.
    atc_class is still resolved via public.drug_classes (DRUGS DB).
    """
    from config.settings import (
        DRUG_CLASSES_TABLE, DRUGS_BRAND_COL, DRUGS_ATC_COL,
        CONDITIONS_TABLE, CONDITIONS_NAME_COL,
    )

    if indication and atc_class:
        # Step 1: resolve ATC brands from DRUGS DB
        from data.db import query_drugs
        atc_sql = f"""
            SELECT DISTINCT {DRUGS_BRAND_COL} AS brand_name
            FROM {DRUG_CLASSES_TABLE}
            WHERE {DRUGS_ATC_COL} = :atc
              AND {DRUGS_BRAND_COL} IS NOT NULL
            LIMIT 2000
        """
        atc_df = query_drugs(atc_sql, {"atc": atc_class})
        atc_brands = atc_df["brand_name"].dropna().tolist() if not atc_df.empty else []
        if not atc_brands:
            return []
        # Step 2: intersect with conditions scope in AACT
        ph = ", ".join(f":bn_{i}" for i in range(len(atc_brands)))
        params: dict = {f"bn_{i}": b for i, b in enumerate(atc_brands)}
        params["bc_ind"] = indication.lower()
        sql = f"""
            SELECT DISTINCT dt.brand_name
            FROM public.drug_trials dt
            JOIN {CONDITIONS_TABLE} c ON c.nct_id = dt.nct_id
            WHERE LOWER(c.{CONDITIONS_NAME_COL}) = :bc_ind
              AND dt.brand_name IN ({ph})
              AND dt.brand_name IS NOT NULL
            ORDER BY 1 LIMIT 300
        """
        df = query_aact(sql, params)

    elif indication:
        # Scope via conditions JOIN drug_trials in AACT
        sql = f"""
            SELECT DISTINCT dt.brand_name
            FROM public.drug_trials dt
            JOIN {CONDITIONS_TABLE} c ON c.nct_id = dt.nct_id
            WHERE LOWER(c.{CONDITIONS_NAME_COL}) = :bc_ind
              AND dt.brand_name IS NOT NULL
            ORDER BY 1 LIMIT 300
        """
        df = query_aact(sql, {"bc_ind": indication.lower()})

    elif atc_class:
        from data.db import query_drugs
        sql = f"""
            SELECT DISTINCT {DRUGS_BRAND_COL}
            FROM {DRUG_CLASSES_TABLE}
            WHERE {DRUGS_ATC_COL} = :atc
              AND {DRUGS_BRAND_COL} IS NOT NULL
            ORDER BY 1 LIMIT 300
        """
        df = query_drugs(sql, {"atc": atc_class})

    else:
        # No global filters — all brands present in drug_trials
        sql = """
            SELECT DISTINCT brand_name
            FROM public.drug_trials
            WHERE brand_name IS NOT NULL
            ORDER BY 1 LIMIT 300
        """
        df = query_aact(sql)

    if df.empty:
        return []
    return df.iloc[:, 0].dropna().tolist()


# ════════════════════════════════════════════════════════════════════════════
#  NL QUERY (uncached)
# ════════════════════════════════════════════════════════════════════════════

def run_nl_query(sql: str) -> pd.DataFrame:
    """Execute a user-confirmed NL-generated SQL query (no cache)."""
    return query_aact_uncached(sql)


# ════════════════════════════════════════════════════════════════════════════
#  PRICING  (annual_pricing_table + historical_pricing)
# ════════════════════════════════════════════════════════════════════════════

def _get_pricing_brand_list(filters: FilterState) -> list[str]:
    """
    Resolve an effective brand name list for pricing queries.

    Priority:
      1. Explicit brand_name filter
      2. ATC class → drug_classes lookup
      3. MeSH indication → mesh_to_indication_map.json → drug_indications lookup
      4. Empty list  → no brand filter, show all pricing data
    """
    if filters.brand_name:
        return list(filters.brand_name)

    if filters.atc_class_name:
        sql = f"""
            SELECT DISTINCT {DRUGS_BRAND_COL}
            FROM {DRUG_CLASSES_TABLE}
            WHERE {DRUGS_ATC_COL} = :atc
              AND {DRUGS_BRAND_COL} IS NOT NULL
            ORDER BY 1
        """
        df = query_drugs(sql, {"atc": filters.atc_class_name})
        return df.iloc[:, 0].dropna().tolist() if not df.empty else []

    if filters.indication_name:
        return _resolve_brands_from_mesh_indication(filters.indication_name)

    return []


def _build_pricing_where(
    brands: list[str],
    drug_indication: str | None,
    *,
    include_disease: bool = True,
) -> tuple[str, dict]:
    """
    Build a parameterized WHERE clause for annual_pricing_table queries.

    Returns (clause_string, params_dict).  The clause never starts with WHERE
    so callers can prepend it however they like.
    """
    # Exclude outlier rows where annual cost exceeds $1M
    clauses: list[str] = ["total_cost_filled <= 1000000"]
    params: dict = {}

    if brands:
        clauses.append("LOWER(brand_name) = ANY(:brands)")
        params["brands"] = [b.lower() for b in brands]

    if include_disease and drug_indication:
        clauses.append("LOWER(TRIM(disease)) = :drug_indication")
        params["drug_indication"] = drug_indication.lower().strip()

    return (" AND ".join(clauses), params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pricing_kpis(filters: FilterState) -> dict:
    """KPI summary for the Drug Pricing page."""
    brands = _get_pricing_brand_list(filters)
    where, params = _build_pricing_where(brands, filters.drug_indication)

    sql_main = f"""
        SELECT
            COUNT(DISTINCT brand_name)              AS unique_drugs,
            COUNT(DISTINCT dosage_form)             AS dosage_forms,
            COUNT(DISTINCT LOWER(TRIM(disease)))    AS unique_diseases,
            MAX(quarter_start)                      AS latest_quarter
        FROM {ANNUAL_PRICING_TABLE}
        WHERE {where}
    """
    df = query_pricing(sql_main, params)
    if df.empty or df.iloc[0]["unique_drugs"] is None:
        return {
            "unique_drugs": 0, "dosage_forms": 0,
            "unique_diseases": 0, "latest_total_cost": None,
            "latest_quarter": None, "price_change_pct": None,
        }

    row = df.iloc[0]
    latest_qtr = row["latest_quarter"]

    # Average cost per drug for latest quarter
    sql_latest = f"""
        SELECT COALESCE(AVG(total_cost_filled), 0) AS avg_cost
        FROM {ANNUAL_PRICING_TABLE}
        WHERE {where}
          AND quarter_start = :latest_qtr
    """
    p_latest = {**params, "latest_qtr": latest_qtr}
    df_latest = query_pricing(sql_latest, p_latest)
    latest_avg_cost = float(df_latest.iloc[0]["avg_cost"]) if not df_latest.empty else None

    # Average cost one year prior (for YoY delta)
    price_change_pct = None
    if latest_qtr is not None:
        try:
            import datetime
            prior_qtr = latest_qtr - datetime.timedelta(days=365)
            sql_prior = f"""
                SELECT COALESCE(AVG(total_cost_filled), 0) AS avg_cost
                FROM {ANNUAL_PRICING_TABLE}
                WHERE {where}
                  AND quarter_start = :prior_qtr
            """
            p_prior = {**params, "prior_qtr": prior_qtr}
            df_prior = query_pricing(sql_prior, p_prior)
            if not df_prior.empty:
                prior_avg_cost = float(df_prior.iloc[0]["avg_cost"])
                if prior_avg_cost and prior_avg_cost != 0:
                    price_change_pct = ((latest_avg_cost - prior_avg_cost) / prior_avg_cost) * 100
        except Exception:
            pass

    return {
        "unique_drugs":       int(row["unique_drugs"]),
        "dosage_forms":       int(row["dosage_forms"]),
        "unique_diseases":    int(row["unique_diseases"]),
        "latest_avg_cost":    latest_avg_cost,
        "latest_quarter":     str(latest_qtr)[:10] if latest_qtr else None,
        "price_change_pct":   price_change_pct,
    }


@st.cache_data(ttl=300, show_spinner=False)
def get_annual_cost_over_time(filters: FilterState) -> pd.DataFrame:
    """Total annual cost aggregated by quarter, for the active filter scope."""
    brands = _get_pricing_brand_list(filters)
    where, params = _build_pricing_where(brands, filters.drug_indication)
    sql = f"""
        SELECT
            quarter_start,
            SUM(total_cost_filled) AS total_cost
        FROM {ANNUAL_PRICING_TABLE}
        WHERE {where}
        GROUP BY quarter_start
        ORDER BY quarter_start
    """
    return query_pricing(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_annual_cost_per_brand_over_time(filters: FilterState) -> pd.DataFrame:
    """Annual cost per brand per quarter — used for the per-drug step-line chart."""
    brands = _get_pricing_brand_list(filters)
    where, params = _build_pricing_where(brands, filters.drug_indication)
    sql = f"""
        SELECT
            brand_name,
            quarter_start,
            SUM(total_cost_filled) AS total_cost
        FROM {ANNUAL_PRICING_TABLE}
        WHERE {where}
        GROUP BY brand_name, quarter_start
        ORDER BY quarter_start, brand_name
    """
    return query_pricing(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_annual_cost_by_dosage_form(filters: FilterState) -> pd.DataFrame:
    """Annual cost broken down by dosage form over time."""
    brands = _get_pricing_brand_list(filters)
    where, params = _build_pricing_where(brands, filters.drug_indication)
    sql = f"""
        SELECT
            COALESCE(dosage_form, 'Unknown') AS dosage_form,
            quarter_start,
            SUM(total_cost_filled) AS total_cost
        FROM {ANNUAL_PRICING_TABLE}
        WHERE {where}
        GROUP BY dosage_form, quarter_start
        ORDER BY quarter_start
    """
    return query_pricing(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_annual_cost_by_disease(filters: FilterState) -> pd.DataFrame:
    """Total cost per disease/indication, for the active filter scope."""
    brands = _get_pricing_brand_list(filters)
    # For disease breakdown we intentionally ignore the drug_indication filter
    # so users can see the full disease split even when no indication is chosen.
    where, params = _build_pricing_where(brands, None, include_disease=False)
    sql = f"""
        SELECT
            COALESCE(LOWER(TRIM(disease)), 'unknown') AS disease,
            SUM(total_cost_filled) AS total_cost
        FROM {ANNUAL_PRICING_TABLE}
        WHERE {where}
        GROUP BY LOWER(TRIM(disease))
        ORDER BY total_cost DESC
        LIMIT 20
    """
    return query_pricing(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_wac_price_history(filters: FilterState) -> pd.DataFrame:
    """WAC unit price history from historical_pricing — one row per NDC per effective date."""
    brands = _get_pricing_brand_list(filters)
    if brands:
        brand_clause = "AND LOWER(brand_name) = ANY(:brands)"
        params: dict = {"brands": [b.lower() for b in brands]}
    else:
        brand_clause = ""
        params = {}

    sql = f"""
        SELECT
            brand_name,
            ndc,
            wac_unit_effective_date,
            wac_unit_price
        FROM {HISTORICAL_PRICING_TABLE}
        WHERE wac_unit_price IS NOT NULL
          {brand_clause}
        ORDER BY wac_unit_effective_date, brand_name
    """
    return query_pricing(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_annual_cost_by_drug_class(filters: FilterState) -> pd.DataFrame:
    """
    Average latest-quarter annual cost per ATC drug class.

    Cross-DB: costs come from the pricing DB; class mapping from the drugs DB.
    The merge is done in Python after both queries return.
    """
    brands = _get_pricing_brand_list(filters)
    where, params = _build_pricing_where(brands, filters.drug_indication)

    # Latest quarter available under the current filter scope
    qtr_sql = f"SELECT MAX(quarter_start) AS latest_qtr FROM {ANNUAL_PRICING_TABLE} WHERE {where}"
    qtr_df = query_pricing(qtr_sql, params)
    if qtr_df.empty or qtr_df.iloc[0]["latest_qtr"] is None:
        return pd.DataFrame()
    latest_qtr = qtr_df.iloc[0]["latest_qtr"]

    # Cost per brand for the latest quarter
    cost_sql = f"""
        SELECT
            LOWER(brand_name) AS brand_key,
            SUM(total_cost_filled) AS total_cost
        FROM {ANNUAL_PRICING_TABLE}
        WHERE {where}
          AND quarter_start = :latest_qtr
        GROUP BY LOWER(brand_name)
    """
    cost_df = query_pricing(cost_sql, {**params, "latest_qtr": latest_qtr})
    if cost_df.empty:
        return pd.DataFrame()

    # ATC class mapping — scoped to resolved brands if any, else all
    if brands:
        class_sql = f"""
            SELECT DISTINCT
                LOWER({DRUGS_BRAND_COL}) AS brand_key,
                {DRUGS_ATC_COL}          AS drug_class
            FROM {DRUG_CLASSES_TABLE}
            WHERE LOWER({DRUGS_BRAND_COL}) = ANY(:brands)
              AND {DRUGS_ATC_COL} IS NOT NULL
              AND {DRUGS_ATC_COL} <> ''
        """
        class_df = query_drugs(class_sql, {"brands": [b.lower() for b in brands]})
    else:
        class_sql = f"""
            SELECT DISTINCT
                LOWER({DRUGS_BRAND_COL}) AS brand_key,
                {DRUGS_ATC_COL}          AS drug_class
            FROM {DRUG_CLASSES_TABLE}
            WHERE {DRUGS_ATC_COL} IS NOT NULL
              AND {DRUGS_ATC_COL} <> ''
        """
        class_df = query_drugs(class_sql, {})

    if class_df.empty:
        return pd.DataFrame()

    merged = cost_df.merge(class_df, on="brand_key", how="inner")
    if merged.empty:
        return pd.DataFrame()

    result = (
        merged.groupby("drug_class", as_index=False)["total_cost"]
        .mean()
        .rename(columns={"total_cost": "avg_cost"})
        .sort_values("avg_cost", ascending=False)
        .head(20)
    )
    return result


@st.cache_data(ttl=300, show_spinner=False)
def get_annual_pricing_raw(filters: FilterState) -> pd.DataFrame:
    """Full annual_pricing_table rows for the table view and CSV download."""
    brands = _get_pricing_brand_list(filters)
    where, params = _build_pricing_where(brands, filters.drug_indication)
    sql = f"""
        SELECT
            brand_name,
            LOWER(TRIM(disease))  AS disease,
            dosage_form,
            quarter_start,
            total_cost_filled
        FROM {ANNUAL_PRICING_TABLE}
        WHERE {where}
        ORDER BY quarter_start DESC, brand_name
        LIMIT {MAX_TABLE_ROWS}
    """
    return query_pricing(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  MARKET ACCESS  (mapped_access_2025 / mapped_access_2026)
# ════════════════════════════════════════════════════════════════════════════

def _get_ma_table(year: int) -> str:
    return MA_TABLE_2025 if year == 2025 else MA_TABLE_2026


def _build_ma_where(brands: list[str]) -> tuple[str, dict]:
    """Parameterized WHERE clause for market access tables (brand filter only)."""
    if brands:
        return "LOWER(brand_name) = ANY(:brands)", {"brands": [b.lower() for b in brands]}
    return "1=1", {}


@st.cache_data(ttl=300, show_spinner=False)
def get_ma_kpis(filters: FilterState, year: int = 2025) -> dict:
    """KPI summary for the Market Access page."""
    brands = _get_pricing_brand_list(filters)
    where, params = _build_ma_where(brands)
    table = _get_ma_table(year)

    sql = f"""
        SELECT
            COUNT(*)                                                               AS total_drugs,
            COUNT(*) FILTER (WHERE aetna_req  ILIKE '%PA%'
                               OR cigna_req   ILIKE '%PA%'
                               OR united_req  ILIKE '%PA%'
                               OR kaiser_req  ILIKE '%PA%'
                               OR optum_req   ILIKE '%PA%'
                               OR anthem_req  ILIKE '%PA%')                        AS pa_count,
            COUNT(*) FILTER (WHERE aetna_req  ILIKE '%QL%'
                               OR cigna_req   ILIKE '%QL%'
                               OR united_req  ILIKE '%QL%'
                               OR kaiser_req  ILIKE '%QL%'
                               OR optum_req   ILIKE '%QL%'
                               OR anthem_req  ILIKE '%QL%')                        AS ql_count,
            COUNT(*) FILTER (WHERE aetna_req  ILIKE '%SP%'
                               OR cigna_req   ILIKE '%SP%'
                               OR united_req  ILIKE '%SP%'
                               OR kaiser_req  ILIKE '%SP%'
                               OR optum_req   ILIKE '%SP%'
                               OR anthem_req  ILIKE '%SP%')                        AS sp_count
        FROM {table}
        WHERE {where}
    """
    df = query_market_access(sql, params)
    if df.empty or df.iloc[0]["total_drugs"] is None:
        return {"total_drugs": 0, "pa_pct": 0.0, "ql_pct": 0.0, "sp_pct": 0.0}

    row = df.iloc[0]
    total = int(row["total_drugs"]) or 1
    return {
        "total_drugs": int(row["total_drugs"]),
        "pa_pct": round(int(row["pa_count"]) / total * 100, 1),
        "ql_pct": round(int(row["ql_count"]) / total * 100, 1),
        "sp_pct": round(int(row["sp_count"]) / total * 100, 1),
    }


@st.cache_data(ttl=300, show_spinner=False)
def get_ma_avg_tier_by_payer(filters: FilterState, year: int = 2025) -> pd.DataFrame:
    """Average formulary tier per payer for the selected year."""
    brands = _get_pricing_brand_list(filters)
    where, params = _build_ma_where(brands)
    table = _get_ma_table(year)

    sql = f"""
        SELECT 'Aetna'           AS payer, ROUND(AVG(NULLIF(aetna_tier,  '')::numeric), 2) AS avg_tier FROM {table} WHERE {where} AND NULLIF(aetna_tier,  '') IS NOT NULL
        UNION ALL
        SELECT 'Cigna',                    ROUND(AVG(NULLIF(cigna_tier,  '')::numeric), 2)             FROM {table} WHERE {where} AND NULLIF(cigna_tier,  '') IS NOT NULL
        UNION ALL
        SELECT 'UnitedHealthcare',         ROUND(AVG(NULLIF(united_tier, '')::numeric), 2)             FROM {table} WHERE {where} AND NULLIF(united_tier, '') IS NOT NULL
        UNION ALL
        SELECT 'Kaiser',                   ROUND(AVG(NULLIF(kaiser_tier, '')::numeric), 2)             FROM {table} WHERE {where} AND NULLIF(kaiser_tier, '') IS NOT NULL
        UNION ALL
        SELECT 'OptumRx',                  ROUND(AVG(NULLIF(optum_tier,  '')::numeric), 2)             FROM {table} WHERE {where} AND NULLIF(optum_tier,  '') IS NOT NULL
        UNION ALL
        SELECT 'Anthem',                   ROUND(AVG(NULLIF(anthem_tier, '')::numeric), 2)             FROM {table} WHERE {where} AND NULLIF(anthem_tier, '') IS NOT NULL
        ORDER BY avg_tier
    """
    return query_market_access(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_ma_requirement_breakdown(filters: FilterState, year: int = 2025) -> pd.DataFrame:
    """Utilization-management requirement type counts per payer."""
    brands = _get_pricing_brand_list(filters)
    where, params = _build_ma_where(brands)
    table = _get_ma_table(year)

    def _payer_block(label: str, col: str) -> str:
        return f"""
        SELECT '{label}' AS payer,
               CASE
                   WHEN {col} IS NULL OR TRIM({col}) = '' THEN 'None'
                   WHEN {col} ILIKE '%PA%' AND {col} ILIKE '%QL%'  THEN 'PA+QL'
                   WHEN {col} ILIKE '%PA%' AND {col} ILIKE '%SP%'  THEN 'PA+SP'
                   WHEN {col} ILIKE '%PA%'                          THEN 'PA'
                   WHEN {col} ILIKE '%QL%'                          THEN 'QL'
                   WHEN {col} ILIKE '%SP%'                          THEN 'SP'
                   ELSE 'Other'
               END AS req_type,
               COUNT(*) AS drug_count
        FROM {table} WHERE {where}
        GROUP BY payer, req_type"""

    sql = (
        _payer_block("Aetna",            "aetna_req")  + " UNION ALL " +
        _payer_block("Cigna",            "cigna_req")  + " UNION ALL " +
        _payer_block("UnitedHealthcare", "united_req") + " UNION ALL " +
        _payer_block("Kaiser",           "kaiser_req") + " UNION ALL " +
        _payer_block("OptumRx",          "optum_req")  + " UNION ALL " +
        _payer_block("Anthem",           "anthem_req") +
        " ORDER BY payer, req_type"
    )
    return query_market_access(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_ma_brand_payer_heatmap(filters: FilterState, year: int = 2025, limit: int = 25) -> pd.DataFrame:
    """
    Wide brand × payer tier data for the heatmap.
    Returns a DataFrame already pivoted: index = brand_name, columns = payer labels, values = tier.
    """
    brands = _get_pricing_brand_list(filters)
    where, params = _build_ma_where(brands)
    params["lim"] = limit
    table = _get_ma_table(year)

    sql = f"""
        SELECT
            brand_name,
            aetna_tier, cigna_tier, united_tier, kaiser_tier, optum_tier, anthem_tier,
            ROUND(
                (COALESCE(NULLIF(aetna_tier,  '')::numeric, 0) + COALESCE(NULLIF(cigna_tier,  '')::numeric, 0) + COALESCE(NULLIF(united_tier, '')::numeric, 0)
               + COALESCE(NULLIF(kaiser_tier, '')::numeric, 0) + COALESCE(NULLIF(optum_tier,  '')::numeric, 0) + COALESCE(NULLIF(anthem_tier, '')::numeric, 0))
                / NULLIF(
                    (CASE WHEN NULLIF(aetna_tier,  '') IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN NULLIF(cigna_tier,  '') IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN NULLIF(united_tier, '') IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN NULLIF(kaiser_tier, '') IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN NULLIF(optum_tier,  '') IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN NULLIF(anthem_tier, '') IS NOT NULL THEN 1 ELSE 0 END)
                , 0)::numeric
            , 2) AS avg_tier
        FROM {table}
        WHERE {where} AND brand_name IS NOT NULL
        ORDER BY avg_tier DESC NULLS LAST
        LIMIT :lim
    """
    df = query_market_access(sql, params)
    if df.empty:
        return pd.DataFrame()

    col_map = {
        "aetna_tier":  "Aetna",
        "cigna_tier":  "Cigna",
        "united_tier": "UnitedHealthcare",
        "kaiser_tier": "Kaiser",
        "optum_tier":  "OptumRx",
        "anthem_tier": "Anthem",
    }
    df = df[["brand_name"] + list(col_map.keys())].rename(columns=col_map)
    return df.set_index("brand_name")


@st.cache_data(ttl=300, show_spinner=False)
def get_ma_brands_by_avg_tier(filters: FilterState, year: int = 2025, limit: int = 20) -> pd.DataFrame:
    """Top brands ranked by average formulary tier (highest = most restrictive)."""
    brands = _get_pricing_brand_list(filters)
    where, params = _build_ma_where(brands)
    params["lim"] = limit
    table = _get_ma_table(year)

    sql = f"""
        SELECT
            brand_name,
            ROUND(
                (COALESCE(NULLIF(aetna_tier,  '')::numeric, 0) + COALESCE(NULLIF(cigna_tier,  '')::numeric, 0) + COALESCE(NULLIF(united_tier, '')::numeric, 0)
               + COALESCE(NULLIF(kaiser_tier, '')::numeric, 0) + COALESCE(NULLIF(optum_tier,  '')::numeric, 0) + COALESCE(NULLIF(anthem_tier, '')::numeric, 0))
                / NULLIF(
                    (CASE WHEN NULLIF(aetna_tier,  '') IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN NULLIF(cigna_tier,  '') IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN NULLIF(united_tier, '') IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN NULLIF(kaiser_tier, '') IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN NULLIF(optum_tier,  '') IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN NULLIF(anthem_tier, '') IS NOT NULL THEN 1 ELSE 0 END)
                , 0)::numeric
            , 2) AS avg_tier
        FROM {table}
        WHERE {where} AND brand_name IS NOT NULL
        ORDER BY avg_tier DESC NULLS LAST
        LIMIT :lim
    """
    return query_market_access(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_ma_yoy_comparison(filters: FilterState) -> pd.DataFrame:
    """Average tier per payer for 2025 and 2026 combined — for the year-comparison grouped bar chart."""
    brands = _get_pricing_brand_list(filters)
    where, params = _build_ma_where(brands)

    def _year_blocks(table: str, year_label: str) -> str:
        return (
            f"SELECT '{year_label}' AS year, 'Aetna'           AS payer, ROUND(AVG(NULLIF(aetna_tier,  '')::numeric), 2) AS avg_tier FROM {table} WHERE {where} AND NULLIF(aetna_tier,  '') IS NOT NULL UNION ALL "
            f"SELECT '{year_label}',         'Cigna',                    ROUND(AVG(NULLIF(cigna_tier,  '')::numeric), 2)             FROM {table} WHERE {where} AND NULLIF(cigna_tier,  '') IS NOT NULL UNION ALL "
            f"SELECT '{year_label}',         'UnitedHealthcare',         ROUND(AVG(NULLIF(united_tier, '')::numeric), 2)             FROM {table} WHERE {where} AND NULLIF(united_tier, '') IS NOT NULL UNION ALL "
            f"SELECT '{year_label}',         'Kaiser',                   ROUND(AVG(NULLIF(kaiser_tier, '')::numeric), 2)             FROM {table} WHERE {where} AND NULLIF(kaiser_tier, '') IS NOT NULL UNION ALL "
            f"SELECT '{year_label}',         'OptumRx',                  ROUND(AVG(NULLIF(optum_tier,  '')::numeric), 2)             FROM {table} WHERE {where} AND NULLIF(optum_tier,  '') IS NOT NULL UNION ALL "
            f"SELECT '{year_label}',         'Anthem',                   ROUND(AVG(NULLIF(anthem_tier, '')::numeric), 2)             FROM {table} WHERE {where} AND NULLIF(anthem_tier, '') IS NOT NULL"
        )

    sql = _year_blocks(MA_TABLE_2025, "2025") + " UNION ALL " + _year_blocks(MA_TABLE_2026, "2026") + " ORDER BY payer, year"
    return query_market_access(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_ma_detail_table(filters: FilterState, year: int = 2025) -> pd.DataFrame:
    """Full brand-level market access detail for the selected year."""
    brands = _get_pricing_brand_list(filters)
    where, params = _build_ma_where(brands)
    table = _get_ma_table(year)

    sql = f"""
        SELECT
            brand_name, generic_name,
            aetna_tier,  aetna_req,
            cigna_tier,  cigna_req,
            united_tier, united_req,
            kaiser_tier, kaiser_req,
            optum_tier,  optum_req,
            anthem_tier, anthem_req
        FROM {table}
        WHERE {where}
        ORDER BY brand_name
        LIMIT {MAX_TABLE_ROWS}
    """
    return query_market_access(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_ma_tier_grid(filters: FilterState, year: int = 2025, limit: int = 50) -> pd.DataFrame:
    """Tier-only grid (brand × payer) for the categorical tier heatmap."""
    brands = _get_pricing_brand_list(filters)
    where, params = _build_ma_where(brands)
    params["lim"] = limit
    table = _get_ma_table(year)

    sql = f"""
        SELECT brand_name, aetna_tier, cigna_tier, united_tier, kaiser_tier, optum_tier, anthem_tier
        FROM {table}
        WHERE {where} AND brand_name IS NOT NULL
        ORDER BY brand_name
        LIMIT :lim
    """
    return query_market_access(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_ma_req_grid(filters: FilterState, year: int = 2025, limit: int = 50) -> pd.DataFrame:
    """Requirement-only grid (brand × payer) for the PA/QL/SP checkbox chart."""
    brands = _get_pricing_brand_list(filters)
    where, params = _build_ma_where(brands)
    params["lim"] = limit
    table = _get_ma_table(year)

    sql = f"""
        SELECT brand_name, aetna_req, cigna_req, united_req, kaiser_req, optum_req, anthem_req
        FROM {table}
        WHERE {where} AND brand_name IS NOT NULL
        ORDER BY brand_name
        LIMIT :lim
    """
    return query_market_access(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  FAERS  (Real World Safety)
# ════════════════════════════════════════════════════════════════════════════

def get_faers_brand_scope(filters: FilterState) -> tuple[list[str], str | None]:
    """
    Resolve the effective brand scope for FAERS using the same precedence as
    pricing and market access.

    Returns (brand_names, resolution_note).
    """
    brands = _get_pricing_brand_list(filters)
    if brands:
        if (
            filters.indication_name
            and not filters.brand_name
            and not filters.atc_class_name
        ):
            note = (
                f'Showing FAERS data for **{len(brands)} drug(s)** linked to '
                f'"{filters.indication_name}" via the pre-built indication mapping.'
            )
            return [b.upper() for b in brands], note
        return [b.upper() for b in brands], None

    if filters.indication_name and not filters.brand_name and not filters.atc_class_name:
        if not _MESH_TO_INDICATION_MAP_PATH.exists():
            note = (
                "MeSH → indication mapping file not found. "
                "Run `streamlit run scripts/generate_mesh_indication_map.py` to generate it, "
                "then reload the dashboard."
            )
        else:
            note = (
                f'No drugs mapped to "{filters.indication_name}" in the indication catalog. '
                f'Select a Drug Class or Brand Name in the sidebar to scope FAERS manually.'
            )
        return [], note

    return [], None


def _build_faers_brand_filter(brand_names: list[str], *, col: str = "dc.brand_name") -> tuple[str, dict]:
    """Return a SQL fragment and params dict for filtering FAERS by brand names."""
    if not brand_names:
        return "", {}
    upper = [b.upper() for b in brand_names]
    return f"AND UPPER({col}) = ANY(:brands)", {"brands": upper}


@st.cache_data(ttl=300, show_spinner=False)
def get_faers_kpis(brand_names: list[str]) -> dict:
    """KPI summary for the Real World Safety page."""
    brand_sql, params = _build_faers_brand_filter(brand_names)

    sql = f"""
        SELECT
            COUNT(DISTINCT d.primaryid)          AS total_reports,
            COUNT(DISTINCT r.pt)                 AS unique_reactions,
            COUNT(DISTINCT o.primaryid)          AS serious_outcomes,
            COUNT(DISTINCT UPPER(dc.brand_name)) AS unique_drugs
        FROM demo d
        JOIN public.drug_cases dc ON dc.primaryid = d.primaryid AND dc.role_cod = 'PS'
        JOIN reac r ON r.primaryid = d.primaryid
        LEFT JOIN outc o ON o.primaryid = d.primaryid
        WHERE 1=1
          {brand_sql}
    """
    df = query_fdaers(sql, params or None)
    if df.empty:
        return {
            "total_reports": 0,
            "unique_reactions": 0,
            "serious_outcomes": 0,
            "unique_drugs": 0,
        }
    row = df.iloc[0]
    return {
        "total_reports": int(row["total_reports"] or 0),
        "unique_reactions": int(row["unique_reactions"] or 0),
        "serious_outcomes": int(row["serious_outcomes"] or 0),
        "unique_drugs": int(row["unique_drugs"] or 0),
    }


@st.cache_data(ttl=300, show_spinner=False)
def get_top_reactions(brand_names: list[str], limit: int = 20) -> pd.DataFrame:
    brand_sql, params = _build_faers_brand_filter(brand_names, col="r.brand_name")
    params = {**params, "lim": limit}

    sql = f"""
        SELECT
            r.pt,
            COALESCE(sm.soc, 'Unknown') AS soc,
            COUNT(DISTINCT r.primaryid) AS report_count
        FROM public.faers_ps_reac r
        LEFT JOIN public.soc_map sm ON sm.english_pt = r.pt
        WHERE 1=1
          {brand_sql}
        GROUP BY r.pt, COALESCE(sm.soc, 'Unknown')
        ORDER BY report_count DESC, r.pt
        LIMIT :lim
    """
    return query_fdaers(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_faers_reaction_outcome_aggregates(
    brand_names: list[str],
    *,
    top_reaction_limit: int = 20,
) -> dict[str, pd.DataFrame]:
    """
    Shared FAERS aggregate query for the RW Safety page.

    Only loads data derived from reaction and outcome sources:
      - top reactions
      - reactions by SOC
      - outcomes distribution
    """
    empty = {
        "top_reactions": pd.DataFrame(),
        "soc": pd.DataFrame(),
        "outcomes": pd.DataFrame(),
    }
    if not brand_names:
        return empty

    import json

    brand_sql, base_params = _build_faers_brand_filter(brand_names)

    reaction_sql = f"""
        WITH reaction_base AS (
            SELECT DISTINCT
                dc.primaryid,
                r.pt,
                COALESCE(sm.soc, 'Unknown') AS soc
            FROM public.drug_cases dc
            JOIN reac r ON r.primaryid = dc.primaryid
            LEFT JOIN soc_map sm ON sm.english_pt = r.pt
            WHERE dc.role_cod = 'PS'
              {brand_sql}
        )
        SELECT 'top_reactions' AS _rs, row_to_json(t.*)::text AS data
        FROM (
            SELECT
                pt,
                COUNT(*) AS report_count
            FROM reaction_base
            GROUP BY pt
            ORDER BY report_count DESC, pt
            LIMIT :top_reaction_limit
        ) t
        UNION ALL
        SELECT 'soc', row_to_json(s.*)::text
        FROM (
            SELECT
                soc,
                COUNT(*) AS report_count
            FROM reaction_base
            GROUP BY soc
            ORDER BY report_count DESC, soc
        ) s
    """
    reaction_raw = query_fdaers(
        reaction_sql,
        {**base_params, "top_reaction_limit": top_reaction_limit},
    )

    outcome_sql = f"""
        WITH outcome_base AS (
            SELECT DISTINCT
                dc.primaryid,
                o.outc_cod
            FROM public.drug_cases dc
            JOIN outc o ON o.primaryid = dc.primaryid
            WHERE dc.role_cod = 'PS'
              {brand_sql}
        )
        SELECT
            outc_cod,
            COUNT(*) AS report_count
        FROM outcome_base
        GROUP BY outc_cod
        ORDER BY report_count DESC, outc_cod
    """
    outcome_df = query_fdaers(outcome_sql, base_params)

    result = dict(empty)
    if not reaction_raw.empty:
        for rs, group in reaction_raw.groupby("_rs"):
            rows = [json.loads(r) for r in group["data"]]
            if rs == "top_reactions":
                result["top_reactions"] = pd.DataFrame(rows)
            elif rs == "soc":
                result["soc"] = pd.DataFrame(rows)

    if not outcome_df.empty:
        outcome_df["outcome_label"] = outcome_df["outc_cod"].map(OUTC_LABELS).fillna(outcome_df["outc_cod"])
        result["outcomes"] = outcome_df
    return result


@st.cache_data(ttl=300, show_spinner=False)
def get_reactions_by_soc(brand_names: list[str], limit: int = 20) -> pd.DataFrame:
    brand_sql, params = _build_faers_brand_filter(brand_names, col="r.brand_name")
    params = {**params, "lim": limit}

    sql = f"""
        SELECT
            COALESCE(sm.soc, 'Unknown') AS soc,
            COUNT(DISTINCT r.primaryid) AS report_count
        FROM public.faers_ps_reac r
        LEFT JOIN public.soc_map sm ON sm.english_pt = r.pt
        WHERE 1=1
          {brand_sql}
        GROUP BY COALESCE(sm.soc, 'Unknown')
        ORDER BY report_count DESC, soc
        LIMIT :lim
    """
    return query_fdaers(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_outcomes_distribution(brand_names: list[str]) -> pd.DataFrame:
    brand_sql, params = _build_faers_brand_filter(brand_names, col="o.brand_name")

    sql = f"""
        SELECT o.outc_cod, COUNT(DISTINCT o.primaryid) AS report_count
        FROM public.faers_ps_outc o
        WHERE 1=1
          {brand_sql}
        GROUP BY o.outc_cod
        ORDER BY report_count DESC
    """
    df = query_fdaers(sql, params or None)
    if not df.empty and "outc_cod" in df.columns:
        df["outcome_label"] = df["outc_cod"].map(OUTC_LABELS).fillna(df["outc_cod"])
    return df


@st.cache_data(ttl=300, show_spinner=False)
def get_outcome_brand_heatmap(brand_names: list[str], limit: int = 10) -> pd.DataFrame:
    """
    Pivoted top-brand × outcome matrix for the RW Safety outcomes heatmap.

    Uses only drug_cases scoped by brand and joins to outc.
    """
    if not brand_names:
        return pd.DataFrame()

    brand_sql, params = _build_faers_brand_filter(brand_names, col="o.brand_name")
    params = {**params, "lim": limit}

    sql = f"""
        WITH top_brands AS (
            SELECT
                o.brand_name,
                COUNT(DISTINCT o.primaryid) AS case_count
            FROM public.faers_ps_outc o
            WHERE 1=1
              {brand_sql}
            GROUP BY o.brand_name
            ORDER BY case_count DESC, o.brand_name
            LIMIT :lim
        )
        SELECT
            o.brand_name,
            o.outc_cod,
            COUNT(DISTINCT o.primaryid) AS case_count
        FROM public.faers_ps_outc o
        JOIN top_brands tb ON tb.brand_name = o.brand_name
        GROUP BY o.brand_name, o.outc_cod
        ORDER BY o.brand_name, o.outc_cod
    """
    df = query_fdaers(sql, params)
    if df.empty:
        return pd.DataFrame()

    df["outcome_label"] = df["outc_cod"].map(OUTC_LABELS).fillna(df["outc_cod"])
    pivot = (
        df.pivot(index="brand_name", columns="outcome_label", values="case_count")
        .fillna(0)
        .astype(int)
    )
    return pivot


@st.cache_data(ttl=300, show_spinner=False)
def get_reaction_brand_heatmap(brand_names: list[str], limit: int = 10) -> pd.DataFrame:
    """
    Pivoted top-brand × top-reaction matrix for the RW Safety adverse event heatmap.

    Uses the pre-scoped faers_ps_reac table only.
    """
    if not brand_names:
        return pd.DataFrame()

    brand_sql, params = _build_faers_brand_filter(brand_names, col="r.brand_name")
    params = {**params, "lim": limit}

    sql = f"""
        WITH top_brands AS (
            SELECT
                r.brand_name,
                COUNT(DISTINCT r.primaryid) AS case_count
            FROM public.faers_ps_reac r
            WHERE 1=1
              {brand_sql}
            GROUP BY r.brand_name
            ORDER BY case_count DESC, r.brand_name
            LIMIT :lim
        ),
        top_pts AS (
            SELECT
                r.pt,
                COUNT(DISTINCT r.primaryid) AS case_count
            FROM public.faers_ps_reac r
            WHERE 1=1
              {brand_sql}
            GROUP BY r.pt
            ORDER BY case_count DESC, r.pt
            LIMIT :lim
        )
        SELECT
            r.brand_name,
            r.pt,
            COUNT(DISTINCT r.primaryid) AS case_count
        FROM public.faers_ps_reac r
        JOIN top_brands tb ON tb.brand_name = r.brand_name
        JOIN top_pts tp ON tp.pt = r.pt
        GROUP BY r.brand_name, r.pt
        ORDER BY r.brand_name, r.pt
    """
    df = query_fdaers(sql, params)
    if df.empty:
        return pd.DataFrame()

    pivot = (
        df.pivot(index="brand_name", columns="pt", values="case_count")
        .fillna(0)
        .astype(int)
    )
    return pivot


@st.cache_data(ttl=300, show_spinner=False)
def get_reports_over_time(brand_names: list[str]) -> pd.DataFrame:
    brand_sql, params = _build_faers_brand_filter(brand_names)

    sql = f"""
        SELECT
            DATE_PART('year', d.fda_dt)::int AS year,
            COUNT(DISTINCT d.primaryid) AS report_count
        FROM demo d
        JOIN public.drug_cases dc ON dc.primaryid = d.primaryid AND dc.role_cod = 'PS'
        WHERE d.fda_dt IS NOT NULL
          {brand_sql}
        GROUP BY year
        ORDER BY year
    """
    return query_fdaers(sql, params or None)


@st.cache_data(ttl=300, show_spinner=False)
def get_sex_breakdown(brand_names: list[str]) -> pd.DataFrame:
    brand_sql, params = _build_faers_brand_filter(brand_names)

    sql = f"""
        SELECT
            CASE d.sex
                WHEN 'M' THEN 'Male'
                WHEN 'F' THEN 'Female'
                ELSE 'Unknown'
            END AS sex,
            COUNT(DISTINCT d.primaryid) AS report_count
        FROM demo d
        JOIN public.drug_cases dc ON dc.primaryid = d.primaryid AND dc.role_cod = 'PS'
        WHERE 1=1
          {brand_sql}
        GROUP BY d.sex
        ORDER BY report_count DESC
    """
    return query_fdaers(sql, params or None)


@st.cache_data(ttl=300, show_spinner=False)
def get_age_distribution(brand_names: list[str]) -> pd.DataFrame:
    brand_sql, params = _build_faers_brand_filter(brand_names)

    sql = f"""
        SELECT
            CASE
                WHEN d.age < 18 THEN '<18'
                WHEN d.age < 41 THEN '18-40'
                WHEN d.age < 61 THEN '41-60'
                WHEN d.age < 76 THEN '61-75'
                ELSE '75+'
            END AS age_group,
            COUNT(DISTINCT d.primaryid) AS report_count
        FROM demo d
        JOIN public.drug_cases dc ON dc.primaryid = d.primaryid AND dc.role_cod = 'PS'
        WHERE d.age IS NOT NULL
          AND d.age_cod IN ('YR', 'DEC')
          AND d.age BETWEEN 0 AND 120
          {brand_sql}
        GROUP BY age_group
        ORDER BY MIN(d.age)
    """
    return query_fdaers(sql, params or None)


@st.cache_data(ttl=300, show_spinner=False)
def get_reporter_country(brand_names: list[str], limit: int = 10) -> pd.DataFrame:
    brand_sql, params = _build_faers_brand_filter(brand_names)
    params = {**params, "lim": limit}

    sql = f"""
        SELECT
            COALESCE(d.reporter_country, 'Unknown') AS reporter_country,
            COUNT(DISTINCT d.primaryid) AS report_count
        FROM demo d
        JOIN public.drug_cases dc ON dc.primaryid = d.primaryid AND dc.role_cod = 'PS'
        WHERE 1=1
          {brand_sql}
        GROUP BY d.reporter_country
        ORDER BY report_count DESC
        LIMIT :lim
    """
    return query_fdaers(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_reporter_type(brand_names: list[str]) -> pd.DataFrame:
    brand_sql, params = _build_faers_brand_filter(brand_names)

    sql = f"""
        SELECT
            COALESCE(d.occp_cod, 'Unknown') AS occp_cod,
            COUNT(DISTINCT d.primaryid) AS report_count
        FROM demo d
        JOIN public.drug_cases dc ON dc.primaryid = d.primaryid AND dc.role_cod = 'PS'
        WHERE 1=1
          {brand_sql}
        GROUP BY d.occp_cod
        ORDER BY report_count DESC
    """
    df = query_fdaers(sql, params or None)
    if not df.empty and "occp_cod" in df.columns:
        df["reporter_type"] = df["occp_cod"].map(OCCP_LABELS).fillna(df["occp_cod"])
    return df


@st.cache_data(ttl=300, show_spinner=False)
def get_ror_signals(brand_names: list[str], limit: int = 20) -> pd.DataFrame:
    if not brand_names:
        sql = """
            SELECT brand_name, pt, ror
            FROM public.top_n_ror
            ORDER BY ror DESC
            LIMIT :lim
        """
        params: dict = {"lim": limit}
    else:
        upper = [b.upper() for b in brand_names]
        sql = """
            SELECT brand_name, pt, ror
            FROM public.top_n_ror
            WHERE UPPER(brand_name) = ANY(:brands)
            ORDER BY ror DESC
            LIMIT :lim
        """
        params = {"brands": upper, "lim": limit}
    return query_fdaers(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_faers_detail_table(brand_names: list[str], limit: int = 500) -> pd.DataFrame:
    brand_sql, params = _build_faers_brand_filter(brand_names)
    params = {**params, "lim": limit}

    sql = f"""
        SELECT
            d.primaryid,
            dc.brand_name,
            dc.generic_name,
            r.pt AS reaction,
            COALESCE(sm.soc, 'Unknown') AS soc,
            STRING_AGG(DISTINCT o.outc_cod, ', ') AS outcomes,
            d.age,
            d.sex,
            d.reporter_country,
            d.fda_dt
        FROM demo d
        JOIN public.drug_cases dc ON dc.primaryid = d.primaryid AND dc.role_cod = 'PS'
        JOIN reac r ON r.primaryid = d.primaryid
        LEFT JOIN soc_map sm ON sm.english_pt = r.pt
        LEFT JOIN outc o ON o.primaryid = d.primaryid
        WHERE 1=1
          {brand_sql}
        GROUP BY
            d.primaryid, dc.brand_name, dc.generic_name,
            r.pt, sm.soc, d.age, d.sex, d.reporter_country, d.fda_dt
        ORDER BY d.fda_dt DESC NULLS LAST
        LIMIT :lim
    """
    return query_fdaers(sql, params)
