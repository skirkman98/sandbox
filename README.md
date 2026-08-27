# Imprint Corporate Finance Case Study

## The problem

Imprint runs credit-card programs for 10 merchant partners. The case brief hands over
a ~67K-row vintage-triangle dataset — every merchant program's actuals, broken out by
booked vintage (cohort quarter), FICO tier, and quarters-since-book — and asks for
three things: a consolidated forward-looking Management P&L, cohort/vintage views of
how the book is aging, and a written narrative covering risks, merchant winners and
drags, and where the data itself falls short. The brief leaves the modeling approach
open; the only fixed points are the shape of the raw data and the shape of the ask.

## How the solution was formulated

The approach was decided before any code was written — the case brief, the raw data,
and a short scratch file sketching field renames and forecast architecture came
first, then a throwaway visualization pass to look at the actuals before modeling
them. Three decisions anchor everything downstream:

- **Driver-based, not top-down.** Every forecasted line item is either a volume
  driver rolled forward on its own development curve, or a rate applied to that
  driver's basis (e.g. a cost as a rate of Net Transaction Volume). Nothing is
  grown as a lump P&L line in isolation from the account/volume mechanics that
  actually produce it.
- **Frontbook / backbook, not one blended curve.** Existing cohorts age forward on
  development factors measured from their own observed history; new cohorts are
  sized off recent trailing growth and enter the same aging curve from quarter
  zero. One engine, two different starting conditions — not two different models.
- **Grounded first, assumed second, and the difference disclosed.** Every curve,
  rate, and seasonal pattern is measured from actuals wherever the data supports
  it; where judgment is required (growth caps, pooling thresholds, how far a
  thin-history curve can be trusted before it's backstopped), that's a named,
  in-code parameter, not a hidden default. `docs/FORECAST_METHODOLOGY.md` and
  `docs/SCRIPTS_GUIDE.md` mark each component grounded vs. assumed explicitly.

The build itself was iterative and adversarial toward its own output, not a single
pass trusted on completion. Each stage was run and its output inspected before the
next stage was built on top of it, which surfaces problems in the numbers rather
than the code. Confidence beyond "it ran without error" came from deliberately
independent checks: an audit script that re-derives key figures from source data
via separate logic rather than importing the pipeline's own functions, a second,
separately-scoped review with no context from the first pass, weighted-average
tie-outs and full reconciliations back to the raw source, and hand-derivation of
headline findings from raw rows before trusting their magnitude. That process
caught several real, output-changing bugs — including one where a one-time cost
was leaking into a recurring profit metric — that a single self-review pass had
already signed off on.

## The output pipeline

The engine runs as a numbered sequence of scripts, each reading the prior stage's
output and writing its own — cleaning and classification, then curve-fitting, then
the forecast itself, then the P&L and cohort roll-ups, then an independent audit,
then four presentation layers built from the same underlying files so they can
never disagree with each other:

```
scripts/            all pipeline scripts, flat (numbered 01-14 = run order; see docs/SCRIPTS_GUIDE.md
                     for which are core-engine vs. reporting)
  pnl_utils.py, viz_utils.py — shared helpers imported by the numbered scripts
data/             raw source data + line-item classification
output/
  parquet/, csv/, html/, json/ — every pipeline output, grouped by file type
docs/             short reference docs (methodology, scripts guide, build process, known gaps, next steps)
```

Run in order from `imprint_case/`:

```
python3 scripts/01_ingest_clean.py            # clean + classify raw data
python3 scripts/02_gap_analysis.py             # coverage/sparsity/sign-anomaly checks
python3 scripts/03_curve_library.py            # vintage maturation curves + rate curves
python3 scripts/04_forecast_engine.py          # backbook + frontbook forecast
python3 scripts/05_pnl_rollup.py                # consolidated P&L + cohort economics
python3 scripts/06_cohort_views.py              # cohort-level views
python3 scripts/09_export_dashboard_data.py       # aggregates data for the dashboard (run before audit -- see note)
python3 scripts/07_audit.py                     # independent audit, separate code paths
python3 scripts/08_build_narrative_deck.py        # narrative_report.html (the financial story, in slides)
python3 scripts/10_build_dashboard.py              # dashboard.html
python3 scripts/11_build_pitch_deck.py             # pitch_deck.html
python3 scripts/12_validate_exceptional_fico.py  # diagnostic: FICO-tier finding, validated beyond one example
python3 scripts/13_seasonality_analysis.py       # diagnostic: calendar-quarter seasonality check
python3 scripts/14_build_unified_narrative.py      # unified_narrative.html (single-entry-point deliverable)
```

Note: `09_export_dashboard_data.py` has to run before `07_audit.py`, not after, despite the
numbers -- one of the audit's checks independently recomputes driver KPIs from
`dashboard_data.json`, so it needs that file to already exist. `07_audit.py`'s own number
reflects when it was built in the original sequence, not a strict "must run Nth" order; every
other script's number does match its required run position.

Requires `pandas`, `numpy`. All outputs land in `output/`, grouped into `parquet/`,
`csv/`, `html/`, and `json/` subfolders by file type. All four HTML deliverables are
self-contained (data embedded inline) and cross-link each other — open any of them
directly in a browser, no server needed.

## The four deliverables

Each targets a different audience, all with light/dark mode (toggle top-right,
defaults to system preference):

- [`output/html/unified_narrative.html`](output/html/unified_narrative.html) —
  **the front door.** One document, read start to finish: the Consolidated P&L,
  Cohort & Vintage Views, the Working Model, and the Narrative (risks /
  winners-drags / where better data would help) — the four things the case brief
  asks for, each its own chapter, pointing to the other three outputs as
  supporting detail.
- [`output/html/dashboard.html`](output/html/dashboard.html) — **the primary
  executive reporting tool.** Rolled-up Management P&L with live filters by
  Merchant, Vintage, and FICO tier, KPI tiles, comparison charts, driver-KPI
  views, and a full-detail data table. Built for ongoing reporting and ad hoc
  analysis, not a one-time snapshot.
- [`output/html/narrative_report.html`](output/html/narrative_report.html) — the
  financial story, told progressively in slides: where the book stands today,
  where it's headed, how it's aging, what the cohort curves reveal, merchant
  winners and drags, and the risks — each slide makes one point, backed by a
  chart.
- [`output/html/pitch_deck.html`](output/html/pitch_deck.html) — how the model
  was built: architecture, core assumptions, the bugs found and fixed along the
  way, and the independent audit trail. Presentation-style, a few minutes to
  read or present.

`docs/` holds a set of short, focused references: `SCRIPTS_GUIDE.md`
(script-by-script ownership), `BUILD_PROCESS.md` (the condensed build
narrative), `FORECAST_METHODOLOGY.md` (grain, segments, grounded vs. assumed),
`KNOWN_GAPS.md` (open limitations), and `NEXT_STEPS.md` (what would close
them).
