"""
scripts/generate_snapshot_sql.py

Generates a complete SQL file to:
  1. Add a scope_key column to public.overview_kpis_snapshot (idempotent)
  2. Add a UNIQUE constraint on scope_key (idempotent)
  3. Upsert one snapshot row per unique access profile defined in config/user_access.py

Run from the project root:
    python scripts/generate_snapshot_sql.py

Output: scripts/snapshot_upsert.sql   (run this file on your database)

Does NOT connect to the database — safe to run anywhere.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path
from datetime import datetime, timezone

# Allow importing from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.user_access import USER_ACCESS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sql_str(value: str) -> str:
    """Escape a string literal for SQL (single-quote escaping)."""
    return "'" + value.replace("'", "''") + "'"


def _sql_list(values: list[str]) -> str:
    """Return a SQL IN-list literal: ('a', 'b', 'c')"""
    return "(" + ", ".join(_sql_str(v) for v in values) + ")"


def build_scope_key(disease_areas: list[str] | None, drug_classes: list[str] | None) -> str:
    """
    Deterministic string key for a given access profile.
    Same inputs always produce the same key, regardless of order.
    Returns 'global' for fully unrestricted profiles.
    """
    parts = []
    if disease_areas is not None:
        parts.append("ind:" + "|".join(sorted(disease_areas)))
    if drug_classes is not None:
        parts.append("atc:" + "|".join(sorted(drug_classes)))
    return "__".join(parts) if parts else "global"


def build_scope_subquery(disease_areas: list[str] | None, drug_classes: list[str] | None) -> str:
    """
    Build the SQL subquery that scopes studies to the given access profile.
    This mirrors what QueryBuilder.nct_subquery_clause() produces, but
    resolves ATC classes inline via a JOIN (no Python-side brand resolution needed).

    Returns a fragment:  s.nct_id IN ( ... )
    """
    # No restriction at all — scope to all drug_trials
    if disease_areas is None and drug_classes is None:
        return "s.nct_id IN (SELECT DISTINCT nct_id FROM public.drug_trials)"

    joins: list[str] = []
    wheres: list[str] = []

    # Indication restriction — JOIN browse_conditions
    if disease_areas is not None:
        joins.append(
            "JOIN ctgov.browse_conditions bc ON bc.nct_id = dt.nct_id"
        )
        wheres.append("bc.mesh_type = 'mesh-list'")
        wheres.append(f"bc.downcase_mesh_term IN {_sql_list(disease_areas)}")

    # ATC class restriction — JOIN drug_classes to resolve brands inline
    if drug_classes is not None:
        joins.append(
            "JOIN public.drug_classes dc ON dc.brand_name = dt.brand_name"
        )
        wheres.append(f"dc.atc_class_name IN {_sql_list(drug_classes)}")

    join_sql  = "\n        ".join(joins)
    where_sql = "WHERE " + "\n          AND ".join(wheres) if wheres else ""

    return f"""s.nct_id IN (
        SELECT DISTINCT dt.nct_id
        FROM public.drug_trials dt
        {join_sql}
        {where_sql}
    )"""


def build_upsert_block(scope_key: str, scope_subquery: str) -> str:
    """
    Generate the full INSERT ... ON CONFLICT DO UPDATE block for one scope.
    All KPI sub-selects are CTEs so the scope subquery is computed once.
    """
    sk = _sql_str(scope_key)
    now = _sql_str(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00"))

    return f"""\
-- ── Scope: {scope_key} ────────────────────────────────────────────────────────
INSERT INTO public.overview_kpis_snapshot (
    scope_key,
    total_trials,
    active_trials,
    completed_trials,
    trials_with_results,
    median_enrollment,
    unique_sponsors,
    unique_drugs,
    unique_conditions,
    trials_with_pros,
    refreshed_at
)
WITH scoped AS (
    SELECT s.nct_id,
           s.overall_status,
           s.enrollment,
           s.results_first_submitted_date
    FROM ctgov.studies s
    WHERE {scope_subquery}
),
kpi_main AS (
    SELECT
        COUNT(DISTINCT nct_id)                                                         AS total_trials,
        COUNT(DISTINCT CASE WHEN overall_status IN
            ('RECRUITING', 'ACTIVE_NOT_RECRUITING') THEN nct_id END)                   AS active_trials,
        COUNT(DISTINCT CASE WHEN overall_status = 'COMPLETED' THEN nct_id END)         AS completed_trials,
        COUNT(DISTINCT CASE WHEN results_first_submitted_date IS NOT NULL
            THEN nct_id END)                                                           AS trials_with_results,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY enrollment)                        AS median_enrollment
    FROM scoped
),
kpi_sponsors AS (
    SELECT COUNT(DISTINCT sp.name) AS unique_sponsors
    FROM ctgov.sponsors sp
    WHERE sp.nct_id IN (SELECT nct_id FROM scoped)
      AND sp.lead_or_collaborator = 'lead'
),
kpi_drugs AS (
    SELECT COUNT(DISTINCT dt.brand_name) AS unique_drugs
    FROM public.drug_trials dt
    WHERE dt.nct_id IN (SELECT nct_id FROM scoped)
),
kpi_conditions AS (
    SELECT COUNT(DISTINCT bc.downcase_mesh_term) AS unique_conditions
    FROM ctgov.browse_conditions bc
    WHERE bc.nct_id IN (SELECT nct_id FROM scoped)
      AND bc.mesh_type = 'mesh-list'
),
kpi_pros AS (
    SELECT COUNT(DISTINCT p.nct_id) AS trials_with_pros
    FROM public.drug_trial_design_outcomes_pro p
    WHERE p.nct_id IN (SELECT nct_id FROM scoped)
)
SELECT
    {sk},
    kpi_main.total_trials,
    kpi_main.active_trials,
    kpi_main.completed_trials,
    kpi_main.trials_with_results,
    kpi_main.median_enrollment,
    kpi_sponsors.unique_sponsors,
    kpi_drugs.unique_drugs,
    kpi_conditions.unique_conditions,
    kpi_pros.trials_with_pros,
    {now}::timestamptz
FROM kpi_main, kpi_sponsors, kpi_drugs, kpi_conditions, kpi_pros
ON CONFLICT (scope_key) DO UPDATE SET
    total_trials        = EXCLUDED.total_trials,
    active_trials       = EXCLUDED.active_trials,
    completed_trials    = EXCLUDED.completed_trials,
    trials_with_results = EXCLUDED.trials_with_results,
    median_enrollment   = EXCLUDED.median_enrollment,
    unique_sponsors     = EXCLUDED.unique_sponsors,
    unique_drugs        = EXCLUDED.unique_drugs,
    unique_conditions   = EXCLUDED.unique_conditions,
    trials_with_pros    = EXCLUDED.trials_with_pros,
    refreshed_at        = EXCLUDED.refreshed_at;
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def generate() -> str:
    lines: list[str] = []

    lines.append(f"""\
-- =============================================================================
-- overview_kpis_snapshot — scoped snapshot upserts
-- Generated by scripts/generate_snapshot_sql.py on {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
--
-- HOW TO USE:
--   1. Run the SCHEMA section once (adds scope_key column + unique constraint).
--   2. Run the UPSERT section whenever user access profiles change.
--      Each statement is idempotent — safe to re-run.
-- =============================================================================

-- ── SCHEMA (run once) ────────────────────────────────────────────────────────

ALTER TABLE public.overview_kpis_snapshot
    ADD COLUMN IF NOT EXISTS scope_key TEXT NOT NULL DEFAULT 'global';

-- Back-fill existing rows as 'global' (if any were inserted before this migration)
UPDATE public.overview_kpis_snapshot
SET scope_key = 'global'
WHERE scope_key IS NULL OR scope_key = '';

ALTER TABLE public.overview_kpis_snapshot
    DROP CONSTRAINT IF EXISTS overview_kpis_snapshot_scope_key_key;

ALTER TABLE public.overview_kpis_snapshot
    ADD CONSTRAINT overview_kpis_snapshot_scope_key_key UNIQUE (scope_key);

-- ── UPSERTS (re-run whenever access profiles change) ─────────────────────────
""")

    # Collect unique profiles — deduplicate by scope_key so users with identical
    # access don't generate duplicate SQL blocks.
    seen: dict[str, tuple] = {}   # scope_key → (disease_areas, drug_classes)

    for username, cfg in USER_ACCESS.items():
        disease_areas = cfg.get("disease_areas")   # None or list
        drug_classes  = cfg.get("drug_classes")    # None or list
        key = build_scope_key(disease_areas, drug_classes)
        if key not in seen:
            seen[key] = (disease_areas, drug_classes)

    # Always include global
    if "global" not in seen:
        seen["global"] = (None, None)

    # Sort so global comes first, then alphabetically
    ordered = sorted(seen.items(), key=lambda kv: (kv[0] != "global", kv[0]))

    users_per_scope: dict[str, list[str]] = {}
    for username, cfg in USER_ACCESS.items():
        key = build_scope_key(cfg.get("disease_areas"), cfg.get("drug_classes"))
        users_per_scope.setdefault(key, []).append(username)

    for scope_key, (disease_areas, drug_classes) in ordered:
        users = users_per_scope.get(scope_key, [])
        if users:
            lines.append(f"-- Users with this scope: {', '.join(sorted(users))}\n")
        subquery = build_scope_subquery(disease_areas, drug_classes)
        lines.append(build_upsert_block(scope_key, subquery))

    lines.append("-- End of generated SQL\n")
    return "\n".join(lines)


if __name__ == "__main__":
    output_path = Path(__file__).parent / "snapshot_upsert.sql"
    sql = generate()
    output_path.write_text(sql, encoding="utf-8")
    print(f"Written to: {output_path}")
    print()
    print("Scopes generated:")
    seen: dict[str, list[str]] = {}
    for username, cfg in USER_ACCESS.items():
        key = build_scope_key(cfg.get("disease_areas"), cfg.get("drug_classes"))
        seen.setdefault(key, []).append(username)
    for key, users in sorted(seen.items()):
        print(f"  {key:<60}  (users: {', '.join(sorted(users))})")
