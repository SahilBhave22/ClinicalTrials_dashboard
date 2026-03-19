# Clinical Trials Intelligence Platform

A production-quality Streamlit application for pharmaceutical competitive intelligence, pipeline analysis, PRO analytics, and clinical safety benchmarking.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure secrets

The app reads credentials from `.streamlit/secrets.toml`. This file is already present in the project. It contains:

- `openai_api_key` — for Ask the Data NL queries
- `[gcp]` — Cloud SQL instance and service account
- `[db_creds]` — database user/password
- `[dbs]` — database names per key

### 3. Verify the Drugs DB table name

Open `config/settings.py` and confirm:

```python
DRUGS_LOOKUP_TABLE = "public.drugs"       # Adjust to your actual table
DRUGS_BRAND_COL      = "brand_name"
DRUGS_INDICATION_COL = "indication_name"
DRUGS_ATC_COL        = "atc_class_name"
```

This table must exist in the `drugs_db` database with at least those columns.

### 4. Run the app

```bash
streamlit run app.py
```

---

## Architecture

```
app.py                   ← Entry point; page router; sidebar filter injection
│
├── config/settings.py   ← App constants, DB keys, colour palettes
│
├── utils/
│   ├── db_conn.py       ← GCP Cloud SQL connector (existing)
│   ├── constants.py     ← Domain constants (phases, statuses, etc.)
│   ├── formatting.py    ← Number/date formatters
│   └── filters.py       ← FilterState dataclass + session_state helpers
│
├── data/
│   ├── db.py            ← Thin wrapper over db_conn; cached exec helpers
│   ├── query_builder.py ← Builds parameterised WHERE clauses from FilterState
│   └── repository.py    ← ALL SQL queries (no SQL elsewhere)
│
├── components/
│   ├── metric_cards.py  ← KPI card HTML components
│   ├── filters.py       ← Sidebar filter UI
│   ├── charts.py        ← Reusable Plotly chart builders
│   ├── tables.py        ← AG Grid + CSV download helpers
│   ├── page_header.py   ← Page header HTML
│   ├── alerts.py        ← Warning / info callouts
│   └── filter_summary.py← Active filter chip bar
│
├── services/
│   ├── analytics.py          ← Cross-page aggregation helpers
│   ├── outcome_analysis.py   ← Score comparability, box plot prep
│   ├── pro_analysis.py       ← PRO funnel, domain pivot
│   ├── safety_analysis.py    ← AE incidence, organ system aggregation
│   ├── pipeline_analysis.py  ← Pipeline diversity, sponsor-indication pivot
│   └── trial_design_analysis.py ← Allocation, model, purpose summaries
│
├── pages/               ← One module per page; each exports render(filters)
│   ├── home.py
│   ├── landscape.py
│   ├── pipeline_landscape.py
│   ├── drug_detail.py
│   ├── sponsor_benchmark.py
│   ├── trial_design.py
│   ├── planned_endpoints.py
│   ├── reported_outcomes.py
│   ├── outcome_scores.py
│   ├── pro_overview.py
│   ├── pro_domains.py
│   ├── trial_groups.py
│   ├── safety_analysis.py
│   └── ask_the_data.py
│
├── prompts/
│   └── nl_query_prompt.txt  ← System prompt for NL → SQL
│
├── catalogs/
│   ├── clinicaltrials_schema_catalog.json
│   └── drugs_schema_catalog.json
│
└── requirements.txt
```

---

## Global Filter System

### Two primary global filters (from Drugs DB)

| Filter | Column | Effect |
|---|---|---|
| **Indication (Disease Area)** | `indication_name` | Finds matching `brand_name`s in drugs_db, then scopes all AACT queries to matching `nct_id`s |
| **Drug Class (ATC)** | `atc_class_name` | Same process, independent of Indication |

### Independence

The two global filters are **independent** — each works alone, together, or not at all:

- Only indication → scope to drugs in that disease
- Only ATC class → scope to drugs in that class
- Both → intersection of the two
- Neither → full dataset

### Cascade logic

```
User selects indication / atc_class
        ↓
query_builder.resolve_brand_names(indication, atc_class)
  → SELECT DISTINCT brand_name FROM drugs_db WHERE ...
        ↓
query_builder.resolve_nct_ids(brand_names)
  → SELECT DISTINCT nct_id FROM public.drug_trials WHERE brand_name IN (...)
        ↓
All other queries use:
  nct_id IN (resolved_nct_ids)
  [as a subquery or direct IN clause]
        ↓
Downstream filters (sponsor, phase, status, country, etc.)
  are constrained to options available within the resolved nct_id set
```

### Filter persistence

`FilterState` is stored in `st.session_state["filter_state"]` and persists across all page navigations within a session.

---

## SQL Optimisation Approach

- **No `SELECT *`** — only explicitly named columns
- **Aggregation in SQL** — counts, medians, sums all computed in PostgreSQL
- **Filters pushed to SQL** — parameterised IN clauses via `query_builder.py`
- **CTEs** used for top-N pre-aggregation before joining to avoid cartesian products
- **Indexed columns** used for joins: `nct_id`, `outcome_id`, `result_group_id`, `brand_name`
- **`subjects_affected > 0`** enforced on all adverse event queries
- **`mesh_type = 'mesh-list'`** enforced on `browse_conditions`
- **`lead_or_collaborator = 'lead'`** for sponsor queries
- **LIMIT** enforced on all queries; MAX_TABLE_ROWS configurable in `config/settings.py`
- **Cross-database**: drugs_db queried first → brand_names passed as params to aact queries

---

## Pages

| Page | Key Insight |
|---|---|
| **Home** | Platform KPIs, trial trends, top sponsors/conditions |
| **Disease Landscape** | Competitive trial landscape for selected indication/class |
| **Pipeline Landscape** | Investigational asset landscape from `onco_pipeline_trials` |
| **Drug Detail** | Single-drug deep dive: trials, conditions, endpoints, PROs |
| **Sponsor Benchmark** | Cross-sponsor comparison: volume, phase, PRO adoption, endpoints |
| **Trial Design** | Allocation, intervention model, arms, eligibility patterns |
| **Planned Endpoints** | Protocol-level endpoint frequency and type analysis |
| **Reported Outcomes** | Posted result outcomes and endpoint category distribution |
| **Outcome Scores** | Numeric score box plots with comparability warnings |
| **PRO Overview** | Planned vs reported PRO funnel; instrument adoption |
| **PRO Domains** | Domain/subscale analysis from `domain_score_match` |
| **Trial Groups** | Design groups, result groups, arm counts |
| **Safety Analysis** | AE terms, organ systems, drug linkage via `drug_result_groups` |
| **Ask the Data** | Natural language → SQL via OpenAI GPT-4o |

---

## Ask the Data (NL Query)

- Uses OpenAI `gpt-4o` with a schema-aware system prompt
- System prompt located at `prompts/nl_query_prompt.txt`
- Safety checks enforced before execution:
  - SELECT / WITH only (no mutating statements)
  - LIMIT clause required
- Users can review and edit generated SQL before running
- Results downloadable as CSV
- Requires `openai_api_key` in `.streamlit/secrets.toml`

---

## Adverse Event Logic

Critical design decisions:
1. **Always filter `subjects_affected > 0`** — eliminates zero-count reporting noise
2. **Drug linkage via `public.drug_result_groups`** — joins AE result groups to specific drugs
3. **Never compare across incompatible trials** — interpretation warning displayed on page
4. **MedDRA coding** — uses `adverse_event_term` (not `event_type`) for specific AE terms

---

## Outcome Score Comparability

When displaying numeric outcome scores:
1. A **warning banner** is shown on the Outcome Scores page
2. If multiple units are detected, an additional warning flags which categories have mixed units
3. Users can filter by endpoint category to narrow to comparable results
4. Baseline timepoints (classification ∈ `baseline`, `cycle 1 day 1`, etc.) can be excluded

---

## Extending the Platform

- **New page**: Create `pages/mypage.py` with `def render(filters: FilterState)`, add route in `app.py`
- **New query**: Add function to `data/repository.py` following existing patterns
- **New filter**: Add field to `FilterState` in `utils/filters.py`, render in `components/filters.py`, handle in `data/query_builder.py`
- **New chart**: Add builder function to `components/charts.py`
