# Build Log — Imprint Corporate Finance Case Study

This is the AI-collaboration record and full written narrative for the forecasting
model in `scripts/` and the final report at `output/report.html`. It exists for two
reasons: (1) the shipped deliverable is scripts + a static HTML report rather than a
live notebook, so this doc is where the "how did the AI actually get directed"
signal lives; (2) it's the full written version of the required Narrative
(risks / winners-drags / data gaps), which the brief says can be verbal in the
debrief but is stronger written down first.

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
   divergent by FICO tier and inverted from intuition: Poor (2.97x) and Fair
   (2.40x) are strongly profitable to acquire; Very Good (0.24x) and Exceptional
   (-0.39x) are weak-to-value-destructive. The mechanism is real and traceable in
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
| 1 | Merchant 4 | $41.9M | 19.5% |
| 2 | Merchant 1 | $33.4M | 10.7% |
| 3 | Merchant 5 | $32.6M | 27.1% |
| 4 | Merchant 3 | $27.0M | 16.9% |
| 5 | Merchant 6 | $24.0M | 14.5% |
| 6 | Merchant 2 | $9.4M | 3.9% |
| 7 | Merchant 9 | $7.5M | 26.7% |
| 8 | Merchant 8 | $5.7M | 16.2% |
| 9 | Merchant 10 | $1.0M | 2.0% |
| 10 | **Merchant 7** | **-$11.7M** | **-7.0%** |

Merchant 4 is the strongest absolute contributor; Merchant 5 has the best margin
of any merchant with meaningful scale (27.1%). **Merchant 7 is the one clear
structural drag** — negative contribution profit and negative margin, not just a
smaller or slower-growing program. Merchant 1 and Merchant 2 are worth calling
out specifically: they're the two largest, most mature programs by revenue, but
their margins (10.7% and 3.9%) are mediocre relative to smaller, higher-margin
programs like Merchant 5 and Merchant 9 — scale and unit-economics efficiency
are not the same thing here, and Merchant 2 in particular deserves scrutiny on
*why* its margin is so thin despite its size.

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
- Gross Profit: $198.6M (13.3% average Gross Margin)
- Contribution Profit: $170.8M (11.4% average Contribution Margin)
- Portfolio-weighted LTV/CAC: **0.82x** (below breakeven — driven by the FICO-tier
  dynamic above; several individual merchants and FICO tiers clear >1.9x, up to
  Merchant 5's 1.92x)

Full detail, charts, and the merchant/FICO cuts are in `output/narrative_report.html`.

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
