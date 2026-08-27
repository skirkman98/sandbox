# Build Process

Full detail in `BUILD_LOG.md`. This is the condensed version of how it actually happened.

## Where it started

Before any code: the case brief (PDF, converted to Markdown), the raw Excel converted to CSV, and a notes file (`starting_thoughts.rtf`) sketching the architecture up front — rename `Booked Quarter`→`Vintage`/`Quarter On Book`→`Report Date`, split the forecast into **frontbook/backbook** segments (from prior vintage-level forecasting experience), define line-item scope by hand-annotating a draft classification tab, and build a throwaway actuals-visualization tool first to gut-check the data before modeling it. Organize context, sketch structure, look at the data, *then* build — that order held for the whole project.

## Where iteration was heaviest

Day 1 was mostly a straight build: ingest → curves → forecast → P&L → audit → decks, each script run and inspected before the next started. Day 2 was driven by explicit follow-up requests, not open-ended exploration — a `TODO.md` was written at the end of Day 1 so Day 2 had a concrete, human-ordered list: seasonality (needing "is this even material" evidence before building it), Exceptional-FICO magnitude validation (confirming a finding held beyond one cherry-picked example), a full-detail P&L view, driver-KPI tabs, multi-select comparison charts. Mid-build human feedback caught real bugs directly — pointing out driver-KPI charts looked suspiciously flat next to a swing already visible elsewhere led straight to a y-axis auto-scaling bug.

## How confidence is established beyond "Claude said so"

- **An independent audit script** (`07_audit.py`) that deliberately does not import the pipeline's own code — it re-derives 8 checks from source data via separate logic, so a bug shared between "build the number" and "check the number" can't hide.
- **A second, independently-scoped review** (a different persona, no context from the first pass) caught the most consequential bug — a one-time cost leaking into a recurring metric — that self-review had already signed off on.
- **A weighted-average tie-out audit**: every portfolio/merchant/FICO average re-checked for accounts-weighting (not a naive mean of ratios), plus a from-scratch reconciliation of every output file back to the raw source CSV, no shared code.
- **Cross-tool reconciliation**: dashboard JavaScript math asserted against Python's known-correct figures via a separate JS runtime (`jsc`), not just eyeballed.
- **Visual QA in an actual browser** (Claude in Chrome), not just "the code looks right" — console errors, live filter behavior, and chart rendering checked directly against expected values.
- **Hand-derivation**: re-deriving headline findings (like the Exceptional-FICO result) from raw rows by hand for several more examples before trusting the magnitude.

The common thread: every significant claim has at least one independent, differently-derived check behind it, not just a single code path's own output.
