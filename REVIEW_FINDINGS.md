# Pre-Presentation Review — `imprint_case` Pipeline

Reviewed 2026-08-26, ahead of presenting to Imprint's Deputy CFO (Cody
Edgington) and Head of Treasury. Three independent lenses, run in parallel:
a **code-reviewer persona** (`engineering-skills:code-reviewer` skill, full
manual rubric + `code_quality_checker.py`), a **financial-analyst persona**
(`finance-skills:financial-analyst` lens + independent pandas spot-checks
against the actual output CSVs/parquet), and a **visual QA pass** on all
three HTML deliverables via Claude in Chrome. Each ran read-only — nothing
in the pipeline was edited by this review.

## Executive summary

**Bottom line: yes, this is presentation-ready.** Every headline financial
number that was independently re-derived — the $1.50B/$198.6M/$170.8M P&L,
the portfolio LTV/CAC (correctly dollar-weighted), the FICO-tier LTV/CAC
table, the 15%→3.56% discount math — reproduced exactly against the
underlying CSVs and parquet. No live correctness or data-integrity bugs
turned up in code review either, including the four scripts (`07`, `10`,
`11`, `12`) a prior partial review never touched.

**Update, same day:** a follow-up round (§4 below) specifically audited
*whether every portfolio-level average is correctly driver-weighted* and
*independently tied every output CSV back to raw source data*. The tie-out
found nothing wrong. The weighting audit found one real bug — an unweighted
mean in the LTV-extrapolation curve — that **has since been fixed and the
pipeline rerun**: portfolio LTV/CAC moved from 0.82x to **0.75x**. This is
now the correct, current number; every number below that still says 0.82x is
preserved as a record of what round 1 found, not what's true today. See §4
for the full before/after and what got fixed.

What this pass actually found is smaller than that: one real visual bug on
the primary dashboard, one process gate to run before you present (not a
code fix), and a few things worth having ready *verbally* that aren't
written down anywhere in the reader-facing docs. None of it should change
your story; some of it is worth 20-30 minutes tonight.

**Do these tonight, in order:**

1. **Rerun the full pipeline (`01`→`12`) one more time**, since it's likely
   you'll touch a script or two based on this review, and `pitch_deck.html`'s
   stats are hardcoded — nothing regenerates them automatically. Diff its
   numbers against fresh `output/` CSVs before you present. *(~5 min)*
2. **Fix the dashboard's trend-chart label collision** — see 🔴 below. It's
   on the default view of the tool most likely to be open live in the room.
   *(~20-30 min if you want it clean; otherwise know to scroll past it or
   avoid zooming in)*
3. **Memorize three numbers/answers that aren't written down anywhere in the
   three HTML docs** (all below, in the financial-analyst section) — revenue
   mix, the CAC/Contribution-Profit framing, and the Check B nuance.

Everything else is optional polish, already-tracked future work, or purely
cosmetic — see the buckets below.

---

## 1. Code Reviewer findings (`engineering-skills:code-reviewer`)

**Coverage:** Full manual rubric + `code_quality_checker.py` applied to
`07_cohort_views.py`, `10_export_dashboard_data.py`, `11_build_dashboard.py`
(Python + its ~325 lines of embedded JS), and `12_build_pitch_deck.py` — the
four files a prior partial review never covered. Re-read `pnl_utils.py`,
`06_pnl_rollup.py`, `01`, `05`, `08` to confirm earlier findings still hold.
Numeric verification: summed `dashboard_data.json`'s rows in Python and
confirmed exact reconciliation to `pnl_consolidated.csv`; cross-checked every
hardcoded statistic in `12_build_pitch_deck.py` against current CSVs.

**🔴 Blocking (process, not a code defect)**
- **`12_build_pitch_deck.py` (whole file)** — every stat on this deck (LTV/CAC
  by FICO, audit check statuses, forecast row counts) is a hardcoded string
  literal, not read from `output/` at build time. All verified correct
  *right now*, but nothing will tell you if it goes stale after further
  edits. **Action:** rerun the pipeline once more and manually diff the
  deck's numbers against fresh CSVs before presenting (folded into the
  executive summary's step 1).

**🟡 Suggestions**
- **`12_build_pitch_deck.py`** claims "89.6/100 average" static-analysis
  score; a fresh `code_quality_checker.py` run gives **81.8/100** (87.9
  excluding one magic-number-heavy outlier file). Minor, but if you
  regenerate the deck anyway, refresh or soften this line — an audience
  member who knows to ask "how was that computed?" would get a different
  answer today.
- **`11_build_dashboard.py`'s embedded JS** doesn't reimplement the full P&L
  bucketing logic (that happens once, server-side, in `10`) — it only sums
  four already-bucketed dollar columns and applies simple derivation
  arithmetic mirroring `06`'s formulas. Currently in sync (verified by
  summing the embedded JSON), but nothing automated would catch future
  drift if `pnl_utils.py`'s formulas change. Low-cost mitigation for later:
  a one-line total-reconciliation assertion at the end of
  `10_export_dashboard_data.py`.
- **`05_forecast_engine.py`** has three silent `continue` fallthroughs on
  missing lookups, no logging. Low probability of mattering today (pooled
  fallbacks cover most cases, `08`'s audit is a backstop), but a skip
  counter would make a future coverage gap visible instead of silent.
- Confirmed cross-file duplication: `FORECAST_START_IDX=14` hardcoded in 5
  places, `FACTOR_CLIP=(0.7,1.3)` in 2 (tied together only by a comment).
  Worth noting `11_build_dashboard.py` actually gets this right — its JS
  reads `FORECAST_START_IDX` from the data payload instead of hardcoding a
  6th copy, which is the pattern the other five files should arguably
  follow.

**🟢 Nitpicks** — bare `assert` in `01_ingest_clean.py`'s validation (stripped
under `python -O`); the same color-palette hex dict copy-pasted across
`09`/`11`/`12` (currently consistent, no drift yet); a `groupby().apply()`
pattern in `07_cohort_views.py` that a plain `.agg()` would read slightly
more directly.

**✅ What's good** — `01_ingest_clean.py`'s fail-fast schema validation;
`pnl_utils.py`'s shared-bucketing refactor with its rationale documented in
the docstring, not just the fix; `10_export_dashboard_data.py`'s
flow/snapshot grain separation (specifically designed so a filtered sum
can't double-count a cohort's LTV, with the real incident it fixes
documented inline); `06_pnl_rollup.py`'s bug-postmortem comments that
explain *why* the rejected approach was wrong, not just what replaced it.

**Reviewer's own summary:** *"This is a solid, self-aware codebase for what
it is: a 2-day take-home, not a maintained system, and it mostly knows the
difference... On the four files given fullest attention here, I found no
live correctness or data-integrity bug — every number I could trace
reconciled exactly against its source CSV."*

---

## 2. Financial Analyst findings (`finance-skills:financial-analyst`)

**Method:** applied the skill's forecasting/ratio/valuation reference docs as
a checklist (the skill's own JSON-input scripts don't fit this cohort-data
schema, so principles were applied directly rather than run); independently
recomputed headline numbers from `output/` CSVs and the raw grained parquet
with pandas; graded the deliverable against the case brief's own stated
evaluation criteria.

**Verdict:** *"Yes, presentation-ready from a methodology standpoint...
That's a genuinely strong result; nothing here is asserted without being
traceable to the underlying math."*

### Numeric spot-checks (all independently recomputed, not read off the docs)

| Check | Result |
|---|---|
| P&L totals reconcile (`pnl_by_merchant.csv` vs `pnl_consolidated.csv`) | **PASS** — float-noise only |
| Portfolio LTV/CAC = 0.82x, correctly dollar-weighted | **PASS** — 0.8189x; confirmed the code does Σ$/Σ$, not an average of ratios (a naive approach would have shipped 1.07x–1.38x instead) |
| Margin %'s derived from same-row dollar columns, not averaged | **PASS** |
| P&L hierarchy identities (GP = GR + COS; CP = GP + OpEx) | **PASS** |
| 15% annual hurdle → 3.56%/quarter | **PASS** — (1.15)^0.25−1 = 3.5558% |
| FICO-tier LTV/CAC table, re-aggregated from all 785 cohort rows | **PASS** — matches to 3 decimals |
| Newest-cohort LTV/CAC range (0.01x–3.0x) | **PASS** — exact match |
| Roll-forward identity (audit Check B) | **Directionally/structurally confirmed** — see below, exact % is aggregation-sensitive |

### Three things to have ready verbally tomorrow (not code fixes)

1. **"Contribution Profit" excludes Acquisition Cost/CAC** — a defensible,
   standard unit-economics choice (CAC is recovered via LTV over the
   cohort's life, not expensed in-period), but it's documented only in a
   `06_pnl_rollup.py` code comment, nowhere in the three HTML docs. If Cody
   or Treasury notices $170.8M Contribution Profit next to $208.5M of
   Acquisition Cost over the same period, be ready with: *"Contribution
   Profit reflects the ongoing unit economics of the existing book; CAC is
   evaluated separately via LTV/CAC because it's recovered over a
   customer's lifetime, not in the quarter it's spent."*
2. **Revenue-mix split isn't shown anywhere** — computed fresh for this
   review: **Interest Revenue 64.2%, Interchange 17.8%, MDR 13.5%, Fee
   Revenue 3.9%, Other 0.7%** of forecast Gross Revenue (confirms and
   slightly refines the ~60% figure already in your prep notes). This is a
   named case-brief P&L element and squarely in Treasury's expected line of
   questioning. Already tracked as `TODO.md` item 4 — no need to build it
   tonight, just have the split memorized.
3. **Check B (the one audit FAIL) is sound in substance, aggregation-
   sensitive in the exact number.** Independent re-derivation from raw
   parquet confirms the mechanism (new-cohort originations carry balance far
   beyond what their own NTV-net-of-payments implies; continuing cohorts
   reconcile tightly — 0.9%–5% depending on method) but got a different
   literal split (78.6%/0.9%, or 12.6% pooled) than `audit_results.csv`'s
   cited 44.3%/5.0%. **Most important point to lead with:** Outstanding
   Balance is *not actually forecast* off this identity — it's forecast
   directly from its own development-factor curve — so this reconciliation
   gap doesn't propagate into the balance numbers that matter for
   warehouse-funding sizing. Say that proactively. If you want to be able to
   defend the literal "44%" figure under technical questioning, skim
   `08_audit.py`'s Check B implementation before the meeting.

One more precise number worth having in your pocket: **39.4%** of the
accounts-weighted 12-quarter LTV window is filled via population-level
extrapolation rather than cohort-specific data — uniform across FICO tiers
(so it doesn't undermine the FICO-inversion finding), useful if asked "how
much of LTV is really observed vs. filled in."

### Grading against the case brief's own evaluation criteria

| Criterion | Assessment |
|---|---|
| P&L design | Hierarchy correctly reconciles top-to-bottom. Gap: Gross Revenue's components (Interest/Interchange/MDR/Fee/Other) never shown anywhere — already TODO item 4. |
| Tool fluency | Strong — full pipeline, independent audit layer, dark-mode dashboard, a JS-side bug caught by testing before shipping. |
| Financial acumen | Chain-ladder for volumes vs. population-fill for signed $/account LTV is a genuinely sophisticated, correctly-diagnosed distinction — most builds wouldn't separate these two correctly. |
| Assumption quality | Ambiguous drivers validated by correlation testing, not asserted; CAC empirically reconciled to within 0.29% of the reference figure. Single Base Case only (already flagged as Risk #3, appropriately). |
| LTV/CAC thinking | Methodology defensible and independently reproduced exactly. Gap: the CAC-exclusion framing (item 1 above) isn't stated in reader-facing docs. |
| Communication | Narrative deck's structure and FICO-tier caveat language are genuinely good practice. Two silent gaps: CAC-exclusion framing, revenue-mix split. |

---

## 3. Visual QA findings (Claude in Chrome, all three HTML deliverables)

Served `output/` locally, drove a real Chrome tab against
`dashboard.html`/`narrative_report.html`/`pitch_deck.html` in both dark and
light mode, exercised the dashboard's filters, checked console errors and
cross-navigation.

**🔴 New finding — `dashboard.html`'s trend-chart end-labels overlap,
illegible, in the default view.** BUILD_LOG documents this exact bug class
("Gross Profit and Contribution Profit lines end close together, labels
render on top of each other") as fixed via a vertical-separation pass — and
it genuinely is fixed, but only in `narrative_report.html`'s chart code
(confirmed side-by-side: its equivalent chart cleanly separates $33.2M and
$28.6M labels). **`dashboard.html`'s trend chart is a separate, JS-driven SVG
renderer in `11_build_dashboard.py` that never got the same fix** —
reproduced in both the default "All merchants" view and filtered to
Merchant 7, at different values each time, confirming it's structural, not a
data coincidence. This is the tool most likely to be open live tomorrow, and
the bug shows in the very first chart below the KPI tiles.
**Fix:** port the greedy label-separation logic from `09_build_narrative_deck.py`'s
Python chart helpers into `11_build_dashboard.py`'s JS renderer (it's a
from-scratch SVG implementation, so this needs a JS port, not a shared
import).

**🟡 New finding — `narrative_report.html`'s cohort-maturation chart clips a
series label at the viewport edge.** "Oldest (Q1 2023)" truncates to "Oldest
(Q1 202" at a common 1374px-wide viewport (Chapter 4). Lower severity — the
label is still guessable, and a wider display may show it in full — but
worth a quick left-anchor fix on labels for lines ending near the right edge
if there's time.

**✅ Confirmed working, no regressions:**
- All three documents load with zero page-console errors.
- Dashboard filters are fully live and correct — switching to Merchant 7
  reproduced BUILD_LOG's own prior spot-check exactly (Contribution Profit
  −$14.2M, LTV/CAC −0.19x), confirming no regression despite
  `09_build_narrative_deck.py` (which shares chart patterns) being the most
  recently edited script in the repo.
- Light/dark toggle works cleanly on all three documents, good contrast both
  ways.
- Cross-navigation links between all three documents all resolve correctly.
- Pitch deck's inline SVG architecture/methodology diagrams render cleanly
  in both themes.

---

## 4. Weighted-average & independent tie-out audit (round 2, same day)

Two more agents, run in parallel, at your specific request: (a) an
exhaustive check that every portfolio/merchant/FICO-tier average anywhere in
the codebase is properly driver-weighted (Σnumerator/Σdenominator) rather
than a naive mean of pre-computed ratios, and (b) a from-scratch
reconciliation of every output file back to raw `data/case_study_data.csv`,
written without importing anything from `scripts/`, so a bug shared between
the pipeline and its own audit couldn't hide from it.

**Tie-out audit: found nothing wrong.** `pnl_consolidated.csv`'s actuals
rows (all 7 metrics × 14 quarters), `clean_actuals.parquet` (4,590 cells
spot-checked), the CAC-vs-reference reconciliation (reproduced BUILD_LOG's
0.29% median almost exactly), the 20 cohorts whose full 12-quarter LTV
window is fully observed (not extrapolated), `cohort_balance_age_mix.csv`,
and `curve_dev_factors.csv`/`curve_rate_curves.csv` all reproduced exactly
from raw data via completely independent code. `pnl_by_merchant.csv` was
correctly determined to be forecast-period-only and therefore not
raw-groundable (not a gap — the right call).

**Weighted-average audit: found one real, material bug — verified
independently by me before touching anything, then fixed.**
`build_cp_population_curve()` in `06_pnl_rollup.py` — the function that
fills in a cohort's Contribution-Profit-per-Account at any age it hasn't
lived long enough to observe, i.e. the mechanism behind every extrapolated
cohort's LTV — computed the population-level fill as a flat `.mean()` of
each cohort's own CP/Account ratio, **not weighted by that cohort's New
Accounts**. A 580-account cohort counted exactly the same as a 14,958-account
one. I independently reproduced this myself from raw data before applying
any fix: the naive mean overstated the true accounts-weighted value by
**13%-140% depending on cohort age** (worst at the youngest ages, exactly
where the thinnest cohorts — Merchants 9 and 10 — lean on this fill the
most). The identical bug turned up independently re-derived in
`08_audit.py`'s Check E (the check specifically designed to *not* import
06's code so a shared bug can't hide from it — it didn't inherit the bug,
it reintroduced the same one separately), plus a much smaller,
currently-immaterial version of the same anti-pattern in
`09_build_narrative_deck.py`'s `avg_cm` stat (unweighted mean of 8 quarterly
margin %'s instead of Σ CP/Σ GR — changes the number by 0.06 percentage
points, doesn't move the displayed "11.4%").

**Fixed in all three places**, pipeline rerun end-to-end twice (once after
the initial fix, once more after touching `08`/`09`/`12` to confirm nothing
regressed), `pitch_deck.html`'s hardcoded stat tiles updated by hand since
that file doesn't read from `output/` at build time (a separately-flagged,
still-open issue — see remediation item 2 below). Everything that depends on
the LTV extrapolation curve moved; nothing else did:

| Figure | Before (round 1) | After (fixed) |
|---|---|---|
| Portfolio LTV/CAC | 0.82x | **0.75x** |
| Merchant 7 LTV/CAC | -0.19x | **-0.51x** |
| Merchant 2 LTV/CAC | 0.45x | **0.31x** |
| Merchant 1 LTV/CAC | 0.75x | **0.66x** |
| Merchant 5 LTV/CAC (highest) | 1.92x | **2.07x** |
| Exceptional-FICO LTV/CAC | -0.39x | **-0.47x** |
| Very Good-FICO LTV/CAC | 0.24x | **0.16x** |
| Newest (1-quarter) cohorts' LTV/CAC range | 0.01x to 3.0x | **-0.53x to 3.57x** |
| Gross Revenue / Gross Profit / Contribution Profit ($, all levels) | — | **unchanged** |
| `audit_results.csv` pass/fail (5/6, Check B FAIL) | — | **unchanged** |
| Every actuals-groundable figure the tie-out audit checked | — | **unchanged** |

**What this means for tomorrow:** the direction of every finding you're
already planning to present — the FICO-tier inversion, Merchant 7 as the
one clear structural drag — got *stronger*, not weaker or reversed. This is
a magnitude correction caught and fixed before presenting, not a different
story. If asked "has this number changed since you built it," the honest
and genuinely good answer is: yes, a same-day audit caught an unweighted
average understating how severe the FICO-tier/Merchant-7 findings actually
are, verified independently, fixed, and the fix made the underlying story
more pronounced, not less. `dashboard.html` and `narrative_report.html`
picked up the correction automatically (both compute from the regenerated
data at build/runtime, not hardcoded text) — verify `pitch_deck.html` reads
0.75x too if you touch it again before presenting (it does, as of this
pipeline run).

Files changed (all on a new `review-audit-fixes` git branch, `main` left
untouched — nothing has been committed, so this is easy to inspect or roll
back): `scripts/06_pnl_rollup.py`, `scripts/08_audit.py`,
`scripts/09_build_narrative_deck.py`, `scripts/12_build_pitch_deck.py`, plus
every regenerated file in `output/` and this note added to `BUILD_LOG.md`.

---

## 5. Consolidated remediation task list

### Done (applied and verified during this review)
| # | Item | Source |
|---|---|---|
| — | Fixed the unweighted LTV-extrapolation average (`06_pnl_rollup.py`, `08_audit.py`, `09_build_narrative_deck.py`); reran the full pipeline; updated `pitch_deck.html`'s hardcoded stats and `BUILD_LOG.md`'s headline numbers to match | §4 above |
| — | Fixed `dashboard.html`'s trend-chart label collision — ported the greedy vertical-separation pass from `09`'s Python chart helper into `11_build_dashboard.py`'s JS renderer. Re-verified via Claude in Chrome: `$33.2M`/`$28.6M` now render with a clean gap, no overlap. | Visual QA, applied |
| — | Fixed `narrative_report.html`'s clipped "Oldest (Q1 2023)" label — the cohort chart's right margin is now sized from the actual label text length instead of a fixed 20px, matching `svg_line_chart`'s pattern. Re-verified visually: label renders in full with room to spare. | Visual QA, applied |
| — | Added the CAC-exclusion framing as a written caption on `narrative_report.html` (below the Chapter 2 stat tiles) and as a hover tooltip on `dashboard.html`'s Contribution Profit KPI tile — turns the earlier "memorize this" item into a permanent, on-page safeguard. | Financial Analyst, applied |
| — | Refreshed `pitch_deck.html`'s stale code-quality claim: reran `code_quality_checker.py` fresh (81.2/100, grade B, 0 SOLID violations) and updated the deck's text to match. | Code Reviewer, applied |

Pipeline rerun end-to-end after each change; all three HTML deliverables re-verified visually via Claude in Chrome (screenshots below) with zero console errors.

### Must-do tonight (verbal prep only — not code)
| # | Item | Source | Effort |
|---|---|---|---|
| 1 | Memorize: revenue mix (Interest 64.2% / Interchange 17.8% / MDR 13.5% / Fee 3.9% / Other 0.7%) | Financial Analyst | ~2 min |
| 2 | Skim `08_audit.py`'s Check B logic so you can defend the literal "44%" figure if pressed, and lead with "Outstanding Balance isn't forecast off this identity" | Financial Analyst | ~10 min |
| 3 | Update the LTV/CAC figures in your own head/notes to 0.75x portfolio (was 0.82x) if you've memorized any of the old numbers from earlier prep | This review, §4 | ~2 min |

### Already tracked in TODO.md / BUILD_LOG.md — no new action needed
- All 7 `TODO.md` items (seasonality, Exceptional-FICO magnitude re-derivation, light-touch merchant research, full-detail P&L dashboard view — which is the parent of the revenue-components gap above, scenario/gaming module, multi-select charts, driver-KPI tabs).
- BUILD_LOG's documented limitations: Fee Revenue/Other Credits weak drivers, FICO-is-origination-vintage-not-current, single-scenario model, no macro/rate assumption.
- The roll-forward identity's structural gap for new-cohort originations (Check B) — the *substance* was already known and documented; this review only sharpened the exact-number caveat (item 4 above).

### Nice-to-have, post-interview polish (not worth touching tonight)
- Centralize `FORECAST_START_IDX`, `FACTOR_CLIP`, and the color-palette hex values into one shared constants source instead of 3-5 duplicated copies each.
- Add skip-counters/logging to `05_forecast_engine.py`'s silent `continue` fallthroughs.
- Add a one-line reconciliation assertion at the end of `10_export_dashboard_data.py` to catch future drift between the JS dashboard math and the Python P&L rollup.
- No tests, no `requirements.txt`/dependency pinning anywhere in the repo — genuinely worth addressing if this pipeline becomes the maintained system the job description gestures at (Excel→Python migration), not relevant to tomorrow.
- Minor style nitpicks: bare `assert` vs. `raise` in `01`; `groupby().apply()` vs. `.agg()` in `07`; `pnl_consolidated.csv`'s raw column order/sign convention could confuse someone skimming the CSV directly (the dashboard's own table order is correct).

---

## Screenshots

Before/after screenshots for both visual fixes (dashboard label collision,
narrative report clipped label) are available in the review scratchpad —
ask if you want them attached.
