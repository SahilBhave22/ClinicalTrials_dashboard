"""
AI Summary service.
Builds structured context from page data and calls GPT-4o to generate
an analyst-style summary report.

Usage (from a view):
    from services.ai_summary import build_drug_detail_context, generate_summary
    context = build_drug_detail_context(kpis, brands_df, classes_df, phase_heat_df, trials_df, filters)
    markdown_text = generate_summary(context, page_name="Drug Detail")
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd

from utils.filters import FilterState

# Max rows serialised per table to keep token usage predictable
_TABLE_LIMIT = 25


# ── Context builders ──────────────────────────────────────────────────────────

def build_drug_detail_context(
    kpis: dict,
    brands_df: pd.DataFrame,
    classes_df: pd.DataFrame,
    phase_heat_df: pd.DataFrame,
    trials_df: pd.DataFrame,
    filters: FilterState,
) -> dict:
    """Serialise Drug Detail page data into a structured dict for the prompt."""
    return {
        "page": "Drug Detail",
        "filters": filters.active_filter_summary(),
        "kpis": {
            "Total Trials":        kpis.get("total_trials", 0),
            "Completed":           kpis.get("completed_trials", 0),
            "Trials with Results": kpis.get("trials_with_results", 0),
            "Unique Brand Names":  len(brands_df),
            "ATC Drug Classes":    len(classes_df),
        },
        "sections": {
            "Brand Names (Top 25 by Trial Count)":   _df_to_md(brands_df,  ["brand_name", "trial_count"], _TABLE_LIMIT),
            "ATC Drug Classes (Top 25 by Brand Count)": _df_to_md(classes_df, ["drug_class", "brand_count"], _TABLE_LIMIT),
            "Phase × Brand Distribution":            _summarise_heatmap(phase_heat_df),
            "Trial List Overview":                   _summarise_trials(trials_df),
        },
    }


def build_pipeline_context(
    kpis: dict,
    sp_df: pd.DataFrame,
    ind_df: pd.DataFrame,
    intv_df: pd.DataFrame,
    pro_df: pd.DataFrame,
    trials_df: pd.DataFrame,
    filters: FilterState,
) -> dict:
    """Serialise Pipeline Landscape page data into a structured dict for the prompt."""
    return {
        "page": "Pipeline Landscape",
        "filters": filters.active_filter_summary(),
        "kpis": {
            "Pipeline Trials":      kpis.get("pipeline_trials", 0),
            "Unique Assets":        kpis.get("unique_assets", 0),
            "Active Sponsors":      kpis.get("active_sponsors", 0),
            "Indications Covered":  kpis.get("indications_covered", 0),
            "With Planned PROs":    kpis.get("with_pros", 0),
        },
        "sections": {
            "Top Sponsors (by Pipeline Trials)": _df_to_md(sp_df,   ["sponsor", "pipeline_trials", "unique_assets"], _TABLE_LIMIT),
            "Top Indications":                   _df_to_md(ind_df,  ["condition", "trial_count"],                    _TABLE_LIMIT),
            "Top Interventions":                 _df_to_md(intv_df, ["intervention", "trial_count"],                 _TABLE_LIMIT),
            "PRO Instrument Usage":              _df_to_md(pro_df,  ["instrument_name", "trial_count"],              15),
            "Trial List Overview":               _summarise_trials(trials_df),
        },
    }


def build_pro_overview_context(
    kpis_dict: dict,
    top_df: pd.DataFrame,
    sp_df: pd.DataFrame,
    phase_df: pd.DataFrame,
    funnel_df: pd.DataFrame,
    pivot_df: pd.DataFrame,
    filters: FilterState,
) -> dict:
    """Serialise PRO Overview page data into a structured dict for the prompt."""
    # Deduplicate sponsor rows (sp_df has one row per sponsor×instrument)
    sp_agg = pd.DataFrame()
    if not sp_df.empty and "sponsor" in sp_df.columns and "sponsor_total" in sp_df.columns:
        sp_agg = (
            sp_df.drop_duplicates("sponsor")[["sponsor", "sponsor_total"]]
            .rename(columns={"sponsor_total": "trials_with_pro"})
            .sort_values("trials_with_pro", ascending=False)
        )

    return {
        "page": "PRO Overview",
        "filters": filters.active_filter_summary(),
        "kpis": {
            "Unique PRO Instruments":    kpis_dict.get("unique_instruments", 0),
            "Trials with Planned PRO":   kpis_dict.get("planned_pro_trials", 0),
            "Trials with Reported PRO":  kpis_dict.get("reported_pro_trials", 0),
        },
        "sections": {
            "Top PRO Instruments (by Total Usage)": _df_to_md(top_df,    ["instrument_name", "total"],         15),
            "PRO Adoption by Sponsor (Top 15)":     _df_to_md(sp_agg,    ["sponsor", "trials_with_pro"],       15),
            "PRO Trials by Phase":                  _df_to_md(phase_df,  ["phase", "pro_trials"],               20),
            "Planned → Reported PRO Funnel":        _df_to_md(funnel_df, ["stage", "trial_count"],              10),
        },
    }


# ── Core generation ───────────────────────────────────────────────────────────

def generate_summary(context_dict: dict, page_name: str = "Drug Detail") -> str | None:
    """
    Call GPT-4o with structured page context and return a markdown summary.
    Returns None (and shows st.error) if the API key is missing or the call fails.
    """
    try:
        import openai
        import streamlit as st

        api_key = st.secrets.get("openai_api_key", "")
        if not api_key:
            st.error("OpenAI API key not found. Add `openai_api_key` to `.streamlit/secrets.toml`.")
            return None

        system_prompt = (
            "You are a pharmaceutical intelligence analyst specialising in clinical trials data. "
            "You analyse clinical trial portfolio data and generate concise, insightful summaries "
            "for senior healthcare and pharma professionals. Write in clear, professional prose. "
            "Use markdown headers and bullet points. Be specific — cite numbers from the data provided."
        )

        user_prompt = _build_user_prompt(context_dict, page_name)

        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()

    except Exception as exc:
        import streamlit as st
        st.error(f"AI Summary failed: {exc}")
        return None


def filter_hash(filters: FilterState) -> str:
    """MD5 hash of the current FilterState — used to detect filter changes."""
    payload = json.dumps(filters.active_filter_summary(), sort_keys=True, default=str)
    return hashlib.md5(payload.encode()).hexdigest()


# ── Private helpers ───────────────────────────────────────────────────────────

def _build_user_prompt(ctx: dict, page_name: str) -> str:
    filters_block = (
        "\n".join(f"- {k}: {v}" for k, v in ctx["filters"].items())
        if ctx["filters"] else "- No filters applied (all data)"
    )

    kpis_block = "\n".join(
        f"- {k}: {v:,}" if isinstance(v, int) else f"- {k}: {v}"
        for k, v in ctx["kpis"].items()
    )

    sections_block = "\n\n".join(
        f"### {title}\n{content}"
        for title, content in ctx.get("sections", {}).items()
    )

    # Legacy Drug Detail context used flat keys instead of "sections"
    if not sections_block:
        legacy_keys = ["brand_names_table", "drug_classes_table", "phase_brand_summary", "trial_list_overview"]
        sections_block = "\n\n".join(
            f"### {k.replace('_', ' ').title()}\n{ctx[k]}"
            for k in legacy_keys if k in ctx
        )

    return f"""## Clinical Trials Portfolio — {page_name} Summary Request

### Active Filters
{filters_block}

### Portfolio KPIs
{kpis_block}

{sections_block}

---

Please produce a concise report with these exact sections (keep each section brief):
1. **Executive Summary** — 2–3 sentences with the headline story and key numbers
2. **Activity Analysis** — 3–4 bullets on the most active entities and what the counts suggest
3. **Phase / Stage Insights** — 2–3 bullets on what the phase or stage mix reveals
4. **Strategic Implications** — 2–3 bullets on what this data signals about development strategy
"""


def _df_to_md(df: pd.DataFrame, cols: list[str], limit: int) -> str:
    """Render a subset of DataFrame columns as a markdown table (up to `limit` rows)."""
    available_cols = [c for c in cols if c in df.columns]
    if df.empty or not available_cols:
        return "_No data available._"
    subset = df[available_cols].head(limit)
    header = " | ".join(available_cols)
    separator = " | ".join(["---"] * len(available_cols))
    rows = "\n".join(
        " | ".join(str(val) for val in row)
        for row in subset.itertuples(index=False)
    )
    return f"{header}\n{separator}\n{rows}"


def _summarise_heatmap(df: pd.DataFrame) -> str:
    """Produce a text summary of the phase × brand heatmap pivot DataFrame."""
    if df.empty:
        return "_No phase/brand data available._"

    lines: list[str] = []
    for phase in df.index:
        row = df.loc[phase]
        top = row[row > 0].sort_values(ascending=False).head(5)
        if top.empty:
            continue
        brands_str = ", ".join(f"{brand} ({int(cnt)})" for brand, cnt in top.items())
        lines.append(f"- {phase}: {brands_str}")

    return "\n".join(lines) if lines else "_No phase distribution data._"


def _summarise_trials(df: pd.DataFrame) -> str:
    """Summarise the trial list DataFrame as counts, not raw rows."""
    if df.empty:
        return "Total rows: 0"

    lines = [f"Total rows: {len(df):,}"]

    for col, label in [("overall_status", "Status"), ("phase", "Phase")]:
        if col in df.columns:
            counts = df[col].value_counts().head(8).to_dict()
            breakdown = ", ".join(f"{k}: {v}" for k, v in counts.items())
            lines.append(f"{label} breakdown: {breakdown}")

    return "\n".join(lines)
