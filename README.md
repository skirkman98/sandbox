# Imprint Corporate Finance Case Study

A driver-based forecasting model for 10 credit-card merchant programs, built from a
~67K-row vintage-triangle dataset, rolled up into a consolidated 8-quarter
Management P&L (Q3 2026–Q2 2028).

**Start here:**
- [`BUILD_LOG.md`](BUILD_LOG.md) — methodology, assumptions, the AI-collaboration
  build log (including two real bugs found and fixed along the way), and the full
  written narrative (risks, merchant winners/drags, data gaps).
- [`output/report.html`](output/report.html) — the final deliverable: consolidated
  P&L, cohort views, and LTV/CAC by FICO tier. Download and open in a browser.

## Pipeline

Run in order from `imprint_case/`:

```
python3 scripts/01_ingest_clean.py       # clean + classify raw data
python3 scripts/02_gap_analysis.py       # coverage/sparsity/sign-anomaly checks
python3 scripts/03_actuals_explorer.py   # throwaway gut-check charts
python3 scripts/04_curve_library.py      # vintage maturation curves + rate curves
python3 scripts/05_forecast_engine.py    # backbook + frontbook forecast
python3 scripts/06_pnl_rollup.py         # consolidated P&L + cohort LTV/CAC
python3 scripts/07_cohort_views.py       # cohort-level views for the report
python3 scripts/08_audit.py              # independent audit, separate code paths
python3 scripts/09_build_report.py       # final HTML report
```

Requires `pandas`, `numpy`, `matplotlib`. All outputs land in `output/`.

## Headline result

Portfolio-weighted LTV/CAC of **0.82x**, driven by a sharp, counterintuitive
FICO-tier inversion — see `BUILD_LOG.md` for the full explanation.
