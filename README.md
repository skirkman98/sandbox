# Imprint Corporate Finance Case Study

A driver-based forecasting model for 10 credit-card merchant programs, built from a
~67K-row vintage-triangle dataset, rolled up into a consolidated 8-quarter
Management P&L (Q3 2026–Q2 2028).

**Three outputs, three audiences — all with light/dark mode (toggle top-right,
defaults to system preference):**
- [`output/dashboard.html`](output/dashboard.html) — **the primary executive
  reporting tool.** Rolled-up Management P&L with live filters by Merchant,
  Vintage, and FICO tier, KPI tiles, comparison charts, and a data table. Built
  for ongoing reporting and ad hoc analysis, not a one-time snapshot.
- [`output/narrative_report.html`](output/narrative_report.html) — the
  financial story, told progressively in slides: where the book stands today,
  where it's headed, how it's aging, what cohort curves reveal, the FICO-tier
  LTV/CAC finding, merchant winners/drags, and the risks — each slide makes
  one point, backed by a chart.
- [`output/pitch_deck.html`](output/pitch_deck.html) — how the model was
  built: architecture, core assumptions, the bugs found and fixed along the
  way, and the independent audit trail. Presentation-style, a few minutes to
  read or present.
- [`BUILD_LOG.md`](BUILD_LOG.md) — the full-detail backing document behind all
  three: every assumption, every bug, the AI-collaboration build log, and the
  complete written narrative.

## Pipeline

Run in order from `imprint_case/`:

```
python3 scripts/01_ingest_clean.py            # clean + classify raw data
python3 scripts/02_gap_analysis.py            # coverage/sparsity/sign-anomaly checks
python3 scripts/03_actuals_explorer.py        # throwaway gut-check charts
python3 scripts/04_curve_library.py           # vintage maturation curves + rate curves
python3 scripts/05_forecast_engine.py         # backbook + frontbook forecast
python3 scripts/06_pnl_rollup.py              # consolidated P&L + cohort LTV/CAC
python3 scripts/07_cohort_views.py            # cohort-level views
python3 scripts/08_audit.py                   # independent audit, separate code paths
python3 scripts/09_build_narrative_deck.py    # narrative_report.html (the financial story, in slides)
python3 scripts/10_export_dashboard_data.py   # aggregates data for the dashboard
python3 scripts/11_build_dashboard.py         # dashboard.html
python3 scripts/12_build_pitch_deck.py        # pitch_deck.html
```

Requires `pandas`, `numpy`, `matplotlib`. All outputs land in `output/`. All three
HTML files are self-contained (data embedded inline) — open any of them directly
in a browser, no server needed.

## Headline result

Portfolio-weighted LTV/CAC of **0.82x**, driven by a sharp, counterintuitive
FICO-tier inversion — see `BUILD_LOG.md` for the full explanation.
