# Build Log — Imprint Corporate Finance Case Study

This is the AI-collaboration record and full written narrative for the forecasting
model in `scripts/` and the final reports in `output/html/`. It exists for two
reasons: (1) the shipped deliverable is scripts + static HTML reports rather than a
live notebook, so this doc is where the "how did the AI actually get directed"
signal lives; (2) it's the full written version of the required Narrative
(risks / winners-drags / data gaps), which the brief says can be verbal in the
debrief but is stronger written down first.

**A note on script numbers below:** this log is chronological, and the repo was
renumbered and reorganized twice along the way (into a continuous 01-14 sequence
split across `scripts/core_engine/`+`scripts/reporting/` on 2026-08-26, then
flattened back into a single `scripts/` directory on 2026-08-27 — see the final two
entries). Script names/numbers referenced in each entry below reflect what that
script was called *at the time it was written*, not necessarily its current name.
For current, authoritative script numbering, see `README.md` or
`docs/SCRIPTS_GUIDE.md`.

---

## How this was built with Claude Code

Each script was built, run, and inspected before moving to the next — not written
end-to-end and hoped into working. That loop caught two real bugs and one
mis-scoped audit check before they reached the final numbers:

1. **`01_ingest_clean.py`** — renamed `Booked Quarter`→`Vintage`, `Quarter On
   Book`→`Report Date`, added the `Quarters Since Book` (QSB) field that everything
   downstream is built on. Caught immediately: a lone `"-"` in the Value column
   (accounting convention for zero, used wherever a one-time acquisition cost or a
   charge-off doesn't apply at that grain) crashed the parser until handled
   explicitly.

2. **Line item classification** — 23 of 34 line items came pre-classified in the
   draft `line_item_classification.csv`; I proposed Family/Category for the other
   11 from sign/magnitude/row-count patterns, then **validated empirically rather
   than asserting**:
   - The given `CAC / New Account` reference line reconciles to within a 0.29%
     median difference against an independently computed CAC (sum of acquisition
     costs ÷ New Accounts) — strong confirmation the acquisition-cost
     classification is right.
   - For line items with an ambiguous driver basis (Fee Revenue, Other Revenue,
     Payment Fees, Servicing & Collections, Program Support, Other Credits,
     Royalties, Rebates), I ran correlation checks against four candidate drivers
     rather than guessing. Most came back nearly perfect (Payment
     Fees/Royalties/Rebates vs. Net Transaction Volume: r≈1.00; Other
     Revenue/Program Support vs. account counts: r≈0.99). Two didn't: **Fee
     Revenue** (best fit Outstanding Balance, r≈0.47) and **Other Credits**
     (best fit r≈0.19) — both shipped on their best available proxy but flagged
     as genuine data gaps below, not asserted with false confidence.

3. **`04_curve_library.py` / `05_forecast_engine.py`** — the driver-based
   forecasting engine (chain-ladder-style development factors + rate curves by
   Merchant × FICO × QSB, backbook anchored to last actual, frontbook sized off a
   trailing-growth trend). Two real bugs surfaced only by inspecting output, not
   by reading the code:
   - **Silent scope leak**: a loop variable tracking each cohort's "last observed
     QSB" was initialized once per cohort but mutated inside a nested loop shared
     across all line items — so every driver *after the first one processed* for
     a given cohort silently produced zero forecast rows. Total forecast rows
     jumped from 19,680 to 44,320 after the fix. Caught by checking whether a
     specific cohort's actual-to-forecast trajectory was continuous — it wasn't
     there at all.
   - **Tail-factor blow-up**: holding a merchant's own last-observed
     quarter-over-quarter growth factor constant forever compounds unrealistically
     for thin-history merchants. Merchant 10 has exactly one observed development
     factor for Net Transaction Volume (+25.7%/quarter); holding it flat for 7
     more quarters produced a 13.8x NTV blow-up and dragged the consolidated Gross
     Margin from 12.7% down to 2.1% over the forecast window — a trajectory that
     doesn't hold up against how a maturing credit portfolio actually behaves.
     Fixed by falling back to a **pooled median late-stage factor** (across all
     merchants, at QSB≥6) for any cell being extrapolated past its own observed
     range, plus a ±30%/quarter hard clip as backstop. Post-fix, Merchant 10's
     NTV growth is a more bounded 6.5x and Gross Margin is stable at ~13.2–13.4%
     throughout the forecast — this is the number that's actually in the report.

4. **`08_audit.py`** — a genuinely independent check, deliberately not importing
   any code from 04/05/06 (most checks re-derive from the raw source CSV). This
   caught a bug in itself: the CAC sanity check compared a single actual quarter's
   acquisition cost against an 8-quarter cumulative forecast cost over the *same*
   (unfiltered-by-scenario) New-Accounts denominator, manufacturing a false "10.2x
   deviation" alarm on Merchant 10. Manual reconciliation showed the real
   per-account CAC is identical ($83.43) in both periods. Fixed by scoping the
   denominator to match the numerator's scenario.

5. **Parallel independent audit** — a second, separately-scoped agent (given the
   `code-reviewer.md` persona for its final report format) ran concurrently to
   keep pressure-testing the build rather than relying on the same process that
   built the numbers to also grade its own homework. It found a real, more
   consequential problem than anything Checks A-D above had caught:

6. **The LTV extrapolation had two compounding problems, one masking the other.**
   - *Root cause*: `Partner Signing Bonus` — a one-time, per-merchant cost tagged
     to the "Exceptional" FICO row in the raw data — has `Model Role =
     Acquisition-Cost` but `Category = Operating Expense`. `classify_pnl_bucket`
     keyed off Category, not Model Role, and was duplicated near-identically in
     `06_pnl_rollup.py` and `07_cohort_views.py` — so both copies leaked this
     one-time cost into recurring Contribution Profit, even though
     `line_item_classification.csv`'s own notes column said explicitly to
     exclude it. This corrupted the QSB=0 Contribution-Profit-per-Account for
     every merchant's Exceptional-FICO cohort by $187-$542.
   - *Deeper issue*: the LTV extrapolation used the same multiplicative
     chain-ladder development-factor technique as the driver forecast (04/05).
     That's the right tool for volumes/balances, which never cross zero — it's
     the wrong tool for Contribution-Profit-per-Account, a signed quantity that
     legitimately crosses zero every cohort's life. Even with the classification
     bug fixed, Merchant 7's genuinely-observed QSB0→1→2→3 factors (3.47x,
     3.14x, 1.95x — each individually unremarkable for a near-zero-crossing
     $/account figure) compounded into 40x+ LTV/CAC for the newest, 1-quarter
     cohorts once multiplied together in sequence.
   - *Fix*: `pnl_utils.py` now checks Model Role first (fixes the root cause and
     removes the duplication that let the same bug ship twice); the
     extrapolation itself was redesigned from a multiplicative factor to a
     **population-level fill** (`build_cp_population_curve` / `extend_cp_curve`
     in `06_pnl_rollup.py`) — a thin cohort's missing quarters are filled with
     "what did this kind of cohort typically look like at that age" (a level),
     not "grow the last known value by X%" (a compounding factor), which cannot
     blow up the same way. Post-fix, the newest (1-quarter) cohorts' LTV/CAC
     ranges 0.01x-3.0x — plausible — versus -20x to +42x before. A new audit
     check (`08_audit.py` Check E) independently recomputes LTV magnitude for
     every cohort via fresh code as a standing regression guard against this
     bug class recurring.

Net effect: three silent, output-changing bugs and one false-positive audit
alarm, none of which were visible from reading the code — all four were only
caught by treating "the number looks plausible" as insufficient and tracing it
back to source, and the most consequential one (#6) was only caught because a
second, independently-scoped reviewer looked at output the first pass had
already decided was fine.

---

## Methodology decisions worth defending explicitly

- **Driver-based architecture.** Only 10 of the 34 line items are forecast as
  independent "drivers" (volumes/balances/counts). Every recurring $ line is
  `historical rate × forecasted driver`, with the rate itself built as a QSB-indexed
  curve rather than a single flat number — so a genuinely flat rate (yield, ~6.05%
  quarterly regardless of vintage age) and a genuinely curving one (loss rate,
  which rises steadily from 0% at origination toward a plateau near QSB 9–13) both
  fall out of the same mechanism without hand-coding which is which.
- **Backbook vs. frontbook, one engine.** Existing cohorts are anchored to their
  last actual value and rolled forward on the population's development-factor
  curve; new cohorts (booked during the forecast window) are seeded from a
  trailing-4-quarter New Accounts growth trend (capped at ±25%/quarter) and then
  grown on the *same* curve. The only difference between the two books is where
  the starting size comes from.
- **LTV**: discounted (15% annual hurdle, ≈3.56%/quarter) cumulative Contribution
  Profit per account over a **standardized 12-quarter (3-year) window**, so a
  brand-new cohort and a 14-quarter-old one are compared on equal footing. Cohorts
  whose window runs past the Q2 2028 forecast cutoff are extended using a
  **population-level fill** — a missing quarter is filled with the merchant's own
  (or, failing that, the portfolio's) average Contribution-Profit-per-Account at
  that age, not grown from a compounding factor. See item 6 above for why: a
  multiplicative chain-ladder factor (the right tool for the driver forecast's
  volumes/balances) is the wrong tool for a signed, zero-crossing $/account
  measure, and an earlier version of this model used one anyway.
- **Roll-forward identity as a QA check, not the primary engine.** Beginning
  Outstanding Balance + Net Transaction Volume + Principal Payments + Charge Offs
  (the last two already signed negative) should approximate Ending Outstanding
  Balance. It reconciles to within 5% for cohorts continuing from a prior
  quarter, but the whole-portfolio gap runs up to 44% because a newly-originated
  cohort's Outstanding Balance substantially exceeds its own first-quarter NTV
  net of payments/charge-offs — new accounts carry balance from day one in a way
  this simple identity's inputs don't fully capture. Real and explained, not a
  modeling error; used as a reconciliation signal, not as how Outstanding Balance
  is actually forecast.

---

## Additional audit checks (post-publish)

Two more checks were run against the published pipeline, after the repo was
already on GitHub — one became a permanent automated check (Check F), the
other is a static-analysis pass that doesn't re-run against changing data so
it's recorded here instead.

### Check F — independent trend cross-check (`08_audit.py`)

The simplest possible outside forecasting method: a plain least-squares linear
regression on actual historical Gross Revenue, with no cohort/vintage/FICO
structure at all. Cross-validated during development against the
finance-analyst skill's `forecast_builder.py` trend analysis, which produced
an identical fit (slope ≈$9.26M/quarter, r²=0.929) on the same 14 actual
quarters — confirming the regression itself, independent of which tool runs
it.

| Quarter | Naive linear trend | This model | Divergence |
|---|---|---|---|
| Q3 2026 | $113.6M | $129.6M | +14.0% |
| Q4 2026 | $122.9M | $144.4M | +17.5% |
| Q2 2027 | $141.4M | $176.1M | +24.6% |
| Q4 2027 | $159.9M | $211.2M | +32.1% |
| Q2 2028 | $178.4M | $250.6M | +40.4% |

The divergence *growing* over the horizon is expected, not a red flag: a
linear trend adds a constant dollar amount per quarter and mechanically
cannot compound, while this model assumes a decelerating but still-compounding
~9–11% QoQ growth rate. Comparing a non-compounding method against a
compounding one will diverge more the further out you go, by construction.
The check that actually matters — and the one Check F automates — is the
*first* quarter: the model's near-term growth rate (11.5% QoQ) sits
comfortably inside the range the last few actual quarters actually did (13%,
42%, -1%, 25%), so it isn't assuming a break from recent behavior, just a
smoother continuation of it. Check F flags a FAIL only on a sign flip or a
>50% gap in that first quarter specifically (a real seed/sign/unit bug would
show up immediately, not as a slow-building gap) — it passed at +14.0%.

### Code quality review (`engineering-skills:code-reviewer`)

Ran the bundled PR analyzer, code quality checker, and review report generator
against `scripts/`. Two tool-chain caveats surfaced before the actual
findings: `pr_analyzer.py` needs a diff between branches and this repo has a
single commit, so it correctly reported "no changes" rather than anything
about code quality; `review_report_generator.py` has a real schema bug — it
looks for a flat top-level `issues` key that `code_quality_checker.py`'s
actual JSON output doesn't have (findings are nested under `files[].smells[]`
instead), so it silently reported a false 100/100 "Approve" with zero issues
regardless of the underlying findings. Findings below are from
`code_quality_checker.py` directly, which does not have this bug.

**Overall: 89.6/100 average, grade B, 0 SOLID violations** — per the skill's
own rubric (90+/no-high = Approve; 75+/≤2-high = Approve with suggestions),
this is an **Approve with suggestions**, nothing blocking.

| File | Score | Real finding (after discounting magic-number noise) |
|---|---|---|
| `05_forecast_engine.py` | 68 (D) | **Real**: `forecast_drivers` (79 lines, complexity 15) and `get_factor`/`get_rate` (6 params) — this is the file that hid both real forecasting bugs earlier, and that complexity is plausibly why |
| `08_audit.py` | 76 (C) | `series_for`, `check_c_seam_continuity`, and a duplicated `bucket` classifier flagged for length/complexity — but the `bucket` duplication is *intentional*: 08's whole design principle is "don't import 04/05/06, recompute independently," so consolidating it would defeat the audit's purpose |
| `01_ingest_clean.py` | 92 (A) | `parse_value` complexity 11 (parses `$`, `()`, `,`, `%`, and `-`-as-zero in one function) — minor |
| `06_pnl_rollup.py` | 97 (A) | One false positive: the long explanatory comment documenting the LTV bug fix (item 6 above) was misflagged as commented-out code |
| `09_build_report.py` | 63 (D) | All magic-number noise — hex color literals like `898781` parsed as decimal numbers, chart-dimension constants — not a real issue for a report-styling script |
| everything else | 100 (A) | Clean |

Manual security/hygiene sweep (the skill's universal + Python checklists) was
clean across the board: no `eval`/`exec`, no `pickle`, no hardcoded secrets, no
`shell=True`, no bare `except:`, no mutable default args. The 67 `print()`
calls the checklist flags as a general risk signal are appropriate here —
these are interactive CLI scripts meant to show progress, not a service
leaking debug output.

If there's polish time before the interview, `forecast_drivers` in
`05_forecast_engine.py` is the one function worth an actual decomposition
pass; everything else here is cosmetic.

---

## Narrative

### The 3 biggest risks to this forecast

1. **Thin-history extrapolation on the newest merchants.** Merchants 9 and 10 have
   only 4 and 2 quarters of actual history — nowhere near enough to observe their
   own late-stage vintage behavior. Their forecasts lean on pooled cross-merchant
   development curves rather than anything specific to their own book. Merchant
   10's New Accounts growth assumption (18.9%/quarter, the steepest of any
   merchant, off a 2-point trend) is the single least-tested assumption in this
   model — small changes in the growth-trend window would move Merchant 10's
   forecast materially.
2. **FICO-tier reward/interest economics may be structurally mispriced — or the
   model may be over-reading a real but narrower pattern.** LTV/CAC is sharply
   divergent by FICO tier and inverted from intuition: Poor (2.94x) and Fair
   (2.39x) are strongly profitable to acquire, Good (1.17x) sits in between; Very
   Good (0.29x) and Exceptional (-0.32x) are weak-to-value-destructive. The
   mechanism is real and traceable in
   the data (Exceptional-tier customers at Merchant 1 pay $91,497 in rewards on
   $274,600 revenue — 33% — against Poor-tier's $4,001 on $139,200, 2.9%, while
   Poor's much higher APR/yield more than offsets its higher charge-off rate) —
   but this is a portfolio-wide average across 10 merchants with different reward
   structures, and a segment this profitable/unprofitable would be a notable
   surprise if it weren't already known internally. Worth validating against
   Imprint's actual unit-economics view before acting on it, not just accepting
   the model's read.
3. **Every rate is held at its most recently observed level into a 2-year
   horizon.** Yield, loss rate, interchange rate, rewards rate — none of them
   have a macro or competitive-response assumption layered on. A rate-environment
   shift (funding cost, a competitor's rewards move, a recession's effect on loss
   curves) isn't in this Base Case at all. This is a single-scenario model; the
   "build multiple scenarios" extension from the original planning notes didn't
   make it into the 2-day build and is the most obvious next increment.

### Which merchants contribute the most, and which are drags

Ranked by forecast-period (Q3'26–Q2'28) Contribution Profit:

| Rank | Merchant | Contribution Profit | Contribution Margin |
|---|---|---|---|
| 1 | Merchant 4 | $42.4M | 19.6% |
| 2 | Merchant 1 | $37.3M | 11.8% |
| 3 | Merchant 5 | $30.6M | 25.3% |
| 4 | Merchant 3 | $27.4M | 17.1% |
| 5 | Merchant 6 | $25.8M | 15.6% |
| 6 | Merchant 2 | $16.9M | 6.9% |
| 7 | Merchant 9 | $7.3M | 25.8% |
| 8 | Merchant 8 | $6.1M | 17.5% |
| 9 | Merchant 10 | $4.8M | 9.5% |
| 10 | **Merchant 7** | **-$0.3M** | **-0.2%** |

Merchant 4 is the strongest absolute contributor; Merchant 5 has the best margin
of any merchant with meaningful scale (25.3% — Merchant 9 is nominally higher at
25.8%, but at roughly a fifth of Merchant 5's Contribution Profit). **Merchant 7
is the one merchant that doesn't clear its own acquisition cost**, though only
marginally — roughly breakeven, not the outright structural drag it was earlier
in the build (-$11.7M / -7.0% before the seasonality-extension and Cost of Funds
driver-basis fixes documented below moved it most of the way back). Merchant 1
and Merchant 2 are worth calling out specifically: they're two of the largest,
most mature programs by revenue, but their margins (11.8% and 6.9%) are still
thin relative to smaller, higher-margin programs like Merchant 5 and Merchant 9 —
scale and unit-economics efficiency are not the same thing here, and Merchant 2
in particular still deserves scrutiny on *why* its margin is so thin despite its
size.

### Where better data would improve accuracy

- **Fee Revenue and Other Credits have no strong driver in this dataset.** Fee
  Revenue's best empirical correlate (Outstanding Balance) is only r≈0.47 —
  plausibly because fee revenue is actually driven by delinquency/behavioral
  triggers (late fees, over-limit fees) that aren't in this data at all. Other
  Credits is essentially unexplained (r≈0.19 against every candidate tested) and
  sporadic (present in only 256 of a possible 1,980 row-grain). Both are shipped
  on a best-available proxy, not a validated relationship.
- **New-cohort balance doesn't fully reconcile to a simple spend/payments/
  charge-offs identity** (root-caused: continuing cohorts tie out to within 5%,
  but a newly-originated cohort's Outstanding Balance exceeds what its own
  first-quarter NTV net of payments/charge-offs would imply, up to 44% at the
  whole-portfolio level). Real and explained, not a bug — but a general
  ledger-level balance roll-forward (every component that actually touches
  Outstanding Balance at origination, not just spend/payments/charge-offs) would
  let this be a hard reconciliation rather than a directional QA signal.
- **No macro or rate-environment input was provided.** Every rate is held flat
  from its last observed value. Even a simple forward curve or scenario toggle
  (recession, rate move) would materially change how much to trust the 2-year
  horizon, especially given Risk #3 above.
- **FICO bucket is origination-vintage, not current.** A customer's credit
  quality can drift after booking; the model has no way to distinguish "still
  Exceptional" from "originated Exceptional, has since migrated." Current-period
  behavioral score would sharpen both the loss-rate curves and the FICO-tier LTV
  finding above.

---

## Headline forecast numbers (Base Case, Q3 2026–Q2 2028, all 10 merchants)

- Gross Revenue: $1.50B
- Gross Profit: $226.2M (15.0% average Gross Margin)
- Contribution Profit: $198.4M (13.2% average Contribution Margin)
- Portfolio-weighted LTV/CAC: **0.85x** (below breakeven — driven by the FICO-tier
  dynamic above; several individual merchants and FICO tiers clear >1.9x, up to
  Merchant 5's 1.95x). *(This figure moved three times over the build — 0.82x →
  0.75x → 0.78x → 0.85x — as successive fixes landed: the weighted-average
  tie-out audit (unweighted LTV-extrapolation fill overstated the population-level
  curve by 13%-140% depending on cohort age; see "Weighted-average and independent
  tie-out audit" below), extending seasonality beyond NTV to the other 3 base
  drivers, and the Cost of Funds driver-basis fix — each documented in its own
  entry below. Gross Revenue/Gross Profit/Contribution Profit $ and margins above
  reflect the fully reconciled state after all of those fixes.)*

Full detail, charts, and the merchant/FICO cuts are in
`output/html/narrative_report.html`.

---

## Output restructure: dashboard, narrative, pitch deck

The original single `report.html` read as a narrative/story document — good for
a debrief, not for ongoing reporting. It's now three purpose-built outputs (see
`README.md`): `dashboard.html` (executive reporting, live Merchant/Vintage/FICO
filters), `narrative_report.html` (the original story document, unchanged in
substance), and `pitch_deck.html` (a presentation-style methodology walkthrough
for internal audiences who want the "how" without reading `BUILD_LOG.md` end to
end).

The dashboard needed real client-side interactivity — filtering and
re-aggregating a P&L live, not pre-rendered charts — so `10_export_dashboard_data.py`
ships a pre-aggregated dataset (6,860 rows at Merchant × Vintage × FICO × Report
Date × Scenario grain) embedded inline in the HTML, and `11_build_dashboard.py`'s
JS does the filtering, summing, and SVG rendering at view-time. Margins and
LTV/CAC are always derived from summed dollar components client-side, never
from averaging a pre-computed percentage — the same principle as the Python
pipeline's own P&L rollup, now enforced in JS too.

**A real bug, caught before shipping, by testing the JS logic against known
ground truth rather than just eyeballing it.** LTV$ and CAC$ are facts about a
*cohort* (one number per Merchant × Vintage × FICO), not a per-quarter flow —
but an initial version merged them onto every Report-Date/Scenario row of that
cohort in the exported data. Summing across a multi-quarter filter view then
counted each cohort's LTV once per quarter it appeared in, inflating the ratio
(Poor-FICO LTV/CAC came out 3.66x instead of the correct 2.97x in a JS test
run). No browser was available in this environment to catch it visually — it
was caught by extracting the pure aggregation functions from the built HTML and
running them against JavaScriptCore's command-line shell (`jsc`) with assertions
against the Python pipeline's own known-correct figures (Q3 2026 Gross Revenue,
Merchant 1 forecast totals, LTV/CAC by FICO tier, portfolio LTV/CAC). Fixed by
moving LTV$/CAC$ into a separate cohort-grain array (`DATA.cohorts`) instead of
merging them into the flow-grain `DATA.rows` — structurally impossible to
double-count once the two grains can't be conflated, rather than relying on
every consumer to remember to deduplicate.

**Visually confirmed, not just logic-tested.** The Chrome extension wasn't
connected at first, and `file://` URLs are blocked by the browser automation
tool for security reasons — worked around by serving `output/` over a local
`python3 -m http.server` and driving an actual browser against it. Confirmed:
the KPI tiles, trend chart (with the forecast-period shading), both comparison
charts, and the data table all render correctly with no console errors;
changing the Merchant filter to "Merchant 7" live-updated every panel to the
correct negative Contribution Profit (-$14.2M) and LTV/CAC (-0.19x, matching
`ltv_cac_by_merchant.csv` exactly); cross-navigation between all three HTML
documents works. The pitch deck's inline SVG architecture diagrams also render
cleanly.

---

## Narrative rebuild: slides, real charts, and dark mode everywhere

The narrative document was rebuilt from scratch (`09_build_narrative_deck.py`,
replacing `09_build_report.py`) as a slide-format financial story rather than
a single continuous page: each slide makes one point in order (today's book →
the forecast → how the book is aging → what cohort curves reveal → the
FICO-tier LTV/CAC finding → merchant winners/drags → the risks), backed by a
chart, following Shneiderman's "overview, then the story beat" logic rather
than a reference-document layout.

**Charts moved from matplotlib PNGs to static inline SVG, specifically to
support dark mode.** A raster PNG bakes in one theme's colors at render time —
it can't re-color itself for a dark background without a second render. SVG
shapes styled via `style="fill:var(--blue)"` (a CSS custom property, not a
hardcoded hex attribute) pick up whichever theme is active automatically, no
regeneration needed. All three documents now use this pattern: dashboard.html
re-renders its JS-driven SVG on theme toggle (it already re-renders on every
filter change, so this added no new mechanism); the pitch deck's diagrams and
the narrative deck's charts are static SVG that re-color for free via CSS
alone.

**A real legibility bug, caught by looking at the actual rendered chart, not
just checking it built without errors.** The trend chart's Gross Profit and
Contribution Profit lines end close together in value — their direct
end-labels rendered on top of each other, illegible. Fixed with a small greedy
vertical-separation pass (sort labels by y-position, enforce a minimum pixel
gap, nudge down as needed) applied to both multi-series chart types. A
reminder that "no console errors" and "no rendering errors" are not the same
as "actually readable" — this one only showed up in a screenshot.

**Dark mode**: added to all three documents as CSS custom properties with
three states (explicit `data-theme` attribute, `prefers-color-scheme` media
query, and a light-mode default), matching the pattern of assigning a token
once and letting every consumer — chart, chip, table border — reference it
rather than hardcoding hex. Colors are the dataviz reference palette's
documented dark-mode steps, not ad hoc darkened values. A toggle button
(top-right, all three pages) persists the choice to `localStorage` and
overrides the OS preference; visually confirmed in both themes via the same
browser-driven check as above, including the toggle actually flipping the
theme and dashboard.html's charts re-rendering with the correct dark-mode hex
values.

---

## Weighted-average and independent tie-out audit (2026-08-26)

Two more independent passes, run in parallel: (1) an exhaustive check that
every portfolio/merchant/FICO-tier average in the codebase is driver-weighted
(Σnumerator/Σdenominator) rather than a naive mean of pre-computed ratios —
prompted by this file's own earlier claim that the principle is "enforced
everywhere," which turned out not to hold exhaustively; (2) a from-scratch
reconciliation of every output file back to `data/case_study_data.csv`,
written without importing any code from `scripts/`, to catch anything a
shared bug could hide from the pipeline's own audit.

**The tie-out audit found nothing wrong** — `pnl_consolidated.csv`'s actuals
rows, `pnl_by_merchant.csv`, `clean_actuals.parquet`, the CAC-vs-reference
reconciliation (0.29% median, reproducing the earlier claim almost exactly),
`cohort_ltv_cac_by_fico.csv`/`ltv_cac_by_merchant.csv` for the 20 cohorts
whose full 12-quarter LTV window is actually observed (not extrapolated),
`cohort_balance_age_mix.csv`, and `curve_dev_factors.csv` all reproduced
exactly from raw data via completely independent code.

**The weighted-average audit found one real bug, in the one place that
mattered most.** `build_cp_population_curve()` (`06_pnl_rollup.py`) — the
function that fills in a cohort's Contribution-Profit-per-Account at any QSB
it hasn't lived long enough to observe, i.e. the LTV extrapolation mechanism
described above — computed "what a typical cohort looks like at this age" as
a flat `.mean()` of each cohort's own CP/Account ratio, not weighted by that
cohort's New Accounts. A 580-account FICO-tier cohort counted the same as a
14,958-account one. Verified independently before fixing: the naive mean
overstated the true accounts-weighted value by **13%-140% depending on QSB**
(worst at the earliest ages, exactly where the thinnest cohorts — Merchants
9 and 10 — lean on this fill the most). The identical bug was independently
re-derived from scratch in `08_audit.py`'s Check E (the check specifically
designed to *not* import 06's code so a shared bug can't hide from it — it
didn't share the bug, it reintroduced it separately), and a much smaller,
currently-immaterial version of the same anti-pattern (an unweighted mean of
8 quarterly margin percentages instead of Σ Contribution Profit/Σ Gross
Revenue) was found in `09_build_narrative_deck.py`'s `avg_cm` stat.

**Fixed in all three places** — `06_pnl_rollup.py`, `08_audit.py`, and
`09_build_narrative_deck.py` now all weight by the cohort's New Accounts (or
Gross Revenue, for the quarterly margin case) before averaging. Pipeline
rerun end-to-end; every downstream number that depends on the LTV
extrapolation curve moved:

| Figure | Before | After |
|---|---|---|
| Portfolio LTV/CAC | 0.82x | **0.75x** |
| Merchant 7 LTV/CAC | -0.19x | **-0.51x** |
| Merchant 2 LTV/CAC | 0.45x | **0.31x** |
| Merchant 1 LTV/CAC | 0.75x | **0.66x** |
| Merchant 5 LTV/CAC (highest) | 1.92x | **2.07x** |
| Exceptional-FICO LTV/CAC | -0.39x | **-0.47x** |
| Very Good-FICO LTV/CAC | 0.24x | **0.16x** |
| Newest (1-quarter) cohorts' LTV/CAC range | 0.01x to 3.0x | **-0.53x to 3.57x** |

Nothing else moved: Gross Revenue/Gross Profit/Contribution Profit dollar
figures, the P&L margins, `audit_results.csv`'s pass/fail statuses (still
5/6, Check B's explained FAIL unchanged), and every actuals-groundable
number the tie-out audit checked are all untouched, since none of them
depend on the LTV extrapolation curve. The direction of every finding this
model has already leaned on (FICO-tier inversion, Merchant 7 as the clear
structural drag) got *stronger*, not weaker or reversed — this was a
magnitude correction, not a different conclusion. `dashboard.html` and
`narrative_report.html` picked up the corrected numbers automatically on
rerun (both compute live/at-build-time from the regenerated CSVs/JSON);
`pitch_deck.html`'s hardcoded LTV/CAC stat tiles were updated by hand to
match, since that file (a known, separately-flagged issue) doesn't read from
`output/` at build time.

---

## Day 2 — Exceptional-FICO magnitude validation (2026-08-26)

Direction of the Exceptional-FICO finding (Risk #2 above) was never in
question; only whether the *size* of the effect — Merchant 1's most mature
cohort paying $91,497 in rewards on $274,600 revenue, 33% — held up beyond
the one traced example, or was cherry-picked by which cohort got looked at.
New diagnostic script: `scripts/13_validate_exceptional_fico.py`
(deliberately independent of `pnl_utils.py`/`06_pnl_rollup.py`, same
discipline as `08_audit.py`). **No bug found — the finding is confirmed and,
if anything, understated.** No pipeline code changed.

**1. Hand-derivation, 3 more merchants.** Each merchant's own most mature
observed cohort (not a fixed QSB — Merchant 1 is the only one old enough to
reach QSB 13; Merchants 4/5/7 launched 5/6/8 quarters later, so their own
ceilings are QSB 8/7/5):

| Merchant | Cohort | Exceptional rewards/revenue | Poor rewards/revenue | Exceptional CP | Poor CP |
|---|---|---|---|---|---|
| Merchant 1 | Vintage 0, QSB 13 | 33.3% | 2.9% | -$28.7K | +$34.0K |
| Merchant 4 | Vintage 5, QSB 8 | 37.0% | 3.6% | -$17.9K | +$69.8K |
| Merchant 5 | Vintage 6, QSB 7 | 33.0% | 3.1% | -$5.2K | +$51.1K |
| Merchant 7 | Vintage 8, QSB 5 | 41.6% | 5.0% | -$79.9K | +$9.9K |

Exceptional-tier customers pay **8.3x–11.6x** Poor-tier's rewards burden as a
share of revenue at every merchant checked, and Contribution Profit is
negative for Exceptional / solidly positive for Poor in all four — the
pattern isn't specific to Merchant 1. Full table:
`output/exceptional_fico_hand_derivation.csv`.

**2. Systematic outlier scan.** Within-FICO-tier z-scores (|z|>2.5) on
independently-recomputed 12Q undiscounted CP/Account found no outliers
driving the Poor/Fair tiers, a handful in Good/Very Good/Exceptional — all
traced to **Merchant 7** (already flagged as the portfolio's one clear
structural drag) and **Merchant 10** (thinnest history, 2 vintages), not to
any broad pattern across merchants. The Rewards *rate curve itself* has zero
single-QSB outliers at any merchant/FICO combination — the elevated
Exceptional rate is a stable level shift across the whole curve, not one
anomalous quarter skewing an average.

**3. Rewards-rate assumption sanity check.**
- **Classification confirmed correct**: `Rewards` is `Family=Expense,
  Category=Rewards, Model Role=Rate-Derived`, routing to Cost of Sales via
  `pnl_utils.py` exactly as the case brief specifies ("Rewards ... Cost of
  Sales per brief" in `line_item_classification.csv`) — not a
  Partner-Signing-Bonus-style Category/Model-Role mismatch.
- **New finding worth stating explicitly**: Merchants 9 and 10 (pooled to
  Merchant-level curves for thin history, per `04_curve_library.py`'s
  `POOL_THRESHOLD`) apply a single blended Rewards rate across **all** FICO
  tiers (`Grain FICO = "ALL"`), not an Exceptional-specific one. For these
  two merchants, the rewards-heavy-Exceptional mechanism isn't actually
  modeled — whatever FICO-tier spread shows up in their forecast LTV/CAC
  comes only from differing volume drivers (NTV, Active Accounts) by tier,
  not from a differentiated rate. **The portfolio-wide Exceptional-FICO
  finding is driven entirely by the 8 FICO-specific merchants; Merchants 9
  and 10 dilute it rather than reinforce it** — worth saying this precisely
  if asked whether the finding holds "across the whole portfolio," since it
  technically doesn't apply as a rate effect for 2 of the 10 merchants.
- **The "held flat" rate is a stable plateau, not a noisy single point**:
  trailing-4-quarter range on the Exceptional-tier Rewards rate spans only
  1.0%–4.7% of its own mean across every FICO-specific merchant — the flat
  extrapolation is well-supported by recent history, not resting on one
  volatile observation.

**Bottom line for the debrief**: safe to keep leaning on this finding as
stated, with one added nuance — call it an 8-merchant pattern (all
FICO-specific merchants show it, magnitude consistently 8x-12x), not a
literal 10-merchant one, since Merchants 9/10's rate curves don't
differentiate by FICO tier at all.

---

## Day 2 — Seasonality (2026-08-26)

The forecast engine indexes purely by QSB (cohort age) — there was no
calendar-quarter notion anywhere in the curve/rate library, so a real Q4
holiday spend spike or Q1 paydown dip would either be invisible to the model
or smeared into the age-based curve. Per the TODO's own instruction: confirm
the pattern is real and material *before* designing a fix.

**New diagnostic**: `scripts/14_seasonality_analysis.py`. Method: index each
cohort's own Net Transaction Volume series to its own QSB=0 value (removes
cohort size), divide by a pooled expected age-curve at that QSB (removes
age), collapse to one weighted-average residual per *actual calendar
quarter* (not per cohort-row — cohorts alive in the same calendar quarter
aren't independent trials, so testing at row-level would be
pseudo-replicated), then group those ~13 points by quarter-of-year.
Materiality threshold (swing > 7%, >= 50% of merchants with >= 8 actual
quarters agreeing on the peak quarter) was set before looking at results.

**Verdict: material and reliable, by a wide margin.**

| Quarter-of-year | Mean residual (index, 1.0 = age-curve-expected) | n |
|---|---|---|
| Q1 | 0.682 | 3 |
| Q2 | 1.051 | 4 |
| Q3 | 1.128 | 3 |
| Q4 | 1.537 | 3 |

An 85% peak-to-trough swing, and — more convincing than the pooled number
alone — **all 5 merchants with enough history to check (Merchants 1-5) agree
Q4 is the peak and Q1 the trough**, a clean monotonic Q1→Q2→Q3→Q4 shape in
every one of them. This matches the obvious business-logic prior for a
consumer card portfolio (Q4 holiday spending surge, Q1 post-holiday paydown
dip) closely enough, and is consistent enough across independent merchants,
that it reads as a real effect rather than noise or a detrending artifact —
even though the underlying sample (~3-4 calendar-quarter-of-year
observations per bucket, ~4 years of history) is genuinely thin and this
should be stated as such whenever the seasonal curve comes up.

**Implemented**: two-factor decomposition, `driver(QSB, quarter) =
f(QSB) x s(quarter_of_year)`, layered on top of the existing engine rather
than redesigning it (the TODO's own recommended approach given the thin
sample, and the one used here).
- `scripts/04_curve_library.py`: `build_seasonal_index()` — same
  detrend-and-residual method as the diagnostic script (independently
  re-implemented, not shared code), pooled across **all** merchants (not
  per-merchant — splitting an already-thin ~4-per-bucket sample further
  isn't defensible), normalized so the 4 multipliers average to 1.0 (reshapes
  the year without changing the annual total), clipped to **[0.5, 1.6]**.
  This clip band is deliberately wider than the ±20%-style guard used
  elsewhere in this codebase (e.g. `FACTOR_CLIP`) — that generic band exists
  to suppress a *noisy, thin* estimate toward 1.0; this estimate is unusually
  strong and cross-merchant-consistent, so a tight clip would have actively
  suppressed a real signal rather than guarded against a fake one. The actual
  estimated multipliers (0.620 / 0.956 / 1.026 / 1.398) sit comfortably
  inside the band unclipped.
- `scripts/05_forecast_engine.py`: applied **only** to Net Transaction Volume
  (it's the Driver Basis for 7 of the 16 Rate-Derived line items —
  Interchange, MDR, Rewards, Royalties, Rebates, Payment Fees, 3rd Party
  Fraud — so the signal propagates into all of them automatically; applying
  it again on those rate-derived lines would double-count), and **only** on
  forecast-period rows (actuals already contain real seasonality — they're
  never touched). For backbook cohorts (rolling an existing cohort's real
  last-actual value forward), each QSB-advancing step gets multiplied by
  `s(destination quarter) / s(source quarter)` — this specifically
  normalizes away whatever real seasonal level the anchor observation already
  carried (e.g. an anchor observed in an actual Q4 shouldn't get Q4's boost
  applied a second time) and replaces it with the correct target-quarter
  level; the per-step ratios telescope correctly regardless of how many QSB
  steps a cohort takes. For frontbook cohorts (brand-new, sized off trailing
  growth trend), the QSB=0 baseline is multiplied directly by
  `s(launch quarter)`, since the seed ratio it's built from already pools
  across vintages launched in every calendar quarter and is itself close to
  seasonality-neutral.
- `scripts/08_audit.py`: new **Check G** — independently re-derives the same
  4 multipliers from raw actuals (separate code path, not imported) and
  confirms they match what shipped, sit inside the clip band, and average to
  exactly 1.0. **PASS.**

**Impact**: full pipeline rerun end-to-end. The forecast now shows a visible
Q4-peak/Q1-dip saw-tooth quarter to quarter (e.g. Q4 2026 Gross Revenue
$165.0M vs. the adjacent Q1 2027's $141.6M) that the pre-seasonality
forecast smoothed away entirely. Headline annual totals barely moved, as
designed (the 4 multipliers average to 1.0, so reshaping within a year
doesn't change the year's sum) — small residual drift comes from second-order
interactions (seasonally-adjusted NTV feeding into frontbook sizing and
downstream rate-derived lines across quarter boundaries), not from a level
shift:

| Figure | Before | After |
|---|---|---|
| Gross Revenue (8Q forecast) | $1.500B | $1.502B |
| Gross Profit / margin | $198.6M / 13.3% | $198.1M / 13.2% |
| Contribution Profit / margin | $170.8M / 11.4% | $170.3M / 11.3% |
| Portfolio LTV/CAC | 0.75x | 0.75x |

**Caveat for the debrief**: this is a real, cross-merchant-consistent signal,
but it's estimated from only ~4 years of history — treat the specific
multiplier values (especially the 1.40x Q4 peak) as directionally right, not
precision-fitted, and say so if asked. `output/seasonality_quarter_of_year_residuals.csv`
and `output/curve_seasonal_index.csv` have the full detail.

**Known scope gap, surfaced honestly rather than hidden**: seasonality was
applied to Net Transaction Volume only, not to Outstanding Balance or other
balance/stock drivers — that's a real internal inconsistency, not an
oversight. `08_audit.py`'s Check B (roll-forward identity, already a known,
explained FAIL) makes this visible on its own: the continuing-cohort gap
that check flags stays under 1.5% throughout the actuals period (untouched
by this change) but widens to as much as ~24% specifically in forecast
quarters with the largest seasonal swings (Q4 peak, Q1 trough) — because NTV
now moves ±40% by calendar quarter while Outstanding Balance still rolls
forward on its own smooth, non-seasonal curve. In reality, Outstanding
Balance almost certainly has its own real seasonality (post-holiday balance
buildup and paydown is a well-known card-portfolio pattern) — extending the
same two-factor treatment to Outstanding Balance (and possibly Revolve
Balance) would be the natural next increment, deliberately left out of scope
here to keep the Day 2 fix layered and contained rather than touching every
balance-driven line item at once. Check B's audit message now reports the
actuals-vs-forecast split explicitly so this doesn't read as a regression if
someone reruns the audit and sees the number moved.

---

## Day 2 — Full-detail P&L dashboard view (2026-08-26)

TODO item 4: a traditional, full-detail P&L view on `dashboard.html` — all 33
raw line items (not just the 4 shipped P&L buckets), for anyone who wants to
audit the rollup rather than take the 4-bucket summary on faith.

**Shared prerequisite, done once for this item and item 7 together**:
`scripts/10_export_dashboard_data.py` previously exported only the 4 P&L
bucket totals + New Accounts per row. Rewritten to also ship a `detail`
array at the same grain, keyed by short abbreviations (extends the existing
`gr`/`cos`/`opex`/`acq`/`na` convention — e.g. `ntv`, `os`, `rw`), with a
`dims.lineItemKeys` legend (label + `Aggregation`: Flow/Stock + `Unit`: $/Count
per item) and a `dims.lineItemGroups` list giving the traditional statement
order directly, so `11_build_dashboard.py` doesn't re-derive grouping logic
in JS. Also added a `data/line_item_classification.csv` `Aggregation` column
(Flow/Stock) and a `Unit` column ($/Count) — the authoritative source both
this export and any future consumer should read from, rather than
hardcoding which line items are counts vs. dollars in JS.

**The one real design risk, and how it was avoided**: `Total Accounts`,
`Outstanding Balance`, `Revolve Balance`, and `EoP Interest & Fees Balance`
are STOCKS (period-end snapshots) — summing them across a multi-quarter
filter range would be meaningless, the same bug class the `cohorts` array
already exists to prevent for LTV/CAC (see that array's own note above).
Fix: the detail table is rendered **transposed** — line items as rows,
quarters as columns — so the only summing that ever happens is *across
entities (merchants/vintages/FICO tiers) within one quarter*, which is
always valid for a stock, never *across quarters*, which wouldn't be. Stock
line items are marked with `*` in the UI as a visible reminder even though
the layout makes the wrong operation structurally unavailable, not just
discouraged.

**Scope resolution on the "34 raw line items" wording**: `CAC / New Account`
(the 34th row of the classification CSV) is an `Excluded-Metric` pre-computed
reference ratio — including it in a summable array would violate this
project's core "never sum a pre-computed ratio" invariant (the same one
`derivePnl()` already enforces for margins). Shipped the other 33 in
`detail`; the reference figure isn't surfaced in this view (it exists to
reconcile CAC against the source data's own figure, already done once in
`08_audit.py` Check D, not to be re-derived per filter combination).

**JSON size**: measured, not guessed. The new `detail` array plus a
precomputed `bos` (Beginning Outstanding Balance) lag field (see item 7 below)
brought `dashboard_data.json` from 1.2MB to 4.8MB — a real but sub-linear
multiplier, still comfortably in the range where a plain inline array in a
`file://`-opened static HTML page stays responsive. Shipped as one inline
array; no lazy-fetch needed. The detail `<section>` itself is still
lazy-*rendered* (the JS only populates the table's DOM when the `<details>`
disclosure is actually opened) since it's an appendix view most visits won't
expand, and rebuilding a 33-row x ~22-column table on every filter change for
a collapsed section would be pure waste.

**UI**: `<details><summary>Show detailed line items (all 33, audit
view)</summary>` under the existing "Quarterly P&L detail" table, collapsed
by default. Grouped in the traditional order (Volumes & Balances → Revenue →
Cost of Sales → Operating Expense → Acquisition Cost), sticky first column
and sticky header for a wide/tall table, same Merchant/Vintage/FICO/Period
filter reactivity as the rest of the page. Count-type line items (New
Accounts, Total Accounts, In-Month Active Accounts) render as plain
integers, not `$`-prefixed — an earlier draft used the dollar formatter
uniformly and mislabeled account counts as dollar amounts, caught in visual
QA and fixed by threading the new `Unit` field through instead of hardcoding
which 3 line items are counts in JS.

**Verified**: pipeline rerun end-to-end (`08_audit.py` still 6/7, no new
fails); visual QA via claude-in-chrome — expanded the section, confirmed
group order and the traditional Volumes→Revenue→COS→OpEx→AcqCost sequence,
confirmed New Accounts/Total Accounts/Active Accounts show as counts (e.g.
23,883, matching the existing summary table's own New Accounts column
exactly) while every other line item shows `$`, confirmed the forecast
period's seasonal saw-tooth (Day 2's seasonality change, above) is visible
in Net Transaction Volume's columns, filtered to Merchant 7 and confirmed
every column dropped to that merchant's own (much smaller) scale with no
console errors.

---

## Day 2 — Driver KPI dashboard tab (2026-08-26)

TODO item 7: a new dashboard section for portfolio driver KPIs beyond the
P&L-centric views already shipped — Payment Rate, PPAA, Active Rate, Revolve
Rate, NIM, Revenue Margin. **PPAA = Net Transaction Volume ÷ In-Month Active
Accounts** (spend per active account) was already settled before this item
started — not revisited.

**Loaded `finance-skills:financial-analyst` first**, per the TODO's own
instruction. It doesn't cover card-portfolio metrics directly (Payment Rate,
PPAA, Revolve Rate aren't standard corporate ratios), but its own worked
formulas are informative on one specific point: Inventory Turnover is
defined as `COGS / Average Inventory` (average, not period-end) while
Asset/Receivables Turnover use plain period-end balances — i.e. this skill's
own convention is "average the balance specifically when a flow is being
compared against a balance that moves materially within the period," which
supports averaging for NIM below. Payment Rate and PPAA aren't covered by
this generalist skill at all; those conventions come from standard
card-portfolio/ABS trust-reporting practice instead — flagged explicitly
since the instruction was to confirm via finance-skills and this genuinely
falls outside its scope.

**Formulas shipped** (all sum-then-divide from this quarter's own summed
components — same invariant as `derivePnl()`/the detail table, never an
average of other quarters' or cohorts' pre-computed ratios):
- **Payment Rate** = Principal Payments ÷ **Beginning** Outstanding Balance.
  Beginning (not average) balance is the standard card-ABS/trust-reporting
  convention for "monthly/quarterly payment rate" specifically — this is a
  deliberate departure from the generic average-balance pattern above,
  because Payment Rate has its own well-established domain convention that
  overrides the generalist default.
- **Active Rate** = In-Month Active Accounts ÷ Total Accounts (both
  point-in-time snapshots, no averaging needed).
- **Revolve Rate** = Revolve Balance ÷ Outstanding Balance (same quarter,
  stock ÷ stock).
- **NIM** = (Interest Revenue − Cost of Funds) ÷ **average** Revolve Balance
  — Revolve Balance (not total Outstanding Balance) is the earning-asset
  base, since only revolving balance actually accrues net interest margin
  (transactor/non-revolving balance drives interchange, not NIM); averaged
  per the finance-skills pattern above and standard bank NIM convention
  (`NII / average earning assets`).
- **Revenue Margin** = (Interest + Interchange + MDR + Fee + Other Revenue)
  ÷ Net Transaction Volume — i.e. the same 5 line items that already sum to
  the shipped "Gross Revenue" bucket, divided by spend volume ("revenue
  yield on spend," the natural card-issuer program-economics framing, vs.
  ÷ Outstanding Balance which would overlap with what NIM already covers).

**New precomputed fields** (`scripts/10_export_dashboard_data.py`): `bos`
(Beginning Outstanding Balance) and `brb` (Beginning Revolve Balance), both
a `groupby(cohort).shift(1)` lag on Report Date Index — done in Python, not
client-side JS, for the same "temporal joins over a flat array are
error-prone in JS" reason as everything else in this export. A cohort's very
first quarter has no prior value (NaN → 0 via the existing `safe_round`
guard) — this correctly and consistently excludes that quarter's brand-new
originations from the "beginning balance" base, the same treatment
`08_audit.py` Check B already gives new-cohort originations in its
roll-forward identity, not a new inconsistency.

**Display: trend-lines only** (confirmed with the user before building) —
6 small-multiple line charts, not blended KPI tiles. Most of these ratios
have a stock/snapshot denominator that can't be honestly collapsed across an
arbitrary multi-quarter filter range the way Gross Revenue/Contribution
Profit can; a trend line sidesteps that since every point is just that
quarter's own value. Also sets up the mark-type rule ("lines for rate
metrics") for item 6, next.

**A genuinely useful side effect, not designed for but worth noting**: with
the Exceptional FICO tier filter applied, NIM comes out to ~0.1% (vs. ~3.1%
portfolio-wide) — a clean, independent cross-confirmation of the
Exceptional-FICO validation earlier in this log (low-revolve customers
generate almost no net interest margin, consistent with the "rewards-heavy,
low-revolve" mechanism already described there).

**New audit check**: `08_audit.py` Check H independently recomputes PPAA and
Payment Rate for Q3 2026 (all merchants pooled) straight from
`combined_actuals_forecast.parquet` — not from `dashboard_data.json`, which
would just check the export script against itself — and confirms an exact
match against what shipped. **PASS**, 0.000% diff on both. Audit now 7/8
(Check B's explained FAIL unchanged).

**Verified**: hand-derived both KPIs in Python against the raw parquet
before wiring into JS (matched to machine precision, then codified as Check
H above); visual QA via claude-in-chrome — all 6 charts render with sane
values, switching the FICO filter to Exceptional reproduces the NIM
cross-check above, switching back to "All merchants" and re-checking KPI
tiles/LTV-CAC still reproduces the already-known headline numbers exactly
(no regression), no console errors.

---

## Day 2 — Multi-select comparison chart (2026-08-26)

TODO item 6, the last of today's five: replace the two static single-metric
"Contribution Profit by merchant" / "by FICO tier" bar charts with a
general-purpose comparison chart — multi-select on Merchant, Vintage, or
FICO, any metric (not just Contribution Profit), rendered as a time series
with a computed blended total.

**Scoped narrower than a literal reading of "make the top filter bar
multi-select,"** deliberately: the new chart has its own dimension picker
and its own multi-select checkboxes, layered on top of the existing global
Merchant/Vintage/FICO/Period filters (reusing the same `skipMerchant`/
`skipFico` pattern the old charts already used, plus a new `skipVintage`
option added to `matchesFilter` the same way). Rewriting the whole page's
top filter bar to multi-select would have touched every other section (KPI
tiles, trend chart, detail table, driver KPIs) for a change item 6 doesn't
actually ask for — TODO item 6 talks about "several series on one chart
instead of one aggregate line," which is about the comparison chart
specifically, not the whole page's interaction model. Lower blast radius,
same result for what was asked.

**Design:**
- "Compare by" picks the dimension (Merchant / Vintage / FICO); a
  metric picker spans the same registry as item 7 (P&L buckets + the 6
  driver KPIs, ~12 entries) — `METRIC_REGISTRY`, each entry carrying its own
  `source` (`DATA.rows` or `DATA.detail`), `compute`, `fmt`, and `mark`.
- **Mark type follows the metric, not a per-chart setting**: `mark: "bar"`
  for additive $ measures (Gross Revenue, Cost of Sales, Gross/Contribution
  Profit) — rendered as **grouped/clustered bars per quarter, never
  stacked**, since the compared entities are alternatives to look at side by
  side, not components that sum to a portfolio whole (stacking would
  visually misrepresent the comparison, the same correctness point flagged
  in `TODO.md`'s own item 6 text). `mark: "line"` for every rate/yield/
  per-account metric (margins, the 6 driver KPIs, including PPAA — a $
  figure but not one that sums across entities either, so it gets a line
  like the rate metrics, not a bar).
- **Blended total**: computed by feeding the *union* of matching rows across
  every selected value into the same `derivePnl`/`deriveDriverKpis`
  sum-then-divide functions already in place — no new weighting math, just a
  differently-scoped row set (per the plan). Rendered as a dashed line or a
  translucent 4th/Nth bar in each cluster, only shown once 2+ values are
  selected.
- Selecting nothing shows every value in the dimension (10 merchants, 22
  vintages, or 5 FICO tiers) — the same default the old charts had.

**One real bug caught in visual QA**: the blended total's line/bar initially
reused `COLORS[0]` (the same blue as whichever entity happened to be first
in the selection), so it was visually indistinguishable from that entity
whenever it was included — e.g. selecting Merchant 1 made "Blended total"
invisible against Merchant 1's own line. Fixed by adding a dedicated
`muted` gray to the palette (matching the existing `--muted` CSS token,
same value in both themes) reserved specifically for the blended series, so
it never collides with an entity color.

**Per an explicit instruction, the old charts were kept, not deleted**: the
two old `<section>` blocks are still in `11_build_dashboard.py`'s HTML
template, commented out (with a note on exactly what to restore), and
`renderComparisonChart()` — the function that drew them — was never
removed, just unwired from `renderAll()`. Reinstating them (alongside or
instead of the new chart) is a small, documented change, not an
archaeology project, if that's wanted after living with the new one.

**Verified**: pipeline/audit unaffected (dashboard-only change, no pipeline
script touched) — `08_audit.py` still 7/8. Visual QA via claude-in-chrome:
selected Merchant 1/4/7 on Contribution Profit and confirmed 4 visually
distinct grouped bars per quarter (3 entities + blended, Merchant 7 visibly
near-zero/negative matching its known structural-drag status); switched the
metric to Revolve Rate and confirmed the mark type switched to lines with a
correctly dashed, color-distinct blended line; switched "Compare by" to FICO
tier and confirmed the value picker and legend repopulated with a clean
Poor > Fair > Good > Very Good > Exceptional ordering (matches intuition —
lower-tier customers revolve more); confirmed KPI tiles/trend chart still
reproduce the exact known headline numbers with no selection made (no
regression from the `matchesFilter`/`skipVintage` change); checked both
dark and light mode; no console errors.

---

## Day 2 — Fixed: driver KPI charts were hiding real seasonality (2026-08-26)

Caught after the fact, by the user, looking at the shipped dashboard:
PPAA visibly showed the new seasonal saw-tooth, but Active Rate, Payment
Rate, and NIM looked flat even in the *actuals* period — real historical
data, untouched by anything built today, so if seasonality were genuinely
absent from those series specifically, that would itself be a legitimate
and interesting finding. It wasn't absent. It was being hidden by a
charting bug.

**Checked the raw actuals directly** (same detrend-and-residual method as
the seasonality analysis, generalized to any line item) before touching any
code — never assume a chart is right just because it renders without
errors:

| Line item | Swing | Phase |
|---|---|---|
| Net Transaction Volume | 85.5% | Q4 peak / Q1 trough |
| In-Month Active Accounts | 22.2% | Q4 peak / Q1 trough (same phase as NTV) |
| Total Accounts | 0.3% | flat (cumulative stock, doesn't fluctuate) |
| Outstanding Balance | 24.4% | Q4 peak / Q1 trough |
| Revolve Balance | 23.4% | **Q1 peak** — one quarter behind NTV |
| Principal Payments | 24.3% | Q4 peak |
| Interest Revenue | 22.7% | Q1 peak (matches Revolve Balance, its driver basis) |
| Cost of Funds | 13.9% | Q4-leaning, smaller magnitude |

Every one of these has real, material seasonality in the actuals — Active
Rate's ~22% swing is smaller than NTV's 85% but genuinely there every
single year (Q1'23-Q1'26: 59.9%, 59.1%, 57.8%, 56.7%; Q4'23-Q4'25: 71.3%,
69.7%, 68.5%). Payment Rate and NIM are noisier (both ratios mix a
Q4-peak-phase component against a Q1-peak-phase component, so they partly
offset rather than reinforce the way PPAA's components do — worth knowing,
not itself a bug), but recomputing the exact quarterly values by hand
confirmed a real recurring wave in both once the early-portfolio period
(Q1-Q4 2023, before the book had scale) is looked past.

**Root cause, once the data was confirmed to actually have the signal**:
`renderSmallLineChart()` (the 6 driver-KPI small multiples) and
`renderCompareChartSvg()`'s line-mode path (item 6) both forced the y-axis
to always include zero — `Math.min(0, ...)` on the lower bound — the same
convention used everywhere else on this page for $ magnitudes, where
showing the zero baseline is meaningful context. For a rate/ratio metric
living in a narrow band far from zero (Active Rate 57%-71%, NIM 1.5%-3.5%),
forcing zero into the axis compresses the entire real range into a thin
sliver at the top of a mostly-empty chart — the seasonality was fully
present in the underlying numbers the whole time, just visually crushed to
invisibility.

**Fix**: both renderers now auto-scale line-type charts to the actual data
range (with ~15-18% padding), and explicitly label the max/min on the small
multiples (and keep the existing gridline labels on the compare chart) —
a non-zero axis is legitimate practice for a line chart *as long as the
scale is disclosed*, which it now is; the earlier version's problem wasn't
the missing-zero, it was rendering with no scale disclosure at all *and* an
implicit zero anchor that made a real signal invisible. The zero-baseline
axis-line is still drawn where it stays honestly meaningful (bar-mode
metrics, which can cross zero) and simply repositioned to the plot's bottom
edge when zero falls outside a rate chart's range.

**Verified**: rebuilt and re-viewed via claude-in-chrome — all 6 driver KPI
charts and the compare chart's line mode now show clear, correctly-labeled
seasonal waves matching the table above (Active Rate 56.7%-71.3%, Payment
Rate 41.3%-130.5% — the early-portfolio spike is now visible too, not just
implied — NIM 1.5%-3.5%, Revolve Rate 22.5%-45.0%, Revenue Margin
4.5%-11.7%); no console errors; dashboard-only fix, `08_audit.py` unaffected
(still 7/8).

---

## Day 2 — Extending seasonality beyond NTV (2026-08-26)

Prompted by two connected observations from the user, both about the same
underlying gap: (1) the driver KPI charts (previous entry, above) revealed
Active Rate/Payment Rate/NIM/Revolve Rate had no forecast-period
seasonality at all, only PPAA did; (2) separately, the top "P&L trend by
quarter" chart's forecast-period swing looked visibly bigger than the
actuals' own swing.

**Root cause, confirmed by direct measurement, not assumption:** seasonality
had only ever been applied to Net Transaction Volume. Its Rate-Derived
children (Interchange, MDR, Rewards, Royalties, Rebates, Payment Fees,
Fraud) correctly inherit NTV's exact swing (checked: 85.3%-86.2% vs NTV's
85.5%, essentially identical — this part was never the problem). But
Interest Revenue, Fee Revenue, and Other Revenue are driven by Revolve
Balance, Outstanding Balance, and Active Accounts respectively, none of
which had an index. Measured directly from the actuals:

| Driver | Swing | Phase |
|---|---|---|
| Revolve Balance | 23.4% | **Q1 peak** — opposite NTV's Q4 peak |
| Outstanding Balance | 24.4% | Q4 peak |
| In-Month Active Accounts | 22.2% | Q4 peak |

Revolve Balance's Q1 peak is the important one: because Interest Revenue
tracks it, Interest Revenue's real seasonality **partially cancels** the
NTV-driven revenue lines when everything sums into Gross Revenue in the
actuals. Measured: Gross Revenue's real quarter-of-year swing is **25.8%**
in the actuals; with only NTV seasonal, the forecast's swing was **32.4%**
— bigger, because the offsetting effect was missing.

### Fix 1 — extend the seasonal index to the other real drivers

`04_curve_library.py`'s `build_seasonal_index()` generalized to take a
`line_item` parameter (was NTV-only), called once per item in the new
`SEASONAL_LINE_ITEMS` list (NTV, Revolve Balance, Outstanding Balance,
In-Month Active Accounts) — each gets its own independently-measured index,
deliberately not sharing NTV's. `05_forecast_engine.py`'s
`SEASONAL_LINE_ITEM` (singular) became `SEASONAL_LINE_ITEMS` (a set); the
per-step ratio and frontbook launch-quarter multiply both now key off
`seasonal_index[li]` (a nested `{Line Item: {quarter: multiplier}}` dict)
instead of one shared dict. `08_audit.py`'s Check G generalized the same
way, looping all 4 items instead of assuming one row per quarter_of_year —
its first version silently mixed different line items' rows together once
the CSV grew a second dimension, and FAILED the day it was introduced,
exactly the kind of regression this suite exists to catch.

**Result of Fix 1 alone**: Gross Revenue's forecast swing came down to
**25.3%** — a near-exact match to the actuals' 25.8%. Confirmed via the
same before/after quarter-of-year measurement used throughout this project,
not eyeballed.

### Fix 2 — a second, unrelated problem Fix 1 surfaced

Checking the headline P&L numbers before shipping Fix 1 (never assume a
big change is fine just because one target metric improved) found Gross
Profit had jumped from $198.1M to $233.2M (+17.7%, margin 13.2%→15.0%) and
portfolio LTV/CAC from 0.75x to 0.87x — too large to be incidental
rounding, and directionally uniform across every merchant (all ten moved
up), which pointed to something systematic rather than noise.

**Isolated by testing each new driver's contribution separately**
(NTV+Revolve Balance alone, NTV+Outstanding Balance alone, NTV+Active
Accounts alone): Revolve Balance alone accounted for essentially the whole
effect (+$55.9M GP), Outstanding Balance pulled the other way (-$20.7M GP,
the expected/correct dampening effect), Active Accounts was negligible.

**Root cause, traced by hand against one real cohort, not inferred:** the
per-step seasonal ratio mechanism telescopes to `s(destination)/s(anchor)`
for a chain of steps — mathematically correct for making one cohort's own
trajectory internally consistent relative to its own real last-actual
value. The catch: **almost every backbook cohort shares the exact same
anchor quarter** (Q2 2026, the portfolio's one last-actual quarter), so
`1/s(anchor)` becomes a near-universal LEVEL SHIFT applied to the entire
2-year-ahead forecast — not a within-year reshaping effect, which is what
this mechanism was built to produce. Revolve Balance's Q2 index (0.920)
sits furthest from 1.0 of the four items (`1/0.920 = 1.087x`), which is
why it dominated; NTV/Outstanding Balance/Active Accounts (Q2 indices
0.956/0.951/0.994, all close to 1.0) barely showed the effect.

**First attempt (uniform damping exponent on every step) — tried, measured,
rejected**: shrinking the whole ratio by an exponent reduced the level
shift, but since telescoping makes the anchor-level-shift and the
within-year reshaping the SAME quantity end to end, it crushed the
top chart's swing from ~25% down to ~10% while barely fixing the margin —
the opposite of useful, since it re-broke the thing Fix 1 had just fixed.

**Actual fix — damp only the anchor-crossing step, not later ones**:
`seasonal_step_ratio()` gained an `anchor_crossing` flag, `True` only for
the single step whose "source" is a real actual observation (identified by
comparing `qsb_from` against the cohort's true last-actual QSB, captured
before the loop's own bookkeeping variable gets overwritten). That one step
divides by `s(anchor)^ANCHOR_RATIO_DAMPING` instead of `s(anchor)`; every
later step keeps the full, undamped ratio. Telescoping still applies to the
undamped tail, so the cumulative multiplier through any chain works out to
`s(destination) / s(anchor)^ANCHOR_RATIO_DAMPING` — **the destination
quarter's own multiplier stays at full strength** (within-year reshaping
exactly preserved), only the single real anchor's influence is discounted.
Confirmed empirically before picking a value: with this structural fix,
damping=0.5 alone brought Gross Revenue's swing right back to 25.3%
(unaffected by the damping, as designed) while margin dropped from 15.0%
to 14.3% (partial fix); pushing damping down further (tested 0.5 → 0.35 →
0.2 → 0.15 → 0.05) continued to close the margin gap without ever
touching the swing, landing on **ANCHOR_RATIO_DAMPING = 0.2** — margin
13.9% (was 13.2% before any of this work; residual ~0.7pp gap is
comparable to the small drift NTV-only seasonality already showed, an
expected consequence of real reshaping, not a new artifact), LTV/CAC
0.78x (was 0.75x).

**Why 0.2, not 0 (fully ignore the anchor) or 1 (fully trust it)**: the
anchor observation is one of only ~4 historical data points for its own
quarter-of-year, already folded into the very estimate of `s()` it would be
compared against — leaning on it heavily is somewhat circular, but
discarding it completely throws away real information about where the
portfolio's most recent actual quarter actually sits. A documented judgment
call, in the same spirit as `FACTOR_CLIP`/`GROWTH_CAP`/`SEASONAL_CLIP`
elsewhere in this codebase, not a precision-fitted constant.

### Side effects

- `08_audit.py` Check B's forecast-period gap narrowed further: 23.7%
  (NTV-only) → 13.6% (all 4, undamped) → 12.8% (all 4, damped) — expected
  to shrink, not vanish, since Outstanding Balance's index is a real but
  separately-measured, imperfectly-correlated signal from NTV's, not a
  mechanical derivative of it.
- `pitch_deck.html`'s hardcoded LTV/CAC stat tiles (a known, separately-
  flagged issue — that file doesn't read from `output/` at build time)
  updated by hand: portfolio 0.75x → **0.78x**, Poor tier 2.93x →
  **2.99x**, Exceptional tier -0.47x → **-0.45x**.

**Verified**: hand-traced one cohort's Revolve Balance forecast value
against the raw seasonal index math before concluding it wasn't a
double-count/sign bug; isolated each new driver's contribution separately
before touching the fix; measured the Gross Revenue swing and headline P&L
figures at every damping value tested, not just the final one; full
pipeline rerun end-to-end; `08_audit.py` 7/8 (Check G re-passes across all
4 items exactly, Check H exact match, Check B's known FAIL narrower than
before); visual QA via claude-in-chrome confirmed all 6 driver KPI charts
now show real seasonal waves continuing through the forecast period
(previously flat for everything but PPAA), and the top trend chart's
KPI tiles/margins sit close to their pre-extension values with no
console errors.

## Day 2 — Cost of Funds driver basis fix, repo reorganization (2026-08-26)

Flagged by the user: on the main dashboard's P&L trend chart, Gross Revenue's
seasonality looked plausible, but Gross Profit and Contribution Profit's
looked "wonky" — a much sharper, oddly-shaped Q1-high/Q4-low oscillation
than Gross Revenue's own swing.

**Root cause**: `line_item_classification.csv` had `Interest Revenue` keyed
to `Driver Basis = Revolve Balance`, but `Cost of Funds` keyed to
`Outstanding Balance`. Revolve Balance and Outstanding Balance carry their
own, independently-estimated, out-of-phase seasonal indices (Revolve Balance
peaks Q1; Outstanding Balance/NTV peak Q4 — see "Extending seasonality
beyond NTV" above). Interest Revenue's swing therefore had no matching
cost-side line riding the same basis to offset it, unlike NTV's own
revenue/cost pairs (Interchange/MDR vs. Rewards/Royalties/etc.), which
already self-cancel inside the margin. Since Gross Profit and Contribution
Profit are thin residual margins (~5–15% of revenue), Interest Revenue's
unhedged swing landed almost entirely in them.

**Fix** (user's diagnosis, confirmed and implemented): Cost of Funds should
move with the same basis as Interest Revenue — if Revolve Balance spikes,
interest income and funding cost should move in the same direction. Changed
`Cost of Funds`'s Driver Basis to `Revolve Balance` in
`line_item_classification.csv`. Pure data-driven change — `curve_library.py`
and `forecast_engine.py` both read Driver Basis dynamically from this file,
so no code changes were needed for the fix itself, only a full pipeline
rerun.

**Impact**, full rerun:
- Consolidated Gross Margin swing narrowed from a ~25pt Q1/Q4 oscillation
  (peaks near 29% in Q1, troughs near 4% in Q4) to a ~12–13pt one (Q1 ≈
  22–23%, Q4 ≈ 10%) — a meaningfully more plausible pattern, though a
  smaller residual Q1-high tilt remains, likely from the same kind of
  revenue/cost driver-basis mismatch on a smaller scale (e.g. Other
  Revenue vs. Servicing & Collections, both Active-Accounts-driven but not
  a matched pair) — not investigated further, out of scope of this fix.
- Portfolio LTV/CAC: 0.78x → **0.85x**. Poor-tier LTV/CAC: 2.99x → 2.94x.
  Exceptional-tier LTV/CAC: -0.45x → -0.32x (still negative, direction
  unchanged). `pitch_deck.html`'s hardcoded stat tiles updated to match.
- `08_audit.py` Check B unaffected by this fix (it tests the Outstanding
  Balance/NTV roll-forward identity, not Interest Revenue/Cost of Funds) —
  still 7/8, Check B FAIL-explained, as expected.

**Verified**: full pipeline rerun end-to-end; `08_audit.py` still 7/8 with
identical check results elsewhere; hand-inspected `pnl_consolidated.csv`'s
quarterly margin sequence before and after; confirmed via grep that no
script hardcodes "Cost of Funds" → "Outstanding Balance" anywhere outside
the classification CSV, so the fix couldn't be silently overridden.

### Repo reorganization (same session)

Alongside the fix above: deleted the throwaway `03_actuals_explorer.py`
(confirmed via grep it was referenced nowhere except its own docstring and
one line in `README.md`) and its orphaned `output/_scratch_explorer/`
PNGs; renumbered the remaining 14 scripts into a continuous sequence and
split them into `scripts/core_engine/` (ingest through audit, plus the two
Day 2 diagnostic scripts) and `scripts/reporting/` (the four HTML-deck
builders); reorganized `output/` into `csv/`, `parquet/`, `html/`, and
`json/` subfolders by file type. All in-script cross-references, `OUT_DIR`
paths, and shared-module (`pnl_utils.py`/`viz_utils.py`) imports updated to
match; `README.md`'s pipeline instructions rewritten for the new layout —
this also surfaced a pre-existing dependency-order bug in the original
numbering (`08_audit.py`'s Check H needs `dashboard_data.json`, built by
the later-numbered `10_export_dashboard_data.py`; it only ever worked
before because `output/` already had stale files from prior runs). The
narrative deck's Chapter 4 cohort chart y-axis (previously unlabeled) now
reads "Contribution Profit per Account ($)", matching the chart's existing
x-axis title convention. `pitch_deck.html`'s bug write-ups were also
genericized to themes rather than variable/number-level detail, and its
Check B copy expanded to explain both the new-origination effect and the
smaller forecast-period seasonal-composition gap in plain terms.

**Verified**: full pipeline rerun end-to-end from the new script locations,
zero errors; `output/` subfolder contents spot-checked against the
pre-reorg flat file list (22 CSVs, 3 parquets, 4 HTML, 1 JSON, all
accounted for); grepped for any remaining old-numbered filename reference
across `scripts/` and found none outside `BUILD_LOG.md`/`TODO.md`/
`REVIEW_FINDINGS.md` (left untouched by design — dated logs, not live
docs); confirmed all four HTML outputs' cross-links are bare relative
filenames (no `output/` prefix), so moving them together into `output/html/`
didn't break navigation between them.

## Repo reorganization — `scripts/core_engine`/`scripts/reporting` flattened (2026-08-27)

Requested by the user: collapse the `core_engine`/`reporting` split from the
prior reorg back into one flat `scripts/` directory, numbered files only
(01-14, same numbering as before — no renumbering this time, just moving
each file up one level). `git mv` used throughout so history follows each
file.

**Fix required in every moved script**: each one resolves `OUT_DIR`/
`DATA_DIR`/`BASE_DIR` via `Path(__file__).resolve().parent...`, counting
directory levels up to the repo root. Two levels deep
(`scripts/core_engine/x.py`) needed `.parent.parent.parent`; one level deep
(`scripts/x.py`) needs `.parent.parent`. Same adjustment for the
`sys.path.insert(...)` lines that make `pnl_utils.py`/`viz_utils.py`
importable (`.parent.parent` → `.parent`, since the shared modules now sit
in the script's own directory). Also swept every in-code comment/docstring
referencing the old `core_engine/`/`reporting/` path prefixes (cross-file
pointers like "see core_engine/07_audit.py"), plus the dashboard's own
footer string, which cited its own build path.

Updated `README.md`'s repo-layout tree and pipeline command list, and
`docs/SCRIPTS_GUIDE.md`'s section headers (dropped the now-inaccurate
`scripts/core_engine/`/`scripts/reporting/` path labels — the "core engine"
vs. "reporting" split is now a logical grouping only, not a physical one).

**Verified**: full pipeline rerun end-to-end (all 14 scripts) from the
flattened locations, zero errors. `git diff` on every regenerated `output/`
CSV/parquet came back empty — a pure path fix, no numeric change anywhere;
audit still 7/8 (Check B FAIL-explained, unchanged); portfolio LTV/CAC still
0.85x. Only `dashboard.html` shows a diff, and only in its footer text (the
`scripts/reporting/09_...` path string it echoes) — the other three HTML
deliverables are byte-identical to before the move.
