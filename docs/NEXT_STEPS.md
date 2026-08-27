# Proposed Next Steps

## Not yet built (from `TODO.md`)

Everything else in `TODO.md` shipped on Day 2. Two items remain:

1. **Light-touch public research** on Imprint's actual program economics/credit policy and its merchant partners (H-E-B, Rakuten, Booking.com, Shell, etc.), to sanity-check what this model infers from the data alone against what's publicly known — deliberately bounded, not a research dossier.
2. **A scenario module + a separate "gaming" sandbox** — two distinct things:
   - *Scenario module*: macro (recession — loss rates up, growth down, funding cost up) or business-event (a specific merchant exit — that book runs off, originations stop) layered on the Base Case.
   - *Gaming/lever sandbox*: tweaking business levers and watching the P&L respond (e.g. "raise frontbook credit lines," "run a spend-stimulation program") — a what-if tool, not a named scenario. Real scope additions either way (new assumption surfaces, comparison UI) — worth scoping carefully before starting.

## Data gaps and what would close them

- **Fee Revenue and Other Credits** have no strong empirical driver in this dataset (best correlations 0.47 and 0.19) — shipped on a proxy, flagged not asserted. Likely driven by delinquency/behavior fields not present here; transaction-level detail on these two line items would let a real driver be identified instead of assumed.
- **FICO Bucket is origination-vintage, not current** — the model can't distinguish "still Exceptional" from "migrated since booking," which sharpens both the loss curves and the FICO/LTV finding. A current-FICO refresh feed (even quarterly) would let both be re-cut on live credit quality.
- **No macro or rate-environment input** — every rate is held at its last-observed level into a 2-year horizon. A funding-cost/rate index and a macro indicator (unemployment, spend index) would let the "every rate held flat" assumption — the single biggest one in the model — be relaxed into an actual scenario input.
- **New-cohort balance doesn't fully reconcile** to a simple flow identity (real, explained by origination timing, not a bug — see `BUILD_LOG.md` and `07_audit.py` Check B) — more granular within-quarter timing data (when in the quarter a cohort actually books) would let this be modeled explicitly instead of reconciled around.

## The bigger opportunity

This build is a working prototype of something bigger than one case study: a standardized, driver-based, independently-auditable forecasting pattern (grounded curves + explicit assumptions + separate-code-path checks) that could generalize across every merchant program, not just this one-off model. The repo structure itself — a documented pipeline, a shared classification schema, an audit layer that catches drift automatically — is the kind of foundation a centralized finance data/modeling function would want before scaling to many programs and many analysts, rather than each program getting its own bespoke spreadsheet. Worth treating this less as a finished deliverable and more as a first concrete step toward that shared infrastructure.
