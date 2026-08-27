"""
reporting/11_build_pitch_deck.py

Builds output/pitch_deck.html -- a presentation-style walkthrough of how the
forecasting model was built: architecture, core assumptions, the bugs found
and fixed along the way, and the independent audit trail. Content is a
curated distillation of BUILD_LOG.md, not a literal dump of it -- this is
meant to be read/presented in a few minutes, with BUILD_LOG.md as the
full-detail backing document for anyone who wants to go deeper.

Single scrolling page, full-height slide sections (not JS-driven slide
transitions -- simpler and more robust for an internal reference doc that
also needs to work as a plain scroll-through). Two small hand-built inline
SVG diagrams (the driver-based architecture, and backbook/frontbook) --
at this scale (a handful of boxes and arrows) a diagram library would be
overkill; plain SVG is the right tool per the data-visualization skill's
"use established algorithms for complex layouts, but don't reach for one
when a few boxes and arrows will do" spirit.
"""
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from viz_utils import ARCHITECTURE_DIAGRAM_SVG, BACKBOOK_FRONTBOOK_DIAGRAM_SVG

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"

PALETTE = {
    "blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a",
    "red": "#e34948", "yellow": "#eda100",
    "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
    "grid": "#e1e0d9", "surface": "#fcfcfb", "page": "#f9f9f7",
}

# Audit stats read from output/audit_results.csv at build time, not
# hardcoded -- a hardcoded "5 / 6" here is exactly what drifted stale after
# Day 2 added checks G and H (8 total, 7 pass) without anyone re-running
# this script. Short labels are curated for readability; a check letter not
# in _AUDIT_LABELS falls back to the CSV's own (longer) Check text rather
# than silently dropping it, so a new check still shows up correctly even
# before its label is curated.
_AUDIT_LABELS = {
    "A": "Actuals reconciliation vs. raw source CSV",
    "B": "Roll-forward identity (root-caused: new-cohort origination effect)",
    "C": "Actual/forecast seam continuity",
    "D": "Forecast CAC/account vs. historical, per merchant",
    "E": "Cohort LTV magnitude sanity (regression guard)",
    "F": "Independent trend cross-check vs. naive linear regression",
    "G": "Seasonal index sanity (independent recompute)",
    "H": "Driver KPI sanity (PPAA, Payment Rate, independent recompute)",
}
_audit_df = pd.read_csv(OUT_DIR / "csv" / "audit_results.csv")
AUDIT_N_TOTAL = len(_audit_df)
AUDIT_N_PASS = int((_audit_df["Status"] == "PASS").sum())


def _audit_row_html(check_text, status):
    letter = check_text.split(".", 1)[0].strip()
    label = _AUDIT_LABELS.get(letter, check_text)
    status_html = '<span class="status pass">PASS</span>' if status == "PASS" else '<span class="status fail">FAIL, explained</span>'
    return f'<div class="check-row"><span>{letter} &mdash; {label}</span>{status_html}</div>'


AUDIT_ROWS_HTML = "\n  ".join(_audit_row_html(r["Check"], r["Status"]) for _, r in _audit_df.iterrows())

HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Imprint P&amp;L Model &mdash; How It Was Built</title>
<style>
  :root {{
    color-scheme: light;
    --blue: {PALETTE['blue']}; --orange: {PALETTE['orange']}; --aqua: {PALETTE['aqua']};
    --red: {PALETTE['red']}; --yellow: {PALETTE['yellow']};
    --ink: {PALETTE['ink']}; --ink-2: {PALETTE['ink2']}; --muted: {PALETTE['muted']};
    --grid: {PALETTE['grid']}; --surface: {PALETTE['surface']}; --page: {PALETTE['page']};
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --blue: #3987e5; --orange: #d95926; --aqua: #199e70; --red: #e66767; --yellow: #c98500;
      --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
      --grid: #2c2c2a; --surface: #1a1a19; --page: #0d0d0d;
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --blue: #3987e5; --orange: #d95926; --aqua: #199e70; --red: #e66767; --yellow: #c98500;
    --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --surface: #1a1a19; --page: #0d0d0d;
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; background: var(--page); color: var(--ink); margin: 0; }}
  .deck {{ max-width: 980px; margin: 0 auto; }}
  nav.top-nav {{ position: sticky; top: 0; background: var(--page); border-bottom: 1px solid var(--grid); padding: 0.7rem 1.5rem; font-size: 0.85rem; z-index: 10; display: flex; justify-content: space-between; }}
  nav.top-nav a {{ color: var(--blue); text-decoration: none; margin-left: 1rem; }}
  nav.top-nav a:hover {{ text-decoration: underline; }}
  button.theme-toggle {{ margin-left: 1.1rem; font-size: 0.85rem; background: var(--surface); border: 1px solid var(--grid); color: var(--ink-2); border-radius: 999px; padding: 0.25rem 0.65rem; cursor: pointer; }}
  button.theme-toggle:hover {{ color: var(--ink); }}
  section.slide {{ padding: 3.2rem 1.75rem; border-bottom: 1px solid var(--grid); }}
  section.slide.alt {{ background: var(--surface); }}
  section.slide h1 {{ font-size: 2rem; margin: 0 0 0.3rem; }}
  section.slide h2 {{ font-size: 1.5rem; margin: 0 0 1.1rem; }}
  section.slide .kicker {{ text-transform: uppercase; letter-spacing: 0.06em; font-size: 0.78rem; color: var(--muted); margin-bottom: 0.5rem; }}
  section.slide p.lede {{ font-size: 1.1rem; color: var(--ink-2); max-width: 640px; }}
  section.slide p {{ line-height: 1.55; color: var(--ink-2); }}
  section.slide ul, section.slide ol {{ line-height: 1.6; color: var(--ink-2); padding-left: 1.3rem; }}
  section.slide li {{ margin-bottom: 0.5rem; }}
  section.slide strong {{ color: var(--ink); }}
  .stat-row {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 1.5rem 0; }}
  .stat {{ flex: 1; min-width: 150px; background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 0.9rem 1.1rem; }}
  section.slide.alt .stat {{ background: var(--page); }}
  .stat .n {{ font-size: 1.55rem; font-weight: 700; }}
  .stat .l {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.15rem; }}
  .two-col {{ display: grid; grid-template-columns: 1.05fr 0.95fr; gap: 2rem; align-items: center; }}
  @media (max-width: 760px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
  table.mini {{ border-collapse: collapse; width: 100%; font-size: 0.88rem; margin-top: 0.5rem; }}
  table.mini th {{ text-align: left; color: var(--muted); font-weight: 500; border-bottom: 1px solid #c3c2b7; padding: 0.4rem 0.5rem; }}
  table.mini td {{ padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--grid); color: var(--ink-2); }}
  table.mini td:first-child {{ color: var(--ink); font-weight: 600; }}
  .bug-card {{ background: var(--surface); border-left: 3px solid var(--red); border-radius: 0 8px 8px 0; padding: 0.85rem 1.1rem; margin-bottom: 0.9rem; }}
  section.slide.alt .bug-card {{ background: var(--page); }}
  .bug-card .bug-title {{ font-weight: 700; margin-bottom: 0.2rem; }}
  .bug-card .bug-fix {{ color: var(--aqua); font-weight: 600; }}
  .check-row {{ display: flex; justify-content: space-between; align-items: baseline; padding: 0.55rem 0; border-bottom: 1px solid var(--grid); font-size: 0.92rem; }}
  .check-row .status {{ font-weight: 700; }}
  .status.pass {{ color: var(--aqua); }}
  .status.fail {{ color: var(--red); }}
  .badge {{ display: inline-block; background: var(--yellow); color: #4a3500; font-size: 0.72rem; font-weight: 700; padding: 0.1rem 0.5rem; border-radius: 10px; margin-left: 0.5rem; }}
  .cta-row {{ display: flex; gap: 0.9rem; margin-top: 1.4rem; flex-wrap: wrap; }}
  .cta-row a {{ display: inline-block; background: var(--blue); color: #fff; text-decoration: none; padding: 0.65rem 1.2rem; border-radius: 8px; font-weight: 600; font-size: 0.92rem; }}
  .cta-row a.secondary {{ background: transparent; color: var(--blue); border: 1px solid var(--blue); }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 2rem; }}
  svg.diagram {{ width: 100%; height: auto; }}
</style>
</head>
<body>
<script>
  (function() {{
    try {{
      const saved = localStorage.getItem("imprint-theme");
      if (saved === "dark" || saved === "light") document.documentElement.setAttribute("data-theme", saved);
    }} catch (e) {{}}
  }})();
</script>
<nav class="top-nav">
  <span><strong>Imprint P&amp;L Model</strong> &middot; How It Was Built</span>
  <span><a href="unified_narrative.html">Overview</a><a href="dashboard.html">Executive dashboard</a><a href="narrative_report.html">Narrative walkthrough</a><button class="theme-toggle" id="theme-toggle" type="button" aria-label="Toggle dark mode">&#9789;</button></span>
</nav>

<div class="deck">

<section class="slide">
  <div class="kicker">Corporate Finance &middot; Forecasting Infrastructure</div>
  <h1>How We Built the Management P&amp;L Forecasting Model</h1>
  <p class="lede">A driver-based vintage forecasting model for all 10 merchant programs &mdash; how it's architected, the assumptions it rests on, the bugs a second independent pass caught before they shipped, and where it should be pushed further.</p>
  <div class="stat-row">
    <div class="stat"><div class="n">10</div><div class="l">merchant programs</div></div>
    <div class="stat"><div class="n">~67K</div><div class="l">raw actuals rows</div></div>
    <div class="stat"><div class="n">8Q</div><div class="l">forecast horizon</div></div>
    <div class="stat"><div class="n">{AUDIT_N_PASS} / {AUDIT_N_TOTAL}</div><div class="l">independent audit checks passing</div></div>
  </div>
</section>

<section class="slide alt">
  <div class="kicker">The ask</div>
  <h2>Cohort-level actuals in, consolidated P&amp;L out</h2>
  <p>The source data is a vintage triangle: 10 merchants, each with 2&ndash;14 quarters of cohort-level history across 34 line items and 5 FICO tiers &mdash; not a flat time series. The task: project every program forward 8 quarters (Q3 2026&ndash;Q2 2028) and roll it up into one consolidated Management P&amp;L, with cohort-level views and a defensible LTV/CAC methodology.</p>
  <ul>
    <li>No pre-built P&amp;L existed &mdash; the hierarchy, subtotals, and aggregation logic had to be designed from the raw line items.</li>
    <li>No valuation curve existed for accounts not yet booked &mdash; frontbook sizing had to be built from a growth-trend assumption.</li>
    <li>No single "right answer" &mdash; the brief explicitly grades judgment and defensibility, not a target number.</li>
  </ul>
</section>

<section class="slide">
  <div class="kicker">Architecture</div>
  <h2>Driver-based, not curve-per-line-item</h2>
  <p class="lede">Only 10 of the 34 line items are forecast as independent drivers. Every recurring dollar line is <strong>historical rate &times; forecasted driver</strong>, with the rate itself built as a curve indexed by cohort age &mdash; not a flat number.</p>
  {ARCHITECTURE_DIAGRAM_SVG}
  <div class="stat-row">
    <div class="stat"><div class="n">10</div><div class="l">forecasted drivers</div></div>
    <div class="stat"><div class="n">24</div><div class="l">rate-derived $ lines</div></div>
    <div class="stat"><div class="n">7</div><div class="l">acquisition-cost lines (feed CAC)</div></div>
  </div>
</section>

<section class="slide alt">
  <div class="kicker">Architecture</div>
  <h2>Backbook and frontbook, one engine</h2>
  <div class="two-col">
    <div>
      <p>Existing cohorts (<strong>backbook</strong>) are anchored to their last actual value and rolled forward on the population's development-factor curve. New cohorts booked during the forecast window (<strong>frontbook</strong>) are seeded from a trailing-4-quarter New Accounts growth trend, capped at &plusmn;25%/quarter, then grown on the <em>same</em> curve.</p>
      <p>The only difference between the two books is where the starting size comes from &mdash; everything downstream is identical machinery.</p>
    </div>
    {BACKBOOK_FRONTBOOK_DIAGRAM_SVG}
  </div>
</section>

<section class="slide">
  <div class="kicker">LTV / CAC methodology</div>
  <h2>Discounted, standardized, and defended in two layers</h2>
  <ul>
    <li><strong>CAC</strong> = acquisition-family costs (marketing, origination, sign-on bonus, KYC/AML, added features, bounties) &divide; New Accounts, at the cohort's own booking quarter.</li>
    <li><strong>LTV</strong> = discounted cumulative Contribution Profit per account over a <strong>standardized 12-quarter (3-year) window</strong> &mdash; so a brand-new cohort and a 14-quarter-old one compare on equal footing. Discount rate: 15% annual hurdle (&asymp;3.56%/quarter).</li>
    <li>Cohorts whose window runs past the Q2 2028 cutoff are extended with a <strong>population-level fill</strong> (what did this kind of cohort typically look like at that age), not a compounding growth factor &mdash; Contribution Profit per account is a signed quantity that crosses zero, and a multiplicative factor is the wrong tool for that (see the bug log).</li>
  </ul>
  <div class="stat-row">
    <div class="stat"><div class="n">0.85x</div><div class="l">portfolio LTV/CAC</div></div>
    <div class="stat"><div class="n">2.94x</div><div class="l">Poor FICO tier</div></div>
    <div class="stat"><div class="n">-0.32x</div><div class="l">Exceptional FICO tier</div></div>
  </div>
</section>

<section class="slide alt">
  <div class="kicker">What went wrong, and how it was caught</div>
  <h2>Three recurring failure modes, each caught before shipping</h2>
  <p class="lede">Each script was built, run, and inspected before moving to the next. That loop &mdash; plus a second, independently-scoped review that owed the first pass nothing &mdash; caught all of these before they reached the final numbers.</p>

  <div class="bug-card">
    <div class="bug-title">1. Silent bugs that don't crash, they just quietly drop output</div>
    <p style="margin:0">A scoping bug in the forecast engine caused most driver calculations to silently produce zero rows instead of failing loudly &mdash; a clean run gave no signal anything was wrong.</p>
    <p class="bug-fix" style="margin:0.3rem 0 0">Caught by: checking whether output was actually continuous and complete, not by trusting that "it ran without errors" means "it's right."</p>
  </div>
  <div class="bug-card">
    <div class="bug-title">2. Naive extrapolation on thin-history data compounds into nonsense</div>
    <p style="margin:0">Holding a thin-history merchant's own last-observed growth rate flat and compounding it multiple quarters forward produces unrealistic blow-ups &mdash; a pattern that showed up more than once, in both the driver forecast and the LTV extrapolation.</p>
    <p class="bug-fix" style="margin:0.3rem 0 0">Fixed by: borrowing a pooled, cross-merchant pattern for the parts of the curve a thin-history cohort hasn't lived long enough to show, plus hard clips as a backstop.</p>
  </div>
  <div class="bug-card">
    <div class="bug-title">3. Subtle classification and methodology bugs need a second reviewer</div>
    <p style="margin:0">A one-time cost leaked into a recurring metric through a subtle classification bug, compounded by using the wrong extrapolation technique (a multiplicative factor) on a quantity that isn't supposed to be multiplied (a signed $/account figure that legitimately crosses zero).</p>
    <p class="bug-fix" style="margin:0.3rem 0 0">Fixed by: correcting the classification logic and redesigning the extrapolation around the data's actual shape. Found by a second, independently-scoped review <span class="badge">not self-review</span> &mdash; self-review alone had already signed off.</p>
  </div>
</section>

<section class="slide">
  <div class="kicker">Independent audit</div>
  <h2>{AUDIT_N_TOTAL} automated checks, recomputed via separate code paths</h2>
  <p class="lede">Every check re-derives its answer without importing the pipeline's own functions &mdash; most start from the raw source CSV &mdash; so a bug shared between "build the number" and "check the number" can't hide.</p>
  {AUDIT_ROWS_HTML}
  <p style="margin-top:1.2rem"><strong>On Check B (roll-forward identity):</strong> the bulk of the headline gap is a real, explained effect, not a bug &mdash; a newly-originated cohort shows up with its full starting balance the same quarter it books, and this simple flow identity has no clean "additions" term for that. Excluding new originations and looking only at continuing cohorts, the gap collapses to roughly 1% in the actuals period. A smaller gap remains specifically in forecast quarters: Outstanding Balance and Net Transaction Volume each carry their own, independently-estimated seasonal pattern with different phase and magnitude, so a balance identity that mixes both doesn't reconcile quite as tightly once both are seasonalized separately. Both effects are understood and small relative to the identity's purpose as a reconciliation signal, not as how Outstanding Balance is actually forecast.</p>
  <p style="margin-top:0.8rem">Also reviewed with an automated static-analysis pass (81.2/100 average, grade B, zero SOLID violations, zero security findings) &mdash; the one real finding was the complexity of the forecast engine's core loop, the same function that hid the first failure mode above.</p>
</section>

<section class="slide alt">
  <div class="kicker">Where to push next</div>
  <h2>Known limitations, stated plainly</h2>
  <table class="mini">
    <tr><th>Limitation</th><th>Why it's there</th></tr>
    <tr><td>Single scenario</td><td>Every rate is held at its last observed level into a 2-year horizon &mdash; no macro/rate-environment toggle yet.</td></tr>
    <tr><td>Thin-history extrapolation</td><td>Merchants 9 &amp; 10 have only 4 and 2 quarters of history; their curves lean on pooled cross-merchant patterns.</td></tr>
    <tr><td>Fee Revenue / Other Credits</td><td>No strong empirical driver in this dataset (best correlations 0.47 and 0.19) &mdash; shipped on a proxy, flagged not asserted.</td></tr>
    <tr><td>FICO is origination-vintage</td><td>No way to track credit-quality drift after booking &mdash; sharpens both loss curves and the FICO/LTV finding.</td></tr>
  </table>
</section>

<section class="slide">
  <div class="kicker">Go deeper</div>
  <h2>Four documents, four audiences</h2>
  <div class="stat-row">
    <div class="stat"><div class="n">Overview</div><div class="l">The board-ready front door &mdash; P&amp;L, cohorts, model, narrative, one page</div></div>
    <div class="stat"><div class="n">Dashboard</div><div class="l">Filter by merchant/vintage/FICO for reporting &amp; quick analysis</div></div>
    <div class="stat"><div class="n">Narrative</div><div class="l">The full written story &mdash; risks, winners/drags, data gaps</div></div>
    <div class="stat"><div class="n">BUILD_LOG.md</div><div class="l">Every assumption, bug, and fix, in full technical detail</div></div>
  </div>
  <div class="cta-row">
    <a href="unified_narrative.html">Back to overview</a>
    <a href="dashboard.html">Open the executive dashboard</a>
    <a class="secondary" href="narrative_report.html">Read the narrative walkthrough</a>
  </div>
</section>

<footer>Built from combined_actuals_forecast.parquet via the scripts/ pipeline &middot; see BUILD_LOG.md for full detail.</footer>
</div>
<script>
  document.getElementById("theme-toggle").addEventListener("click", () => {{
    const isDark = document.documentElement.getAttribute("data-theme") === "dark"
      || (document.documentElement.getAttribute("data-theme") !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    const next = isDark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {{ localStorage.setItem("imprint-theme", next); }} catch (e) {{}}
  }});
</script>
</body>
</html>
"""


def main():
    out_path = OUT_DIR / "html" / "pitch_deck.html"
    out_path.write_text(HTML)
    print(f"Wrote pitch deck -> {out_path}")


if __name__ == "__main__":
    main()
