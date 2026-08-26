"""
09_build_narrative_deck.py

Builds output/narrative_report.html -- the financial story, told progressively
in slides: where the book stands today, where it's headed, how it's aging,
what cohort economics reveal, the FICO-tier finding, who's winning and who's
dragging, and the risks. This replaced an earlier single-page report that read
more like a reference document than a story; this version is built to be
read (or presented) top to bottom in order, each slide making one point.

Follows the data-visualization skill:
  - Position/length encodings only -- line charts and bar charts, no pie,
    no 3D, no dual-axis.
  - Categorical hues in FIXED order (blue/orange/aqua), never reassigned
    per view -- a merchant or vintage that appears in two charts keeps its
    color, and colors are never used as the only channel (every mark is
    also direct-labeled).
  - Sequential shading is avoided in favor of a small number of clearly
    labeled representative series (3 vintages, not a 22-line spaghetti
    chart) -- a static page can't re-render on hover, so clarity has to
    come from what's on the page, not from interaction.
  - Every chart ships with alt text (role="img" + aria-label) and the
    underlying numbers are in the surrounding prose/tables, not locked
    inside the SVG only.
  - Charts are static SVG using `style="fill:var(--x)"` / `stroke:var(--x)`
    (not hardcoded hex) specifically so dark mode -- a CSS-only concern --
    re-colors them for free, with no per-theme chart regeneration needed.
"""
import pandas as pd
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "output"

FORECAST_START_IDX = 14


def index_to_quarter(idx: int) -> str:
    year = 2023 + idx // 4
    qtr = idx % 4 + 1
    return f"Q{qtr} {year}"


def fmt_money(x, decimals=1):
    sign = "-" if x < 0 else ""
    a = abs(x)
    if a >= 1e9:
        return f"{sign}${a/1e9:.2f}B"
    if a >= 1e6:
        return f"{sign}${a/1e6:.{decimals}f}M"
    if a >= 1e3:
        return f"{sign}${a/1e3:.0f}K"
    return f"{sign}${a:.0f}"


def fmt_pct(x):
    return f"{x*100:.1f}%"


def fmt_x(x):
    return f"{x:.2f}x"


# ---------------------------------------------------------------------------
# SVG chart helpers -- static markup, theme-reactive via CSS var() in style=
# ---------------------------------------------------------------------------

def svg_line_chart(series, x_labels, seam_index=None, width=860, height=300, value_fmt=fmt_money, aria_label=""):
    """series: list of (key_unused, label, css_color_var, values) tuples, all same length as x_labels."""
    ML, MR, MT, MB = 58, 20, 16, 40
    plot_w, plot_h = width - ML - MR, height - MT - MB
    n = len(x_labels)
    all_vals = [v for _, _, _, vals in series for v in vals]
    y_max = max(0, max(all_vals)) * 1.12 or 1
    y_min = min(0, min(all_vals)) * 1.12

    def x(i):
        return ML + (plot_w / 2 if n == 1 else (i / (n - 1)) * plot_w)

    def y(v):
        return MT + plot_h - ((v - y_min) / (y_max - y_min)) * plot_h

    parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{aria_label}">']

    if seam_index and 0 < seam_index < n:
        band_x = x(seam_index) - (x(seam_index) - x(seam_index - 1)) / 2
        parts.append(f'<rect class="seam-band" x="{band_x:.1f}" y="{MT}" width="{(width - MR) - band_x:.1f}" height="{plot_h}"/>')
        parts.append(f'<text class="seam-label" x="{band_x+4:.1f}" y="{MT+12}">Forecast &rarr;</text>')

    for frac in (0.25, 0.5, 0.75, 1.0):
        v = y_min + (y_max - y_min) * frac
        gy = y(v)
        parts.append(f'<line class="gridline" x1="{ML}" x2="{width-MR}" y1="{gy:.1f}" y2="{gy:.1f}"/>')
        parts.append(f'<text class="axis-text" x="{ML-8}" y="{gy+3:.1f}" text-anchor="end">{value_fmt(v)}</text>')
    parts.append(f'<line class="axis-line" x1="{ML}" x2="{width-MR}" y1="{MT+plot_h}" y2="{MT+plot_h}"/>')

    label_step = max(1, -(-n // 9))
    for i, lab in enumerate(x_labels):
        if i % label_step == 0 or i == n - 1:
            parts.append(f'<text class="axis-text" x="{x(i):.1f}" y="{height-14}" text-anchor="middle">{lab}</text>')

    for _, label, color_var, vals in series:
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
        parts.append(f'<polyline class="series-line" points="{pts}" style="stroke:var({color_var})"/>')
        for i, v in enumerate(vals):
            parts.append(f'<circle class="series-dot" cx="{x(i):.1f}" cy="{y(v):.1f}" r="3" style="fill:var({color_var})"/>')

    # End labels: drawn after all lines, with a greedy vertical-separation pass
    # so two series ending at similar values (e.g. Gross Profit and
    # Contribution Profit, often close together) don't render as overlapping,
    # illegible text -- a label collision is a real readability bug, not
    # cosmetic, per the annotation guidance (labels must be legible on their
    # own, not just "technically present").
    last_x = min(x(n - 1) + 6, width - MR - 2)
    label_positions = sorted(
        [{"color": color_var, "text": value_fmt(vals[-1]), "y": y(vals[-1])} for _, _, color_var, vals in series],
        key=lambda d: d["y"],
    )
    min_gap = 13
    for i in range(1, len(label_positions)):
        if label_positions[i]["y"] - label_positions[i - 1]["y"] < min_gap:
            label_positions[i]["y"] = label_positions[i - 1]["y"] + min_gap
    for lp in label_positions:
        parts.append(f'<text class="series-end-label" x="{last_x:.1f}" y="{lp["y"]+3:.1f}" style="fill:var({lp["color"]})">{lp["text"]}</text>')

    parts.append("</svg>")
    return "".join(parts)


def svg_diverging_bar_chart(bars, width=760, row_h=32, aria_label=""):
    """bars: list of (label, value) tuples. Diverging blue(+)/red(-), sorted as given."""
    ML, MR, MT, MB = 150, 80, 8, 8
    h = MT + MB + len(bars) * row_h
    plot_w = width - ML - MR
    max_abs = max(1, max(abs(v) for _, v in bars))
    zero_x = ML + plot_w / 2
    scale = (plot_w / 2) / max_abs

    parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {h}" role="img" aria-label="{aria_label}">']
    parts.append(f'<line class="axis-line" x1="{zero_x}" x2="{zero_x}" y1="0" y2="{h}"/>')
    for i, (label, v) in enumerate(bars):
        cy = MT + i * row_h + row_h / 2
        bar_w = abs(v) * scale
        bar_x = zero_x if v >= 0 else zero_x - bar_w
        color_var = "--blue" if v >= 0 else "--red"
        parts.append(f'<text class="axis-text" x="{ML-8}" y="{cy+4:.1f}" text-anchor="end">{label}</text>')
        parts.append(f'<rect x="{bar_x:.1f}" y="{cy-9:.1f}" width="{max(bar_w,1):.1f}" height="18" rx="3" style="fill:var({color_var})"/>')
        label_x = bar_x + bar_w + 6 if v >= 0 else bar_x - 6
        anchor = "start" if v >= 0 else "end"
        parts.append(f'<text class="bar-value-label" x="{label_x:.1f}" y="{cy+4:.1f}" text-anchor="{anchor}">{fmt_money(v) if abs(v) > 100 else fmt_x(v)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_stacked_area(x_labels, series, width=860, height=280, aria_label=""):
    """series: list of (label, css_color_var, values 0-100 pct) -- stacked to 100%."""
    ML, MR, MT, MB = 20, 20, 16, 40
    plot_w, plot_h = width - ML - MR, height - MT - MB
    n = len(x_labels)

    def x(i):
        return ML + (plot_w / 2 if n == 1 else (i / (n - 1)) * plot_w)

    def y(v):
        return MT + plot_h - (v / 100) * plot_h

    parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{aria_label}">']
    cum_prev = [0] * n
    for label, color_var, vals in series:
        cum_now = [cum_prev[i] + vals[i] for i in range(n)]
        top_pts = " ".join(f"{x(i):.1f},{y(cum_now[i]):.1f}" for i in range(n))
        bot_pts = " ".join(f"{x(n-1-i):.1f},{y(cum_prev[n-1-i]):.1f}" for i in range(n))
        parts.append(f'<polygon points="{top_pts} {bot_pts}" style="fill:var({color_var})" opacity="0.85"/>')
        cum_prev = cum_now

    for frac in (0, 0.5, 1.0):
        gy = y(frac * 100)
        parts.append(f'<text class="axis-text" x="{ML}" y="{gy-3:.1f}">{int(frac*100)}%</text>')
    label_step = max(1, -(-n // 8))
    for i, lab in enumerate(x_labels):
        if i % label_step == 0 or i == n - 1:
            parts.append(f'<text class="axis-text" x="{x(i):.1f}" y="{height-14}" text-anchor="middle">{lab}</text>')
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_all():
    pnl = pd.read_csv(OUT_DIR / "pnl_consolidated.csv")
    pnl_by_merchant = pd.read_csv(OUT_DIR / "pnl_by_merchant.csv")
    ltv_cac_merchant = pd.read_csv(OUT_DIR / "ltv_cac_by_merchant.csv")
    lcf = pd.read_csv(OUT_DIR / "cohort_ltv_cac_by_fico.csv")
    age_mix = pd.read_csv(OUT_DIR / "cohort_balance_age_mix.csv", index_col=0)
    cp_m1 = pd.read_csv(OUT_DIR / "cohort_cp_per_account_merchant_1.csv")
    audit = pd.read_csv(OUT_DIR / "audit_results.csv")
    df = pd.read_parquet(OUT_DIR / "combined_actuals_forecast.parquet")
    return pnl, pnl_by_merchant, ltv_cac_merchant, lcf, age_mix, cp_m1, audit, df


def main():
    pnl, pnl_by_merchant, ltv_cac_merchant, lcf, age_mix, cp_m1, audit, df = load_all()

    # ---- Slide 2: today ----
    actual = pnl[pnl["Scenario"] == "Actual"].sort_values("Report Date Index")
    today = actual.iloc[-1]
    last_actual_idx = int(today["Report Date Index"])
    snap = df[df["Report Date Index"] == last_actual_idx]
    total_accounts_today = snap[snap["Line Item"] == "Total Accounts"]["Value"].sum()
    os_balance_today = snap[snap["Line Item"] == "Outstanding Balance"]["Value"].sum()
    ntv_today = snap[snap["Line Item"] == "Net Transaction Volume"]["Value"].sum()

    # ---- Slide 3: trend chart ----
    all_pnl = pnl.sort_values("Report Date Index")
    x_labels = [index_to_quarter(i) for i in all_pnl["Report Date Index"]]
    trend_series = [
        ("gr", "Gross Revenue", "--blue", all_pnl["Gross Revenue"].tolist()),
        ("gp", "Gross Profit", "--aqua", all_pnl["Gross Profit"].tolist()),
        ("cp", "Contribution Profit", "--orange", all_pnl["Contribution Profit"].tolist()),
    ]
    trend_chart = svg_line_chart(trend_series, x_labels, seam_index=FORECAST_START_IDX,
                                  aria_label="Gross Revenue, Gross Profit, and Contribution Profit by quarter, actuals through Q2 2026 then forecast")
    fcst = pnl[pnl["Scenario"] == "Base Case"]
    total_gr_8q = fcst["Gross Revenue"].sum()
    total_cp_8q = fcst["Contribution Profit"].sum()
    avg_cm = fcst["Contribution Margin %"].mean()

    # ---- Slide 4: aging mix ----
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

    # ---- Slide 5: cohort curves (3 representative vintages) ----
    vintage_picks = [(0, "Oldest (Q1 2023)", "--blue"), (7, "Mid (Q4 2024)", "--orange"), (13, "Newest (Q2 2026)", "--aqua")]
    cohort_series = []
    max_qsb = 0
    for v_idx, label, color in vintage_picks:
        sub = cp_m1[cp_m1["Vintage Index"] == v_idx].sort_values("QSB")
        max_qsb = max(max_qsb, sub["QSB"].max())
        cohort_series.append((str(v_idx), label, color, sub["CP per Account"].tolist(), sub["QSB"].tolist()))
    # Pad shorter series is unnecessary for the chart fn since each line uses its own x positions;
    # build a dedicated small multiline chart instead of reusing svg_line_chart (different x-domain per series).
    def svg_cohort_chart(series, width=860, height=300, aria_label=""):
        ML, MR, MT, MB = 58, 20, 16, 40
        plot_w, plot_h = width - ML - MR, height - MT - MB
        all_qsb = [q for *_ , qsbs in series for q in qsbs]
        all_vals = [v for _, _, _, vals, _ in series for v in vals]
        qsb_max = max(all_qsb)
        y_max = max(0, max(all_vals)) * 1.15 or 1
        y_min = min(0, min(all_vals)) * 1.15

        def x(q):
            return ML + (q / qsb_max) * plot_w if qsb_max else ML
        def y(v):
            return MT + plot_h - ((v - y_min) / (y_max - y_min)) * plot_h

        parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{aria_label}">']
        parts.append(f'<line class="gridline" x1="{ML}" x2="{width-MR}" y1="{y(0):.1f}" y2="{y(0):.1f}"/>')
        parts.append(f'<text class="axis-text" x="{ML-8}" y="{y(0)+3:.1f}" text-anchor="end">$0</text>')
        for frac in (0.5, 1.0):
            v = y_max * frac
            gy = y(v)
            parts.append(f'<line class="gridline" x1="{ML}" x2="{width-MR}" y1="{gy:.1f}" y2="{gy:.1f}"/>')
            parts.append(f'<text class="axis-text" x="{ML-8}" y="{gy+3:.1f}" text-anchor="end">${v:.0f}</text>')
        parts.append(f'<line class="axis-line" x1="{ML}" x2="{width-MR}" y1="{MT+plot_h}" y2="{MT+plot_h}"/>')
        for q in range(0, qsb_max + 1, max(1, qsb_max // 8)):
            parts.append(f'<text class="axis-text" x="{x(q):.1f}" y="{height-14}" text-anchor="middle">{q}</text>')
        parts.append(f'<text class="axis-text" x="{(ML+width-MR)/2:.1f}" y="{height-2}" text-anchor="middle">Quarters Since Book</text>')

        end_labels = []
        for _, label, color_var, vals, qsbs in series:
            pts = " ".join(f"{x(q):.1f},{y(v):.1f}" for q, v in zip(qsbs, vals))
            parts.append(f'<polyline class="series-line" points="{pts}" style="stroke:var({color_var})"/>')
            lx, ly = x(qsbs[-1]), y(vals[-1])
            parts.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" style="fill:var({color_var})"/>')
            end_labels.append({"x": min(lx + 6, width - MR - 2), "y": ly, "color": color_var, "text": label})
        # Same greedy vertical-separation pass as svg_line_chart, in case two
        # vintages' final values land close together.
        end_labels.sort(key=lambda d: d["y"])
        for i in range(1, len(end_labels)):
            if end_labels[i]["y"] - end_labels[i - 1]["y"] < 13:
                end_labels[i]["y"] = end_labels[i - 1]["y"] + 13
        for lbl in end_labels:
            parts.append(f'<text class="series-end-label" x="{lbl["x"]:.1f}" y="{lbl["y"]+3:.1f}" style="fill:var({lbl["color"]})">{lbl["text"]}</text>')
        parts.append("</svg>")
        return "".join(parts)

    cohort_chart = svg_cohort_chart(cohort_series, aria_label="Contribution Profit per Account by Quarters Since Book, for the oldest, a middle, and the newest vintage of Merchant 1")

    # ---- Slide 6: LTV/CAC by FICO ----
    fico_order = ["Poor (300-579)", "Fair (580-669)", "Good (670-739)", "Very Good (740-799)", "Exceptional (800-850)"]
    lcf_ordered = lcf.set_index("FICO Bucket").reindex(fico_order).reset_index()
    fico_bars = list(zip(lcf_ordered["FICO Bucket"], lcf_ordered["LTV/CAC"]))
    fico_chart = svg_diverging_bar_chart(fico_bars, aria_label="LTV to CAC ratio by FICO tier, Poor through Exceptional")

    # ---- Slide 7: winners & drags ----
    merch_sorted = pnl_by_merchant.sort_values("Contribution Profit", ascending=True)
    merch_bars = list(zip(merch_sorted["Merchant"], merch_sorted["Contribution Profit"]))
    merch_chart = svg_diverging_bar_chart(merch_bars, aria_label="Contribution Profit by merchant, forecast period")
    top_merchant = pnl_by_merchant.sort_values("Contribution Profit", ascending=False).iloc[0]
    bottom_merchant = pnl_by_merchant.sort_values("Contribution Profit", ascending=True).iloc[0]

    # ---- Portfolio LTV/CAC ----
    import numpy as np
    ltv_cac_cohort = pd.read_csv(OUT_DIR / "ltv_cac_by_cohort.csv")
    portfolio_ltv = np.average(ltv_cac_cohort["LTV per Account"], weights=ltv_cac_cohort["New Accounts"])
    portfolio_cac = np.average(ltv_cac_cohort["CAC per Account"].fillna(0), weights=ltv_cac_cohort["New Accounts"])
    portfolio_ltv_cac = portfolio_ltv / portfolio_cac

    def data_table(headers, rows):
        th = "".join(f"<th>{h}</th>" for h in headers)
        body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
        return f'<table class="mini-table"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'

    html = HTML_TEMPLATE.format(
        total_accounts_today=f"{total_accounts_today:,.0f}",
        os_balance_today=fmt_money(os_balance_today),
        ntv_today=fmt_money(ntv_today),
        gr_today=fmt_money(today["Gross Revenue"]),
        cm_today=fmt_pct(today["Contribution Margin %"]),
        today_quarter=today["Report Date"],
        trend_chart=trend_chart,
        total_gr_8q=fmt_money(total_gr_8q),
        total_cp_8q=fmt_money(total_cp_8q),
        avg_cm=fmt_pct(avg_cm),
        age_chart=age_chart,
        young_start=f"{young_start:.0f}%", young_end=f"{young_end:.0f}%",
        seasoned_start=f"{seasoned_start:.0f}%", seasoned_end=f"{seasoned_end:.0f}%",
        cohort_chart=cohort_chart,
        fico_chart=fico_chart,
        fico_table=data_table(["FICO Tier", "LTV/Account", "CAC/Account", "LTV/CAC"],
                               [[r["FICO Bucket"], fmt_money(r["LTV/Account"]), fmt_money(r["CAC/Account"]), fmt_x(r["LTV/CAC"])] for _, r in lcf_ordered.iterrows()]),
        merch_chart=merch_chart,
        top_merchant=top_merchant["Merchant"], top_merchant_cp=fmt_money(top_merchant["Contribution Profit"]), top_merchant_cm=fmt_pct(top_merchant["Contribution Margin %"]),
        bottom_merchant=bottom_merchant["Merchant"], bottom_merchant_cp=fmt_money(bottom_merchant["Contribution Profit"]), bottom_merchant_cm=fmt_pct(bottom_merchant["Contribution Margin %"]),
        portfolio_ltv_cac=fmt_x(portfolio_ltv_cac),
        n_pass=(audit["Status"] == "PASS").sum(), n_total=len(audit),
    )

    out_path = OUT_DIR / "narrative_report.html"
    out_path.write_text(html)
    print(f"Wrote narrative deck -> {out_path} ({out_path.stat().st_size/1024:.0f} KB)")


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Imprint P&amp;L &mdash; The Portfolio Story</title>
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

  section.slide {{ padding: 3.2rem 1.75rem; border-bottom: 1px solid var(--grid); }}
  section.slide.alt {{ background: var(--surface); }}
  section.slide h1 {{ font-size: 2rem; margin: 0 0 0.3rem; }}
  section.slide h2 {{ font-size: 1.5rem; margin: 0 0 1.1rem; }}
  section.slide .kicker {{ text-transform: uppercase; letter-spacing: 0.06em; font-size: 0.78rem; color: var(--muted); margin-bottom: 0.5rem; }}
  section.slide p.lede {{ font-size: 1.1rem; color: var(--ink-2); max-width: 660px; }}
  section.slide p {{ line-height: 1.55; color: var(--ink-2); max-width: 760px; }}
  section.slide ul, section.slide ol {{ line-height: 1.6; color: var(--ink-2); padding-left: 1.3rem; max-width: 760px; }}
  section.slide li {{ margin-bottom: 0.5rem; }}
  section.slide strong {{ color: var(--ink); }}

  .stat-row {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 1.5rem 0; }}
  .stat {{ flex: 1; min-width: 155px; background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 0.9rem 1.1rem; }}
  section.slide.alt .stat {{ background: var(--page); }}
  .stat .n {{ font-size: 1.5rem; font-weight: 700; }}
  .stat .l {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.15rem; }}
  .stat .n.neg {{ color: var(--red); }}

  .legend-row {{ display: flex; gap: 1.1rem; flex-wrap: wrap; font-size: 0.85rem; margin-bottom: 0.7rem; }}
  .legend-item {{ display: flex; align-items: center; gap: 0.4rem; color: var(--ink-2); }}
  .legend-swatch {{ width: 12px; height: 3px; border-radius: 2px; display: inline-block; }}

  svg.chart-svg {{ width: 100%; height: auto; overflow: visible; }}
  svg.chart-svg text {{ font-family: inherit; }}
  .axis-text {{ font-size: 10.5px; fill: var(--muted); }}
  .axis-line {{ stroke: var(--baseline); stroke-width: 1; }}
  .gridline {{ stroke: var(--grid); stroke-width: 1; }}
  .series-line {{ fill: none; stroke-width: 2.25; }}
  .series-dot {{ stroke: var(--surface); stroke-width: 1.5; }}
  .series-end-label {{ font-size: 11px; font-weight: 700; }}
  .bar-value-label {{ font-size: 11px; font-weight: 600; fill: var(--ink-2); }}
  .seam-band {{ fill: var(--blue); opacity: 0.06; }}
  .seam-label {{ font-size: 10.5px; fill: var(--muted); }}

  table.mini-table {{ border-collapse: collapse; width: 100%; font-size: 0.88rem; margin-top: 0.6rem; }}
  table.mini-table th {{ text-align: right; color: var(--muted); font-weight: 500; border-bottom: 1px solid var(--baseline); padding: 0.4rem 0.55rem; }}
  table.mini-table th:first-child, table.mini-table td:first-child {{ text-align: left; }}
  table.mini-table td {{ text-align: right; padding: 0.4rem 0.55rem; border-bottom: 1px solid var(--grid); color: var(--ink-2); font-variant-numeric: tabular-nums; }}

  .risk-card {{ background: var(--surface); border-left: 3px solid var(--orange); border-radius: 0 8px 8px 0; padding: 0.85rem 1.1rem; margin-bottom: 0.9rem; max-width: 760px; }}
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
  <span><strong>Imprint P&amp;L</strong> &middot; The Portfolio Story</span>
  <span><a href="dashboard.html">Executive dashboard</a><a href="pitch_deck.html">How this was built</a><button class="theme-toggle" id="theme-toggle" type="button" aria-label="Toggle dark mode">&#9789;</button></span>
</nav>

<div class="deck">

<section class="slide">
  <div class="kicker">The Imprint Portfolio &middot; Q1 2023 &ndash; Q2 2028</div>
  <h1>A Financial Story, Told Progressively</h1>
  <p class="lede">Ten merchant programs, tracked from origination through today, then projected two years forward. This walkthrough builds the story in order: where the book stands, where it's headed, how it's aging, what the cohorts reveal about unit economics, and who's actually driving returns.</p>
</section>

<section class="slide alt">
  <div class="kicker">Chapter 1 &middot; Where We Start</div>
  <h2>The book today, as of {today_quarter}</h2>
  <p class="lede">Ten programs, four years of originations, a portfolio that's grown from nothing to real scale.</p>
  <div class="stat-row">
    <div class="stat"><div class="n">{total_accounts_today}</div><div class="l">total accounts on book</div></div>
    <div class="stat"><div class="n">{os_balance_today}</div><div class="l">outstanding balance</div></div>
    <div class="stat"><div class="n">{ntv_today}</div><div class="l">quarterly transaction volume</div></div>
    <div class="stat"><div class="n">{gr_today}</div><div class="l">quarterly gross revenue</div></div>
    <div class="stat"><div class="n">{cm_today}</div><div class="l">contribution margin, this quarter</div></div>
  </div>
</section>

<section class="slide">
  <div class="kicker">Chapter 2 &middot; Where It's Headed</div>
  <h2>Growth continues, margins hold</h2>
  <p class="lede">Projecting all 10 programs forward 8 quarters: revenue keeps compounding, and &mdash; once a thin-history extrapolation bug was caught and fixed &mdash; margins settle into a stable band rather than eroding.</p>
  <div class="legend-row">
    <span class="legend-item"><span class="legend-swatch" style="background:var(--blue)"></span>Gross Revenue</span>
    <span class="legend-item"><span class="legend-swatch" style="background:var(--aqua)"></span>Gross Profit</span>
    <span class="legend-item"><span class="legend-swatch" style="background:var(--orange)"></span>Contribution Profit</span>
  </div>
  {trend_chart}
  <div class="stat-row">
    <div class="stat"><div class="n">{total_gr_8q}</div><div class="l">8-quarter Gross Revenue</div></div>
    <div class="stat"><div class="n">{total_cp_8q}</div><div class="l">8-quarter Contribution Profit</div></div>
    <div class="stat"><div class="n">{avg_cm}</div><div class="l">average Contribution Margin</div></div>
  </div>
</section>

<section class="slide alt">
  <div class="kicker">Chapter 3 &middot; How the Book Is Aging</div>
  <h2>The portfolio is seasoning, not just growing</h2>
  <p class="lede">Even as new cohorts keep originating, the balance mix is shifting toward older, more-matured vintages &mdash; the existing book ages into "seasoned" faster than new originations can dilute it.</p>
  {age_chart}
  <div class="legend-row">
    <span class="legend-item"><span class="legend-swatch" style="background:var(--blue)"></span>Young (0-4Q)</span>
    <span class="legend-item"><span class="legend-swatch" style="background:var(--orange)"></span>Mid (5-8Q)</span>
    <span class="legend-item"><span class="legend-swatch" style="background:var(--aqua)"></span>Seasoned (9Q+)</span>
  </div>
  <p>Young-cohort share of the balance falls from <strong>{young_start}</strong> to <strong>{young_end}</strong>, while seasoned share rises from <strong>{seasoned_start}</strong> to <strong>{seasoned_end}</strong> over the forecast window.</p>
</section>

<section class="slide">
  <div class="kicker">Chapter 4 &middot; What Cohorts Reveal</div>
  <h2>Per-account economics mature on a predictable curve</h2>
  <p class="lede">Every vintage starts negative (acquisition costs land before revenue does), climbs through its first several quarters, then plateaus. Older and newer cohorts of the same merchant follow essentially the same shape at the same age &mdash; a sign the underlying unit economics are stable, not drifting.</p>
  {cohort_chart}
  <p>Merchant 1 shown, three representative vintages by age at booking. The newest vintage's later quarters are forecast, not yet observed.</p>
</section>

<section class="slide alt">
  <div class="kicker">Chapter 5 &middot; The Reveal</div>
  <h2>LTV/CAC is inverted by FICO tier &mdash; sharply</h2>
  <p class="lede">Better credit tiers are <em>less</em> profitable to acquire, not more. High-FICO customers spend heavily &mdash; driving proportionally more rewards cost, since rewards scale with spend &mdash; but revolve less, generating far less interest income, the portfolio's largest revenue line. Lower-FICO customers carry higher charge-off rates, but a materially higher APR/yield on what they do revolve more than compensates.</p>
  {fico_chart}
  {fico_table}
</section>

<section class="slide">
  <div class="kicker">Chapter 6 &middot; Winners and Drags</div>
  <h2>Scale and unit-economics efficiency aren't the same thing</h2>
  <p class="lede"><strong>{top_merchant}</strong> is the strongest contributor ({top_merchant_cp} Contribution Profit, {top_merchant_cm} margin) over the forecast window. <strong>{bottom_merchant}</strong> is the one clear structural drag ({bottom_merchant_cp}, {bottom_merchant_cm} margin) &mdash; not just smaller or slower-growing, genuinely negative.</p>
  {merch_chart}
</section>

<section class="slide alt">
  <div class="kicker">Chapter 7 &middot; The Bottom Line</div>
  <h2>Portfolio LTV/CAC: {portfolio_ltv_cac}</h2>
  <p class="lede">Below breakeven on a blended basis &mdash; driven almost entirely by the FICO-tier dynamic in Chapter 5, not by any single merchant. Several individual merchants and every below-Good FICO tier clear well above 1x; the blend is dragged down by acquisition spend on segments that don't pay it back within three years.</p>
  <div class="risk-card">
    <div class="risk-title">Risk 1 &middot; Thin-history extrapolation</div>
    <p style="margin:0">The two newest merchants have only 2&ndash;4 quarters of actual history. Their forecasts lean on pooled cross-merchant patterns rather than their own observed behavior.</p>
  </div>
  <div class="risk-card">
    <div class="risk-title">Risk 2 &middot; FICO-tier reward economics may be mispriced</div>
    <p style="margin:0">The mechanism is real and traceable in the data, but this is a portfolio-wide average &mdash; worth validating against the actual unit-economics view before acting on it.</p>
  </div>
  <div class="risk-card">
    <div class="risk-title">Risk 3 &middot; Every rate is held flat</div>
    <p style="margin:0">Yield, loss rate, interchange, rewards &mdash; none carry a macro or competitive-response assumption into the 2-year horizon.</p>
  </div>
</section>

<section class="slide">
  <div class="kicker">Go deeper</div>
  <h2>{n_pass}/{n_total} independent audit checks pass</h2>
  <p class="lede">Every number in this story is recomputed via a separate code path from source, not just asserted. Explore the live filterable P&amp;L, or see exactly how the model was built.</p>
  <div class="cta-row">
    <a href="dashboard.html">Open the executive dashboard</a>
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
