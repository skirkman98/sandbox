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
  :root {
    --blue: #2a78d6; --orange: #eb6834; --aqua: #1baf7a; --yellow: #eda100; --red: #e34948;
    --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781; --grid: #e1e0d9;
    --surface: #fcfcfb; --page: #f9f9f7; --border: rgba(11,11,11,0.10);
  }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; background: var(--page); color: var(--ink); margin: 0; }
  .wrap { max-width: 1180px; margin: 0 auto; padding: 1.75rem 1.5rem 4rem; }
  header.page-head { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.25rem; }
  h1 { font-size: 1.55rem; margin: 0; }
  .subtitle { color: var(--ink-2); margin: 0.15rem 0 1.25rem; }
  nav.doc-links { font-size: 0.85rem; }
  nav.doc-links a { color: var(--blue); text-decoration: none; margin-left: 1rem; }
  nav.doc-links a:hover { text-decoration: underline; }

  .filter-bar { display: flex; gap: 0.9rem; flex-wrap: wrap; align-items: flex-end; background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 0.9rem 1.1rem; margin-bottom: 1.25rem; }
  .filter-field { display: flex; flex-direction: column; gap: 0.25rem; }
  .filter-field label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted); }
  .filter-field select { font: inherit; font-size: 0.88rem; padding: 0.4rem 0.55rem; border: 1px solid var(--grid); border-radius: 6px; background: #fff; color: var(--ink); min-width: 168px; }
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
  table.datatable th { text-align: right; color: var(--muted); font-weight: 500; border-bottom: 1px solid #c3c2b7; padding: 0.4rem 0.55rem; position: sticky; top: 0; background: var(--surface); }
  table.datatable th:first-child, table.datatable td:first-child { text-align: left; }
  table.datatable td { text-align: right; padding: 0.38rem 0.55rem; border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; }
  .table-scroll { max-height: 420px; overflow-y: auto; border: 1px solid var(--grid); border-radius: 8px; }
  .table-scroll table.datatable th { top: -1px; }
  td.neg { color: var(--red); }

  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }
  footer.page-foot { color: var(--muted); font-size: 0.8rem; margin-top: 2rem; }
</style>
</head>
<body>
<div class="wrap">

<header class="page-head">
  <h1>Imprint Management P&amp;L Dashboard</h1>
  <nav class="doc-links">
    <a href="narrative_report.html">Narrative walkthrough &rarr;</a>
    <a href="pitch_deck.html">How this was built &rarr;</a>
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
</section>

<footer class="page-foot">Built from combined_actuals_forecast.parquet via scripts/10_export_dashboard_data.py + 11_build_dashboard.py. See <a href="pitch_deck.html">pitch_deck.html</a> for methodology and <a href="narrative_report.html">narrative_report.html</a> for the full written narrative.</footer>
</div>

<script>
const DATA = __DASHBOARD_DATA__;
const FORECAST_START = DATA.forecastStartIdx;

const PALETTE = { blue: "#2a78d6", orange: "#eb6834", aqua: "#1baf7a", red: "#e34948" };
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
  if (f.vintage !== "all" && row.v !== Number(f.vintage)) return false;
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
    const last = series[series.length-1];
    const lx = Math.min(x(series.length-1) + 6, W - MR - 2);
    svg.appendChild(Object.assign(svgEl("text", { x: lx, y: y(last[key]) + 3, "font-size": "10.5", fill: color, "font-weight": "600" }), { textContent: fmtMoney(last[key]) }));
  }
  drawSeries("gr", PALETTE.blue);
  drawSeries("gp", PALETTE.aqua);
  drawSeries("cp", PALETTE.orange);

  container.appendChild(svg);

  const hidden = document.createElement("p");
  hidden.className = "visually-hidden";
  hidden.textContent = "Data table: " + series.map(s => `${s.label}: Gross Revenue ${fmtMoney(s.gr)}, Gross Profit ${fmtMoney(s.gp)}, Contribution Profit ${fmtMoney(s.cp)}`).join("; ");
  container.appendChild(hidden);
}

function renderComparisonChart(containerId, dimKey, dimValues, f, skipOpt) {
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
    { label: "Contribution Profit", value: fmtMoney(t.contributionProfit), sub: fmtPct(t.contributionMarginPct) + " margin", cls: t.contributionProfit < 0 ? "neg" : "" },
    { label: "New Accounts", value: fmtInt(t.na) },
    { label: "CAC / Account", value: isFinite(t.cacPerAccount) ? fmtMoney(t.cacPerAccount) : "—" },
    { label: "LTV / CAC", value: fmtX(t.ltvCac), cls: (isFinite(t.ltvCac) && t.ltvCac < 1) ? "neg" : (isFinite(t.ltvCac) ? "pos" : "") },
  ];
  const row = document.getElementById("kpi-row");
  row.innerHTML = tiles.map(tile => `
    <div class="kpi-tile">
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
  renderComparisonChart("merchant-chart", "m", DATA.dims.merchants.map(m => ({value: m, label: m})), f, { skipMerchant: true });
  renderComparisonChart("fico-chart", "f", DATA.dims.ficoBuckets.map(v => ({value: v, label: v})), f, { skipFico: true });
  renderTable(f);
}

[els.merchant, els.vintage, els.fico, els.scenario].forEach(el => el.addEventListener("change", renderAll));
document.getElementById("reset-filters").addEventListener("click", () => {
  els.merchant.value = "all"; els.vintage.value = "all"; els.fico.value = "all"; els.scenario.value = "all";
  renderAll();
});

renderAll();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
