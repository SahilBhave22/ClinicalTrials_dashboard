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

import streamlit as st
import pandas as pd

from data.db import query_aact, query_aact_uncached
from data.query_builder import QueryBuilder
from utils.filters import FilterState
from config.settings import MAX_TABLE_ROWS


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
    # Brands in scope
    sql_brands = f"""
        SELECT DISTINCT dt.brand_name
        FROM public.drug_trials dt
        JOIN ctgov.studies s ON s.nct_id = dt.nct_id
        WHERE {nct_clause}
          AND dt.brand_name IS NOT NULL
        ORDER BY dt.brand_name
        LIMIT 300
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

    # Brands in scope — computed first so we can use them to scope drug_indications
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
def get_overview_kpis(filters: FilterState) -> dict:
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

@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_kpis(indication: str | None, sponsors: tuple[str, ...] = ()) -> dict:
    """Pipeline KPIs from onco_pipeline_trials, filtered by condition matching indication."""
    params: dict = {}
    cond_where = ""
    if indication:
        cond_where = "WHERE LOWER(pt.condition) LIKE :ind_like"
        params["ind_like"] = f"%{indication.lower()}%"
    if sponsors:
        sp_params = {f"_sp{i}": s for i, s in enumerate(sponsors)}
        sp_clause = "AND pt.sponsor_name IN (" + ", ".join(f":_sp{i}" for i in range(len(sponsors))) + ")"
        cond_where = (cond_where + " " + sp_clause) if cond_where else ("WHERE " + sp_clause[4:])
        params.update(sp_params)

    pros_where = cond_where.replace("WHERE", "WHERE", 1)  # same conditions apply to PRO query
    sql = f"""
        SELECT
            COUNT(DISTINCT pt.nct_id)            AS pipeline_trials,
            COUNT(DISTINCT pt.intervention_name) AS unique_assets,
            COUNT(DISTINCT pt.sponsor_name)      AS active_sponsors,
            COUNT(DISTINCT pt.condition)         AS indications_covered
        FROM public.onco_pipeline_trials pt
        {cond_where}
    """
    sql_pros = f"""
        SELECT COUNT(DISTINCT pp.nct_id) AS with_pros
        FROM public.onco_pipeline_design_outcomes_pro pp
        JOIN public.onco_pipeline_trials pt ON pt.nct_id = pp.nct_id
        {pros_where}
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
def get_pipeline_by_sponsor(indication: str | None, sponsors: tuple[str, ...] = (), limit: int = 20) -> pd.DataFrame:
    params: dict = {}
    cond_where = "WHERE pt.sponsor_name IS NOT NULL"
    if indication:
        cond_where += " AND LOWER(pt.condition) LIKE :ind_like"
        params["ind_like"] = f"%{indication.lower()}%"
    if sponsors:
        sp_params = {f"_sp{i}": s for i, s in enumerate(sponsors)}
        cond_where += " AND pt.sponsor_name IN (" + ", ".join(f":_sp{i}" for i in range(len(sponsors))) + ")"
        params.update(sp_params)
    sql = f"""
        SELECT
            pt.sponsor_name              AS sponsor,
            COUNT(DISTINCT pt.nct_id)   AS pipeline_trials,
            COUNT(DISTINCT pt.intervention_name) AS unique_assets
        FROM public.onco_pipeline_trials pt
        {cond_where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_by_indication(indication: str | None, sponsors: tuple[str, ...] = (), limit: int = 25) -> pd.DataFrame:
    params: dict = {}
    cond_where = "WHERE pt.condition IS NOT NULL"
    if indication:
        cond_where += " AND LOWER(pt.condition) LIKE :ind_like"
        params["ind_like"] = f"%{indication.lower()}%"
    if sponsors:
        sp_params = {f"_sp{i}": s for i, s in enumerate(sponsors)}
        cond_where += " AND pt.sponsor_name IN (" + ", ".join(f":_sp{i}" for i in range(len(sponsors))) + ")"
        params.update(sp_params)
    sql = f"""
        SELECT
            pt.condition                 AS condition,
            COUNT(DISTINCT pt.nct_id)   AS trial_count,
            COUNT(DISTINCT pt.sponsor_name) AS sponsors
        FROM public.onco_pipeline_trials pt
        {cond_where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_top_interventions(indication: str | None, sponsors: tuple[str, ...] = (), limit: int = 25) -> pd.DataFrame:
    params: dict = {}
    cond_where = "WHERE pt.intervention_name IS NOT NULL"
    if indication:
        cond_where += " AND LOWER(pt.condition) LIKE :ind_like"
        params["ind_like"] = f"%{indication.lower()}%"
    if sponsors:
        sp_params = {f"_sp{i}": s for i, s in enumerate(sponsors)}
        cond_where += " AND pt.sponsor_name IN (" + ", ".join(f":_sp{i}" for i in range(len(sponsors))) + ")"
        params.update(sp_params)
    sql = f"""
        SELECT
            pt.intervention_name         AS intervention,
            COUNT(DISTINCT pt.nct_id)   AS trial_count,
            COUNT(DISTINCT pt.sponsor_name) AS sponsors
        FROM public.onco_pipeline_trials pt
        {cond_where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_sponsor_indication_heatmap(indication: str | None, sponsors: tuple[str, ...] = ()) -> pd.DataFrame:
    """Return sponsor × condition counts for heatmap."""
    params: dict = {}
    cond_where = "WHERE pt.sponsor_name IS NOT NULL AND pt.condition IS NOT NULL"
    if indication:
        cond_where += " AND LOWER(pt.condition) LIKE :ind_like"
        params["ind_like"] = f"%{indication.lower()}%"
    if sponsors:
        sp_params = {f"_sp{i}": s for i, s in enumerate(sponsors)}
        cond_where += " AND pt.sponsor_name IN (" + ", ".join(f":_sp{i}" for i in range(len(sponsors))) + ")"
        params.update(sp_params)
    sql = f"""
        WITH ranked_sponsors AS (
            SELECT sponsor_name, COUNT(DISTINCT nct_id) AS cnt
            FROM public.onco_pipeline_trials
            {cond_where.replace('pt.', '')}
            GROUP BY 1 ORDER BY 2 DESC LIMIT 15
        ),
        ranked_conditions AS (
            SELECT condition, COUNT(DISTINCT nct_id) AS cnt
            FROM public.onco_pipeline_trials
            {cond_where.replace('pt.', '')}
            GROUP BY 1 ORDER BY 2 DESC LIMIT 15
        )
        SELECT
            pt.sponsor_name  AS sponsor,
            pt.condition     AS condition,
            COUNT(DISTINCT pt.nct_id) AS trial_count
        FROM public.onco_pipeline_trials pt
        JOIN ranked_sponsors rs ON rs.sponsor_name = pt.sponsor_name
        JOIN ranked_conditions rc ON rc.condition = pt.condition
        {cond_where}
        GROUP BY 1, 2
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_pro_usage(indication: str | None, sponsors: tuple[str, ...] = (), limit: int = 20) -> pd.DataFrame:
    params: dict = {}
    ind_filter = ""
    if indication:
        ind_filter = "AND LOWER(pt.condition) LIKE :ind_like"
        params["ind_like"] = f"%{indication.lower()}%"
    sp_filter = ""
    if sponsors:
        sp_params = {f"_sp{i}": s for i, s in enumerate(sponsors)}
        sp_filter = "AND pt.sponsor_name IN (" + ", ".join(f":_sp{i}" for i in range(len(sponsors))) + ")"
        params.update(sp_params)
    sql = f"""
        SELECT
            pp.instrument_name,
            COUNT(DISTINCT pp.nct_id) AS trial_count
        FROM public.onco_pipeline_design_outcomes_pro pp
        JOIN public.onco_pipeline_trials pt ON pt.nct_id = pp.nct_id
        WHERE pp.instrument_name IS NOT NULL
          {ind_filter}
          {sp_filter}
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pipeline_trials_table(indication: str | None, limit: int = MAX_TABLE_ROWS) -> pd.DataFrame:
    params: dict = {}
    cond_where = ""
    if indication:
        cond_where = "WHERE LOWER(pt.condition) LIKE :ind_like"
        params["ind_like"] = f"%{indication.lower()}%"
    sql = f"""
        SELECT
            pt.nct_id,
            pt.sponsor_name,
            pt.intervention_name,
            pt.condition,
            s.phase,
            s.overall_status,
            s.enrollment,
            s.start_date,
            s.primary_completion_date
        FROM public.onco_pipeline_trials pt
        LEFT JOIN ctgov.studies s ON s.nct_id = pt.nct_id
        {cond_where}
        ORDER BY s.start_date DESC NULLS LAST
        LIMIT {limit}
    """
    return query_aact(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  DRUG DETAIL
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_drug_trials(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
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
    """Return ATC drug class counts for the current filter scope (DRUGS DB)."""
    from data.db import query_drugs
    from config.settings import DRUG_CLASSES_TABLE, DRUGS_BRAND_COL, DRUGS_ATC_COL

    qb = QueryBuilder(filters)
    brand_names = qb.brand_names
    # If no ATC/indication filter is set, brand_names will be empty — fetch all
    if not brand_names:
        sql = f"""
            SELECT
                {DRUGS_ATC_COL}                   AS drug_class,
                COUNT(DISTINCT {DRUGS_BRAND_COL}) AS brand_count
            FROM {DRUG_CLASSES_TABLE}
            WHERE {DRUGS_ATC_COL} IS NOT NULL
              AND {DRUGS_ATC_COL} <> ''
            GROUP BY 1 ORDER BY 2 DESC
            LIMIT 10
        """
        return query_drugs(sql)

    from data.query_builder import _list_clause
    params: dict = {}
    bn_frag = _list_clause(DRUGS_BRAND_COL, brand_names, params, "bn")
    sql = f"""
        SELECT
            {DRUGS_ATC_COL}                   AS drug_class,
            COUNT(DISTINCT {DRUGS_BRAND_COL}) AS brand_count
        FROM {DRUG_CLASSES_TABLE}
        WHERE {bn_frag}
          AND {DRUGS_ATC_COL} IS NOT NULL
          AND {DRUGS_ATC_COL} <> ''
        GROUP BY 1 ORDER BY 2 DESC
        LIMIT 10
    """
    return query_drugs(sql, params)


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
def get_planned_pro_usage(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            p.instrument_name,
            COUNT(DISTINCT p.nct_id) AS trial_count,
            s.phase
        FROM public.drug_trial_design_outcomes_pro p
        JOIN ctgov.studies s ON s.nct_id = p.nct_id
        WHERE p.instrument_name IS NOT NULL {scope_where}
        GROUP BY 1, 3 ORDER BY 2 DESC LIMIT 30
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_top_design_endpoints(filters: FilterState, limit: int = 25) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            dc.outcome_category,
            COUNT(DISTINCT dc.nct_id) AS trial_count
        FROM public.drug_trial_design_outcome_categories dc
        JOIN ctgov.studies s ON s.nct_id = dc.nct_id
        WHERE dc.outcome_category IS NOT NULL {scope_where}
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
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            oc.outcome_category AS category,
            COUNT(DISTINCT oc.outcome_id) AS outcome_count,
            COUNT(DISTINCT oc.nct_id)     AS trial_count
        FROM public.drug_trial_outcome_categories oc
        JOIN ctgov.studies s ON s.nct_id = oc.nct_id
        WHERE oc.outcome_category IS NOT NULL {scope_where}
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
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            'Planned PROs'  AS stage,
            COUNT(DISTINCT p.nct_id) AS trial_count
        FROM public.drug_trial_design_outcomes_pro p
        JOIN ctgov.studies s ON s.nct_id = p.nct_id
        WHERE TRUE {scope_where}
        UNION ALL
        SELECT
            'Reported PROs' AS stage,
            COUNT(DISTINCT p.nct_id) AS trial_count
        FROM public.drug_trial_outcomes_pro p
        JOIN ctgov.studies s ON s.nct_id = p.nct_id
        WHERE TRUE {scope_where}
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


# ════════════════════════════════════════════════════════════════════════════
#  PRO OVERVIEW
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_pro_usage(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            p.instrument_name,
            COUNT(DISTINCT p.nct_id)  AS planned_count,
            0                         AS reported_count
        FROM public.drug_trial_design_outcomes_pro p
        JOIN ctgov.studies s ON s.nct_id = p.nct_id
        WHERE p.instrument_name IS NOT NULL {scope_where}
        GROUP BY 1
        UNION ALL
        SELECT
            r.instrument_name,
            0                         AS planned_count,
            COUNT(DISTINCT r.nct_id)  AS reported_count
        FROM public.drug_trial_outcomes_pro r
        JOIN ctgov.studies s ON s.nct_id = r.nct_id
        WHERE r.instrument_name IS NOT NULL {scope_where}
        GROUP BY 1
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pro_by_sponsor(filters: FilterState, limit: int = 15) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        WITH sponsor_totals AS (
            SELECT sp.name AS sponsor,
                   COUNT(DISTINCT p.nct_id) AS sponsor_total
            FROM public.drug_trial_design_outcomes_pro p
            JOIN ctgov.studies s ON s.nct_id = p.nct_id
            JOIN ctgov.sponsors sp ON sp.nct_id = s.nct_id
                   AND sp.lead_or_collaborator = 'lead'
            WHERE p.instrument_name IS NOT NULL {scope_where}
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
        WHERE p.instrument_name IS NOT NULL {scope_where}
        GROUP BY 1, 2, st.sponsor_total
        ORDER BY 4 DESC, 3 DESC LIMIT {limit * 5}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_pro_by_phase(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            COALESCE(s.phase,'N/A') AS phase,
            COUNT(DISTINCT p.nct_id) AS pro_trials
        FROM public.drug_trial_design_outcomes_pro p
        JOIN ctgov.studies s ON s.nct_id = p.nct_id
        WHERE TRUE {scope_where}
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
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            d.criteria         AS domain,
            d.instrument_name,
            COUNT(DISTINCT d.nct_id) AS trial_count,
            COUNT(DISTINCT d.brand_name) AS drug_count
        FROM public.domain_score_match d
        JOIN ctgov.studies s ON s.nct_id = d.nct_id
        WHERE d.criteria IS NOT NULL {scope_where}
        GROUP BY 1, 2
        ORDER BY 3 DESC
        LIMIT 200
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_domain_instrument_heatmap(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
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
        WHERE d.criteria IS NOT NULL {scope_where}
        GROUP BY 1, 2
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_domain_by_drug(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            d.brand_name,
            d.criteria   AS domain,
            COUNT(DISTINCT d.nct_id) AS trial_count
        FROM public.domain_score_match d
        JOIN ctgov.studies s ON s.nct_id = d.nct_id
        WHERE d.criteria IS NOT NULL
          AND d.brand_name IS NOT NULL {scope_where}
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
            rg.scope,
            rg.count,
            drg.brand_name,
            s.phase,
            s.overall_status
        FROM ctgov.result_groups rg
        JOIN ctgov.studies s ON s.nct_id = rg.nct_id
        LEFT JOIN public.drug_result_groups drg
               ON drg.nct_id = rg.nct_id
               AND drg.result_group_id::text = rg.result_group_id::text
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

@st.cache_data(ttl=300, show_spinner=False)
def get_adverse_event_summary(filters: FilterState) -> dict:
    """KPIs for the safety page."""
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""

    sql = f"""
        WITH ae_base AS (
            SELECT re.nct_id, re.adverse_event_term, re.organ_system,
                   re.subjects_affected, re.subjects_at_risk, re.event_count
            FROM ctgov.reported_events re
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
        JOIN ctgov.studies s ON s.nct_id = re.nct_id
        WHERE TRUE {scope_where}
    """
    df = query_aact(sql, params)
    row = df.iloc[0] if not df.empty else {}
    return {
        "trials_with_ae":        int(row.get("trials_with_ae",          0) or 0),
        "total_ae_records":      int(row.get("total_ae_records",         0) or 0),
        "unique_ae_terms":       int(row.get("unique_ae_terms",          0) or 0),
        "unique_organ_systems":  int(row.get("unique_organ_systems",     0) or 0),
        "total_subjects_affected": int(row.get("total_subjects_affected",0) or 0),
    }


@st.cache_data(ttl=300, show_spinner=False)
def get_top_adverse_events(filters: FilterState, limit: int = 25) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            re.adverse_event_term,
            re.organ_system,
            COUNT(DISTINCT re.nct_id)  AS trial_count,
            SUM(re.subjects_affected)  AS total_affected,
            SUM(re.event_count)        AS total_events
        FROM ctgov.reported_events re
        JOIN ctgov.studies s ON s.nct_id = re.nct_id
        WHERE re.subjects_affected > 0
          AND re.adverse_event_term IS NOT NULL
          {scope_where}
        GROUP BY 1, 2
        ORDER BY 3 DESC, 4 DESC
        LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_ae_by_organ_system(filters: FilterState) -> pd.DataFrame:
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            COALESCE(re.organ_system,'Unknown') AS organ_system,
            COUNT(DISTINCT re.nct_id)           AS trial_count,
            COUNT(DISTINCT re.adverse_event_term) AS unique_terms,
            SUM(re.subjects_affected)            AS total_affected
        FROM ctgov.reported_events re
        JOIN ctgov.studies s ON s.nct_id = re.nct_id
        WHERE re.subjects_affected > 0 {scope_where}
        GROUP BY 1 ORDER BY 2 DESC, 4 DESC
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_ae_by_drug(filters: FilterState, limit: int = 20) -> pd.DataFrame:
    """Adverse events per drug, using drug_result_groups to link drug → result group."""
    qb = QueryBuilder(filters)
    scope_clause, params = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    sql = f"""
        SELECT
            drg.brand_name,
            COUNT(DISTINCT re.nct_id)             AS trial_count,
            COUNT(DISTINCT re.adverse_event_term) AS unique_terms,
            SUM(re.subjects_affected)             AS total_affected
        FROM ctgov.reported_events re
        JOIN public.drug_result_groups drg
               ON drg.nct_id = re.nct_id
               AND drg.result_group_id::text = re.result_group_id::text
        JOIN ctgov.studies s ON s.nct_id = re.nct_id
        WHERE re.subjects_affected > 0
          AND drg.brand_name IS NOT NULL
          {scope_where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """
    return query_aact(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_ae_detail_table(filters: FilterState,
                         organ_system: str | None = None,
                         ae_term: str | None = None,
                         limit: int = MAX_TABLE_ROWS) -> pd.DataFrame:
    """Full adverse event detail table with drug linkage."""
    qb = QueryBuilder(filters)
    scope_clause, scope_p = qb.study_scope_clause("s")
    scope_where = f"AND {scope_clause}" if scope_clause else ""
    params = dict(scope_p)

    extra = ""
    if organ_system:
        extra += " AND re.organ_system = :organ_system"
        params["organ_system"] = organ_system
    if ae_term:
        extra += " AND re.adverse_event_term = :ae_term"
        params["ae_term"] = ae_term

    sql = f"""
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
        JOIN ctgov.studies s ON s.nct_id = re.nct_id
        LEFT JOIN public.drug_result_groups drg
               ON drg.nct_id = re.nct_id
               AND drg.result_group_id::text = re.result_group_id::text
        LEFT JOIN ctgov.sponsors sp
               ON sp.nct_id = s.nct_id AND sp.lead_or_collaborator = 'lead'
        WHERE re.subjects_affected > 0
          AND re.adverse_event_term IS NOT NULL
          {scope_where} {extra}
        ORDER BY re.subjects_affected DESC
        LIMIT {limit}
    """
    return query_aact(sql, params)


# ════════════════════════════════════════════════════════════════════════════
#  DRUGS DB  – indication / atc_class option queries
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def get_indication_options() -> list[str]:
    """
    Returns distinct MeSH mesh_term values (mesh-list type only) from
    ctgov.browse_conditions, scoped to trials present in public.drug_trials.
    These are the options for the global Indication filter.
    """
    from config.settings import (
        BROWSE_CONDITIONS_TABLE,
        BROWSE_CONDITIONS_MESH_TERM,
        BROWSE_CONDITIONS_MESH_TYPE,
        BROWSE_CONDITIONS_MESH_LIST,
    )
    sql = f"""
        SELECT DISTINCT bc.{BROWSE_CONDITIONS_MESH_TERM}
        FROM {BROWSE_CONDITIONS_TABLE} bc
        JOIN public.drug_trials dt ON dt.nct_id = bc.nct_id
        WHERE bc.{BROWSE_CONDITIONS_MESH_TYPE} = '{BROWSE_CONDITIONS_MESH_LIST}'
          AND bc.{BROWSE_CONDITIONS_MESH_TERM} IS NOT NULL
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
        BROWSE_CONDITIONS_TABLE, BROWSE_CONDITIONS_MESH_TERM,
        BROWSE_CONDITIONS_MESH_TYPE, BROWSE_CONDITIONS_MESH_LIST,
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
        # Step 2: intersect with browse_conditions scope in AACT
        ph = ", ".join(f":bn_{i}" for i in range(len(atc_brands)))
        params: dict = {f"bn_{i}": b for i, b in enumerate(atc_brands)}
        params["bc_ind"] = indication
        sql = f"""
            SELECT DISTINCT dt.brand_name
            FROM public.drug_trials dt
            JOIN {BROWSE_CONDITIONS_TABLE} bc ON bc.nct_id = dt.nct_id
            WHERE bc.{BROWSE_CONDITIONS_MESH_TYPE} = '{BROWSE_CONDITIONS_MESH_LIST}'
              AND bc.{BROWSE_CONDITIONS_MESH_TERM} = :bc_ind
              AND dt.brand_name IN ({ph})
              AND dt.brand_name IS NOT NULL
            ORDER BY 1 LIMIT 300
        """
        df = query_aact(sql, params)

    elif indication:
        # Scope via browse_conditions JOIN drug_trials in AACT
        sql = f"""
            SELECT DISTINCT dt.brand_name
            FROM public.drug_trials dt
            JOIN {BROWSE_CONDITIONS_TABLE} bc ON bc.nct_id = dt.nct_id
            WHERE bc.{BROWSE_CONDITIONS_MESH_TYPE} = '{BROWSE_CONDITIONS_MESH_LIST}'
              AND bc.{BROWSE_CONDITIONS_MESH_TERM} = :bc_ind
              AND dt.brand_name IS NOT NULL
            ORDER BY 1 LIMIT 300
        """
        df = query_aact(sql, {"bc_ind": indication})

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
