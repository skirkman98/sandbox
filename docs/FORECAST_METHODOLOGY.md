# Forecast Methodology

## Grain

The engine forecasts at **Merchant × FICO Bucket × QSB** (Quarters Since Book — cohort age), vintage-by-vintage. Merchants with fewer than `POOL_THRESHOLD` (5) vintages of history are pooled to Merchant-only grain (`Grain FICO = "ALL"`) — too little history for a reliable FICO split. Two of ten merchants (9, 10) are pooled; their forecasts, and any FICO-tier finding built on them, are coarser as a result.

## Frontbook vs. backbook — the only two segments

No third "mid-book" tier exists here — just two:

- **Backbook** (existing cohorts, booked before Q3 2026): each driver's last actual value rolls forward QSB-by-QSB on chain-ladder development factors. Beyond a cohort's own observed range, the last known factor holds flat (backstopped by a pooled cross-merchant late-stage factor plus a hard clip).
- **Frontbook** (new cohorts, booked during the 8Q window): New Accounts sized off trailing-4Q growth (capped ±25%/quarter), split by trailing FICO mix. Every other driver's QSB=0 level is set via a seed ratio (value-per-New-Account from historical QSB=0 actuals), then grown on the *same* curve as the backbook.

**One engine, two differences**: where the starting size comes from, and where it enters the QSB curve. A mid-book split (e.g. recently-matured vs. long-seasoned backbook) isn't warranted — ~4 years of history isn't enough signal to support a third segment beyond relabeling the same curve.

## What's grounded vs. assumed

**Grounded** (computed directly from actuals, not hand-set):
- Development factors — chain-ladder ratio-of-sums, vintage-by-vintage.
- Rate curves — `rate = line item ÷ its Driver Basis`, by Merchant × FICO × QSB.
- Seasonal index — measured from actuals' own detrended quarter-of-year residuals, applied to 4 base drivers (every rate-derived line inherits it through its driver basis).
- Acquisition-cost rates — $/New Account from actuals' own QSB=0 costs.

**Assumed** (judgment-set parameters/techniques, disclosed in-code):
- `GROWTH_CAP` (±25%/q), `FACTOR_CLIP` (0.7–1.3x), `SEASONAL_CLIP` (0.5–1.6x) — hard backstops preventing thin-sample noise from compounding into unrealistic trajectories.
- `POOL_THRESHOLD`, `MATURE_QSB_THRESHOLD` — when to pool a merchant's grain or borrow a cross-merchant late-stage curve.
- `ANCHOR_RATIO_DAMPING` (0.2) — weight given to a cohort's single real anchor-quarter observation vs. the destination quarter's full seasonal multiplier.
- Applying a historical QSB=0 seed ratio to *future*, not-yet-observed frontbook cohorts.
- Every rate/factor beyond its observed range held flat — the biggest embedded assumption: no macro/rate-environment shift is in the Base Case.
- LTV: discounted (15% hurdle) cumulative Contribution Profit/account over a 12-quarter window; cohorts running past the cutoff extend via a population-level fill (the portfolio's own observed level at that age), not a compounding factor — since CP/account is signed and crosses zero.

See `docs/SCRIPTS_GUIDE.md` for ownership, `BUILD_LOG.md` for full defense of each call.
