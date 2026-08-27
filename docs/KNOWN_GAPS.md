# Known Gaps & Open Issues

Where this stands *today* — not everything here needs fixing now, but each
item is a real limitation worth having in mind when reading or extending the
forecast. Bugs already found and fixed live in `BUILD_LOG.md` and
`REVIEW_FINDINGS.md`; this is the open list only.

## Data gaps (affect forecast accuracy)

- **Fee Revenue and Other Credits have no strong driver** in this dataset
  (best correlations 0.47 and 0.19) — shipped on a best-available proxy,
  flagged not asserted. Likely governed by delinquency/behavioral fields
  (late fees, over-limit triggers) not present here.
- **FICO Bucket is origination-vintage, not current** — the model can't tell
  "still Exceptional" from "migrated since booking." Directly softens the
  FICO-tier LTV/CAC finding (the sharpest result in the model) and the
  loss-rate curves it's built on.
- **No macro or rate-environment input.** Every rate — yield, loss, funding
  cost, interchange — holds flat at its last observed value across the full
  2-year horizon. Single Base Case only; no recession or competitive-response
  scenario is layered on. The single biggest embedded assumption.
- **New-cohort Outstanding Balance doesn't fully reconcile** to a simple
  spend/payments/charge-offs identity (up to 44% at the portfolio level,
  root-caused to origination-quarter timing, not a bug — `07_audit.py` Check
  B). Directionally sound but aggregation-sensitive; finer within-quarter
  timing data would let it be modeled explicitly instead of reconciled around.
- **Merchants 9 and 10 lean on pooled, cross-merchant curves**, not their own
  late-stage behavior (4 and 2 quarters of history). Merchant 10's
  18.9%/quarter growth assumption — the steepest of any merchant — is the
  least-tested single input in the model.

## Open code issues (not blocking, worth closing before reuse)

- **`pitch_deck.html`'s stats are hardcoded**, not read from `output/` at
  build time. Verified correct as of the last pipeline run, but nothing
  catches drift after further edits.
- **Constants duplicated across files** — `FORECAST_START_IDX=14` in 5
  places, `FACTOR_CLIP=(0.7, 1.3)` in 2, tied together only by a comment, not
  a shared source.
- **`04_forecast_engine.py`'s silent `continue` fallthroughs** on missing
  lookups have no logging — pooled fallbacks and the audit layer backstop
  this today, but a coverage gap wouldn't announce itself.
- **No automated check between the dashboard's embedded JS math and
  `05_pnl_rollup.py`'s Python** — in sync today (verified by hand), but
  nothing would catch future drift if `pnl_utils.py`'s formulas change.
- **No tests, no pinned dependencies.** Fine for a 2-day build; a real gap if
  this becomes a maintained pipeline.

## Structural limitations (by design, not oversight)

- **Single Base Case, no scenario module** — recession, funding-cost shock,
  and single-merchant-exit scenarios are all unbuilt.
- **No lever/gaming sandbox** for testing business decisions (credit-line
  changes, spend-stimulation programs) against the P&L.
- **Two-segment frontbook/backbook split only**, no mid-book tier — defensible
  at ~4 years of history, but a longer series could support a finer cut.

See `docs/NEXT_STEPS.md` for what would close the data gaps, `BUILD_LOG.md`
for the full defense of each call, and `REVIEW_FINDINGS.md` for the
pre-presentation review that found and fixed the bugs not listed above.
