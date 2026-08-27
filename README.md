# Imprint Corporate Finance Case Study

A driver-based forecasting model for 10 credit-card merchant programs, built from a
~67K-row vintage-triangle dataset, rolled up into a consolidated 8-quarter
Management P&L (Q3 2026–Q2 2028).

**Four outputs, four audiences — all with light/dark mode (toggle top-right,
defaults to system preference):**
- [`output/html/unified_narrative.html`](output/html/unified_narrative.html) —
  **the front door.** One document, read start to finish: the Consolidated
  P&L, Cohort & Vintage Views, the Working Model, and the Narrative (risks /
  winners-drags / where better data would help) — the four things the case
  brief asks for, each its own chapter, pointing to the other three outputs
  as supporting detail.
- [`output/html/dashboard.html`](output/html/dashboard.html) — **the primary
  executive reporting tool.** Rolled-up Management P&L with live filters by
  Merchant, Vintage, and FICO tier, KPI tiles, comparison charts, driver-KPI
  views, and a full-detail data table. Built for ongoing reporting and ad hoc
  analysis, not a one-time snapshot.
- [`output/html/narrative_report.html`](output/html/narrative_report.html) —
  the financial story, told progressively in slides: where the book stands
  today, where it's headed, how it's aging, what cohort curves reveal, the
  FICO-tier LTV/CAC finding, merchant winners/drags, and the risks — each
  slide makes one point, backed by a chart.
- [`output/html/pitch_deck.html`](output/html/pitch_deck.html) — how the
  model was built: architecture, core assumptions, the bugs found and fixed
  along the way, and the independent audit trail. Presentation-style, a few
  minutes to read or present.
- [`BUILD_LOG.md`](BUILD_LOG.md) — the full-detail backing document behind
  all four: every assumption, every bug, the AI-collaboration build log, and
  the complete written narrative. See also [`docs/`](docs/) for a set of
  short, focused references (script-by-script guide, build process, forecast
  methodology, proposed next steps).

## Repo layout

```
scripts/
  core_engine/    01-07, 12-13 — ingest through audit, plus diagnostics
  reporting/      08-11, 14    — the four HTML deliverables
  pnl_utils.py, viz_utils.py   — shared helpers (both folders import these)
data/             raw source data + line-item classification
output/
  parquet/, csv/, html/, json/ — every pipeline output, grouped by file type
docs/             short reference docs (see below)
```

## Pipeline

Run in order from `imprint_case/`:

```
python3 scripts/core_engine/01_ingest_clean.py            # clean + classify raw data
python3 scripts/core_engine/02_gap_analysis.py             # coverage/sparsity/sign-anomaly checks
python3 scripts/core_engine/03_curve_library.py            # vintage maturation curves + rate curves
python3 scripts/core_engine/04_forecast_engine.py          # backbook + frontbook forecast
python3 scripts/core_engine/05_pnl_rollup.py                # consolidated P&L + cohort LTV/CAC
python3 scripts/core_engine/06_cohort_views.py              # cohort-level views
python3 scripts/reporting/09_export_dashboard_data.py       # aggregates data for the dashboard (run before audit -- see note)
python3 scripts/core_engine/07_audit.py                     # independent audit, separate code paths
python3 scripts/reporting/08_build_narrative_deck.py        # narrative_report.html (the financial story, in slides)
python3 scripts/reporting/10_build_dashboard.py              # dashboard.html
python3 scripts/reporting/11_build_pitch_deck.py             # pitch_deck.html
python3 scripts/core_engine/12_validate_exceptional_fico.py  # diagnostic: Exceptional-FICO magnitude validation
python3 scripts/core_engine/13_seasonality_analysis.py       # diagnostic: calendar-quarter seasonality check
python3 scripts/reporting/14_build_unified_narrative.py      # unified_narrative.html (single-entry-point deliverable)
```

Note: `09_export_dashboard_data.py` has to run before `07_audit.py`, not after, despite the
numbers -- one of the audit's checks independently recomputes driver KPIs from
`dashboard_data.json`, so it needs that file to already exist. `07_audit.py`'s own number
reflects when it was built in the original sequence, not a strict "must run Nth" order; every
other script's number does match its required run position.

Requires `pandas`, `numpy`. All outputs land in `output/`, grouped
into `parquet/`, `csv/`, `html/`, and `json/` subfolders by file type. All four
HTML files are self-contained (data embedded inline) and cross-link each other —
open any of them directly in a browser, no server needed.

## Headline result

Portfolio-weighted LTV/CAC of **0.85x**, driven by a sharp, counterintuitive
FICO-tier inversion — see `BUILD_LOG.md` for the full explanation.
