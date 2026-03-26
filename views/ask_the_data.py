"""
ASK THE DATA page — AI-powered filter extraction.
User asks a natural language question → AI extracts filter values → all tabs filtered.
"""
from __future__ import annotations
import json
from pathlib import Path
import streamlit as st

from components.page_header import page_header
from components.filter_summary import filter_summary_bar
from utils.filters import FilterState, get_filters, set_filters

EXAMPLE_QUESTIONS = [
    "Phase 2 trials for NSCLC by AstraZeneca",
    "Completed breast cancer trials with posted results",
    "Recruiting AML trials from major pharma",
    "Merck's Phase 3 oncology pipeline",
    "DLBCL trials by BMS or Roche-Genentech",
    "Phase 1/2 TNBC immunotherapy trials",
    "Multiple myeloma trials with results posted",
    "Pfizer Phase 3 prostate cancer trials",
]

# Chip colours per dimension
_CHIP_COLORS = {
    "Condition":   "#0F4C81",
    "Drug Class":  "#1D3557",
    "Sponsor":     "#2E86AB",
    "Phase":       "#2A9D8F",
    "Status":      "#F18F01",
    "Country":     "#E76F51",
    "Agency Class": "#457B9D",
    "Has Results": "#6B7280",
}


# ── Catalog loaders ────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def _load_catalog() -> dict:
    """Load and parse condition_sponsor_values.json. Cached for 24 h."""
    path = Path("catalogs/condition_sponsor_values.json")
    data = json.loads(path.read_text("utf-8"))
    conditions   = [v.strip() for v in data["condition_values"].split("|")        if v.strip()]
    sponsors     = [v.strip() for v in data["sponsor_values"].split("|")          if v.strip()]
    drug_classes = [v.strip() for v in data.get("drug_class_values", "").split("|") if v.strip()]
    return {"conditions": conditions, "sponsors": sponsors, "drug_classes": drug_classes}


@st.cache_data(show_spinner=False)
def _load_static_catalog() -> dict:
    """Load filter_static_values.json (phases, statuses, countries, agency classes)."""
    path = Path("catalogs/filter_static_values.json")
    return json.loads(path.read_text("utf-8"))


# ── LLM filter extraction ──────────────────────────────────────────────────────

def _extract_filters(question: str, catalog: dict) -> dict | None:
    """
    Call GPT-4o with the full catalog lists and return structured filter values.
    The LLM resolves abbreviations and synonyms from the raw catalog text.
    """
    try:
        import openai

        api_key = st.secrets.get("openai_api_key", "")
        if not api_key:
            st.error("OpenAI API key not found in secrets.toml.")
            return None

        static = _load_static_catalog()
        phases         = static.get("phases", [])
        statuses       = static.get("overall_statuses", [])
        countries      = static.get("countries", [])
        agency_classes = static.get("agency_classes", [])
        drug_classes   = catalog.get("drug_classes", [])

        conditions_str   = " | ".join(catalog["conditions"])
        sponsors_str     = " | ".join(catalog["sponsors"])
        drug_classes_str = " | ".join(drug_classes)

        system_prompt = (
            "You are a filter extraction agent for a clinical trials analytics platform "
            "used by pharmaceutical industry professionals.\n\n"
            "Extract structured filter values from the user's question and match them "
            "EXACTLY to the values in the lists below. Resolve abbreviations, synonyms, "
            "and common brand/company short-forms yourself using the provided lists.\n\n"
            "=== CONDITION VALUES (MeSH terms — match indication here) ===\n"
            f"{conditions_str}\n\n"
            "=== SPONSOR VALUES (exact company names) ===\n"
            f"{sponsors_str}\n\n"
            "=== DRUG CLASS VALUES (ATC class — match atc_class here) ===\n"
            f"{drug_classes_str}\n\n"
            "=== PHASE VALUES (use only these exact strings) ===\n"
            f"{' | '.join(phases)}\n\n"
            "=== STATUS VALUES (use only these exact strings) ===\n"
            f"{' | '.join(statuses)}\n\n"
            "=== COUNTRY VALUES (use only these exact strings) ===\n"
            f"{' | '.join(countries)}\n\n"
            "=== AGENCY CLASS VALUES (use only these exact strings) ===\n"
            f"{' | '.join(agency_classes)}\n\n"
            "Return a JSON object with exactly these keys:\n"
            "{\n"
            '  "indication":     "<exact condition value from the list above, or null>",\n'
            '  "atc_class":      "<exact drug class value from the list above, or null>",\n'
            '  "sponsors":       ["<exact sponsor values from the list above>"],\n'
            '  "phases":         ["<exact phase values from the list above>"],\n'
            '  "statuses":       ["<exact status values from the list above>"],\n'
            '  "countries":      ["<exact country values from the list above>"],\n'
            '  "agency_class":   ["<exact agency class values from the list above>"],\n'
            '  "has_results":    null | true | false,\n'
            '  "interpretation": "<one sentence describing what was extracted>"\n'
            "}\n\n"
            "Rules:\n"
            "- Match indication, sponsors, atc_class to EXACT strings from the lists\n"
            "- Only include fields where the question clearly specifies a value\n"
            "- Use empty arrays [] and null for fields not mentioned\n"
            "- For phase ranges like 'Phase 1/2', include both phases in the array\n"
            "- 'with results' / 'has results' → has_results: true\n"
            "- 'no results' / 'without results' → has_results: false\n"
            "- atc_class: only set if user explicitly names a drug class or mechanism of action\n"
            "- agency_class: 'industry / pharma / biotech' → INDUSTRY; 'government / NIH / federal' → FED\n"
            "- countries: match to exact strings from the country list (e.g. 'in the US' → 'United States')\n"
        )

        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": question},
            ],
            temperature=0,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content.strip())

    except Exception as e:
        st.error(f"Error extracting filters: {e}")
        return None


# ── Indication resolver ───────────────────────────────────────────────────────

def _resolve_indication(raw: str) -> str | None:
    """
    Case-insensitive match of an AI-extracted indication against live DB values.
    Returns the exact DB string (correct casing) or None if no match is found.
    Uses the already-cached get_indication_options() — no extra DB cost.
    """
    from data.repository import get_indication_options
    db_values = get_indication_options()
    lookup = {v.lower(): v for v in db_values}
    return lookup.get(raw.lower())


# ── Filter application ─────────────────────────────────────────────────────────

def _apply_filters(extracted: dict) -> None:
    """
    Apply extracted filter values to FilterState and sync sidebar widget keys.
    Clears downstream widget session_state keys so the sidebar's default= logic
    re-reads from FilterState on the next rerun.
    """
    fs = get_filters()

    # 1. Apply indication (global filter) — resolve to exact DB casing first.
    #    Always initialise `resolved` so it is defined for the session_state
    #    assignment below, regardless of whether extraction succeeded.
    resolved = None
    if extracted.get("indication"):
        resolved = _resolve_indication(extracted["indication"])
        if resolved:
            fs.indication_name = resolved

    # 2. Sync global filter widget keys via direct assignment.
    #    Popping these keys is unreliable: Streamlit may fall back to the
    #    browser's cached frontend value rather than the `index` parameter,
    #    causing render_sidebar() to overwrite fs.indication_name back to None
    #    on the very next rerun.  Direct assignment is safe, is respected on
    #    the next render, and does NOT trigger the on_change callback.
    st.session_state["sb_indication"] = resolved or ""
    st.session_state["sb_atc"]        = extracted.get("atc_class") or ""

    # Pop downstream widget keys so sidebar re-reads from FilterState (default=)
    # on next rerun rather than returning stale session_state values.
    for key in ("ms_phase", "ms_status", "ms_sponsor", "ms_agency_class",
                "ms_brand", "ms_drug_ind", "ms_epcat", "ms_pro_inst",
                "ms_pro_dom", "ms_country", "ms_study_type"):
        st.session_state.pop(key, None)

    # 3. Reset FilterState downstream fields
    fs.sponsor              = []
    fs.phase                = []
    fs.overall_status       = []
    fs.country              = []
    fs.sponsor_agency_class = []
    fs.has_results          = None

    # 4. Load valid values from static catalog for validation
    static         = _load_static_catalog()
    valid_phases   = set(static.get("phases", []))
    valid_statuses = set(static.get("overall_statuses", []))
    valid_countries = set(static.get("countries", []))
    valid_agency   = set(static.get("agency_classes", []))
    valid_atc      = set(_load_catalog().get("drug_classes", []))

    # 5. Apply extracted values
    if extracted.get("sponsors"):
        fs.sponsor = extracted["sponsors"]
    if extracted.get("phases"):
        fs.phase = [p for p in extracted["phases"] if p in valid_phases]
    if extracted.get("statuses"):
        fs.overall_status = [s for s in extracted["statuses"] if s in valid_statuses]
    if extracted.get("countries"):
        fs.country = [c for c in extracted["countries"] if c in valid_countries]
    if extracted.get("agency_class"):
        fs.sponsor_agency_class = [a for a in extracted["agency_class"] if a in valid_agency]
    if extracted.get("atc_class") and extracted["atc_class"] in valid_atc:
        fs.atc_class_name = extracted["atc_class"]
    if extracted.get("has_results") is not None:
        fs.has_results = extracted["has_results"]
        st.session_state.pop("sel_results", None)  # let sidebar re-read from FilterState

    set_filters(fs)


# ── Page ──────────────────────────────────────────────────────────────────────

def render(filters: FilterState) -> None:
    page_header(
        title="AI Query",
        subtitle="Ask a question about the clinical trial landscape — filters are applied automatically across all tabs.",
        icon="🤖",
        breadcrumb="Home > AI Query",
    )
    filter_summary_bar(filters)

    catalog = _load_catalog()

    # ── Question input ─────────────────────────────────────────────────────────
    st.markdown(
        "<h3 style='color:#0F4C81;font-weight:700;margin:24px 0 8px 0;font-size:20px;'>"
        "What do you want to explore?</h3>",
        unsafe_allow_html=True,
    )

    col_q, col_btn = st.columns([5, 1])
    with col_q:
        question = st.text_input(
            "Question",
            placeholder="e.g. Phase 2 trials for NSCLC by AstraZeneca",
            label_visibility="collapsed",
            key="ai_question_input",
        )
    with col_btn:
        ask_btn = st.button("Ask ▶", key="ai_ask_btn", use_container_width=True, type="primary")

    # ── Example questions ──────────────────────────────────────────────────────
    st.markdown(
        "<p style='color:#6B7280;font-size:13px;font-weight:500;margin:12px 0 6px 0;'>"
        "Try asking:</p>",
        unsafe_allow_html=True,
    )
    ex_cols = st.columns(4)
    for i, ex in enumerate(EXAMPLE_QUESTIONS):
        with ex_cols[i % 4]:
            if st.button(ex, key=f"ai_ex_{i}", use_container_width=True):
                st.session_state["ai_pending_q"] = ex
                st.rerun()

    # Handle pending question from example buttons
    if "ai_pending_q" in st.session_state:
        question = st.session_state.pop("ai_pending_q")
        ask_btn = True

    # ── Process question ───────────────────────────────────────────────────────
    if ask_btn and question.strip():
        with st.spinner("Extracting filters from your question…"):
            extracted = _extract_filters(question.strip(), catalog)
        if extracted:
            st.session_state["ai_extracted"]     = extracted
            st.session_state["ai_question_text"] = question.strip()

    # ── Show extracted filters for review ─────────────────────────────────────
    if "ai_extracted" in st.session_state:
        extracted = st.session_state["ai_extracted"]
        q_text    = st.session_state.get("ai_question_text", "")

        st.markdown(
            "<hr style='margin:20px 0;border-color:#E5E7EB;'>",
            unsafe_allow_html=True,
        )

        # Interpretation card
        st.markdown(
            f"""
            <div style="background:white;border:1px solid #E5E7EB;border-radius:12px;
                        padding:20px 24px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
              <div style="font-size:12px;color:#6B7280;font-weight:600;
                          letter-spacing:0.06em;text-transform:uppercase;">
                🎯 Interpreted as
              </div>
              <div style="font-size:20px;font-weight:700;color:#0F4C81;margin-top:8px;line-height:1.3;">
                {extracted.get("interpretation", "—")}
              </div>
              <div style="font-size:12px;color:#6B7280;margin-top:6px;">
                From: <em>"{q_text}"</em>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Filter chips
        chip_items: list[tuple[str, str]] = []
        if extracted.get("indication"):
            chip_items.append(("Condition", extracted["indication"]))
        if extracted.get("atc_class"):
            chip_items.append(("Drug Class", extracted["atc_class"]))
        for sp in extracted.get("sponsors", []):
            chip_items.append(("Sponsor", sp))
        for ph in extracted.get("phases", []):
            chip_items.append(("Phase", ph))
        for st_ in extracted.get("statuses", []):
            chip_items.append(("Status", st_))
        for co in extracted.get("countries", []):
            chip_items.append(("Country", co))
        for ag in extracted.get("agency_class", []):
            chip_items.append(("Agency Class", ag))
        if extracted.get("has_results") is not None:
            chip_items.append(("Has Results", "Yes" if extracted["has_results"] else "No"))

        if chip_items:
            chips_html = "".join(
                f'<span style="display:inline-block;background:{_CHIP_COLORS.get(label,"#6B7280")};'
                f'color:white;padding:5px 14px;border-radius:20px;font-size:13px;'
                f'font-weight:500;margin:6px 6px 0 0;">'
                f'{label}: {value}</span>'
                for label, value in chip_items
            )
            st.markdown(
                f"<div style='margin:14px 0 8px 0;'>{chips_html}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.warning("No filter dimensions could be extracted from your question. Try rephrasing.")

        # Action buttons
        col_apply, col_clear, _ = st.columns([2, 2, 6])
        with col_apply:
            if st.button(
                "✅ Apply to Dashboard", key="ai_apply_btn",
                type="primary", use_container_width=True,
            ):
                _apply_filters(extracted)
                st.session_state.pop("ai_extracted",     None)
                st.session_state.pop("ai_question_text", None)
                st.session_state["ai_applied"] = True
                st.rerun()
        with col_clear:
            if st.button("🔄 Ask Again", key="ai_clear_btn", use_container_width=True):
                st.session_state.pop("ai_extracted",     None)
                st.session_state.pop("ai_question_text", None)
                st.rerun()

    # ── Post-apply confirmation ────────────────────────────────────────────────
    if st.session_state.pop("ai_applied", False):
        st.success(
            "✅ Filters applied! Switch to any other tab to explore the filtered data. "
            "You can also refine filters manually using the sidebar."
        )

    # ── How it works ───────────────────────────────────────────────────────────
    with st.expander("How does this work?"):
        st.markdown("""
**AI-Powered Filter Extraction**

1. Type a question in natural language about the clinical trial landscape
2. Our AI reads your question and extracts relevant filter values — indication, sponsor, phase, status, etc.
3. Values are matched to exact canonical terms used in the database
4. Click **Apply to Dashboard** to scope all tabs to your criteria
5. Refine further using the sidebar filters as usual

**Supported filter dimensions**

| Dimension | Examples |
|---|---|
| Indication / Disease | NSCLC, TNBC, AML, DLBCL, breast cancer, prostate cancer |
| Sponsor | AstraZeneca, BMS, Merck, Pfizer, Roche, Novartis, AZ, MSD |
| Phase | Phase 1, Phase 2, Phase 3, Phase 1/2, Phase 2/3 |
| Status | Recruiting, Completed, Terminated |
| Results | "with results", "posted results", "no results" |
| Country | "in the US", "Japan", "Europe" |

**Example questions**
- *"Phase 2 trials for NSCLC by AstraZeneca"*
- *"Completed breast cancer trials with posted results from Pfizer or Roche"*
- *"Recruiting DLBCL trials"*
- *"Merck's Phase 3 oncology pipeline"*
- *"AML trials with results posted"*
- *"Phase 1/2 TNBC immunotherapy trials"*
- *"CLL trials that are recruiting"*
- *"Novartis solid tumour pipeline — what's in Phase 3?"*
        """)
