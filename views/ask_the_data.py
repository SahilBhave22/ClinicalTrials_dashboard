"""
ASK THE DATA page.
Natural language → SQL query interface using OpenAI.
"""
from __future__ import annotations
import json
from pathlib import Path
import streamlit as st

from components.page_header import page_header
from components.filter_summary import filter_summary_bar
from components.alerts import warning_callout, danger_callout
from components.tables import ag_table, csv_download_button
from utils.filters import FilterState
from data.repository import run_nl_query


# ── Schema context loader ─────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def _load_schema_context() -> str:
    ct_path = Path("catalogs/clinicaltrials_schema_catalog.json")
    dr_path = Path("catalogs/drugs_schema_catalog.json")
    parts: list[str] = []
    try:
        ct = json.loads(ct_path.read_text("utf-8"))
        tables_desc = []
        for t in ct.get("tables", []):
            cols = ", ".join(
                f"{c['name']} ({c['type']})"
                for c in t.get("columns", [])
            )
            tables_desc.append(f"  TABLE {t['name']}: {cols}")
        parts.append("=== CLINICAL TRIALS SCHEMA (AACT DB) ===\n" + "\n".join(tables_desc))
    except Exception:
        pass
    try:
        dr = json.loads(dr_path.read_text("utf-8"))
        parts.append(
            "\n=== DRUGS DB VALUES ===\n"
            f"drug_class_values (atc_class_name): {dr.get('drug_class_values','')[:500]}\n"
            f"drug_indication_values (indication_name): {dr.get('drug_indication_values','')[:500]}"
        )
    except Exception:
        pass
    return "\n\n".join(parts)


def _load_prompt_template() -> str:
    try:
        return Path("prompts/nl_query_prompt.txt").read_text("utf-8")
    except Exception:
        return ""


# ── SQL safety check ─────────────────────────────────────────────────────────

def _is_safe_sql(sql: str) -> tuple[bool, str]:
    """Block mutating statements and enforce LIMIT."""
    upper = sql.upper().strip()
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
                 "ALTER", "CREATE", "GRANT", "REVOKE", "COPY"]
    for kw in forbidden:
        if kw in upper:
            return False, f"Statement contains forbidden keyword: {kw}"
    if not upper.startswith("SELECT") and not upper.startswith("WITH"):
        return False, "Only SELECT / WITH queries are allowed."
    if "LIMIT" not in upper:
        return False, "Query must include a LIMIT clause."
    return True, ""


# ── OpenAI call ───────────────────────────────────────────────────────────────

def _generate_sql(user_question: str, schema_ctx: str, filter_context: str) -> str:
    """Call OpenAI to generate a SQL query from the user question."""
    try:
        import openai
        api_key = st.secrets.get("openai_api_key", "")
        if not api_key:
            return "-- ERROR: OpenAI API key not found in secrets.toml"

        prompt_template = _load_prompt_template()
        system_prompt = prompt_template or (
            "You are an expert SQL analyst for a clinical trials analytics platform. "
            "Generate optimised PostgreSQL queries using ONLY the schema provided. "
            "Rules:\n"
            "- SELECT only\n"
            "- Always include LIMIT (max 200)\n"
            "- Use schema-qualified table names\n"
            "- No SELECT *\n"
            "- Push filters to SQL\n"
            "- subjects_affected > 0 for adverse events\n"
            "- mesh_type = 'mesh-list' for browse_conditions\n"
            "Return ONLY the SQL, no explanation.\n\n"
            f"{schema_ctx}\n\n"
            f"Active filter context:\n{filter_context}"
        )

        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_question},
            ],
            temperature=0,
            max_tokens=600,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"-- ERROR generating SQL: {e}"


# ── Page ─────────────────────────────────────────────────────────────────────

def render(filters: FilterState) -> None:
    page_header(
        title="Ask the Data",
        subtitle="Natural language query interface — describe what you want to know and we'll generate optimised SQL.",
        icon="💬",
        breadcrumb="Home > Ask the Data",
    )
    filter_summary_bar(filters)

    warning_callout(
        "All generated SQL is read-only (SELECT only) and has a LIMIT enforced. "
        "Always review the query before running it.",
        title="Safety Notice",
    )

    # ── Instructions ──────────────────────────────────────────────────────────
    with st.expander("How to use"):
        st.markdown("""
**How it works:**
1. Type your question in natural language
2. The system generates an optimised PostgreSQL query
3. Review the generated SQL and explanation
4. Click **Run Query** to execute it
5. Download results as CSV

**Example questions:**
- "Show me the top 10 sponsors by number of Phase 3 trials in non-small cell lung cancer"
- "What are the most common adverse events for pembrolizumab?"
- "How many trials report EQ-5D as a PRO instrument by year?"
- "List drugs with both Phase 2 and Phase 3 trials that have posted results"

**Data scope:** Results respect the active global filters (indication / drug class).
        """)

    # ── Input ─────────────────────────────────────────────────────────────────
    schema_ctx = _load_schema_context()

    question = st.text_area(
        "Your question:",
        placeholder="e.g. What are the top 15 adverse events by subjects affected in completed trials?",
        height=100,
        key="nl_question",
    )

    if st.button("🔍 Generate SQL", key="btn_gen_sql", use_container_width=False):
        if not question.strip():
            st.warning("Please enter a question.")
            return

        # Build filter context description for the prompt
        active = filters.active_filter_summary()
        filter_context = (
            "Active filters: " + "; ".join(f"{k}={v}" for k, v in active.items())
            if active else "No filters active (full dataset)."
        )

        with st.spinner("Generating SQL…"):
            generated_sql = _generate_sql(question, schema_ctx, filter_context)

        st.session_state["atd_sql"]      = generated_sql
        st.session_state["atd_question"] = question
        st.session_state["atd_results"]  = None

    # ── Display / edit generated SQL ──────────────────────────────────────────
    if "atd_sql" in st.session_state and st.session_state["atd_sql"]:
        st.markdown("#### Generated SQL")
        st.caption(f"Question: *{st.session_state.get('atd_question', '')}*")

        edited_sql = st.text_area(
            "Review and edit SQL before running:",
            value=st.session_state["atd_sql"],
            height=220,
            key="atd_editable_sql",
        )

        # Safety check
        is_safe, reason = _is_safe_sql(edited_sql)
        if not is_safe:
            danger_callout(f"Query blocked: {reason}", title="Query Blocked")
        else:
            col1, col2 = st.columns([1, 4])
            with col1:
                run_btn = st.button("▶ Run Query", key="btn_run_sql", use_container_width=True)
            with col2:
                st.caption("✅ Query passed safety checks (SELECT only, LIMIT present)")

            if run_btn:
                with st.spinner("Running query…"):
                    try:
                        result_df = run_nl_query(edited_sql)
                        st.session_state["atd_results"] = result_df
                    except Exception as e:
                        st.error(f"Query failed: {e}")
                        st.session_state["atd_results"] = None

    # ── Results ───────────────────────────────────────────────────────────────
    if st.session_state.get("atd_results") is not None:
        result_df = st.session_state["atd_results"]
        if result_df.empty:
            st.info("Query returned no rows.")
        else:
            st.markdown(f"#### Results — {len(result_df):,} rows")
            ag_table(result_df, height=460, key="atd_results_table")
            csv_download_button(result_df, "nl_query_results.csv")
