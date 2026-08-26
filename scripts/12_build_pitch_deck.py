"""
12_build_pitch_deck.py

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

OUT_DIR = Path(__file__).resolve().parent.parent / "output"

PALETTE = {
    "blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a",
    "red": "#e34948", "yellow": "#eda100",
    "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
    "grid": "#e1e0d9", "surface": "#fcfcfb", "page": "#f9f9f7",
}

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
  <span><a href="dashboard.html">Executive dashboard</a><a href="narrative_report.html">Narrative walkthrough</a><button class="theme-toggle" id="theme-toggle" type="button" aria-label="Toggle dark mode">&#9789;</button></span>
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
    <div class="stat"><div class="n">5 / 6</div><div class="l">independent audit checks passing</div></div>
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
  <svg class="diagram" viewBox="0 0 900 220" role="img" aria-label="Architecture diagram: drivers feed a rate curve library, which multiplies out to P&amp;L dollar lines">
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" style="fill:var(--muted)"/>
      </marker>
    </defs>
    <g font-family="inherit" font-size="13.5">
      <rect x="20" y="70" width="190" height="80" rx="10" style="fill:var(--blue);stroke:var(--blue)" opacity="0.12"/>
      <text x="115" y="100" text-anchor="middle" font-weight="700" style="fill:var(--blue)">Drivers</text>
      <text x="115" y="120" text-anchor="middle" style="fill:var(--ink-2)" font-size="11.5">New Accounts, Balances,</text>
      <text x="115" y="135" text-anchor="middle" style="fill:var(--ink-2)" font-size="11.5">Volume &mdash; chain-ladder curves</text>

      <line x1="210" y1="110" x2="290" y2="110" style="stroke:var(--muted)" stroke-width="1.5" marker-end="url(#arrow)"/>

      <rect x="300" y="70" width="220" height="80" rx="10" style="fill:var(--orange);stroke:var(--orange)" opacity="0.12"/>
      <text x="410" y="100" text-anchor="middle" font-weight="700" style="fill:var(--orange)">Rate curve library</text>
      <text x="410" y="120" text-anchor="middle" style="fill:var(--ink-2)" font-size="11.5">$ line &divide; driver, by cohort age</text>
      <text x="410" y="135" text-anchor="middle" style="fill:var(--ink-2)" font-size="11.5">(loss rate, yield, interchange rate...)</text>

      <line x1="520" y1="110" x2="600" y2="110" style="stroke:var(--muted)" stroke-width="1.5" marker-end="url(#arrow)"/>

      <rect x="610" y="70" width="270" height="80" rx="10" style="fill:var(--aqua);stroke:var(--aqua)" opacity="0.12"/>
      <text x="745" y="100" text-anchor="middle" font-weight="700" style="fill:var(--aqua)">P&amp;L dollar lines</text>
      <text x="745" y="120" text-anchor="middle" style="fill:var(--ink-2)" font-size="11.5">rate &times; forecasted driver</text>
      <text x="745" y="135" text-anchor="middle" style="fill:var(--ink-2)" font-size="11.5">&rarr; Gross Revenue, Cost of Sales, ...</text>

      <text x="450" y="20" text-anchor="middle" style="fill:var(--muted)" font-size="12">One mechanism handles a genuinely flat rate (yield, ~6.05%/quarter) and a genuinely curving one</text>
      <text x="450" y="36" text-anchor="middle" style="fill:var(--muted)" font-size="12">(loss rate, rising from 0% toward a plateau near quarter 9&ndash;13) without hand-coding which is which.</text>
    </g>
  </svg>
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
    <svg class="diagram" viewBox="0 0 380 240" role="img" aria-label="Backbook cohorts anchored to last actual and grown forward; frontbook cohorts seeded from a growth trend and grown on the same curve">
      <g font-family="inherit" font-size="12">
        <text x="10" y="20" font-weight="700" style="fill:var(--blue)">Backbook</text>
        <line x1="10" y1="60" x2="130" y2="60" style="stroke:var(--blue)" stroke-width="2"/>
        <circle cx="130" cy="60" r="4" style="fill:var(--blue)"/>
        <line x1="130" y1="60" x2="230" y2="45" style="stroke:var(--blue)" stroke-width="2" stroke-dasharray="4,3"/>
        <text x="10" y="80" style="fill:var(--ink-2)" font-size="11">actual history</text>
        <text x="140" y="42" style="fill:var(--ink-2)" font-size="11">curve-forecast</text>

        <text x="10" y="130" font-weight="700" style="fill:var(--orange)">Frontbook</text>
        <circle cx="30" cy="170" r="4" style="fill:var(--orange)"/>
        <line x1="30" y1="170" x2="230" y2="150" style="stroke:var(--orange)" stroke-width="2" stroke-dasharray="4,3"/>
        <text x="10" y="190" style="fill:var(--ink-2)" font-size="11">seeded from</text>
        <text x="10" y="203" style="fill:var(--ink-2)" font-size="11">growth trend</text>
        <text x="140" y="143" style="fill:var(--ink-2)" font-size="11">same curve library</text>
      </g>
    </svg>
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
    <div class="stat"><div class="n">0.82x</div><div class="l">portfolio LTV/CAC</div></div>
    <div class="stat"><div class="n">2.97x</div><div class="l">Poor FICO tier</div></div>
    <div class="stat"><div class="n">-0.39x</div><div class="l">Exceptional FICO tier</div></div>
  </div>
</section>

<section class="slide alt">
  <div class="kicker">What went wrong, and how it was caught</div>
  <h2>Three real bugs, one false-positive audit alarm</h2>
  <p class="lede">Each script was built, run, and inspected before moving to the next. That loop &mdash; plus a second, independently-scoped review that owed the first pass nothing &mdash; caught all four before they reached the final numbers.</p>

  <div class="bug-card">
    <div class="bug-title">1. Silent scope leak in the forecast engine</div>
    <p style="margin:0">A loop variable tracking each cohort's "last observed quarter" was reset once per cohort but mutated inside a nested loop shared across all line items &mdash; every driver after the first processed one silently produced zero forecast rows. Forecast rows jumped from 19,680 to 44,320 after the fix.</p>
    <p class="bug-fix" style="margin:0.3rem 0 0">Caught by: checking whether one cohort's actual-to-forecast trajectory was even continuous. It wasn't there at all.</p>
  </div>
  <div class="bug-card">
    <div class="bug-title">2. Tail-factor blow-up on thin-history merchants</div>
    <p style="margin:0">Holding a merchant's own last-observed growth factor constant forever compounds unrealistically. Merchant 10 has exactly one observed factor for Net Transaction Volume (+25.7%/quarter); holding it flat produced a 13.8x blow-up and dragged consolidated Gross Margin from 12.7% to 2.1%.</p>
    <p class="bug-fix" style="margin:0.3rem 0 0">Fixed by: a pooled median late-stage factor across all merchants, plus a &plusmn;30%/quarter clip. Margin is now stable at ~13.2&ndash;13.4%.</p>
  </div>
  <div class="bug-card">
    <div class="bug-title">3. LTV extrapolation reused the wrong tool &mdash; twice</div>
    <p style="margin:0">A one-time Partner Signing Bonus cost leaked into recurring Contribution Profit via a Category-based (not Model-Role-based) classification bug, duplicated across two files. That alone corrupted a handful of cohorts &mdash; but the deeper issue was using a <em>multiplicative</em> growth factor on a <em>signed</em> $/account quantity that crosses zero, which compounded individually-plausible factors into 40x+ LTV/CAC for the newest cohorts.</p>
    <p class="bug-fix" style="margin:0.3rem 0 0">Fixed by: a shared, Model-Role-first classifier, and redesigning the extrapolation as a population-level fill instead of a compounding factor. Found by a second, independently-scoped review <span class="badge">not self-review</span>.</p>
  </div>
</section>

<section class="slide">
  <div class="kicker">Independent audit</div>
  <h2>Six automated checks, recomputed via separate code paths</h2>
  <p class="lede">Every check re-derives its answer without importing the pipeline's own functions &mdash; most start from the raw source CSV &mdash; so a bug shared between "build the number" and "check the number" can't hide.</p>
  <div class="check-row"><span>A &mdash; Actuals reconciliation vs. raw source CSV</span><span class="status pass">PASS</span></div>
  <div class="check-row"><span>B &mdash; Roll-forward identity (root-caused: new-cohort origination effect)</span><span class="status fail">FAIL, explained</span></div>
  <div class="check-row"><span>C &mdash; Actual/forecast seam continuity</span><span class="status pass">PASS</span></div>
  <div class="check-row"><span>D &mdash; Forecast CAC/account vs. historical, per merchant</span><span class="status pass">PASS</span></div>
  <div class="check-row"><span>E &mdash; Cohort LTV magnitude sanity (regression guard)</span><span class="status pass">PASS</span></div>
  <div class="check-row"><span>F &mdash; Independent trend cross-check vs. naive linear regression</span><span class="status pass">PASS</span></div>
  <p style="margin-top:1.2rem">Also reviewed with an automated static-analysis pass (89.6/100 average, grade B, zero SOLID violations, zero security findings) &mdash; the one real finding was the complexity of the forecast engine's core loop, the same function that hid bug #1 above.</p>
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
  <h2>Three documents, three audiences</h2>
  <div class="stat-row">
    <div class="stat"><div class="n">Dashboard</div><div class="l">Filter by merchant/vintage/FICO for reporting &amp; quick analysis</div></div>
    <div class="stat"><div class="n">Narrative</div><div class="l">The full written story &mdash; risks, winners/drags, data gaps</div></div>
    <div class="stat"><div class="n">BUILD_LOG.md</div><div class="l">Every assumption, bug, and fix, in full technical detail</div></div>
  </div>
  <div class="cta-row">
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
    out_path = OUT_DIR / "pitch_deck.html"
    out_path.write_text(HTML)
    print(f"Wrote pitch deck -> {out_path}")


if __name__ == "__main__":
    main()
