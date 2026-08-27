"""
14_build_unified_narrative.py

Builds output/unified_narrative.html -- the new top-level entry point for
the whole deliverable. Where dashboard.html, narrative_report.html, and
pitch_deck.html each cover one facet (live filtering, the extended written
story, the build/methodology trail) with no single front door between them,
this page is the one document meant to be read start to finish by someone
who opens exactly one file: the Consolidated P&L, the Cohort & Vintage
Views, the Working Model, and the Narrative (risks / winners-drags / where
better data would help) -- the four things the case study brief asks for,
in that order, each getting its own chapter. It closes by pointing to the
three existing docs as supporting detail for a reader who wants to go
deeper on any one facet.

Design choices mirror 08_build_narrative_deck.py deliberately (fixed
narrative, precomputed static SVG, not another live-filtering surface --
that's the dashboard's job): same palette, same slide/stat-row/risk-card
CSS, same chart helpers (now shared via viz_utils.py rather than a third
copy-paste). Two additions not needed by the other decks:
  - table-scroll: the quarterly P&L table is 10 columns wide (label + last
    actual + 8 forecast quarters) -- wrapped in a horizontally-scrollable
    container rather than letting a wide table force the whole page to
    scroll sideways.
  - callout: a definitions box (Contribution Profit, LTV, CAC) so a reader
    never has to leave this page to know what a number means -- the rubric
    explicitly wants LTV/CAC methodology stated and defensible, not just
    computed.
"""
import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from viz_utils import (
    index_to_quarter, fmt_money, fmt_pct, fmt_x, data_table,
    svg_line_chart, svg_diverging_bar_chart, svg_stacked_area, svg_cohort_chart,
    ARCHITECTURE_DIAGRAM_SVG, BACKBOOK_FRONTBOOK_DIAGRAM_SVG,
)
from pnl_utils import classify_pnl_bucket

OUT_DIR = Path(__file__).resolve().parent.parent / "output"

FORECAST_START_IDX = 14


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_all():
    pnl = pd.read_csv(OUT_DIR / "csv" / "pnl_consolidated.csv")
    pnl_by_merchant = pd.read_csv(OUT_DIR / "csv" / "pnl_by_merchant.csv")
    ltv_cac_merchant = pd.read_csv(OUT_DIR / "csv" / "ltv_cac_by_merchant.csv")
    lcf = pd.read_csv(OUT_DIR / "csv" / "cohort_ltv_cac_by_fico.csv")
    lcv = pd.read_csv(OUT_DIR / "csv" / "cohort_ltv_cac_by_vintage.csv")
    age_mix = pd.read_csv(OUT_DIR / "csv" / "cohort_balance_age_mix.csv", index_col=0)
    cp_m1 = pd.read_csv(OUT_DIR / "csv" / "cohort_cp_per_account_merchant_1.csv")
    ltv_cac_cohort = pd.read_csv(OUT_DIR / "csv" / "ltv_cac_by_cohort.csv")
    audit = pd.read_csv(OUT_DIR / "csv" / "audit_results.csv")
    df = pd.read_parquet(OUT_DIR / "parquet" / "combined_actuals_forecast.parquet")
    return pnl, pnl_by_merchant, ltv_cac_merchant, lcf, lcv, age_mix, cp_m1, ltv_cac_cohort, audit, df


def line_mix_table(df, bucket, scenario="Base Case"):
    """$ and % composition of one P&L bucket, at raw-Line-Item grain, over
    the given scenario -- e.g. what actually makes up Gross Revenue or Cost
    of Sales, not just the bucket total. Uses the same classify_pnl_bucket
    as the P&L rollup itself (05/06), not a second reimplementation, so this
    table can never disagree with the totals above it."""
    sub = df[df["Scenario"] == scenario].copy()
    sub["PnL Bucket"] = sub.apply(classify_pnl_bucket, axis=1)
    sub = sub[sub["PnL Bucket"] == bucket]
    totals = sub.groupby("Line Item")["Value"].sum()
    totals = totals.reindex(totals.abs().sort_values(ascending=False).index)
    grand = totals.abs().sum()
    return [[item, fmt_money(v), f"{abs(v)/grand*100:.1f}%"] for item, v in totals.items()]


def pnl_quarterly_table(pnl):
    """Last actual quarter + all 8 forecast quarters, wide."""
    actual = pnl[pnl["Scenario"] == "Actual"].sort_values("Report Date Index")
    last_actual = actual.iloc[[-1]]
    fcst = pnl[pnl["Scenario"] == "Base Case"].sort_values("Report Date Index")
    combined = pd.concat([last_actual, fcst])
    headers = [""] + [
        f"{r} (actual)" if i == 0 else r for i, r in enumerate(combined["Report Date"].tolist())
    ]
    rows_def = [
        ("Gross Revenue", "Gross Revenue", fmt_money),
        ("Cost of Sales", "Cost of Sales", fmt_money),
        ("Gross Profit", "Gross Profit", fmt_money),
        ("Gross Margin %", "Gross Margin %", fmt_pct),
        ("Operating Expense", "Operating Expense", fmt_money),
        ("Contribution Profit", "Contribution Profit", fmt_money),
        ("Contribution Margin %", "Contribution Margin %", fmt_pct),
        ("New Accounts", "New Accounts", lambda v: f"{v:,.0f}"),
        ("Acquisition Cost (total)", "CAC", fmt_money),
        ("CAC / New Account", "CAC / New Account", fmt_money),
    ]
    rows = [[label, *[fmt(v) for v in combined[col].tolist()]] for label, col, fmt in rows_def]
    return f'<div class="table-scroll">{data_table(headers, rows)}</div>'


def main():
    pnl, pnl_by_merchant, ltv_cac_merchant, lcf, lcv, age_mix, cp_m1, ltv_cac_cohort, audit, df = load_all()

    # ---- Cover: today + 8Q headline ----
    actual = pnl[pnl["Scenario"] == "Actual"].sort_values("Report Date Index")
    today = actual.iloc[-1]
    last_actual_idx = int(today["Report Date Index"])
    snap = df[df["Report Date Index"] == last_actual_idx]
    total_accounts_today = snap[snap["Line Item"] == "Total Accounts"]["Value"].sum()
    os_balance_today = snap[snap["Line Item"] == "Outstanding Balance"]["Value"].sum()
    ntv_today = snap[snap["Line Item"] == "Net Transaction Volume"]["Value"].sum()

    fcst = pnl[pnl["Scenario"] == "Base Case"]
    total_gr_8q = fcst["Gross Revenue"].sum()
    total_cp_8q = fcst["Contribution Profit"].sum()
    avg_cm = total_cp_8q / total_gr_8q  # revenue-weighted, not mean-of-ratios

    portfolio_ltv = np.average(ltv_cac_cohort["LTV per Account"], weights=ltv_cac_cohort["New Accounts"])
    portfolio_cac = np.average(ltv_cac_cohort["CAC per Account"].fillna(0), weights=ltv_cac_cohort["New Accounts"])
    portfolio_ltv_cac = portfolio_ltv / portfolio_cac

    # ---- Ch.1: Consolidated P&L ----
    all_pnl = pnl.sort_values("Report Date Index")
    x_labels = [index_to_quarter(i) for i in all_pnl["Report Date Index"]]
    trend_series = [
        ("gr", "Gross Revenue", "--blue", all_pnl["Gross Revenue"].tolist()),
        ("gp", "Gross Profit", "--aqua", all_pnl["Gross Profit"].tolist()),
        ("cp", "Contribution Profit", "--orange", all_pnl["Contribution Profit"].tolist()),
    ]
    trend_chart = svg_line_chart(trend_series, x_labels, seam_index=FORECAST_START_IDX,
                                  aria_label="Gross Revenue, Gross Profit, and Contribution Profit by quarter, actuals through Q2 2026 then forecast")
    pnl_table = pnl_quarterly_table(pnl)
    revenue_mix = data_table(["Revenue line", "8Q forecast total", "% of Gross Revenue"], line_mix_table(df, "Gross Revenue"))
    cos_mix = data_table(["Cost of Sales line", "8Q forecast total", "% of Cost of Sales"], line_mix_table(df, "Cost of Sales"))

    # ---- Ch.2: Cohort & Vintage Views ----
    age_mix_q = age_mix.copy()
    age_mix_q.index = [index_to_quarter(i) for i in age_mix_q.index]
    age_pct = age_mix_q.div(age_mix_q.sum(axis=1), axis=0) * 100
    age_series = [
        ("Young (0-4Q)", "--blue", age_pct["Young (0-4Q)"].tolist()),
        ("Mid (5-8Q)", "--orange", age_pct["Mid (5-8Q)"].tolist()),
        ("Seasoned (9Q+)", "--aqua", age_pct["Seasoned (9Q+)"].tolist()),
    ]
    age_chart = svg_stacked_area(age_pct.index.tolist(), age_series,
                                  aria_label="Outstanding Balance mix by cohort age, Young/Mid/Seasoned, over time")
    young_start, young_end = age_pct["Young (0-4Q)"].iloc[0], age_pct["Young (0-4Q)"].iloc[-1]
    seasoned_start, seasoned_end = age_pct["Seasoned (9Q+)"].iloc[0], age_pct["Seasoned (9Q+)"].iloc[-1]

    vintage_picks = [(0, "Oldest (Q1 2023)", "--blue"), (7, "Mid (Q4 2024)", "--orange"), (13, "Newest (Q2 2026)", "--aqua")]
    cohort_series = []
    for v_idx, label, color in vintage_picks:
        sub = cp_m1[cp_m1["Vintage Index"] == v_idx].sort_values("QSB")
        cohort_series.append((str(v_idx), label, color, sub["CP per Account"].tolist(), sub["QSB"].tolist()))
    cohort_chart = svg_cohort_chart(cohort_series, aria_label="Contribution Profit per Account by Quarters Since Book, for the oldest, a middle, and the newest vintage of Merchant 1", y_axis_label="Contribution Profit per Account ($)")

    lcv_sorted = lcv.sort_values("Vintage Index")
    vintage_x_labels = [index_to_quarter(int(v)) for v in lcv_sorted["Vintage Index"]]
    vintage_series = [("ltvcac", "LTV/CAC", "--blue", lcv_sorted["LTV/CAC"].tolist())]
    vintage_chart = svg_line_chart(vintage_series, vintage_x_labels, seam_index=FORECAST_START_IDX, value_fmt=fmt_x,
                                    aria_label="LTV to CAC ratio by origination vintage, oldest to newest cohort")
    backbook_lcv = lcv_sorted[lcv_sorted["Vintage Index"] < FORECAST_START_IDX]["LTV/CAC"]
    frontbook_lcv = lcv_sorted[lcv_sorted["Vintage Index"] >= FORECAST_START_IDX]["LTV/CAC"]

    fico_order = ["Poor (300-579)", "Fair (580-669)", "Good (670-739)", "Very Good (740-799)", "Exceptional (800-850)"]
    lcf_ordered = lcf.set_index("FICO Bucket").reindex(fico_order).reset_index()
    fico_bars = list(zip(lcf_ordered["FICO Bucket"], lcf_ordered["LTV/CAC"]))
    fico_chart = svg_diverging_bar_chart(fico_bars, aria_label="LTV to CAC ratio by FICO tier, Poor through Exceptional")
    fico_table = data_table(["FICO Tier", "LTV/Account", "CAC/Account", "LTV/CAC"],
                             [[r["FICO Bucket"], fmt_money(r["LTV/Account"]), fmt_money(r["CAC/Account"]), fmt_x(r["LTV/CAC"])] for _, r in lcf_ordered.iterrows()])

    # ---- Ch.4: Narrative -- winners/drags ----
    merch_sorted = pnl_by_merchant.sort_values("Contribution Profit", ascending=True)
    merch_bars = list(zip(merch_sorted["Merchant"], merch_sorted["Contribution Profit"]))
    merch_chart = svg_diverging_bar_chart(merch_bars, aria_label="Contribution Profit by merchant, forecast period")
    top_merchant = pnl_by_merchant.sort_values("Contribution Profit", ascending=False).iloc[0]
    bottom_merchant = pnl_by_merchant.sort_values("Contribution Profit", ascending=True).iloc[0]

    ltv_cac_merch_sorted = ltv_cac_merchant.sort_values("LTV/CAC", ascending=False)
    merch_ltv_table = data_table(["Merchant", "LTV/Account", "CAC/Account", "LTV/CAC"],
                                  [[r["Merchant"], fmt_money(r["LTV/Account"]), fmt_money(r["CAC/Account"]), fmt_x(r["LTV/CAC"])] for _, r in ltv_cac_merch_sorted.iterrows()])
    top_ltv_merchant = ltv_cac_merch_sorted.iloc[0]
    bottom_ltv_merchant = ltv_cac_merch_sorted.iloc[-1]

    html = HTML_TEMPLATE.format(
        # cover
        total_accounts_today=f"{total_accounts_today:,.0f}",
        os_balance_today=fmt_money(os_balance_today),
        ntv_today=fmt_money(ntv_today),
        gr_today=fmt_money(today["Gross Revenue"]),
        cm_today=fmt_pct(today["Contribution Margin %"]),
        today_quarter=today["Report Date"],
        total_gr_8q=fmt_money(total_gr_8q),
        total_cp_8q=fmt_money(total_cp_8q),
        avg_cm=fmt_pct(avg_cm),
        portfolio_ltv_cac=fmt_x(portfolio_ltv_cac),
        # ch1
        trend_chart=trend_chart,
        pnl_table=pnl_table,
        revenue_mix=revenue_mix,
        cos_mix=cos_mix,
        # ch2
        age_chart=age_chart,
        young_start=f"{young_start:.0f}%", young_end=f"{young_end:.0f}%",
        seasoned_start=f"{seasoned_start:.0f}%", seasoned_end=f"{seasoned_end:.0f}%",
        cohort_chart=cohort_chart,
        vintage_chart=vintage_chart,
        backbook_lcv_avg=fmt_x(backbook_lcv.mean()),
        frontbook_lcv_avg=fmt_x(frontbook_lcv.mean()),
        vintage_lcv_min=fmt_x(lcv_sorted["LTV/CAC"].min()),
        vintage_lcv_max=fmt_x(lcv_sorted["LTV/CAC"].max()),
        fico_chart=fico_chart,
        fico_table=fico_table,
        # ch3
        architecture_diagram=ARCHITECTURE_DIAGRAM_SVG,
        backbook_frontbook_diagram=BACKBOOK_FRONTBOOK_DIAGRAM_SVG,
        n_pass=(audit["Status"] == "PASS").sum(), n_total=len(audit),
        # ch4
        merch_chart=merch_chart,
        merch_ltv_table=merch_ltv_table,
        top_merchant=top_merchant["Merchant"], top_merchant_cp=fmt_money(top_merchant["Contribution Profit"]), top_merchant_cm=fmt_pct(top_merchant["Contribution Margin %"]),
        bottom_merchant=bottom_merchant["Merchant"], bottom_merchant_cp=fmt_money(bottom_merchant["Contribution Profit"]), bottom_merchant_cm=fmt_pct(bottom_merchant["Contribution Margin %"]),
        top_ltv_merchant=top_ltv_merchant["Merchant"], top_ltv_merchant_x=fmt_x(top_ltv_merchant["LTV/CAC"]),
        bottom_ltv_merchant=bottom_ltv_merchant["Merchant"], bottom_ltv_merchant_x=fmt_x(bottom_ltv_merchant["LTV/CAC"]),
    )

    out_path = OUT_DIR / "html" / "unified_narrative.html"
    out_path.write_text(html)
    print(f"Wrote unified narrative -> {out_path} ({out_path.stat().st_size/1024:.0f} KB)")


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Imprint Management P&amp;L &mdash; Overview</title>
<style>
  :root {{
    color-scheme: light;
    --blue: #2a78d6; --orange: #eb6834; --aqua: #1baf7a; --red: #e34948; --yellow: #eda100;
    --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
    --grid: #e1e0d9; --surface: #fcfcfb; --page: #f9f9f7; --baseline: #c3c2b7;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --blue: #3987e5; --orange: #d95926; --aqua: #199e70; --red: #e66767; --yellow: #c98500;
      --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
      --grid: #2c2c2a; --surface: #1a1a19; --page: #0d0d0d; --baseline: #383835;
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --blue: #3987e5; --orange: #d95926; --aqua: #199e70; --red: #e66767; --yellow: #c98500;
    --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --surface: #1a1a19; --page: #0d0d0d; --baseline: #383835;
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; background: var(--page); color: var(--ink); margin: 0; }}
  .deck {{ max-width: 980px; margin: 0 auto; }}
  nav.top-nav {{ position: sticky; top: 0; background: var(--page); border-bottom: 1px solid var(--grid); padding: 0.7rem 1.5rem; font-size: 0.85rem; z-index: 10; display: flex; justify-content: space-between; }}
  nav.top-nav a {{ color: var(--blue); text-decoration: none; margin-left: 1rem; }}
  nav.top-nav a:hover {{ text-decoration: underline; }}
  button.theme-toggle {{ margin-left: 1.1rem; font-size: 0.85rem; background: var(--surface); border: 1px solid var(--grid); color: var(--ink-2); border-radius: 999px; padding: 0.25rem 0.65rem; cursor: pointer; }}
  button.theme-toggle:hover {{ color: var(--ink); }}

  .toc {{ display: flex; gap: 0.6rem; flex-wrap: wrap; margin-top: 1.2rem; }}
  .toc a {{ font-size: 0.82rem; color: var(--blue); text-decoration: none; border: 1px solid var(--grid); border-radius: 999px; padding: 0.3rem 0.85rem; }}
  .toc a:hover {{ background: var(--surface); }}

  section.slide {{ padding: 3.2rem 1.75rem; border-bottom: 1px solid var(--grid); }}
  section.slide.alt {{ background: var(--surface); }}
  section.slide h1 {{ font-size: 2rem; margin: 0 0 0.3rem; }}
  section.slide h2 {{ font-size: 1.5rem; margin: 0 0 1.1rem; }}
  section.slide h3 {{ font-size: 1.1rem; margin: 1.6rem 0 0.6rem; color: var(--ink); }}
  section.slide .kicker {{ text-transform: uppercase; letter-spacing: 0.06em; font-size: 0.78rem; color: var(--muted); margin-bottom: 0.5rem; }}
  section.slide p.lede {{ font-size: 1.1rem; color: var(--ink-2); max-width: 700px; }}
  section.slide p {{ line-height: 1.55; color: var(--ink-2); max-width: 780px; }}
  section.slide ul, section.slide ol {{ line-height: 1.6; color: var(--ink-2); padding-left: 1.3rem; max-width: 780px; }}
  section.slide li {{ margin-bottom: 0.5rem; }}
  section.slide strong {{ color: var(--ink); }}

  .stat-row {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 1.5rem 0; }}
  .stat {{ flex: 1; min-width: 150px; background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 0.9rem 1.1rem; }}
  section.slide.alt .stat {{ background: var(--page); }}
  .stat .n {{ font-size: 1.5rem; font-weight: 700; }}
  .stat .l {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.15rem; }}

  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; align-items: start; }}
  @media (max-width: 760px) {{ .two-col {{ grid-template-columns: 1fr; }} }}

  .legend-row {{ display: flex; gap: 1.1rem; flex-wrap: wrap; font-size: 0.85rem; margin-bottom: 0.7rem; }}
  .legend-item {{ display: flex; align-items: center; gap: 0.4rem; color: var(--ink-2); }}
  .legend-swatch {{ width: 12px; height: 3px; border-radius: 2px; display: inline-block; }}

  svg.chart-svg, svg.diagram {{ width: 100%; height: auto; overflow: visible; }}
  svg.chart-svg text, svg.diagram text {{ font-family: inherit; }}
  .axis-text {{ font-size: 10.5px; fill: var(--muted); }}
  .axis-line {{ stroke: var(--baseline); stroke-width: 1; }}
  .gridline {{ stroke: var(--grid); stroke-width: 1; }}
  .series-line {{ fill: none; stroke-width: 2.25; }}
  .series-dot {{ stroke: var(--surface); stroke-width: 1.5; }}
  .series-end-label {{ font-size: 11px; font-weight: 700; }}
  .bar-value-label {{ font-size: 11px; font-weight: 600; fill: var(--ink-2); }}
  .seam-band {{ fill: var(--blue); opacity: 0.06; }}
  .seam-label {{ font-size: 10.5px; fill: var(--muted); }}

  .table-scroll {{ overflow-x: auto; margin-top: 0.6rem; }}
  table.mini-table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
  table.mini-table th {{ text-align: right; color: var(--muted); font-weight: 500; border-bottom: 1px solid var(--baseline); padding: 0.4rem 0.6rem; white-space: nowrap; }}
  table.mini-table th:first-child, table.mini-table td:first-child {{ text-align: left; }}
  table.mini-table td {{ text-align: right; padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--grid); color: var(--ink-2); font-variant-numeric: tabular-nums; white-space: nowrap; }}

  .callout {{ background: var(--surface); border-left: 3px solid var(--blue); border-radius: 0 8px 8px 0; padding: 0.9rem 1.15rem; margin: 1.3rem 0; max-width: 780px; }}
  section.slide.alt .callout {{ background: var(--page); }}
  .callout h4 {{ margin: 0 0 0.5rem; font-size: 0.92rem; color: var(--ink); }}
  .callout ul {{ margin: 0; padding-left: 1.1rem; }}
  .callout li {{ margin-bottom: 0.35rem; font-size: 0.9rem; }}

  .risk-card {{ background: var(--surface); border-left: 3px solid var(--orange); border-radius: 0 8px 8px 0; padding: 0.85rem 1.1rem; margin-bottom: 0.9rem; max-width: 780px; }}
  section.slide.alt .risk-card {{ background: var(--page); }}
  .risk-card .risk-title {{ font-weight: 700; margin-bottom: 0.25rem; color: var(--ink); }}

  .cta-row {{ display: flex; gap: 0.9rem; margin-top: 1.4rem; flex-wrap: wrap; }}
  .cta-row a {{ display: inline-block; background: var(--blue); color: #fff; text-decoration: none; padding: 0.65rem 1.2rem; border-radius: 8px; font-weight: 600; font-size: 0.92rem; }}
  .cta-row a.secondary {{ background: transparent; color: var(--blue); border: 1px solid var(--blue); }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 2rem; }}
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
  <span><strong>Imprint Management P&amp;L</strong> &middot; Overview</span>
  <span><a href="dashboard.html">Executive dashboard</a><a href="narrative_report.html">Narrative walkthrough</a><a href="pitch_deck.html">How this was built</a><button class="theme-toggle" id="theme-toggle" type="button" aria-label="Toggle dark mode">&#9789;</button></span>
</nav>

<div class="deck">

<section class="slide">
  <div class="kicker">The Imprint Portfolio &middot; Q1 2023 &ndash; Q2 2028</div>
  <h1>The Imprint Management P&amp;L, Forecast Forward 8 Quarters</h1>
  <p class="lede">Ten merchant co-brand card programs, tracked from origination through today and projected two years forward, driver by driver. This page is the front door: the Consolidated P&amp;L, the Cohort &amp; Vintage Views, how the Working Model is built, and the Narrative &mdash; in one pass, in that order.</p>
  <div class="stat-row">
    <div class="stat"><div class="n">{total_accounts_today}</div><div class="l">accounts on book, {today_quarter}</div></div>
    <div class="stat"><div class="n">{os_balance_today}</div><div class="l">outstanding balance today</div></div>
    <div class="stat"><div class="n">{total_gr_8q}</div><div class="l">8-quarter forecast Gross Revenue</div></div>
    <div class="stat"><div class="n">{total_cp_8q}</div><div class="l">8-quarter forecast Contribution Profit</div></div>
    <div class="stat"><div class="n">{avg_cm}</div><div class="l">average Contribution Margin</div></div>
    <div class="stat"><div class="n">{portfolio_ltv_cac}</div><div class="l">portfolio LTV/CAC</div></div>
  </div>
  <div class="toc">
    <a href="#pnl">1. Consolidated P&amp;L</a>
    <a href="#cohorts">2. Cohort &amp; Vintage Views</a>
    <a href="#model">3. The Working Model</a>
    <a href="#narrative">4. Narrative</a>
    <a href="#bottomline">Bottom line</a>
  </div>
</section>

<section class="slide alt" id="pnl">
  <div class="kicker">Chapter 1 &middot; The Consolidated P&amp;L</div>
  <h2>All 10 programs, rolled up, Q3 2026 &ndash; Q2 2028</h2>
  <p class="lede">Revenue keeps compounding as the book grows; margin holds in a stable band rather than eroding across the horizon.</p>
  <div class="legend-row">
    <span class="legend-item"><span class="legend-swatch" style="background:var(--blue)"></span>Gross Revenue</span>
    <span class="legend-item"><span class="legend-swatch" style="background:var(--aqua)"></span>Gross Profit</span>
    <span class="legend-item"><span class="legend-swatch" style="background:var(--orange)"></span>Contribution Profit</span>
  </div>
  {trend_chart}

  <h3>Quarterly summary</h3>
  {pnl_table}

  <div class="callout">
    <h4>How to read these lines</h4>
    <ul>
      <li><strong>Contribution Profit</strong> = Gross Profit &minus; Operating Expense. It deliberately excludes Acquisition Cost/CAC &mdash; CAC is spent once at booking but recovered over a customer's lifetime, so it's evaluated separately via LTV/CAC (Chapter 2), not netted into a single quarter's profit.</li>
      <li><strong>CAC</strong> = acquisition-family costs (marketing, origination, sign-on bonus, KYC/AML, added features, bounties) &divide; New Accounts, at the cohort's own booking quarter.</li>
      <li><strong>LTV</strong> = discounted cumulative Contribution Profit per account over a standardized 12-quarter (3-year) window at a 15% annual hurdle rate, so cohorts of very different ages compare on equal footing. See Chapter 2 for LTV by vintage and by FICO tier.</li>
    </ul>
  </div>

  <div class="two-col">
    <div>
      <h3>What makes up Gross Revenue</h3>
      {revenue_mix}
    </div>
    <div>
      <h3>What makes up Cost of Sales</h3>
      {cos_mix}
    </div>
  </div>
  <p style="font-size:0.85rem;color:var(--muted);max-width:780px;margin-top:1rem">Composition tables are the 8-quarter forecast total by raw line item; funding cost, net charge-offs, transaction costs, rewards, rebates, royalties, fraud, and servicing all roll into Cost of Sales.</p>
</section>

<section class="slide" id="cohorts">
  <div class="kicker">Chapter 2 &middot; Cohort &amp; Vintage Views</div>
  <h2>How the portfolio's unit economics evolve as it matures</h2>
  <p class="lede">Three lenses on the same book: how the balance mix ages, how a cohort's per-account economics develop over its own lifetime, and how profitable each vintage and each credit tier actually is.</p>

  <h3>The book is seasoning, not just growing</h3>
  {age_chart}
  <div class="legend-row">
    <span class="legend-item"><span class="legend-swatch" style="background:var(--blue)"></span>Young (0-4Q)</span>
    <span class="legend-item"><span class="legend-swatch" style="background:var(--orange)"></span>Mid (5-8Q)</span>
    <span class="legend-item"><span class="legend-swatch" style="background:var(--aqua)"></span>Seasoned (9Q+)</span>
  </div>
  <p>Young-cohort share of the balance falls from <strong>{young_start}</strong> to <strong>{young_end}</strong>, while seasoned share rises from <strong>{seasoned_start}</strong> to <strong>{seasoned_end}</strong> over the forecast window &mdash; even as new cohorts keep originating, the existing book ages into "seasoned" faster than new originations can dilute it.</p>

  <h3>Per-account economics mature on a predictable curve</h3>
  {cohort_chart}
  <p>Merchant 1 shown, three representative vintages by age at booking. Every vintage starts negative (acquisition costs land before revenue does), climbs through its first several quarters, then plateaus &mdash; older and newer cohorts follow essentially the same shape at the same age, a sign the underlying unit economics are stable, not drifting. The newest vintage's later quarters are forecast, not yet observed.</p>

  <h3>LTV/CAC by vintage &mdash; is it improving as the book matures?</h3>
  {vintage_chart}
  <p>No strong secular trend either way: vintage-level LTV/CAC oscillates between {vintage_lcv_min} and {vintage_lcv_max} with no clear improving or worsening drift. Backbook vintages (booked on or before Q2 2026) average {backbook_lcv_avg}; frontbook vintages booked during the forecast window average {frontbook_lcv_avg} &mdash; new cohorts are landing in the same range as historical ones, not a different regime.</p>

  <h3>LTV/CAC is inverted by FICO tier &mdash; sharply</h3>
  <p>Better credit tiers are <em>less</em> profitable to acquire, not more. High-FICO customers spend heavily &mdash; driving proportionally more rewards cost, since rewards scale with spend &mdash; but revolve less, generating far less interest income, the portfolio's largest revenue line. Lower-FICO customers carry higher charge-off rates, but a materially higher APR/yield on what they do revolve more than compensates. This is the single most consequential finding in this forecast (see Chapter 4).</p>
  {fico_chart}
  {fico_table}
</section>

<section class="slide alt" id="model">
  <div class="kicker">Chapter 3 &middot; The Working Model</div>
  <h2>Driver-based: raw cohort data in, forecast P&amp;L out</h2>
  <p class="lede">Only 10 of the 34 raw line items are forecast as independent drivers (New Accounts, balances, transaction volume). Every recurring dollar line is <strong>historical rate &times; forecasted driver</strong>, with the rate itself a curve indexed by cohort age &mdash; not a flat number, so a genuinely flat rate (yield) and a genuinely curving one (loss rate) are handled by the same mechanism.</p>
  {architecture_diagram}

  <div class="two-col">
    <div>
      <h3>Backbook and frontbook, one engine</h3>
      <p>Existing cohorts (<strong>backbook</strong>) are anchored to their last actual value and rolled forward on the population's development-factor curve. New cohorts booked during the forecast window (<strong>frontbook</strong>) are seeded from a trailing-4-quarter New Accounts growth trend, capped at &plusmn;25%/quarter, then grown on the <em>same</em> curve. The only difference is where the starting size comes from.</p>
    </div>
    {backbook_frontbook_diagram}
  </div>

  <p style="margin-top:1.5rem">Built and independently audited in parallel: {n_pass}/{n_total} audit checks recompute every headline number via a separate code path from source &mdash; most starting from the raw source CSV, not the pipeline's own intermediate outputs &mdash; and pass. The one gap (a roll-forward identity check) is root-caused to new-cohort originations, not a modeling error. Full detail, including three real bugs a second independent review caught before these numbers shipped, is in <a href="pitch_deck.html">How This Was Built</a>.</p>
</section>

<section class="slide" id="narrative">
  <div class="kicker">Chapter 4 &middot; Narrative &mdash; What This Means</div>
  <h2>Who's driving returns, what could break this forecast, and where more data would help</h2>

  <h3>Which merchants contribute the most, and which are drags</h3>
  <p class="lede"><strong>{top_merchant}</strong> is the strongest contributor by total dollars ({top_merchant_cp} Contribution Profit, {top_merchant_cm} margin) over the forecast window. <strong>{bottom_merchant}</strong> is the one clear structural drag ({bottom_merchant_cp}, {bottom_merchant_cm} margin) &mdash; not just smaller or slower-growing, genuinely negative. Scale and unit-economics efficiency aren't the same question, though: by per-account LTV/CAC, <strong>{top_ltv_merchant}</strong> is the most efficient program ({top_ltv_merchant_x}) and <strong>{bottom_ltv_merchant}</strong> the least ({bottom_ltv_merchant_x}).</p>
  {merch_chart}
  <h4 style="font-size:0.92rem;margin:1.5rem 0 0.5rem;color:var(--ink)">Ranked by per-account efficiency (LTV/CAC)</h4>
  {merch_ltv_table}

  <h3>The 3 biggest risks to this forecast</h3>
  <div class="risk-card">
    <div class="risk-title">Risk 1 &middot; Thin-history extrapolation</div>
    <p style="margin:0">The two newest merchants have only 2&ndash;4 quarters of actual history. Their forecasts lean on pooled cross-merchant patterns rather than their own observed behavior.</p>
  </div>
  <div class="risk-card">
    <div class="risk-title">Risk 2 &middot; FICO-tier reward economics may be mispriced</div>
    <p style="margin:0">The mechanism is real and traceable in the data, but this is a portfolio-wide average &mdash; worth validating against Imprint's own unit-economics view before acting on it.</p>
  </div>
  <div class="risk-card">
    <div class="risk-title">Risk 3 &middot; Every rate is held flat</div>
    <p style="margin:0">Yield, loss rate, interchange, rewards &mdash; none carry a macro or competitive-response assumption into the 2-year horizon.</p>
  </div>

  <h3>Where better data would help, in priority order</h3>
  <ol>
    <li><strong>Current, not just origination, FICO.</strong> The FICO-tier reveal above is the single most consequential finding in this forecast, built entirely on credit tier <em>at booking</em>. A refreshed/behavioral FICO feed would show whether it's really a FICO-tier effect or a credit-migration effect, and would sharpen every loss-rate curve at the same time.</li>
    <li><strong>Fee Revenue and Other Credits lack a strong empirical driver.</strong> Best observed correlations are 0.47 (Fee Revenue vs. Outstanding Balance) and 0.19 (Other Credits, sporadic). Together under 5% of Gross Revenue, so low stakes today &mdash; but they're shipped on the best available proxy, not a validated relationship.</li>
    <li><strong>More history for Merchants 9 &amp; 10.</strong> 2 and 4 quarters of actuals respectively &mdash; both pooled to cross-merchant curves rather than forecast on their own observed behavior. A few more actual quarters would let each stand on its own.</li>
    <li><strong>A macro or rate-environment signal.</strong> Every rate is held at its last observed level for 8 quarters; even a simple rate-environment or unemployment index would let a sensitivity range replace the current single point estimate.</li>
  </ol>
</section>

<section class="slide alt" id="bottomline">
  <div class="kicker">Bottom line</div>
  <h2>Portfolio LTV/CAC: {portfolio_ltv_cac}</h2>
  <p class="lede">Below breakeven on a blended basis &mdash; driven almost entirely by the FICO-tier dynamic in Chapter 2, not by any single merchant. Several individual merchants and every below-Good FICO tier clear well above 1x; the blend is dragged down by acquisition spend on segments that don't pay it back within three years. That's a pricing/targeting question worth raising with the business, not a flaw in the forecast.</p>
  <div class="cta-row">
    <a href="dashboard.html">Open the executive dashboard</a>
    <a href="narrative_report.html">Read the extended narrative</a>
    <a class="secondary" href="pitch_deck.html">See how it was built</a>
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

if __name__ == "__main__":
    main()
