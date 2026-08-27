# Scripts Guide

One-line scope per script. All scripts live flat in `scripts/`, numbered 01-14 in run order (see `README.md`'s Pipeline section); the two groupings below are logical, not physical. **Grounded** = derived empirically from actuals. **Assumed** = a judgment-set parameter/technique. Full detail: `BUILD_LOG.md`.

## Core engine

| # | Script | Scope | Grounded vs. assumed |
|---|---|---|---|
| 01 | ingest_clean | Load raw CSV, rename fields, derive QSB, validate. | Grounded: pure cleaning/joins. |
| 02 | gap_analysis | Coverage/sparsity/sign-anomaly diagnostics. | Grounded: read-only checks. |
| 03 | curve_library | Dev factors, rate curves, seasonal index. | Grounded from actuals; **assumed**: `POOL_THRESHOLD`, `SEASONAL_CLIP`. |
| 04 | forecast_engine | Backbook roll-forward + frontbook sizing, 8Q forecast. | Most assumption-heavy: `GROWTH_CAP`, `FACTOR_CLIP`, `ANCHOR_RATIO_DAMPING`, hold-flat tail. |
| 05 | pnl_rollup | Consolidated/by-merchant P&L, cohort LTV/CAC. | Grounded bucketing; **assumed**: 15% hurdle rate, 12Q window, pop.-fill for thin cohorts. |
| 06 | cohort_views | CP/account by vintage, LTV/CAC by vintage & FICO, age-mix. | Grounded: weighted aggregation of forecast output. |
| 07 | audit | 8 independent checks, separate code paths. | Grounded: verification only. |
| 12 | validate_exceptional_fico | Diagnostic: hand-derive Exceptional-FICO magnitude, more merchants. | Grounded re-derivation. |
| 13 | seasonality_analysis | Diagnostic: is calendar seasonality material before building it in? | Grounded hypothesis test. |

## Reporting

| # | Script | Scope |
|---|---|---|
| 08 | build_narrative_deck | `narrative_report.html` — the financial story, in slides. |
| 09 | export_dashboard_data | Aggregates pipeline output into `dashboard_data.json`. |
| 10 | build_dashboard | `dashboard.html` — live-filtered executive tool, KPIs, driver-KPI tabs, full-detail table. |
| 11 | build_pitch_deck | `pitch_deck.html` — architecture, assumptions, bugs, audit trail. |
| 14 | build_unified_narrative | `unified_narrative.html` — single front-door doc (P&L, cohorts, model, narrative). |

All reporting scripts are presentation layer: they read already-computed CSVs/parquet/JSON and format, never introduce new forecast logic.

## Shared modules

- **pnl_utils.py** — `classify_pnl_bucket`, keyed off `Model Role` (not `Category`) after a bug shipped from a Category-based, duplicated version.
- **viz_utils.py** — formatting (`fmt_money`, `fmt_pct`, `fmt_x`) + static-SVG chart builders shared by all reporting scripts.

## End-to-end pipeline

`01→02→03→04` builds the forecast engine (grain: Merchant × FICO × QSB, pooled below `POOL_THRESHOLD`). `05→06` roll it into P&L and cohort views. `09` runs before `07` (audit needs `dashboard_data.json` — see `README.md`). `08/10/11/14` build the four HTML deliverables from the same CSVs, so they can never disagree with each other. `12/13` are standalone diagnostics.
