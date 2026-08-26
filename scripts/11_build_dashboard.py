"""
11_build_dashboard.py

Builds output/dashboard.html — the primary executive deliverable: a rolled-up
Management P&L with live filters (Merchant / Vintage / FICO / Scenario), KPI
tiles, a quarterly trend chart, two comparison charts, and a data table.

Design choices, per the data-visualization skill:
  - Position/length encodings only (line + bar charts) -- no pie, no 3D,
    no dual-axis. Comparison bars are horizontal bars (position along a
    common scale), the single most accurate encoding for magnitude compare.
  - Overview -> filter -> details (Shneiderman): KPI tiles + trend chart
    are the overview; the Merchant/Vintage/FICO dropdowns are the
    filter step; the data table underneath is "details on demand."
  - Filtering recomputes P&L bucket dollar totals first, THEN derives
    margins/ratios from the summed dollars client-side -- never averages
    a pre-computed percentage across rows, which would silently misstate
    the margin for any filtered subset.
  - All data embedded inline (no fetch()) so the file works standalone via
    file:// -- consistent with the rest of this deliverable.
  - Same validated categorical palette as the narrative report and pitch
    deck, for visual consistency across all three documents.
"""
import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "output"


def main():
    data = json.loads((OUT_DIR / "dashboard_data.json").read_text())
    data_json = json.dumps(data, separators=(",", ":"))

    html = HTML_TEMPLATE.replace("__DASHBOARD_DATA__", data_json)
    out_path = OUT_DIR / "dashboard.html"
    out_path.write_text(html)
    print(f"Wrote dashboard -> {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Imprint Management P&amp;L Dashboard</title>
<style>
  /* Light palette (default). Dark redefines the same tokens below -- see the
     data-visualization skill's dark-mode pattern: an explicit data-theme
     wins over the OS media query, which wins over this default. Never a
     token defined only inside a media/data-theme block. */
  :root {
    color-scheme: light;
    --blue: #2a78d6; --orange: #eb6834; --aqua: #1baf7a; --yellow: #eda100; --red: #e34948;
    --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781; --grid: #e1e0d9;
    --surface: #fcfcfb; --page: #f9f9f7; --border: rgba(11,11,11,0.10);
    --select-bg: #ffffff; --baseline: #c3c2b7;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      color-scheme: dark;
      --blue: #3987e5; --orange: #d95926; --aqua: #199e70; --yellow: #c98500; --red: #e66767;
      --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781; --grid: #2c2c2a;
      --surface: #1a1a19; --page: #0d0d0d; --border: rgba(255,255,255,0.10);
      --select-bg: #232322; --baseline: #383835;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --blue: #3987e5; --orange: #d95926; --aqua: #199e70; --yellow: #c98500; --red: #e66767;
    --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781; --grid: #2c2c2a;
    --surface: #1a1a19; --page: #0d0d0d; --border: rgba(255,255,255,0.10);
    --select-bg: #232322; --baseline: #383835;
  }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; background: var(--page); color: var(--ink); margin: 0; }
  .wrap { max-width: 1180px; margin: 0 auto; padding: 1.75rem 1.5rem 4rem; }
  header.page-head { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.25rem; }
  h1 { font-size: 1.55rem; margin: 0; }
  .subtitle { color: var(--ink-2); margin: 0.15rem 0 1.25rem; }
  nav.doc-links { font-size: 0.85rem; display: flex; align-items: center; gap: 0.25rem; }
  nav.doc-links a { color: var(--blue); text-decoration: none; margin-left: 1rem; }
  nav.doc-links a:hover { text-decoration: underline; }
  button.theme-toggle { margin-left: 1.1rem; font-size: 0.85rem; background: var(--surface); border: 1px solid var(--grid); color: var(--ink-2); border-radius: 999px; padding: 0.3rem 0.7rem; cursor: pointer; }
  button.theme-toggle:hover { color: var(--ink); }

  .filter-bar { display: flex; gap: 0.9rem; flex-wrap: wrap; align-items: flex-end; background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 0.9rem 1.1rem; margin-bottom: 1.25rem; }
  .filter-field { display: flex; flex-direction: column; gap: 0.25rem; }
  .filter-field label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted); }
  .filter-field select { font: inherit; font-size: 0.88rem; padding: 0.4rem 0.55rem; border: 1px solid var(--grid); border-radius: 6px; background: var(--select-bg); color: var(--ink); min-width: 168px; }
  .filter-bar .reset-btn { font-size: 0.82rem; color: var(--blue); background: none; border: 1px solid var(--grid); border-radius: 6px; padding: 0.42rem 0.75rem; cursor: pointer; }
  .filter-bar .reset-btn:hover { background: var(--page); }
  .active-filter-note { font-size: 0.82rem; color: var(--muted); margin: -0.5rem 0 1.25rem; }

  .kpi-row { display: flex; gap: 0.85rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
  .kpi-tile { flex: 1; min-width: 165px; background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 0.9rem 1.05rem; }
  .kpi-tile .label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.02em; color: var(--muted); }
  .kpi-tile .value { font-size: 1.45rem; font-weight: 600; margin-top: 0.15rem; font-variant-numeric: tabular-nums; }
  .kpi-tile .sub { font-size: 0.78rem; color: var(--ink-2); margin-top: 0.1rem; }
  .kpi-tile .value.neg { color: var(--red); }
  .kpi-tile .value.pos { color: var(--blue); }

  section.panel { background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 1.1rem 1.2rem 1.3rem; margin-bottom: 1.25rem; }
  section.panel h2 { font-size: 1rem; margin: 0 0 0.15rem; }
  section.panel .panel-note { font-size: 0.82rem; color: var(--muted); margin: 0 0 0.75rem; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }
  @media (max-width: 820px) { .two-col { grid-template-columns: 1fr; } }

  /* Driver KPI tab (item 7) -- 6 small-multiple trend lines, one metric
     each, rather than one combined chart: the 6 metrics have unrelated
     scales/units (a rate vs. a $/account figure) and most have stock-based
     denominators that are only ever safe to read per-quarter, not blended
     across a range -- a trend line sidesteps that by construction. */
  .kpi-chart-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
  @media (max-width: 900px) { .kpi-chart-grid { grid-template-columns: repeat(2, 1fr); } }
  @media (max-width: 600px) { .kpi-chart-grid { grid-template-columns: 1fr; } }
  .kpi-chart-cell { border: 1px solid var(--grid); border-radius: 8px; padding: 0.7rem 0.8rem 0.5rem; }
  .kpi-chart-cell h3 { font-size: 0.82rem; margin: 0 0 0.35rem; font-weight: 600; }
  .kpi-chart-cell .kpi-chart-latest { font-size: 0.72rem; color: var(--muted); margin-top: 0.2rem; }

  /* Multi-select compare chart (item 6) */
  .compare-controls { display: flex; gap: 0.9rem; flex-wrap: wrap; margin-bottom: 0.85rem; }
  .compare-value-picker { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.9rem; }
  .compare-value-picker label { display: flex; align-items: center; gap: 0.35rem; font-size: 0.8rem; background: var(--page); border: 1px solid var(--grid); border-radius: 6px; padding: 0.28rem 0.6rem; cursor: pointer; }
  .compare-value-picker input[type="checkbox"] { margin: 0; accent-color: var(--blue); }

  svg.chart-svg { width: 100%; height: auto; overflow: visible; }
  svg text { font-family: inherit; fill: var(--ink-2); }
  .axis-line { stroke: var(--grid); stroke-width: 1; }
  .gridline { stroke: var(--grid); stroke-width: 1; }
  .series-line { fill: none; stroke-width: 2.25; }
  .series-dot { stroke: var(--surface); stroke-width: 1.5; }
  .seam-band { fill: var(--blue); opacity: 0.05; }
  .seam-label { font-size: 0.68rem; fill: var(--muted); }
  .legend-row { display: flex; gap: 1.1rem; flex-wrap: wrap; font-size: 0.82rem; margin-bottom: 0.6rem; }
  .legend-item { display: flex; align-items: center; gap: 0.4rem; }
  .legend-swatch { width: 12px; height: 3px; border-radius: 2px; display: inline-block; }

  table.datatable { border-collapse: collapse; width: 100%; font-size: 0.83rem; }
  table.datatable th { text-align: right; color: var(--muted); font-weight: 500; border-bottom: 1px solid var(--baseline); padding: 0.4rem 0.55rem; position: sticky; top: 0; background: var(--surface); }
  table.datatable th:first-child, table.datatable td:first-child { text-align: left; }
  table.datatable td { text-align: right; padding: 0.38rem 0.55rem; border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; }
  .table-scroll { max-height: 420px; overflow-y: auto; border: 1px solid var(--grid); border-radius: 8px; }
  .table-scroll table.datatable th { top: -1px; }
  td.neg { color: var(--red); }

  /* Detail P&L view (item 4) -- transposed (line items as rows, quarters as
     columns), so a Stock/snapshot line item is only ever summed across
     entities WITHIN one quarter (always valid), never across the columns
     (quarters) themselves. Needs both x and y scroll -- 33 line items x up
     to 22 quarters. */
  details.detail-toggle { margin-top: 0.4rem; }
  details.detail-toggle > summary { cursor: pointer; font-size: 0.88rem; color: var(--blue); padding: 0.3rem 0; list-style: none; }
  details.detail-toggle > summary::-webkit-details-marker { display: none; }
  details.detail-toggle > summary::before { content: "▸ "; }
  details.detail-toggle[open] > summary::before { content: "▾ "; }
  .detail-table-scroll { max-height: 560px; overflow: auto; border: 1px solid var(--grid); border-radius: 8px; margin-top: 0.6rem; }
  table.detail-table th, table.detail-table td { white-space: nowrap; }
  table.detail-table th:first-child, table.detail-table td:first-child { position: sticky; left: 0; background: var(--surface); z-index: 1; }
  tr.group-row td { text-align: left; font-weight: 600; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted); background: var(--page); padding-top: 0.55rem; }
  tr.group-row td:first-child { background: var(--page); }

  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }
  footer.page-foot { color: var(--muted); font-size: 0.8rem; margin-top: 2rem; }
</style>
</head>
<body>
<script>
  // Apply saved theme before first paint, to avoid a flash of the wrong theme.
  (function() {
    try {
      const saved = localStorage.getItem("imprint-theme");
      if (saved === "dark" || saved === "light") document.documentElement.setAttribute("data-theme", saved);
    } catch (e) {}
  })();
</script>
<div class="wrap">

<header class="page-head">
  <h1>Imprint Management P&amp;L Dashboard</h1>
  <nav class="doc-links">
    <a href="narrative_report.html">Narrative walkthrough &rarr;</a>
    <a href="pitch_deck.html">How this was built &rarr;</a>
    <button class="theme-toggle" id="theme-toggle" type="button" aria-label="Toggle dark mode">&#9789;</button>
  </nav>
</header>
<p class="subtitle">All 10 merchant programs, Q1 2023 actuals through Q2 2028 forecast &middot; filter by merchant, vintage, and FICO tier for ad hoc analysis</p>

<div class="filter-bar" role="group" aria-label="P&amp;L filters">
  <div class="filter-field">
    <label for="f-merchant">Merchant</label>
    <select id="f-merchant"></select>
  </div>
  <div class="filter-field">
    <label for="f-vintage">Vintage (cohort)</label>
    <select id="f-vintage"></select>
  </div>
  <div class="filter-field">
    <label for="f-fico">FICO tier</label>
    <select id="f-fico"></select>
  </div>
  <div class="filter-field">
    <label for="f-scenario">Period</label>
    <select id="f-scenario">
      <option value="all">Actuals + Forecast</option>
      <option value="Actual">Actuals only</option>
      <option value="Base Case">Forecast only</option>
    </select>
  </div>
  <button class="reset-btn" id="reset-filters" type="button">Reset filters</button>
</div>
<p class="active-filter-note" id="filter-summary" role="status"></p>

<div class="kpi-row" id="kpi-row"></div>

<section class="panel">
  <h2>P&amp;L trend by quarter</h2>
  <p class="panel-note">Shaded band marks the forecast period (Q3 2026 onward). Reflects the filters above.</p>
  <div class="legend-row">
    <span class="legend-item"><span class="legend-swatch" style="background:var(--blue)"></span>Gross Revenue</span>
    <span class="legend-item"><span class="legend-swatch" style="background:var(--aqua)"></span>Gross Profit</span>
    <span class="legend-item"><span class="legend-swatch" style="background:var(--orange)"></span>Contribution Profit</span>
  </div>
  <div id="trend-chart"></div>
</section>

<!-- Day 2 item 6 replaced the two static "Contribution Profit by merchant" /
     "by FICO tier" bar charts below with the general-purpose multi-select
     compare chart (it's a strict superset: picking Contribution Profit +
     all merchants reproduces the old merchant chart exactly). Kept here,
     commented out, per an explicit request to keep the old view retrievable
     until there's been a chance to see the new one in use. To reinstate:
     un-comment this block, restore #merchant-chart/#fico-chart's two
     renderComparisonChart(...) calls in renderAll() below (the function
     itself was never removed), and decide whether it lives alongside or
     instead of the new compare section.
<div class="two-col">
  <section class="panel">
    <h2>Contribution Profit by merchant</h2>
    <p class="panel-note">Reflects the Vintage / FICO / Period filters above (Merchant filter ignored here so all 10 stay comparable).</p>
    <div id="merchant-chart"></div>
  </section>
  <section class="panel">
    <h2>Contribution Profit by FICO tier</h2>
    <p class="panel-note">Reflects the Merchant / Vintage / Period filters above (FICO filter ignored here so all 5 stay comparable).</p>
    <div id="fico-chart"></div>
  </section>
</div>
-->

<section class="panel">
  <h2>Compare across merchants, vintages, or FICO tiers</h2>
  <p class="panel-note">Pick a dimension and which values to compare on one chart, and a metric. Bars for additive $ measures (they sum to a portfolio total, shown grouped/clustered per quarter -- not stacked, since these are separate entities being compared, not components of one whole); lines for rate/yield metrics (they don't sum, only compare as levels over time). Includes a computed blended total for whatever's selected, derived the same sum-then-divide way as everywhere else on this page. Reflects the Period filter above; the compared dimension's own top filter is ignored here (that's the point of comparing across it).</p>
  <div class="compare-controls">
    <div class="filter-field">
      <label for="cmp-dim">Compare by</label>
      <select id="cmp-dim">
        <option value="m">Merchant</option>
        <option value="v">Vintage (cohort)</option>
        <option value="f">FICO tier</option>
      </select>
    </div>
    <div class="filter-field">
      <label for="cmp-metric">Metric</label>
      <select id="cmp-metric"></select>
    </div>
  </div>
  <div class="compare-value-picker" id="cmp-value-picker" role="group" aria-label="Values to compare"></div>
  <div class="legend-row" id="cmp-legend"></div>
  <div id="compare-chart"></div>
</section>

<section class="panel">
  <h2>Portfolio driver KPIs</h2>
  <p class="panel-note">Payment Rate, PPAA (spend per active account), Active Rate, Revolve Rate, NIM, and Revenue Margin &mdash; shown as trend lines only, not blended into a single figure for the filtered range. Most of these ratios have a balance/snapshot denominator that's only meaningful at a single point in time (e.g. Outstanding Balance at quarter-end), so unlike Gross Revenue or Contribution Profit there's no honest way to collapse them across a multi-quarter filter into one number &mdash; each point on these lines is that quarter's own correctly-derived value. Reflects the filters above.</p>
  <div class="kpi-chart-grid" id="driver-kpi-grid">
    <div class="kpi-chart-cell"><h3>Payment Rate</h3><div id="kpi-chart-paymentRate"></div><p class="kpi-chart-latest" id="kpi-latest-paymentRate"></p></div>
    <div class="kpi-chart-cell"><h3>PPAA (NTV / Active Account)</h3><div id="kpi-chart-ppaa"></div><p class="kpi-chart-latest" id="kpi-latest-ppaa"></p></div>
    <div class="kpi-chart-cell"><h3>Active Rate</h3><div id="kpi-chart-activeRate"></div><p class="kpi-chart-latest" id="kpi-latest-activeRate"></p></div>
    <div class="kpi-chart-cell"><h3>Revolve Rate</h3><div id="kpi-chart-revolveRate"></div><p class="kpi-chart-latest" id="kpi-latest-revolveRate"></p></div>
    <div class="kpi-chart-cell"><h3>NIM</h3><div id="kpi-chart-nim"></div><p class="kpi-chart-latest" id="kpi-latest-nim"></p></div>
    <div class="kpi-chart-cell"><h3>Revenue Margin (Gross Revenue / NTV)</h3><div id="kpi-chart-revenueMargin"></div><p class="kpi-chart-latest" id="kpi-latest-revenueMargin"></p></div>
  </div>
</section>

<section class="panel">
  <h2>Quarterly P&amp;L detail</h2>
  <p class="panel-note">Reflects all filters above &mdash; for copy/paste into other tools.</p>
  <div class="table-scroll">
    <table class="datatable" id="pnl-table">
      <thead>
        <tr>
          <th>Quarter</th><th>Period</th><th>Gross Revenue</th><th>Cost of Sales</th>
          <th>Gross Profit</th><th>GM%</th><th>Contribution Profit</th><th>CM%</th>
          <th>New Accounts</th><th>CAC/Account</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <details class="detail-toggle" id="detail-toggle">
    <summary>Show detailed line items (all 33, audit view)</summary>
    <p class="panel-note">All raw line items behind the 4 P&amp;L buckets above, in traditional statement order (Volumes &amp; Balances, Revenue, Cost of Sales, Operating Expense, Acquisition Cost) &mdash; quarters as columns. Reflects the same filters as the rest of this page. Each cell is that column's own quarter, summed across whichever merchants/vintages/FICO tiers are selected &mdash; balance/snapshot line items (marked *) are never summed across quarters, only within one.</p>
    <div class="detail-table-scroll">
      <table class="datatable detail-table" id="detail-table">
        <thead><tr id="detail-table-head"></tr></thead>
        <tbody id="detail-table-body"></tbody>
      </table>
    </div>
  </details>
</section>

<footer class="page-foot">Built from combined_actuals_forecast.parquet via scripts/10_export_dashboard_data.py + 11_build_dashboard.py. See <a href="pitch_deck.html">pitch_deck.html</a> for methodology and <a href="narrative_report.html">narrative_report.html</a> for the full written narrative.</footer>
</div>

<script>
const DATA = __DASHBOARD_DATA__;
const FORECAST_START = DATA.forecastStartIdx;

// Charts are JS-rendered (fresh SVG per filter change), so dark mode is
// handled by picking the right hex map at render time and re-rendering --
// simpler and more reliably cross-browser than routing dynamically-set SVG
// attributes through CSS custom properties. Values match the CSS tokens above.
// yellow/purple added for item 6's multi-select compare chart, which can
// show more than the original 4 series at once -- values chosen to sit
// visually distinct from the existing 4 in both themes.
// muted matches the --muted CSS token (same value in both themes) --
// reserved for the compare chart's "Blended total" series specifically, so
// it never collides with whichever entity color happens to be first
// (COLORS[0]/blue) among the selected values.
const PALETTE_LIGHT = { blue: "#2a78d6", orange: "#eb6834", aqua: "#1baf7a", red: "#e34948", yellow: "#c98500", purple: "#8456ce", muted: "#898781" };
const PALETTE_DARK = { blue: "#3987e5", orange: "#d95926", aqua: "#199e70", red: "#e66767", yellow: "#e0a53a", purple: "#a684e0", muted: "#898781" };
function isDarkMode() {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark") return true;
  if (attr === "light") return false;
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}
function currentPalette() { return isDarkMode() ? PALETTE_DARK : PALETTE_LIGHT; }
const fmtMoney = (x) => {
  const sign = x < 0 ? "-" : "";
  const a = Math.abs(x);
  if (a >= 1e9) return sign + "$" + (a/1e9).toFixed(2) + "B";
  if (a >= 1e6) return sign + "$" + (a/1e6).toFixed(1) + "M";
  if (a >= 1e3) return sign + "$" + (a/1e3).toFixed(0) + "K";
  return sign + "$" + a.toFixed(0);
};
const fmtPct = (x) => (isFinite(x) ? (x*100).toFixed(1) + "%" : "—");
const fmtX = (x) => (isFinite(x) ? x.toFixed(2) + "x" : "—");
const fmtInt = (x) => Math.round(x).toLocaleString();

// ---- Populate filter dropdowns ----
function populateSelect(id, options, allLabel) {
  const el = document.getElementById(id);
  const optAll = document.createElement("option");
  optAll.value = "all"; optAll.textContent = allLabel;
  el.appendChild(optAll);
  options.forEach(o => {
    const opt = document.createElement("option");
    opt.value = o.value; opt.textContent = o.label;
    el.appendChild(opt);
  });
}
populateSelect("f-merchant", DATA.dims.merchants.map(m => ({value: m, label: m})), "All merchants");
populateSelect("f-vintage", DATA.dims.vintages.map(v => ({value: String(v.idx), label: v.label})), "All vintages");
populateSelect("f-fico", DATA.dims.ficoBuckets.map(f => ({value: f, label: f})), "All FICO tiers");

const els = {
  merchant: document.getElementById("f-merchant"),
  vintage: document.getElementById("f-vintage"),
  fico: document.getElementById("f-fico"),
  scenario: document.getElementById("f-scenario"),
};

function currentFilters() {
  return {
    merchant: els.merchant.value,
    vintage: els.vintage.value,
    fico: els.fico.value,
    scenario: els.scenario.value,
  };
}

function matchesFilter(row, f, opts) {
  opts = opts || {};
  if (!opts.skipMerchant && f.merchant !== "all" && row.m !== f.merchant) return false;
  if (!opts.skipVintage && f.vintage !== "all" && row.v !== Number(f.vintage)) return false;
  if (!opts.skipFico && f.fico !== "all" && row.f !== f.fico) return false;
  if (f.scenario !== "all" && row.s !== f.scenario) return false;
  return true;
}

// ---- Aggregation: sum dollar components first, THEN derive ratios ----
//
// `rows` (DATA.rows) is at flow grain (Merchant x Vintage x FICO x Report
// Date x Scenario) -- gr/cos/opex/acq/na are meaningful to sum across a
// filtered range of report dates.
//
// `cohorts` (DATA.cohorts) is at snapshot grain (Merchant x Vintage x FICO)
// -- LTV$/CAC$ are a single fact per cohort, NOT a per-quarter flow. They
// must be summed from THIS array, never from `rows` (which repeats each
// cohort once per report date it appears in -- summing ltv/cac out of
// `rows` would count every cohort's LTV N times, N = number of quarters
// in the filtered range). This is why the two arrays are kept separate
// rather than merged into one -- see 10_export_dashboard_data.py.
function sumFlow(rows) {
  const t = { gr: 0, cos: 0, opex: 0, acq: 0, na: 0 };
  for (const r of rows) {
    t.gr += r.gr; t.cos += r.cos; t.opex += r.opex; t.acq += r.acq; t.na += r.na;
  }
  return t;
}
function sumCohorts(cohortRows) {
  const t = { ltv: 0, cac: 0 };
  for (const c of cohortRows) { t.ltv += c.ltv; t.cac += c.cac; }
  return t;
}
function derivePnl(rows, cohortRows) {
  const t = sumFlow(rows);
  const grossProfit = t.gr + t.cos;
  const grossMarginPct = t.gr !== 0 ? grossProfit / t.gr : NaN;
  const contributionProfit = grossProfit + t.opex;
  const contributionMarginPct = t.gr !== 0 ? contributionProfit / t.gr : NaN;
  const cacPerAccount = t.na !== 0 ? -t.acq / t.na : NaN;
  let ltvCac = NaN;
  if (cohortRows) {
    const c = sumCohorts(cohortRows);
    ltvCac = c.cac !== 0 ? c.ltv / c.cac : NaN;
  }
  return { ...t, grossProfit, grossMarginPct, contributionProfit, contributionMarginPct, cacPerAccount, ltvCac };
}

// Same (merchant/vintage/fico) filter logic as matchesFilter, but for the
// cohort array which has no report-date or scenario fields.
function matchesCohortFilter(c, f, opts) {
  opts = opts || {};
  if (!opts.skipMerchant && f.merchant !== "all" && c.m !== f.merchant) return false;
  if (f.vintage !== "all" && c.v !== Number(f.vintage)) return false;
  if (!opts.skipFico && f.fico !== "all" && c.f !== f.fico) return false;
  return true;
}

function groupBy(rows, keyFn) {
  const m = new Map();
  for (const r of rows) {
    const k = keyFn(r);
    if (!m.has(k)) m.set(k, []);
    m.get(k).push(r);
  }
  return m;
}

// ---- SVG helpers ----
function svgEl(tag, attrs) {
  const s = "http://www.w3.org/2000/svg";
  const e = document.createElementNS(s, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}

function renderTrendChart(f) {
  const PALETTE = currentPalette();
  const rows = DATA.rows.filter(r => matchesFilter(r, f));
  const byDate = groupBy(rows, r => r.r);
  const dateIdxs = [...byDate.keys()].sort((a,b) => a-b);
  const series = dateIdxs.map(idx => {
    const t = derivePnl(byDate.get(idx));
    const label = DATA.dims.reportDates.find(d => d.idx === idx).label;
    return { idx, label, gr: t.gr, gp: t.grossProfit, cp: t.contributionProfit };
  });

  const container = document.getElementById("trend-chart");
  container.innerHTML = "";
  if (series.length === 0) {
    container.innerHTML = '<p class="panel-note">No data for this filter combination.</p>';
    return;
  }

  const W = 1080, H = 340, ML = 62, MR = 16, MT = 16, MB = 44;
  const plotW = W - ML - MR, plotH = H - MT - MB;
  const allVals = series.flatMap(s => [s.gr, s.gp, s.cp]);
  const yMax = Math.max(0, ...allVals) * 1.12 || 1;
  const yMin = Math.min(0, ...allVals) * 1.12;
  const x = i => ML + (series.length === 1 ? plotW/2 : (i/(series.length-1)) * plotW);
  const y = v => MT + plotH - ((v - yMin) / (yMax - yMin)) * plotH;

  const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Line chart of Gross Revenue, Gross Profit, and Contribution Profit by quarter" });

  const seamIdx = series.findIndex(s => s.idx >= FORECAST_START);
  if (seamIdx > 0) {
    svg.appendChild(svgEl("rect", { class: "seam-band", x: x(seamIdx) - (x(seamIdx)-x(seamIdx-1))/2, y: MT, width: (W-MR) - (x(seamIdx) - (x(seamIdx)-x(seamIdx-1))/2), height: plotH }));
    svg.appendChild(Object.assign(svgEl("text", { class: "seam-label", x: x(seamIdx)+4, y: MT+12 }), { textContent: "Forecast →" }));
  }

  [0.25, 0.5, 0.75, 1].forEach(frac => {
    const v = yMin + (yMax - yMin) * frac;
    const gy = y(v);
    svg.appendChild(svgEl("line", { class: "gridline", x1: ML, x2: W-MR, y1: gy, y2: gy }));
    svg.appendChild(Object.assign(svgEl("text", { x: ML - 8, y: gy + 3, "text-anchor": "end", "font-size": "10.5" }), { textContent: fmtMoney(v) }));
  });
  svg.appendChild(svgEl("line", { class: "axis-line", x1: ML, x2: W-MR, y1: MT+plotH, y2: MT+plotH }));

  const labelStep = Math.max(1, Math.ceil(series.length / 9));
  series.forEach((s, i) => {
    if (i % labelStep === 0 || i === series.length-1) {
      svg.appendChild(Object.assign(svgEl("text", { x: x(i), y: H-14, "text-anchor": "middle", "font-size": "10.5" }), { textContent: s.label }));
    }
  });

  function drawSeries(key, color) {
    const pts = series.map((s,i) => `${x(i)},${y(s[key])}`).join(" ");
    svg.appendChild(svgEl("polyline", { class: "series-line", points: pts, stroke: color }));
    series.forEach((s,i) => {
      svg.appendChild(svgEl("circle", { class: "series-dot", cx: x(i), cy: y(s[key]), r: 3, fill: color }));
    });
  }
  drawSeries("gr", PALETTE.blue);
  drawSeries("gp", PALETTE.aqua);
  drawSeries("cp", PALETTE.orange);

  // End labels: drawn after all lines, with a greedy vertical-separation
  // pass so two series ending at similar values (Gross Profit and
  // Contribution Profit routinely land close together) don't render as
  // overlapping, illegible text. Mirrors the fix already applied to the
  // Python-side chart helpers in 09_build_narrative_deck.py -- this is a
  // separate, from-scratch SVG renderer, so it needed its own copy of the
  // same fix (found by a 2026-08-26 visual QA pass: the two labels
  // rendered fully on top of each other in the default dashboard view).
  const last = series[series.length - 1];
  const lastX = Math.min(x(series.length - 1) + 6, W - MR - 2);
  const labelSpecs = [
    { color: PALETTE.blue, text: fmtMoney(last.gr), y: y(last.gr) },
    { color: PALETTE.aqua, text: fmtMoney(last.gp), y: y(last.gp) },
    { color: PALETTE.orange, text: fmtMoney(last.cp), y: y(last.cp) },
  ].sort((a, b) => a.y - b.y);
  const MIN_LABEL_GAP = 13;
  for (let i = 1; i < labelSpecs.length; i++) {
    if (labelSpecs[i].y - labelSpecs[i - 1].y < MIN_LABEL_GAP) {
      labelSpecs[i].y = labelSpecs[i - 1].y + MIN_LABEL_GAP;
    }
  }
  labelSpecs.forEach(lp => {
    svg.appendChild(Object.assign(svgEl("text", { x: lastX, y: lp.y + 3, "font-size": "10.5", fill: lp.color, "font-weight": "600" }), { textContent: lp.text }));
  });

  container.appendChild(svg);

  const hidden = document.createElement("p");
  hidden.className = "visually-hidden";
  hidden.textContent = "Data table: " + series.map(s => `${s.label}: Gross Revenue ${fmtMoney(s.gr)}, Gross Profit ${fmtMoney(s.gp)}, Contribution Profit ${fmtMoney(s.cp)}`).join("; ");
  container.appendChild(hidden);
}

function renderComparisonChart(containerId, dimKey, dimValues, f, skipOpt) {
  const PALETTE = currentPalette();
  const container = document.getElementById(containerId);
  container.innerHTML = "";

  const bars = dimValues.map(v => {
    const opts = Object.assign({}, skipOpt);
    const rows = DATA.rows.filter(r => matchesFilter(r, f, opts) && r[dimKey] === v.value);
    const t = derivePnl(rows);
    return { label: v.label, value: t.contributionProfit };
  }).sort((a,b) => b.value - a.value);

  const W = 520, rowH = 30, MT = 8, MB = 8, ML = 128, MR = 70;
  const H = MT + MB + bars.length * rowH;
  const plotW = W - ML - MR;
  const maxAbs = Math.max(1, ...bars.map(b => Math.abs(b.value)));
  const zeroX = ML + plotW / 2;
  const scale = (plotW / 2) / maxAbs;

  const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Bar chart of Contribution Profit by ${dimKey}` });
  svg.appendChild(svgEl("line", { class: "axis-line", x1: zeroX, x2: zeroX, y1: 0, y2: H }));

  bars.forEach((b, i) => {
    const cy = MT + i * rowH + rowH/2;
    const barW = Math.abs(b.value) * scale;
    const barX = b.value >= 0 ? zeroX : zeroX - barW;
    svg.appendChild(Object.assign(svgEl("text", { x: ML - 8, y: cy + 4, "text-anchor": "end", "font-size": "11.5" }), { textContent: b.label }));
    svg.appendChild(svgEl("rect", { x: barX, y: cy - 8, width: Math.max(barW,1), height: 16, rx: 3, fill: b.value >= 0 ? PALETTE.blue : PALETTE.red }));
    const labelX = b.value >= 0 ? barX + barW + 6 : barX - 6;
    svg.appendChild(Object.assign(svgEl("text", { x: labelX, y: cy + 4, "text-anchor": b.value >= 0 ? "start" : "end", "font-size": "11", "font-weight": "600" }), { textContent: fmtMoney(b.value) }));
  });

  container.appendChild(svg);
}

function renderKpiTiles(f) {
  const rows = DATA.rows.filter(r => matchesFilter(r, f));
  const cohortRows = DATA.cohorts.filter(c => matchesCohortFilter(c, f));
  const t = derivePnl(rows, cohortRows);
  const tiles = [
    { label: "Gross Revenue", value: fmtMoney(t.gr) },
    { label: "Gross Profit", value: fmtMoney(t.grossProfit), sub: fmtPct(t.grossMarginPct) + " margin" },
    { label: "Contribution Profit", value: fmtMoney(t.contributionProfit), sub: fmtPct(t.contributionMarginPct) + " margin", cls: t.contributionProfit < 0 ? "neg" : "",
      title: "Reflects ongoing unit economics of the existing book -- does not net out Acquisition Cost / CAC, which is recovered over a customer's lifetime and evaluated separately via LTV/CAC." },
    { label: "New Accounts", value: fmtInt(t.na) },
    { label: "CAC / Account", value: isFinite(t.cacPerAccount) ? fmtMoney(t.cacPerAccount) : "—" },
    { label: "LTV / CAC", value: fmtX(t.ltvCac), cls: (isFinite(t.ltvCac) && t.ltvCac < 1) ? "neg" : (isFinite(t.ltvCac) ? "pos" : "") },
  ];
  const row = document.getElementById("kpi-row");
  row.innerHTML = tiles.map(tile => `
    <div class="kpi-tile"${tile.title ? ` title="${tile.title}"` : ""}>
      <div class="label">${tile.label}</div>
      <div class="value ${tile.cls||""}">${tile.value}</div>
      ${tile.sub ? `<div class="sub">${tile.sub}</div>` : ""}
    </div>`).join("");
}

function renderTable(f) {
  const rows = DATA.rows.filter(r => matchesFilter(r, f));
  const byDate = groupBy(rows, r => r.r);
  const dateIdxs = [...byDate.keys()].sort((a,b) => a-b);
  const tbody = document.querySelector("#pnl-table tbody");
  tbody.innerHTML = dateIdxs.map(idx => {
    const g = byDate.get(idx);
    const t = derivePnl(g);
    const label = DATA.dims.reportDates.find(d => d.idx === idx).label;
    const period = idx < FORECAST_START ? "Actual" : "Forecast";
    return `<tr>
      <td>${label}</td><td>${period}</td>
      <td>${fmtMoney(t.gr)}</td><td class="${t.cos<0?"neg":""}">${fmtMoney(t.cos)}</td>
      <td>${fmtMoney(t.grossProfit)}</td><td>${fmtPct(t.grossMarginPct)}</td>
      <td class="${t.contributionProfit<0?"neg":""}">${fmtMoney(t.contributionProfit)}</td><td>${fmtPct(t.contributionMarginPct)}</td>
      <td>${fmtInt(t.na)}</td><td>${isFinite(t.cacPerAccount)?fmtMoney(t.cacPerAccount):"—"}</td>
    </tr>`;
  }).join("");
}

// Detail P&L view (item 4). Filters DATA.detail (same grain as DATA.rows)
// with the existing matchesFilter, groups into one column per Report Date
// Index, and for each line item sums across matching Merchant/Vintage/FICO
// rows WITHIN that one quarter only -- a Stock line item (marked * in the
// legend) is always safe to sum across entities at a single point in time,
// it's summing ACROSS quarters that would be wrong, and this transposed
// layout never does that (each column stays its own quarter). Lazy-rendered
// -- only recomputed when the <details> section is actually open, since it's
// an audit/appendix view most visits won't expand.
function renderDetailTable(f) {
  const rows = DATA.detail.filter(r => matchesFilter(r, f));
  const byDate = groupBy(rows, r => r.r);
  const dateIdxs = [...byDate.keys()].sort((a, b) => a - b);

  const headRow = document.getElementById("detail-table-head");
  headRow.innerHTML = "<th>Line item</th>" + dateIdxs.map(idx => {
    const d = DATA.dims.reportDates.find(d => d.idx === idx);
    return `<th>${d.label}</th>`;
  }).join("");

  const body = document.getElementById("detail-table-body");
  if (dateIdxs.length === 0) {
    body.innerHTML = `<tr><td colspan="1">No data for this filter combination.</td></tr>`;
    return;
  }
  const colCount = dateIdxs.length + 1;
  let html = "";
  for (const group of DATA.dims.lineItemGroups) {
    html += `<tr class="group-row"><td colspan="${colCount}">${group.group}</td></tr>`;
    for (const item of group.items) {
      const isStock = item.aggregation === "Stock";
      const fmt = item.unit === "Count" ? fmtInt : fmtMoney;
      const cells = dateIdxs.map(idx => {
        let sum = 0;
        for (const r of byDate.get(idx)) sum += (r[item.key] || 0);
        return `<td class="${sum < 0 ? "neg" : ""}">${fmt(sum)}</td>`;
      }).join("");
      html += `<tr><td>${item.label}${isStock ? " *" : ""}</td>${cells}</tr>`;
    }
  }
  body.innerHTML = html;
}

// ---- Driver KPIs (item 7) ----
//
// PPAA = NTV / Active Accounts (spend per active account -- settled
// definition, do not re-derive). Other 5 formulas: default conventions
// documented in BUILD_LOG.md "Day 2 -- Driver KPI dashboard tab", informed
// by the finance-skills plugin's general "flow-over-stock ratios use an
// average balance" pattern (its Inventory Turnover formula) plus standard
// card-portfolio/ABS reporting convention for Payment Rate specifically
// (the finance-skills plugin doesn't cover card-portfolio metrics directly).
//
// Same sum-then-divide invariant as derivePnl()/renderDetailTable: every
// KPI is computed from THIS quarter's summed dollar/count components,
// never averaged from other cohorts' pre-computed ratios.
function deriveDriverKpis(detailRows) {
  let ntv = 0, aa = 0, ta = 0, os = 0, rb = 0, bos = 0, brb = 0, pp = 0, ir = 0, cof = 0;
  let grRevenueItems = 0; // ir + ic + mdr + fr + orv, i.e. the same 5 lines that sum to Gross Revenue
  for (const r of detailRows) {
    ntv += r.ntv || 0; aa += r.aa || 0; ta += r.ta || 0; os += r.os || 0; rb += r.rb || 0;
    bos += r.bos || 0; brb += r.brb || 0; pp += r.pp || 0; ir += r.ir || 0; cof += r.cof || 0;
    grRevenueItems += (r.ir||0) + (r.ic||0) + (r.mdr||0) + (r.fr||0) + (r.orv||0);
  }
  const avgRb = brb ? (rb + brb) / 2 : rb; // no prior-quarter balance (portfolio's first quarter) -- fall back to ending
  return {
    paymentRate: bos !== 0 ? -pp / bos : NaN,       // pp is stored negative (an outflow); bos = Beginning Outstanding Balance
    ppaa: aa !== 0 ? ntv / aa : NaN,
    activeRate: ta !== 0 ? aa / ta : NaN,
    revolveRate: os !== 0 ? rb / os : NaN,
    nim: avgRb !== 0 ? (ir + cof) / avgRb : NaN,     // cof stored negative -- ir + cof = net interest income
    revenueMargin: ntv !== 0 ? grRevenueItems / ntv : NaN,
  };
}

const KPI_SPECS = [
  { key: "paymentRate", fmt: fmtPct },
  { key: "ppaa", fmt: fmtMoney },
  { key: "activeRate", fmt: fmtPct },
  { key: "revolveRate", fmt: fmtPct },
  { key: "nim", fmt: fmtPct },
  { key: "revenueMargin", fmt: fmtPct },
];

// Single-series small-multiple line chart -- a simplified version of
// renderTrendChart for one metric at a time (no multi-series end-label
// collision handling needed since there's only one line).
function renderSmallLineChart(containerId, series, fmt, color) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";
  const finite = series.filter(s => isFinite(s.value));
  if (finite.length === 0) {
    container.innerHTML = '<p class="panel-note">No data for this filter combination.</p>';
    return;
  }

  const W = 320, H = 130, ML = 8, MR = 8, MT = 10, MB = 20;
  const plotW = W - ML - MR, plotH = H - MT - MB;
  const vals = finite.map(s => s.value);
  const yMax = Math.max(...vals) * 1.15 || 1;
  const yMin = Math.min(0, Math.min(...vals) * 1.15);
  const x = i => ML + (series.length === 1 ? plotW / 2 : (i / (series.length - 1)) * plotW);
  const y = v => MT + plotH - ((v - yMin) / (yMax - yMin || 1)) * plotH;

  const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": containerId });

  const seamIdx = series.findIndex(s => s.idx >= FORECAST_START);
  if (seamIdx > 0) {
    svg.appendChild(svgEl("rect", { class: "seam-band", x: x(seamIdx), y: MT, width: (W - MR) - x(seamIdx), height: plotH }));
  }
  svg.appendChild(svgEl("line", { class: "axis-line", x1: ML, x2: W - MR, y1: y(0) , y2: y(0) }));

  const pts = series.filter(s => isFinite(s.value)).map(s => `${x(series.indexOf(s))},${y(s.value)}`).join(" ");
  svg.appendChild(svgEl("polyline", { class: "series-line", points: pts, stroke: color, "stroke-width": 1.75 }));
  series.forEach((s, i) => {
    if (!isFinite(s.value)) return;
    svg.appendChild(svgEl("circle", { r: 2, cx: x(i), cy: y(s.value), fill: color }));
  });

  const first = series[0], last = series[series.length - 1];
  svg.appendChild(Object.assign(svgEl("text", { x: ML, y: H - 4, "font-size": "9", "text-anchor": "start" }), { textContent: first.label }));
  svg.appendChild(Object.assign(svgEl("text", { x: W - MR, y: H - 4, "font-size": "9", "text-anchor": "end" }), { textContent: last.label }));

  container.appendChild(svg);
}

function renderDriverKpiCharts(f) {
  const PALETTE = currentPalette();
  const rows = DATA.detail.filter(r => matchesFilter(r, f));
  const byDate = groupBy(rows, r => r.r);
  const dateIdxs = [...byDate.keys()].sort((a, b) => a - b);

  const seriesByKpi = {};
  for (const spec of KPI_SPECS) seriesByKpi[spec.key] = [];
  dateIdxs.forEach(idx => {
    const kpis = deriveDriverKpis(byDate.get(idx));
    const label = DATA.dims.reportDates.find(d => d.idx === idx).label;
    for (const spec of KPI_SPECS) seriesByKpi[spec.key].push({ idx, label, value: kpis[spec.key] });
  });

  for (const spec of KPI_SPECS) {
    const series = seriesByKpi[spec.key];
    renderSmallLineChart(`kpi-chart-${spec.key}`, series, spec.fmt, PALETTE.blue);
    const lastFinite = [...series].reverse().find(s => isFinite(s.value));
    document.getElementById(`kpi-latest-${spec.key}`).textContent = lastFinite
      ? `Latest (${lastFinite.label}): ${spec.fmt(lastFinite.value)}` : "";
  }
}

// ---- Multi-select compare chart (item 6) ----
//
// Metric registry spans both P&L buckets (DATA.rows) and the 6 driver KPIs
// from item 7 (DATA.detail) -- `source` says which array to filter, `mark`
// says bar (additive $, safe to sum -- these get GROUPED/clustered bars per
// quarter, never stacked, since the compared entities are alternatives to
// look at side by side, not components of one whole) vs. line (a rate/yield/
// per-unit figure that doesn't sum across entities, only compares as levels).
const METRIC_REGISTRY = {
  gr:  { label: "Gross Revenue",         source: "rows",   mark: "bar",  fmt: fmtMoney, compute: rows => derivePnl(rows).gr },
  cos: { label: "Cost of Sales",         source: "rows",   mark: "bar",  fmt: fmtMoney, compute: rows => derivePnl(rows).cos },
  gp:  { label: "Gross Profit",          source: "rows",   mark: "bar",  fmt: fmtMoney, compute: rows => derivePnl(rows).grossProfit },
  cp:  { label: "Contribution Profit",   source: "rows",   mark: "bar",  fmt: fmtMoney, compute: rows => derivePnl(rows).contributionProfit },
  gm:  { label: "Gross Margin %",        source: "rows",   mark: "line", fmt: fmtPct,   compute: rows => derivePnl(rows).grossMarginPct },
  cm:  { label: "Contribution Margin %", source: "rows",   mark: "line", fmt: fmtPct,   compute: rows => derivePnl(rows).contributionMarginPct },
  paymentRate:   { label: "Payment Rate",   source: "detail", mark: "line", fmt: fmtPct,   compute: rows => deriveDriverKpis(rows).paymentRate },
  ppaa:          { label: "PPAA",           source: "detail", mark: "line", fmt: fmtMoney, compute: rows => deriveDriverKpis(rows).ppaa },
  activeRate:    { label: "Active Rate",    source: "detail", mark: "line", fmt: fmtPct,   compute: rows => deriveDriverKpis(rows).activeRate },
  revolveRate:   { label: "Revolve Rate",   source: "detail", mark: "line", fmt: fmtPct,   compute: rows => deriveDriverKpis(rows).revolveRate },
  nim:           { label: "NIM",            source: "detail", mark: "line", fmt: fmtPct,   compute: rows => deriveDriverKpis(rows).nim },
  revenueMargin: { label: "Revenue Margin", source: "detail", mark: "line", fmt: fmtPct,   compute: rows => deriveDriverKpis(rows).revenueMargin },
};

const DIM_META = {
  m: { skipOpt: "skipMerchant", options: () => DATA.dims.merchants.map(m => ({ value: m, label: m })) },
  v: { skipOpt: "skipVintage", options: () => DATA.dims.vintages.map(v => ({ value: String(v.idx), label: v.label })) },
  f: { skipOpt: "skipFico", options: () => DATA.dims.ficoBuckets.map(v => ({ value: v, label: v })) },
};

let cmpSelectedValues = new Set(); // empty = "all values in this dimension" (matches the old chart's default)

function renderCmpValuePicker() {
  const dimKey = document.getElementById("cmp-dim").value;
  const opts = DIM_META[dimKey].options();
  const picker = document.getElementById("cmp-value-picker");
  picker.innerHTML = opts.map(o =>
    `<label><input type="checkbox" value="${o.value}"${cmpSelectedValues.has(o.value) ? " checked" : ""}> ${o.label}</label>`
  ).join("");
  picker.querySelectorAll("input[type=checkbox]").forEach(cb => {
    cb.addEventListener("change", () => {
      if (cb.checked) cmpSelectedValues.add(cb.value); else cmpSelectedValues.delete(cb.value);
      renderCompareChart(currentFilters());
    });
  });
}

function compareDateIdxs(seriesList, blended) {
  const s = new Set();
  seriesList.forEach(ser => ser.points.forEach(p => s.add(p.idx)));
  if (blended) blended.points.forEach(p => s.add(p.idx));
  return [...s].sort((a, b) => a - b);
}

function renderCompareChartSvg(seriesList, blended, metric) {
  const container = document.getElementById("compare-chart");
  container.innerHTML = "";
  const dateIdxs = compareDateIdxs(seriesList, blended);
  if (dateIdxs.length === 0 || seriesList.length === 0) {
    container.innerHTML = '<p class="panel-note">No data for this selection.</p>';
    return;
  }
  const dateLabel = idx => DATA.dims.reportDates.find(d => d.idx === idx).label;
  const allSeries = blended ? seriesList.concat([blended]) : seriesList;

  const W = 1080, H = 320, ML = 62, MR = 16, MT = 16, MB = 40;
  const plotW = W - ML - MR, plotH = H - MT - MB;
  const allVals = allSeries.flatMap(ser => ser.points.map(p => p.value)).filter(isFinite);
  const yMax = Math.max(0, ...allVals) * 1.15 || 1;
  const yMin = Math.min(0, ...allVals) * 1.15;
  const x = i => ML + (dateIdxs.length === 1 ? plotW / 2 : (i / (dateIdxs.length - 1)) * plotW);
  const y = v => MT + plotH - ((v - yMin) / (yMax - yMin || 1)) * plotH;

  const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Comparison chart" });

  const seamI = dateIdxs.findIndex(idx => idx >= FORECAST_START);
  if (seamI > 0) {
    svg.appendChild(svgEl("rect", { class: "seam-band", x: x(seamI), y: MT, width: (W - MR) - x(seamI), height: plotH }));
  }
  [0.25, 0.5, 0.75, 1].forEach(frac => {
    const v = yMin + (yMax - yMin) * frac, gy = y(v);
    svg.appendChild(svgEl("line", { class: "gridline", x1: ML, x2: W - MR, y1: gy, y2: gy }));
    svg.appendChild(Object.assign(svgEl("text", { x: ML - 8, y: gy + 3, "text-anchor": "end", "font-size": "10.5" }), { textContent: metric.fmt(v) }));
  });
  svg.appendChild(svgEl("line", { class: "axis-line", x1: ML, x2: W - MR, y1: y(0), y2: y(0) }));

  const labelStep = Math.max(1, Math.ceil(dateIdxs.length / 9));
  dateIdxs.forEach((idx, i) => {
    if (i % labelStep === 0 || i === dateIdxs.length - 1) {
      svg.appendChild(Object.assign(svgEl("text", { x: x(i), y: H - 14, "text-anchor": "middle", "font-size": "10.5" }), { textContent: dateLabel(idx) }));
    }
  });

  if (metric.mark === "bar") {
    const nSeries = allSeries.length;
    const clusterW = (plotW / dateIdxs.length) * 0.72;
    const barW = clusterW / nSeries;
    dateIdxs.forEach((idx, i) => {
      const clusterX = x(i) - clusterW / 2;
      allSeries.forEach((ser, si) => {
        const pt = ser.points.find(p => p.idx === idx);
        if (!pt || !isFinite(pt.value)) return;
        const barX = clusterX + si * barW;
        const barY = pt.value >= 0 ? y(pt.value) : y(0);
        const barH = Math.max(Math.abs(y(pt.value) - y(0)), 0.5);
        svg.appendChild(svgEl("rect", { x: barX, y: barY, width: Math.max(barW - 1, 1), height: barH, fill: ser.color, opacity: ser.dashed ? 0.55 : 1 }));
      });
    });
  } else {
    allSeries.forEach(ser => {
      const pts = ser.points.filter(p => isFinite(p.value)).map(p => `${x(dateIdxs.indexOf(p.idx))},${y(p.value)}`).join(" ");
      const attrs = { class: "series-line", points: pts, stroke: ser.color, "stroke-width": 2 };
      if (ser.dashed) attrs["stroke-dasharray"] = "4,3";
      svg.appendChild(svgEl("polyline", attrs));
      ser.points.forEach(p => {
        if (!isFinite(p.value)) return;
        svg.appendChild(svgEl("circle", { r: 2.5, cx: x(dateIdxs.indexOf(p.idx)), cy: y(p.value), fill: ser.color }));
      });
    });
  }

  container.appendChild(svg);
}

function renderCompareLegend(seriesList, blended) {
  const legend = document.getElementById("cmp-legend");
  const all = blended ? seriesList.concat([blended]) : seriesList;
  legend.innerHTML = all.map(ser =>
    `<span class="legend-item"><span class="legend-swatch" style="background:${ser.color};${ser.dashed ? "opacity:.6" : ""}"></span>${ser.label}</span>`
  ).join("");
}

function renderCompareChart(f) {
  const PALETTE = currentPalette();
  const COLORS = [PALETTE.blue, PALETTE.orange, PALETTE.aqua, PALETTE.red, PALETTE.yellow, PALETTE.purple];

  const dimKey = document.getElementById("cmp-dim").value;
  const meta = DIM_META[dimKey];
  const metric = METRIC_REGISTRY[document.getElementById("cmp-metric").value];
  const skipOpts = { [meta.skipOpt]: true };

  const allOptions = meta.options();
  const selected = cmpSelectedValues.size > 0 ? allOptions.filter(o => cmpSelectedValues.has(o.value)) : allOptions;
  const typedValue = v => (dimKey === "v" ? Number(v) : v);

  const sourceRows = DATA[metric.source];
  const seriesList = selected.map((o, i) => {
    const rows = sourceRows.filter(r => matchesFilter(r, f, skipOpts) && r[dimKey] === typedValue(o.value));
    const byDate = groupBy(rows, r => r.r);
    const points = [...byDate.keys()].sort((a, b) => a - b).map(idx => ({
      idx, value: metric.compute(byDate.get(idx)),
    }));
    return { label: o.label, color: COLORS[i % COLORS.length], points };
  });

  let blended = null;
  if (selected.length > 1) {
    const typedValues = selected.map(o => typedValue(o.value));
    const rows = sourceRows.filter(r => matchesFilter(r, f, skipOpts) && typedValues.includes(r[dimKey]));
    const byDate = groupBy(rows, r => r.r);
    const points = [...byDate.keys()].sort((a, b) => a - b).map(idx => ({
      idx, value: metric.compute(byDate.get(idx)),
    }));
    blended = { label: "Blended total", color: PALETTE.muted, dashed: true, points };
  }

  renderCompareChartSvg(seriesList, blended, metric);
  renderCompareLegend(seriesList, blended);
}

function renderFilterSummary(f) {
  const parts = [];
  parts.push(f.merchant === "all" ? "All merchants" : f.merchant);
  parts.push(f.vintage === "all" ? "all vintages" : "vintage " + DATA.dims.vintages.find(v => v.idx === Number(f.vintage)).label);
  parts.push(f.fico === "all" ? "all FICO tiers" : f.fico);
  parts.push(f.scenario === "all" ? "actuals + forecast" : (f.scenario === "Actual" ? "actuals only" : "forecast only"));
  document.getElementById("filter-summary").textContent = "Showing: " + parts.join(" · ");
}

function renderAll() {
  const f = currentFilters();
  renderFilterSummary(f);
  renderKpiTiles(f);
  renderTrendChart(f);
  renderCompareChart(f);
  renderDriverKpiCharts(f);
  renderTable(f);
  const detailToggle = document.getElementById("detail-toggle");
  if (detailToggle.open) renderDetailTable(f);
}

document.getElementById("detail-toggle").addEventListener("toggle", (e) => {
  if (e.target.open) renderDetailTable(currentFilters());
});

// Compare-chart controls: metric list populated once from the registry;
// the value picker repopulates (and selection resets to "all") whenever the
// compared dimension changes, since the checkbox set itself is different.
document.getElementById("cmp-metric").innerHTML = Object.entries(METRIC_REGISTRY)
  .map(([k, m]) => `<option value="${k}">${m.label}</option>`).join("");
document.getElementById("cmp-metric").value = "cp";
document.getElementById("cmp-dim").addEventListener("change", () => {
  cmpSelectedValues = new Set();
  renderCmpValuePicker();
  renderAll();
});
document.getElementById("cmp-metric").addEventListener("change", renderAll);
renderCmpValuePicker();

[els.merchant, els.vintage, els.fico, els.scenario].forEach(el => el.addEventListener("change", renderAll));
document.getElementById("reset-filters").addEventListener("click", () => {
  els.merchant.value = "all"; els.vintage.value = "all"; els.fico.value = "all"; els.scenario.value = "all";
  renderAll();
});

document.getElementById("theme-toggle").addEventListener("click", () => {
  const next = isDarkMode() ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("imprint-theme", next); } catch (e) {}
  renderAll();
});

renderAll();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
