# Migration Prompt: Clinical Trials Intelligence Platform

Use this prompt for the coding agent that will rebuild this dashboard in a new directory on a `Next.js + TypeScript + FastAPI` stack.

This prompt is based on the current source code in this repository as of `2026-04-23`. Treat the code as the source of truth. Do not trust old docs blindly.

## Before You Start

You are migrating an existing Streamlit dashboard to:

- `frontend`: Next.js App Router + TypeScript
- `backend`: FastAPI + Python
- database access: the same PostgreSQL / Cloud SQL databases and the same SQL logic

Non-negotiable requirements:

- Keep the UI, pages, data, page order, filter behavior, empty states, warnings, and visible UX flow identical to the current dashboard.
- Make no assumptions beyond what is in the current code.
- Do not “improve” semantics unless explicitly called out below as safe backend adaptation.
- Preserve current quirks if they are present in the code.
- Preserve page labels used by access control exactly.

Important current-code facts you must honor:

- The current app is a single Streamlit app with top-level tabs, not separate pages.
- The visible top tab order comes from `app.py -> PAGE_MAP`.
- Per-user permissions depend on the exact tab labels in `config/user_access.py`.
- The page header always shows the logo image, not the emoji icon string, because `components/page_header.py` ignores the passed emoji and renders the logo whenever `icon` is truthy.
- Some repo functions and files are present but unused by the current visible UI. Do not surface them unless asked.
- `README.md` and the old `MIGRATION_PROMPT.md` were stale in places. Follow the code.
- There is at least one current-code inconsistency in the AI-summary helpers for Drug Pricing: `build_drug_pricing_context()` expects fields that do not perfectly match the pricing query outputs. If you hit that during migration, make the smallest possible fix needed to keep the visible feature working, and document it rather than redesigning the page.

## Replication Matrix

Replicate these files into the new project in one of three ways.

### 1. Copy As Reference Or Reuse With Little/No Change

Copy these into the new project so the agent has exact reference material and assets:

- `assets/logos/APP_logo1.png`
- `catalogs/condition_sponsor_values.json`
- `catalogs/filter_static_values.json`
- `catalogs/clinicaltrials_schema_catalog.json`
- `catalogs/drugs_schema_catalog.json`
- `catalogs/pricing_schema_catalog.json`
- `catalogs/marketaccess_schema_catalog.json`
- `prompts/nl_query_prompt.txt`
- `scripts/generate_snapshot_sql.py`
- `scripts/snapshot_upsert.sql`
- `config/user_access.py`
- `utils/constants.py`
- `utils/formatting.py`
- `services/analytics.py`
- `services/pipeline_analysis.py`
- `services/pro_analysis.py`
- `services/safety_analysis.py`
- `services/trial_design_analysis.py`
- `services/outcome_analysis.py`

### 2. Copy Then Refactor For Backend Use

These are the important Python business-logic files, but they currently depend on Streamlit. Copy them into the new backend and refactor them for FastAPI:

- `config/settings.py`
- `utils/db_conn.py`
- `data/db.py`
- `utils/filters.py`
- `data/query_builder.py`
- `data/repository.py`
- `utils/auth.py`
- `services/ai_summary.py`
- `utils/preloader.py`

Backend adaptation rules:

- Remove `streamlit` as a runtime dependency of the new backend.
- Replace `st.cache_data` with backend-side caching.
- Replace `st.secrets` with env-based settings.
- Replace `st.error` with exceptions or structured error responses.
- Replace `st.session_state` usage with request-scoped auth/session handling or frontend state.

### 3. Rebuild In TypeScript / React, Do Not Copy As Runtime Code

These files are Streamlit UI implementations and should be ported, not reused directly:

- `app.py`
- `components/filters.py`
- `components/filter_summary.py`
- `components/metric_cards.py`
- `components/page_header.py`
- `components/alerts.py`
- `components/charts.py`
- `components/chart_tile.py`
- `components/tables.py`
- every file in `views/`

### 4. Reference Only, Do Not Treat As Runtime Requirements

- `README.md`
- `CLAUDE.md`
- this `MIGRATION_PROMPT.md`

## Current App Inventory

### Top-Level App Shell

The current app entrypoint is `app.py`.

It does all of the following:

- loads the logo from `assets/logos/APP_logo1.png`
- sets Streamlit page config
- injects a very large global CSS block
- starts background preload with `utils.preloader.start_background_preload()`
- enforces login with `utils.auth.render_login_form()`
- renders the sidebar user badge
- renders the sidebar filters
- resolves visible tabs from `utils.auth.get_allowed_tabs()`
- renders one Streamlit tab per visible page

### Exact Top-Level Tab Order And Labels

Preserve this exact order and exact labels for permission logic:

1. `🏠 Home`
2. `💬 Ask the Data`
3. `📈 Pipeline`
4. `💊 Drug Detail`
5. `💰 Drug Pricing`
6. `🏥 Market Access`
7. `🏢 Sponsors`
8. `📋 Trial Design`
9. `🎯 Endpoints`
10. `📊 Outcomes`
11. `🔢 Scores`
12. `👤 PRO Overview`
13. `🗂️ Trial Groups`
14. `🛡️ Safety`

Mapped modules:

- `views.home`
- `views.ask_the_data`
- `views.pipeline_landscape`
- `views.drug_detail`
- `views.drug_pricing`
- `views.market_access`
- `views.sponsor_benchmark`
- `views.trial_design`
- `views.planned_endpoints`
- `views.reported_outcomes`
- `views.outcome_scores`
- `views.pro_overview`
- `views.trial_groups`
- `views.safety_analysis`

### Important Stale/Quirky App Facts To Preserve

- The Home page bottom “Explore Platform Modules” cards come from `config.settings.PAGES`, not `PAGE_MAP`.
- Because `config.settings.PAGES` is stale, the Home page cards omit `Drug Pricing` and `Market Access` even though those top-level tabs exist.
- Keep that behavior unless the user explicitly asks to fix it.
- The Home page cards are display-only in the current app. They are not clickable. Do not add click-through behavior unless asked.
- `Outcome Scores` is currently a WIP placeholder page, even though there are repository functions for outcome score analysis.
- `PRO Domain` exists in filter state and sidebar, but there is no visible top-level page using the PRO domain analytics functions.
- The sidebar does not currently render enrollment filters, `outcome_type`, `ae_organ_system`, or `ae_term`, even though those fields exist in `FilterState`.
- Safety local AE filters are page-local text inputs, not global sidebar filters.

## Current Data Sources

### DB Keys Defined In Code

From `utils/db_conn.py` and `config/settings.py`:

- `aact`
- `fdaers`
- `pricing`
- `drugs`
- `marketaccess`

Important:

- `fdaers` is configured but not used by the current visible app.
- Do not invent FDAERS features.

### Databases Actually Used By The Visible UI

- `aact`
  - `ctgov.*` tables
  - `public.drug_trials`
  - `public.drug_trial_outcome_categories`
  - `public.drug_trial_design_outcome_categories`
  - `public.drug_trial_design_outcomes_pro`
  - `public.drug_trial_outcomes_pro`
  - `public.domain_score_match`
  - `public.drug_result_groups`
  - `public.onco_pipeline_trials`
  - `public.onco_pipeline_design_outcomes_pro`
  - `public.overview_kpis_snapshot`
- `drugs`
  - `public.drugs`
  - `public.drug_indications`
  - `public.drug_classes`
- `pricing`
  - `annual_pricing_table`
  - `historical_pricing`
- `marketaccess`
  - `mapped_access_2025`
  - `mapped_access_2026`

### Secrets Currently Read From Streamlit

The current app expects:

- `openai_api_key`
- `gcp.instance_connection_name`
- `gcp.service_account`
- `db_creds.db_user`
- `db_creds.db_pass`
- `dbs.db_name_aact`
- `dbs.db_name_fdaers`
- `dbs.db_name_pricing`
- `dbs.db_name_drugs`
- `dbs.db_name_marketaccess`
- `users.<username>.password`

In the new backend, move these to environment variables or a backend settings file.

## Current Auth And Access Rules

Auth logic comes from `utils/auth.py` and `config/user_access.py`.

Current behavior:

- Login uses username/password from secrets.
- A successful login is blocked if the username is missing from `USER_ACCESS`.
- Unknown users should not get full access.
- `get_allowed_tabs()`:
  - if `tabs is None`, user gets all tabs
  - if username unknown, safe fallback is Home only
- `USER_ACCESS` controls:
  - `display_name`
  - `tabs`
  - `disease_areas`
  - `drug_classes`

Important parity rules:

- Keep exact tab-label-based authorization.
- Keep per-user data restriction enforcement separate from UI-only filtering.
- Preserve the safe fallback behavior for unknown users.

## Filter System: Exact Current Semantics

### Source Files

The filter system is spread across:

- `utils/filters.py`
- `components/filters.py`
- `data/query_builder.py`
- `data/repository.py`
- `views/ask_the_data.py`

### FilterState Fields

Preserve these fields in the backend DTO and frontend store:

- `indication_name`
- `atc_class_name`
- `sponsor`
- `sponsor_agency_class`
- `brand_name`
- `drug_indication`
- `study_type`
- `phase`
- `overall_status`
- `country`
- `endpoint_category`
- `outcome_type`
- `pro_instrument`
- `pro_domain`
- `ae_organ_system`
- `ae_term`
- `has_results`
- `enrollment_min`
- `enrollment_max`
- `allowed_indications`
- `allowed_atc_classes`
- `_resolved_brand_names`

### Visible Sidebar Fields

Only these are actually visible in the current sidebar:

- `indication_name`
- `atc_class_name`
- `study_type`
- `phase`
- `overall_status`
- `has_results`
- `sponsor`
- `sponsor_agency_class`
- `brand_name`
- `drug_indication`
- `endpoint_category`
- `pro_instrument`
- `pro_domain`
- `country`

Do not add visible sidebar controls for:

- `outcome_type`
- `ae_organ_system`
- `ae_term`
- `enrollment_min`
- `enrollment_max`

### Global Filters

The two global filters are:

- `indication_name`
- `atc_class_name`

These are independent.

Critical exact semantics from `data/query_builder.py`:

- `indication_name` is not a drug-indication filter.
- `indication_name` is a `ctgov.browse_conditions.downcase_mesh_term` filter.
- It always uses `mesh_type = 'mesh-list'`.
- `atc_class_name` resolves brand names from `public.drug_classes`.
- Global scope ultimately resolves to `public.drug_trials` nct_ids.
- Even with no explicit filters, study scope defaults to trials present in `public.drug_trials`, not all ctgov studies.

### Per-User Restrictions

Per-user restrictions must always be enforced in queries:

- `allowed_indications`
- `allowed_atc_classes`

Exact parity rules:

- restricted indication users only see allowed indication options
- restricted ATC users only see allowed ATC options
- query builder enforces these restrictions even if the frontend sends broader filters
- if `allowed_atc_classes` resolves to zero allowed brands, the result is an empty set
- if a selected ATC class resolves to zero brands, the result is an empty set

### Downstream Filter Option Loading

This is important and subtle.

Current behavior from `components/filters.py`:

- if no global filter is active, downstream options come from static JSON catalogs
- if a global filter is active, downstream options come from `data.repository.get_filter_options(indication, atc_class)`
- `get_filter_options()` is constrained only by the active global filters
- downstream options are not narrowed by other downstream selections

Preserve that exact behavior.

### Filter Reset Behavior

When either global filter changes:

- clear all downstream filters
- clear relevant widget state
- preserve user access restrictions

When “Reset All Filters” is used:

- clear both global filters
- clear all downstream filters
- preserve per-user restrictions

### Filter Summary Bar

Top-of-page filter chip bar comes from `components/filter_summary.py`.

It shows only:

- indication
- drug class
- sponsor
- agency class
- drug
- drug indication
- study type
- phase
- status
- country
- endpoint category
- PRO instrument
- PRO domain
- has results
- enrollment

It does not show local Safety filters.

Preserve:

- empty state “No filters active”
- active chip count badge
- global filter chip styling distinct from downstream chip styling

## Design System To Preserve

### Core Visual Tokens

From `config/settings.py` and `app.py`:

- background: `#F8FAFC`
- primary: `#0F4C81`
- secondary: `#2E86AB`
- accent: `#F18F01`
- success: `#2A9D8F`
- warning: `#E9C46A`
- danger: `#E76F51`
- text primary: `#1A1A2E`
- text secondary: `#6B7280`
- sidebar top: `#0B1929`
- font: `DM Sans`

### Global Layout Rules

Reproduce the current look:

- full-width app layout
- sidebar expanded by default
- sidebar dark blue vertical gradient
- white cards with subtle border/shadow
- rounded tab navigation pills
- wide content area with compact column gaps
- hidden Streamlit chrome translated into a clean app shell

### KPI Cards

From `components/metric_cards.py`:

- white card
- left border accent
- height-aligned row
- top-right icon badge
- uppercase gray label
- large navy value
- optional delta

### Chart Defaults

From `components/charts.py`:

- transparent plot/paper background inside white card
- DM Sans font
- hover labels on white
- x-axis line `#E5E7EB`
- y-axis grid `#F3F4F6`
- shared categorical palette
- truncated long category tick labels

### Tables

From `components/tables.py`:

- AG Grid when available
- sortable
- filterable
- paginated
- 25 rows per page
- sidebar filters panel enabled
- columns panel disabled
- single row selection without checkboxes
- CSV download button under tables

### Alerts / Callouts

From `components/alerts.py`:

- `filter_required_callout`
- `no_data_callout`
- pipeline info note
- safety interpretation warning
- score comparability warning

Preserve the current text and usage locations.

## Backend Migration Instructions

## Step 1: Build A Streamlit-Free Backend Core

Create a backend package structure that separates:

- settings/env loading
- auth/session/JWT
- DB engine and query execution
- caching
- repositories
- API routers

Recommended principle:

- keep the SQL and business logic as close to the current repo as possible
- move only UI/session concerns out of the backend

Do not keep Streamlit in the backend just to reuse decorators.

## Step 2: Refactor These Files First

Refactor in this order:

1. `utils/db_conn.py`
2. `data/db.py`
3. `utils/filters.py`
4. `data/query_builder.py`
5. `data/repository.py`
6. `utils/auth.py`
7. `services/ai_summary.py`

### Refactor Rules

- replace `st.secrets` with backend settings
- replace `@st.cache_data(ttl=...)` with backend caching preserving roughly the same TTLs
- replace `st.error(...)` with raised HTTP-safe exceptions or logs
- remove `st.session_state`
- keep pure helper logic untouched where possible

### Preserve Current Timeouts / Cache Intent

From current code:

- standard queries: ~300s cache, 120s SQL timeout
- filter options / brand resolution: ~600s cache
- AE queries: ~900s cache, 300s SQL timeout
- indication/ATC options: ~3600s cache

Preserve the intent even if implementation changes.

## Step 3: Backend DTOs

Create request/response models for:

- auth login
- visible user profile
- filter payload
- filter options payload
- generic DataFrame-like table payload
- heatmap payload
- AI extraction payload
- AI summary payload

Recommended response conventions:

- ordinary tables: list of objects
- KPI dicts: plain JSON object
- pivot/heatmap data: serialize as `{index: [...], columns: [...], values: [[...]]}`

Do not change semantics of the underlying queries.

## Step 4: Backend Auth

Recreate current login behavior with FastAPI auth.

Requirements:

- username/password login
- validate against configured users
- reject users missing in `USER_ACCESS`
- return visible tabs and restriction info
- preserve `display_name`

Recommended new implementation:

- JWT-based session cookie or bearer token
- `/api/auth/login`
- `/api/auth/me`
- `/api/auth/logout`

But preserve the same permission logic.

## Step 5: Backend Routers

Expose endpoints for the data actually used by the current visible UI.

### Filters / Auth Support

- `GET /api/filters/indications`
- `GET /api/filters/atc-classes`
- `GET /api/filters/options?indication=&atc_class=`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`

### Home

- `POST /api/home/kpis`
- `POST /api/home/trials-by-phase`
- `POST /api/home/trials-over-time`
- `POST /api/home/top-sponsors`
- `POST /api/home/top-conditions`
- `POST /api/home/top-interventions`

### Ask The Data

- `POST /api/ask-data/extract-filters`

Do not expose raw NL-to-SQL execution as a visible frontend feature unless requested. `run_nl_query()` exists, but the current visible page does not use it.

### Pipeline

Pipeline currently uses only `indication_name` and `sponsor`.

- `POST /api/pipeline/kpis`
- `POST /api/pipeline/by-sponsor`
- `POST /api/pipeline/by-indication`
- `POST /api/pipeline/top-interventions`
- `POST /api/pipeline/sponsor-indication-heatmap`
- `POST /api/pipeline/pro-usage`
- `POST /api/pipeline/trials-table`

### Drug Detail

- `POST /api/drug-detail/kpis`
- `POST /api/drug-detail/trials-table`
- `POST /api/drug-detail/brand-names`
- `POST /api/drug-detail/classes`
- `POST /api/drug-detail/phase-brand-heatmap`

### Drug Pricing

Drug Pricing currently depends only on brand-related filters, not sponsor/phase/status/country.

- `POST /api/drug-pricing/kpis`
- `POST /api/drug-pricing/annual-cost-per-brand-over-time`
- `POST /api/drug-pricing/by-drug-class`
- `POST /api/drug-pricing/wac-history`
- `POST /api/drug-pricing/raw`

### Market Access

Market Access also currently depends only on brand-related filters.

- `POST /api/market-access/kpis?year=2025`
- `POST /api/market-access/tier-grid?year=2025`
- `POST /api/market-access/req-grid?year=2025`

### Sponsors

- `POST /api/sponsor/trial-counts`
- `POST /api/sponsor/phase-mix`
- `POST /api/sponsor/pro-adoption`
- `POST /api/sponsor/endpoint-usage`

### Trial Design

- `POST /api/trial-design/metrics`
- `POST /api/trial-design/arms-distribution`
- `POST /api/trial-design/eligibility`

### Endpoints

- `POST /api/endpoints/heatmap`
- `POST /api/endpoints/top-categories`
- `POST /api/endpoints/pro-funnel`
- `POST /api/endpoints/full-table`

### Outcomes

- `POST /api/outcomes/categories`
- `POST /api/outcomes/type-category-heatmap`
- `POST /api/outcomes/pro-funnel`

### Outcome Scores

No data endpoints required for parity because the current UI is only a WIP placeholder page.

### PRO Overview

- `POST /api/pro/usage`
- `POST /api/pro/by-sponsor`
- `POST /api/pro/by-phase`
- `POST /api/pro/pro-funnel`

### Trial Groups

- `POST /api/trial-groups/design-groups`
- `POST /api/trial-groups/result-groups`
- `POST /api/trial-groups/groups-per-trial`

### Safety

- `POST /api/safety/aggregates`
- `POST /api/safety/by-drug`
- `POST /api/safety/detail-table`

Request body for `detail-table` should include:

- standard filter payload
- optional `organ_system`
- optional `ae_term`

## Step 6: Unused Backend Functions

These exist today but are not used by the visible UI:

- `get_drug_conditions`
- `get_drug_phase_mix`
- `get_design_outcome_type_dist`
- `get_planned_pro_usage`
- `get_reported_outcome_type_dist`
- `get_top_outcome_titles`
- `get_outcome_scores`
- `get_score_by_drug`
- `get_pro_domains`
- `get_domain_instrument_heatmap`
- `get_domain_by_drug`
- `get_adverse_event_summary`
- `get_top_adverse_events`
- `get_ae_by_organ_system`
- `get_brand_options_from_drugs`
- `run_nl_query`
- `get_annual_cost_over_time`
- `get_annual_cost_by_dosage_form`
- `get_annual_cost_by_disease`
- `get_ma_avg_tier_by_payer`
- `get_ma_requirement_breakdown`
- `get_ma_brand_payer_heatmap`
- `get_ma_brands_by_avg_tier`
- `get_ma_yoy_comparison`
- `get_ma_detail_table`

You may port them for completeness, but do not expose new visible UI for them unless asked.

## Frontend Migration Instructions

## Step 1: App Shell

Build a dashboard shell that visually mimics the current Streamlit layout:

- left sidebar
- top-level tab navigation
- main content area
- consistent white-card surfaces
- same typography/colors

The current app uses tabs, but in Next.js you may implement:

- route-based pages with a shared tab-like nav bar

This is acceptable if:

- visible labels and order stay identical
- tab access rules stay identical
- the overall UX still feels like the same dashboard

## Step 2: Login Flow

Recreate the current login screen behavior:

- centered white card
- logo at top
- title `Clinical Trials Intelligence Platform`
- subtitle `Sign in to continue`
- username input
- password input
- primary `Sign in` button
- error text `Incorrect username or password.`
- hide sidebar/app content until authenticated

## Step 3: Sidebar

Recreate the sidebar sections and labels exactly:

- signed-in user badge
- `Sign out` button
- header `⚙️ Filters`
- section `🌐 Global Filters`
- caption `Drug class and MeSH condition filters`
- section `🔽 Downstream Filters`

Global filters:

- `Condition (Disease Area)`
- `Drug Class (ATC)`

Expanders:

- `Trial Attributes`
- `Sponsor / Drug`
- `Endpoints / Outcomes`
- `PRO`
- `Geography`

Fields:

- `Study Type`
- `Phase`
- `Status`
- `Results Posted`
- `Sponsor`
- `Agency Class`
- `Drug (Brand Name)`
- `Drug Indication (Label)`
- `Endpoint Category`
- `PRO Instrument`
- `PRO Domain`
- `Country`

Bottom button:

- `🔄 Reset All Filters`

Important parity rule:

- the sidebar should not show enrollment controls
- the sidebar should not show local safety term filters

## Step 4: Header / Filter Summary / Reusable UI

Rebuild these shared frontend components:

- `PageHeader`
- `FilterSummaryBar`
- `MetricCard`
- `KpiRow`
- `AlertCallout`
- `ChartTile`
- `AgTable`
- `CsvDownloadButton`

Preserve current copy and visual structure.

## Step 5: Chart Layer

Recreate the current chart set with Plotly React:

- bar
- grouped bar
- stacked bar
- donut
- line
- area
- treemap
- sunburst
- scatter
- box plot
- heatmap
- funnel
- phase-colored bar
- status-colored bar

Keep chart defaults aligned with `components/charts.py`.

## Exact Page Specs

Build these pages exactly as they behave today.

## 1. Home

Source: `views/home.py`

Header:

- title: `Clinical Trials Intelligence Platform`
- subtitle: `Competitive landscape, pipeline intelligence, endpoint benchmarking, PRO analytics, and safety analysis.`

Behavior:

- always load and show overview KPIs
- if `filters.has_any_filter()` is false, show the large “Filter Required” callout instead of charts
- even users with implicit access restrictions still hit this gate if they have not explicitly chosen sidebar filters

Visible KPI rows:

- `Total Trials`
- `Active Trials`
- `Completed Trials`
- `Trials with Results`
- `Unique Sponsors`
- `Unique Drugs`
- `Unique Conditions`
- `Trials with PROs`

Charts when filters exist:

- row 1 left: `Trial Count by Phase`
- row 1 right: `Trials First Posted per Year`
- row 2 left: `Top Sponsors by Trial Count`
- row 2 right: `Top MeSH Conditions`
- full width after: `Top Drug Interventions by Trial Count`

Bottom section:

- horizontal rule
- heading `Explore Platform Modules`
- static 3-column card grid from `config.settings.PAGES`, excluding `home`
- keep cards display-only, not clickable
- keep current omission of Drug Pricing and Market Access because that is how current code behaves

## 2. Ask the Data

Source: `views/ask_the_data.py`

Header:

- title: `AI Query`
- subtitle: `Ask a question about the clinical trial landscape — filters are applied automatically across all tabs.`
- breadcrumb: `Home > AI Query`

This page does not run arbitrary SQL in the visible UI.

It does:

- accept natural-language question input
- show 8 example question buttons
- call OpenAI filter extraction
- show interpretation card
- show extracted filter chips
- offer `Apply to Dashboard`
- offer `Ask Again`
- show success confirmation after apply
- show `How does this work?` expander

Current example questions:

- `Phase 2 trials for NSCLC by AstraZeneca`
- `Completed breast cancer trials with posted results`
- `Recruiting AML trials from major pharma`
- `Merck's Phase 3 oncology pipeline`
- `DLBCL trials by BMS or Roche-Genentech`
- `Phase 1/2 TNBC immunotherapy trials`
- `Multiple myeloma trials with results posted`
- `Pfizer Phase 3 prostate cancer trials`

Current extraction model:

- `gpt-4.1-mini`

Current extracted fields:

- `indication`
- `atc_class`
- `sponsors`
- `phases`
- `statuses`
- `countries`
- `agency_class`
- `has_results`
- `interpretation`

Preserve exact semantics:

- resolve indication against live DB values using `get_indication_options()`
- set pending global filter values
- clear downstream widget state
- apply exact validated values only
- pre-warm `get_filter_options(indication, atc_class)` after applying filters

## 3. Pipeline

Source: `views/pipeline_landscape.py`

Header:

- title: `Pipeline Landscape`
- subtitle: `Investigational asset landscape: sponsor activity, indication coverage, and pipeline PRO usage.`
- breadcrumb: `Home > Pipeline Landscape`

Important current filter behavior:

- pipeline data functions only use `indication_name` and `sponsor`
- all other downstream filters do not affect pipeline data today
- keep that exact behavior unless the user later asks to normalize it

Top info note:

- pipeline data note from `components.alerts.pipeline_data_note()`

KPIs:

- `Pipeline Trials`
- `Unique Assets`
- `Active Sponsors`
- `Indications Covered`
- `With Planned PROs`

If no explicit filters:

- show filter-required callout
- return early

Page internal tabs:

1. `🏢 By Sponsor`
2. `🎯 By Indication`
3. `💊 Interventions`
4. `🗺️ Sponsor × Indication`
5. `👤 PRO Usage`

Tab contents:

- By Sponsor
  - left: `Pipeline Trials by Sponsor`
  - right: `Unique Assets by Sponsor`
  - CSV download
- By Indication
  - left: `Pipeline Trials by Indication`
  - right: `Indication Treemap`
- Interventions
  - `Top Pipeline Interventions`
  - CSV download
- Sponsor × Indication
  - heatmap `Sponsor × Indication Pipeline Heatmap`
- PRO Usage
  - `Pipeline PRO Instrument Usage`

After tabs:

- divider
- heading `Pipeline Trial Details`
- table from `get_pipeline_trials_table(indication)`
- if `filters.sponsor` exists, the table is further filtered client-side by `sponsor_name`
- CSV download

AI Summary:

- visible on this page
- uses `build_pipeline_context`, `generate_summary`, and `filter_hash`
- preserve summary invalidation when filters change

## 4. Drug Detail

Source: `views/drug_detail.py`

Header:

- title: `Drug Detail`
- subtitle: `Trial portfolio, conditions studied, and drug classes for the active filter scope.`
- breadcrumb: `Home > Drug Detail`

Behavior:

- load KPIs and tables even before the explicit filter gate
- if total trials is zero, show no-data callout and stop
- if no explicit filters, show filter-required callout after KPIs

KPIs:

- `Total Trials`
- `Completed`
- `With Results`
- `Brand Names`
- `Drug Classes`

Page internal tabs:

1. `💊 Brand Names / Drugs`
2. `📊 Phase & Design`
3. `🏷️ Drug Classes`
4. `📄 Trial List`

Tab contents:

- Brand Names / Drugs
  - horizontal bar `Brand Names — Trial Counts`
- Phase & Design
  - heatmap `Phase × Brand Name — Trial Counts`
- Drug Classes
  - filter out null-like class labels before rendering
  - horizontal bar `ATC Drug Classes — Brands per Class`
- Trial List
  - AG Grid table
  - CSV download

AI Summary:

- visible on this page

## 5. Drug Pricing

Source: `views/drug_pricing.py`

Header:

- title: `Drug Pricing`
- subtitle: `Annual cost trends and WAC unit price history for the active filter scope.`
- breadcrumb: `Home > Drug Pricing`

Important current filter behavior:

- this page only really depends on brand-related filters:
  - `brand_name`
  - `atc_class_name`
  - `indication_name`
  - `drug_indication`
- sponsor/phase/status/country/endpoint/PRO filters do not affect pricing data in current code
- preserve that

Behavior:

- always show KPIs
- if no explicit filters, show filter-required callout instead of charts/tables

KPIs:

- `Unique Drugs`
- `Dosage Forms`
- `Unique Diseases`
- `Avg Annual Cost (<latest quarter>)`
- optional YoY delta shown in KPI

Internal tabs:

1. `📈 Cost Over Time`
2. `🏷️ By Drug Class`
3. `💲 WAC Price History`
4. `📄 Raw Data`

Tab contents:

- Cost Over Time
  - custom multi-brand step-line chart
  - subtitle `Step-line per drug — quarterly total annual cost`
- By Drug Class
  - horizontal bar `Avg Latest Annual Cost by Drug Class`
  - subtitle `Average annual cost per brand within each ATC class (latest quarter)`
- WAC Price History
  - custom multi-brand line chart
  - subtitle `Average WAC unit price per brand over time`
- Raw Data
  - renamed display columns
  - AG Grid table
  - CSV download

AI Summary:

- visible on this page

Pricing-specific query rules from `data/repository.py`:

- exclude rows where `total_cost_filled > 1000000`
- brand resolution priority:
  - explicit brand
  - ATC class
  - indication through `browse_conditions + drug_trials`
  - empty list means no brand filter

## 6. Market Access

Source: `views/market_access.py`

Header:

- title: `Market Access`
- subtitle: `Formulary tier and utilization-management requirements across 6 major US payers (2025 & 2026).`
- breadcrumb: `Home > Market Access`

Important current filter behavior:

- same effective filter behavior as Drug Pricing
- only brand-related filters matter today

Behavior:

- year selector radio with options `2025`, `2026`
- always show KPIs
- if no explicit filters, show filter-required callout instead of charts

KPIs:

- `Drugs Tracked`
- `With Prior Auth (PA)`
- `With Qty Limits (QL)`
- `With Specialty (SP)`
- `Payers Covered`

Internal tabs:

1. `🎨 Formulary Tiers`
2. `✅ Access Requirements`

Tab contents:

- Formulary Tiers
  - custom heatmap with drugs on rows and payers on columns
  - caption about NC = not covered
- Access Requirements
  - radio for `PA`, `QL`, `SP`
  - custom checkbox-style heatmap
  - caption explaining checkmark semantics

AI Summary:

- visible on this page

## 7. Sponsors

Source: `views/sponsor_benchmark.py`

Header:

- title: `Sponsor Benchmark`
- subtitle: `Compare sponsor trial portfolios, phase distribution, PRO adoption rates, and endpoint focus.`
- breadcrumb: `Home > Sponsor Benchmark`

If no explicit filters:

- show filter-required callout and stop

Internal tabs:

1. `📊 Trial Counts`
2. `📐 Phase Mix`
3. `👤 PRO Adoption`
4. `🎯 Endpoint Usage`

Tab contents:

- Trial Counts
  - left: `Total Trials per Sponsor`
  - right: `Active vs Completed`
  - CSV download
- Phase Mix
  - stacked bar `Phase Mix by Sponsor`
- PRO Adoption
  - horizontal bar `% Trials with Planned PROs by Sponsor`
  - section heading `PRO Adoption Details`
  - table + CSV
- Endpoint Usage
  - heatmap `Endpoint Category Usage by Sponsor`
  - section heading `Endpoint Usage Data`
  - table

## 8. Trial Design

Source: `views/trial_design.py`

Header:

- title: `Trial Design`
- subtitle: `Benchmark trial design patterns: allocation method, intervention model, arms count, and eligibility.`
- breadcrumb: `Home > Trial Design`

If no explicit filters:

- show filter-required callout and stop

Charts:

- row 1 left: donut `Allocation Method`
- row 1 right: horizontal bar `Intervention Model`
- after divider: bar `Number of Arms / Groups per Trial`
- after divider:
  - left donut `Gender Eligibility`
  - right bar `Eligible Age Groups`
- CSV download for eligibility table data

## 9. Endpoints

Source: `views/planned_endpoints.py`

Header:

- title: `Planned Endpoints`
- subtitle: `Protocol-level endpoint design: outcome types, most common endpoints, and planned PRO instruments.`
- breadcrumb: `Home > Planned Endpoints`

If no explicit filters:

- show filter-required callout and stop

Internal tabs:

1. `📊 Outcome Types`
2. `🔢 Top Endpoints`
3. `👤 Planned PROs`
4. `📄 Full Table`

Tab contents:

- Outcome Types
  - heatmap `Outcome Type × Category (Unique Trials)`
- Top Endpoints
  - horizontal bar `Top 10 Planned Endpoint Categories by Frequency`
  - CSV download
- Planned PROs
  - this tab currently uses `get_reported_pro_funnel()`
  - funnel chart `Planned vs Reported PRO Funnel`
  - two Streamlit metric tiles for stage counts
  - preserve current behavior even though the function naming is slightly odd
- Full Table
  - AG Grid
  - CSV download

## 10. Outcomes

Source: `views/reported_outcomes.py`

Header:

- title: `Reported Outcomes`
- subtitle: `Analysis of posted result outcomes: category distributions, types, and top reported endpoints.`
- breadcrumb: `Home > Reported Outcomes`

If no explicit filters:

- show filter-required callout and stop

Internal tabs:

1. `📊 Categories`
2. `📋 Outcome Types`
3. `🔢 Top Outcomes`
4. `👤 PRO Funnel`

Tab contents:

- Categories
  - left horizontal bar `Outcomes by Category`
  - right donut `Trials per Category`
  - CSV download
- Outcome Types
  - heatmap `Outcome Type × Category (Unique Trials)`
- Top Outcomes
  - current code uses top categories again, not outcome titles
  - horizontal bar `Top 10 Outcome Categories`
  - table of `cat_df`
  - CSV download
- PRO Funnel
  - funnel `Planned vs Reported PRO Funnel`
  - two stage metrics

## 11. Scores

Source: `views/outcome_scores.py`

Header:

- title: `Outcome Score Analysis`
- subtitle: `Numeric outcome measurements: score distributions, drug comparisons, and result-group analysis.`
- breadcrumb: `Home > Outcome Scores`

Current visible page body:

- single info message: `This page is currently a work in progress.`

Do not build a full score analysis page for parity. Keep the placeholder.

## 12. PRO Overview

Source: `views/pro_overview.py`

Header:

- title: `PRO Overview`
- subtitle: `Patient-reported outcome instrument adoption: planned vs reported, by sponsor, and by phase.`
- breadcrumb: `Home > PRO Overview`

Behavior:

- always compute/show KPI row
- if no explicit filters, show filter-required callout instead of charts

KPIs:

- `Unique PRO Instruments`
- `Trials with Planned PRO`
- `Trials with Reported PRO`

Internal tabs:

1. `📊 Instrument Frequency`
2. `📋 Planned vs Reported`
3. `🏢 By Sponsor`
4. `📐 By Phase`

Tab contents:

- Instrument Frequency
  - left horizontal bar `Top PRO Instruments (Total)`
  - right donut `Instrument Share (Top 10)`
  - CSV download
- Planned vs Reported
  - funnel `Planned → Reported PRO Funnel`
  - stacked bar `Planned vs Reported by Instrument`
- By Sponsor
  - left horizontal bar `PRO Adoption by Sponsor`
  - right heatmap `Sponsor × Instrument Heatmap`
- By Phase
  - bar `Trials with Planned PROs by Phase`

After tabs:

- divider
- heading `PRO Instrument Details`
- AG Grid table
- CSV download

AI Summary:

- visible on this page

## 13. Trial Groups

Source: `views/trial_groups.py`

Header:

- title: `Trial Groups`
- subtitle: `Protocol arms, design groups, and result groups: intervention mapping and group structure.`
- breadcrumb: `Home > Trial Groups`

If no explicit filters:

- show filter-required callout and stop

Internal tabs:

1. `📐 Design Groups`
2. `📋 Result Groups`
3. `📊 Groups per Trial`

Tab contents:

- Design Groups
  - donut `Group Type Distribution`
  - horizontal bar `Top Interventions in Groups`
  - heading `Design Groups Table`
  - table + CSV
- Result Groups
  - metric `Result Groups with Drug Linkage`
  - left donut `Result Group Type Distribution`
  - right horizontal bar `Top Drugs in Result Groups`
  - heading `Result Groups Table`
  - table + CSV
- Groups per Trial
  - bar `Distribution: Design Groups per Trial`

## 14. Safety

Source: `views/safety_analysis.py`

Header:

- title: `Safety Analysis`
- subtitle: `Adverse event reporting: terms, organ systems, drug associations, and incidence analysis.`
- breadcrumb: `Home > Safety Analysis`

Top warning:

- safety interpretation warning from `ae_interpretation_warning()`

Behavior:

- always load KPI aggregate object
- show KPI row even before filter gate
- if no explicit filters, show filter-required callout and stop

KPIs:

- `Trials with AEs`
- `AE Records`
- `Unique AE Terms`
- `Organ Systems`
- `Total Subjects Affected`

Important local page-only filters:

- text input `Filter by Organ System (optional)`
- text input `Filter by AE Term (optional)`

These only affect the detail table query, not the summary charts.

Internal tabs:

1. `🔢 Top AE Terms`
2. `🫀 Organ Systems`
3. `💊 By Drug`
4. `📄 Detail Table`

Tab contents:

- Top AE Terms
  - left bar `Top AE Terms by Trial Count`
  - right bar `Top AE Terms by Subjects Affected`
  - table + CSV
- Organ Systems
  - left bar `Top 10 Organ Systems by Trial Count`
  - right treemap `Top 10 Organ Systems by Subjects Affected`
  - CSV
- By Drug
  - left bar `AE Trials by Drug`
  - right bar `Unique AE Terms per Drug`
  - CSV
- Detail Table
  - heading `Adverse Event Detail Table`
  - caption about drug linkage via `drug_result_groups`
  - explicit `Load Detail Table` button before executing heavy detail query
  - once loaded: table with incidence column + CSV

Critical backend safety logic to preserve:

- use `ae_scope_cte()`
- filter `subjects_affected > 0`
- link drug association through `public.drug_result_groups`

## AI Summary Features

Current visible AI Summary pages:

- Pipeline
- Drug Detail
- Drug Pricing
- Market Access
- PRO Overview

Do not add AI Summary to other pages unless asked.

Current summary generation model:

- `gpt-4o`

Current summary pattern:

- small button on the right
- disabled by UX when no explicit filters
- generate on click
- cache result keyed by filter hash
- clear cached summary if filters change
- render white summary card with left accent border

## Query And Business-Logic Rules You Must Preserve

These are especially important:

- `browse_conditions` indication logic always uses `mesh_type = 'mesh-list'`
- sponsor queries use `lead_or_collaborator = 'lead'`
- country queries exclude `removed IS TRUE`
- adverse event queries always require `subjects_affected > 0`
- AE drug linkage comes from `public.drug_result_groups`
- pricing excludes rows above `$1,000,000`
- pipeline indication filtering is substring match on `LOWER(pt.condition) LIKE :ind_like`
- pipeline trial table only applies indication in SQL and sponsor as a frontend/client filter
- market access year table switches between `mapped_access_2025` and `mapped_access_2026`
- overview KPI fast path uses `public.overview_kpis_snapshot` when there are no explicit sidebar filters
- snapshot scope key depends only on access restrictions, not on regular filters

## Snapshot And Preload Behavior

Current performance helpers:

- `utils.preloader.py`
  - background warmup of Home queries once per process
- `scripts/generate_snapshot_sql.py`
  - generates scoped snapshot upserts for `overview_kpis_snapshot`

You do not need to preserve the exact threading implementation, but you should preserve the effect:

- cached startup data for common Home queries
- support for snapshot-backed overview KPIs
- ability to regenerate scoped snapshot SQL when `USER_ACCESS` changes

## Explicitly Do Not Add These Unless Asked

- a PRO Domains top-level page
- a raw SQL “Ask the Data” execution UI
- FDAERS features
- clickable Home navigation cards
- extra sidebar filters not currently visible
- a fully functional Outcome Scores page
- fixes for current stale Home nav-card omissions

## Validation Checklist

Do not stop until all of these are true.

- All 14 top-level pages exist in the same order.
- Access control uses the exact current tab labels.
- The logo appears in every page header.
- The sidebar matches current sections, labels, and reset behavior.
- Global filter semantics match current query-builder behavior exactly.
- User restrictions are enforced server-side.
- Home nav cards match current stale `PAGES` behavior.
- Outcome Scores remains a WIP placeholder.
- Pipeline only responds to indication/sponsor like the current app.
- Pricing and Market Access only respond to brand-related filters like the current app.
- Safety keeps page-local organ system / AE term filters for the detail table only.
- AI Summary appears only on the five current pages.
- Ask the Data remains a filter-extraction workflow, not a raw SQL tool.
- Overview KPI snapshot logic is preserved.
- CSV downloads exist where they exist today.
- Tables preserve sort/filter/pagination behavior.
- Callouts and warnings appear in the same places.

## Final Instruction To The Coding Agent

Migrate the app faithfully. Reuse the current SQL and business logic wherever possible. Prefer exact parity over cleanup. If you notice code inconsistencies, preserve them unless they would break the migration completely, and document them at the end instead of silently changing behavior.
