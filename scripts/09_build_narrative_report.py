"""
09_build_report.py

Assembles everything from 06/07 into one static HTML report -- the primary
deliverable. Charts are matplotlib PNGs embedded as base64 data URIs (no
external dependencies, opens anywhere, no server needed -- appropriate for a
prototype hand-off, not a production dashboard). Colors follow the
`dataviz` skill's validated default palette: fixed categorical hue order,
one hue for sequential (vintage-age) encoding, blue<->red diverging for
signed values (profit/loss, LTV/CAC above or below 1.0x), no dual axes,
no rainbow.
"""
import base64
import io
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "output"

# --- Palette (dataviz skill reference palette, light mode) ---
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
YELLOW = "#eda100"
RED = "#e34948"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
GOOD = "#0ca30c"
CRITICAL = "#d03b3b"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK_SECONDARY,
    "text.color": INK,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})


def fig_to_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def index_to_quarter(idx: int) -> str:
    year = 2023 + idx // 4
    qtr = idx % 4 + 1
    return f"Q{qtr} {year}"


def fmt_money(x, _pos=None):
    if abs(x) >= 1e9:
        return f"${x/1e9:.1f}B"
    if abs(x) >= 1e6:
        return f"${x/1e6:.0f}M"
    if abs(x) >= 1e3:
        return f"${x/1e3:.0f}K"
    return f"${x:.0f}"


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def chart_pnl_trend(pnl: pd.DataFrame) -> str:
    fcst = pnl[pnl["Scenario"] == "Base Case"].sort_values("Report Date Index")
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(fcst["Report Date"], fcst["Gross Revenue"], color=BLUE, linewidth=2, marker="o", markersize=4, label="Gross Revenue")
    ax.plot(fcst["Report Date"], fcst["Gross Profit"], color=AQUA, linewidth=2, marker="o", markersize=4, label="Gross Profit")
    ax.plot(fcst["Report Date"], fcst["Contribution Profit"], color=ORANGE, linewidth=2, marker="o", markersize=4, label="Contribution Profit")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_money))
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title("Consolidated Management P&L -- Base Case Forecast", loc="left", fontsize=12, color=INK)
    fig.tight_layout()
    return fig_to_data_uri(fig)


def chart_margin_trend(pnl: pd.DataFrame) -> str:
    fcst = pnl[pnl["Scenario"] == "Base Case"].sort_values("Report Date Index")
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(fcst["Report Date"], fcst["Gross Margin %"] * 100, color=BLUE, linewidth=2, marker="o", markersize=4, label="Gross Margin %")
    ax.plot(fcst["Report Date"], fcst["Contribution Margin %"] * 100, color=ORANGE, linewidth=2, marker="o", markersize=4, label="Contribution Margin %")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}%"))
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title("Margin % Trend -- stable through the forecast window", loc="left", fontsize=12, color=INK)
    fig.tight_layout()
    return fig_to_data_uri(fig)


def chart_merchant_ranking(pnl_by_merchant: pd.DataFrame) -> str:
    df = pnl_by_merchant.sort_values("Contribution Profit")
    colors = [BLUE if v >= 0 else RED for v in df["Contribution Profit"]]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.barh(df["Merchant"], df["Contribution Profit"], color=colors)
    ax.axvline(0, color=INK_MUTED, linewidth=1)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(fmt_money))
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title("Contribution Profit by Merchant -- Forecast Period (Q3'26-Q2'28)", loc="left", fontsize=12, color=INK)
    fig.tight_layout()
    return fig_to_data_uri(fig)


def chart_ltv_cac_by_fico(lcf: pd.DataFrame) -> str:
    order = ["Poor (300-579)", "Fair (580-669)", "Good (670-739)", "Very Good (740-799)", "Exceptional (800-850)"]
    df = lcf.set_index("FICO Bucket").reindex(order).reset_index()
    colors = [BLUE if v >= 1 else RED for v in df["LTV/CAC"]]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.bar(df["FICO Bucket"], df["LTV/CAC"], color=colors)
    ax.axhline(1.0, color=INK_MUTED, linewidth=1, linestyle="--")
    ax.text(4.4, 1.05, "break-even (1.0x)", color=INK_MUTED, fontsize=9, ha="right")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}x"))
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    plt.setp(ax.get_xticklabels(), rotation=15, ha="right")
    ax.set_title("LTV / CAC by FICO Tier -- portfolio-weighted", loc="left", fontsize=12, color=INK)
    fig.tight_layout()
    return fig_to_data_uri(fig)


def chart_cohort_curves(cp: pd.DataFrame, merchant_name: str) -> str:
    vintages = sorted(cp["Vintage Index"].unique())
    n = len(vintages)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for i, v in enumerate(vintages):
        sub = cp[cp["Vintage Index"] == v].sort_values("QSB")
        # Sequential ramp: older vintages darker, newer vintages lighter (single hue = blue)
        shade = 0.15 + 0.65 * (i / max(n - 1, 1))
        color = plt.matplotlib.colors.to_hex((1 - shade) * np.array([0.16, 0.47, 0.84]) + shade * np.array([0.8, 0.89, 0.98]))
        ax.plot(sub["QSB"], sub["CP per Account"], color=color, linewidth=1.6)
    ax.axhline(0, color=INK_MUTED, linewidth=1)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.0f}"))
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xlabel("Quarters Since Book (QSB)")
    ax.set_title(f"{merchant_name}: Contribution Profit per Account by Vintage\n(darker = older vintage, lighter = newer)", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    return fig_to_data_uri(fig)


def chart_balance_age_mix(age_mix: pd.DataFrame) -> str:
    age_mix = age_mix.copy()
    age_mix.index = [index_to_quarter(i) for i in age_mix.index]
    pct = age_mix.div(age_mix.sum(axis=1), axis=0) * 100
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.stackplot(
        pct.index, pct["Young (0-4Q)"], pct["Mid (5-8Q)"], pct["Seasoned (9Q+)"],
        colors=[BLUE, ORANGE, AQUA], labels=["Young (0-4Q)", "Mid (5-8Q)", "Seasoned (9Q+)"],
    )
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax.legend(frameon=False, loc="upper left", ncol=3)
    step = max(1, len(pct.index) // 10)
    ax.set_xticks(range(0, len(pct.index), step))
    ax.set_xticklabels([pct.index[i] for i in range(0, len(pct.index), step)], rotation=45, ha="right")
    ax.set_title("Outstanding Balance Mix by Cohort Age -- Actuals + Forecast", loc="left", fontsize=12, color=INK)
    fig.tight_layout()
    return fig_to_data_uri(fig)


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------

def df_to_html_table(df: pd.DataFrame, money_cols=(), pct_cols=(), x_cols=(), n_decimals=0) -> str:
    def fmt(col, val):
        if col in money_cols:
            return fmt_money(val)
        if col in pct_cols:
            return f"{val*100:.1f}%"
        if col in x_cols:
            return f"{val:.2f}x"
        if isinstance(val, float):
            return f"{val:,.{n_decimals}f}"
        return str(val)

    header = "".join(f"<th>{c}</th>" for c in df.columns)
    rows = ""
    for _, row in df.iterrows():
        cells = "".join(f"<td>{fmt(c, row[c])}</td>" for c in df.columns)
        rows += f"<tr>{cells}</tr>"
    return f'<table class="datatable"><thead><tr>{header}</tr></thead><tbody>{rows}</tbody></table>'


def main():
    pnl = pd.read_csv(OUT_DIR / "pnl_consolidated.csv")
    pnl_by_merchant = pd.read_csv(OUT_DIR / "pnl_by_merchant.csv")
    ltv_cac_merchant = pd.read_csv(OUT_DIR / "ltv_cac_by_merchant.csv")
    lcf = pd.read_csv(OUT_DIR / "cohort_ltv_cac_by_fico.csv")
    lcv = pd.read_csv(OUT_DIR / "cohort_ltv_cac_by_vintage.csv")
    age_mix = pd.read_csv(OUT_DIR / "cohort_balance_age_mix.csv", index_col=0)
    audit = pd.read_csv(OUT_DIR / "audit_results.csv")
    cp_m1 = pd.read_csv(OUT_DIR / "cohort_cp_per_account_merchant_1.csv")

    fcst = pnl[pnl["Scenario"] == "Base Case"]
    headline_revenue = fcst["Gross Revenue"].sum()
    headline_gp = fcst["Gross Profit"].sum()
    headline_cp = fcst["Contribution Profit"].sum()
    headline_margin = fcst["Contribution Margin %"].mean()

    top_merchant = pnl_by_merchant.sort_values("Contribution Profit", ascending=False).iloc[0]
    bottom_merchant = pnl_by_merchant.sort_values("Contribution Profit", ascending=True).iloc[0]

    portfolio_ltv = np.average(pd.read_csv(OUT_DIR / "ltv_cac_by_cohort.csv")["LTV per Account"],
                                weights=pd.read_csv(OUT_DIR / "ltv_cac_by_cohort.csv")["New Accounts"])
    ltv_cac_df = pd.read_csv(OUT_DIR / "ltv_cac_by_cohort.csv")
    portfolio_cac = np.average(ltv_cac_df["CAC per Account"].fillna(0), weights=ltv_cac_df["New Accounts"])
    portfolio_ltv_cac = portfolio_ltv / portfolio_cac

    charts = {
        "pnl_trend": chart_pnl_trend(pnl),
        "margin_trend": chart_margin_trend(pnl),
        "merchant_ranking": chart_merchant_ranking(pnl_by_merchant),
        "ltv_cac_fico": chart_ltv_cac_by_fico(lcf),
        "cohort_curves": chart_cohort_curves(cp_m1, "Merchant 1"),
        "balance_age_mix": chart_balance_age_mix(age_mix),
    }

    pnl_table = pnl[pnl["Scenario"] == "Base Case"][
        ["Report Date", "Gross Revenue", "Cost of Sales", "Gross Profit", "Gross Margin %",
         "Contribution Profit", "Contribution Margin %", "New Accounts", "CAC / New Account"]
    ]
    pnl_table_html = df_to_html_table(
        pnl_table, money_cols=["Gross Revenue", "Cost of Sales", "Gross Profit", "Contribution Profit"],
        pct_cols=["Gross Margin %", "Contribution Margin %"], n_decimals=0,
    )

    merchant_table_html = df_to_html_table(
        pnl_by_merchant.sort_values("Contribution Profit", ascending=False)[
            ["Merchant", "Gross Revenue", "Gross Profit", "Contribution Profit", "Contribution Margin %"]
        ],
        money_cols=["Gross Revenue", "Gross Profit", "Contribution Profit"], pct_cols=["Contribution Margin %"],
    )

    ltv_cac_table_html = df_to_html_table(
        ltv_cac_merchant.reset_index().sort_values("LTV/CAC", ascending=False)[
            ["Merchant", "LTV/Account", "CAC/Account", "LTV/CAC"]
        ],
        money_cols=["LTV/Account", "CAC/Account"], x_cols=["LTV/CAC"],
    )

    audit_rows = "".join(
        f'<tr><td>{r["Check"]}</td><td class="audit-{"pass" if r["Status"]=="PASS" else "fail"}">{r["Status"]}</td><td>{r["Detail"]}</td></tr>'
        for _, r in audit.iterrows()
    )

    n_fail = (audit["Status"] == "FAIL").sum()

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Imprint P&amp;L -- Narrative Walkthrough</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; background: #f9f9f7; color: #0b0b0b; margin: 0; padding: 0 0 4rem; }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 2rem 1.5rem; }}
  h1 {{ font-size: 1.7rem; margin-bottom: 0.2rem; }}
  h2 {{ font-size: 1.2rem; margin-top: 2.5rem; border-bottom: 1px solid #e1e0d9; padding-bottom: 0.4rem; }}
  .subtitle {{ color: #52514e; margin-top: 0; }}
  .stat-row {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 1.5rem 0; }}
  .stat-tile {{ background: #fcfcfb; border: 1px solid #e1e0d9; border-radius: 8px; padding: 1rem 1.2rem; flex: 1; min-width: 180px; }}
  .stat-tile .label {{ color: #898781; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.02em; }}
  .stat-tile .value {{ font-size: 1.6rem; font-weight: 600; margin-top: 0.2rem; }}
  .stat-tile .value.neg {{ color: #d03b3b; }}
  .stat-tile .value.pos {{ color: #2a78d6; }}
  img.chart {{ max-width: 100%; display: block; margin: 1rem 0; }}
  table.datatable {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; margin: 1rem 0; }}
  table.datatable th {{ text-align: right; color: #898781; font-weight: 500; border-bottom: 1px solid #c3c2b7; padding: 0.4rem 0.6rem; }}
  table.datatable th:first-child, table.datatable td:first-child {{ text-align: left; }}
  table.datatable td {{ text-align: right; padding: 0.4rem 0.6rem; border-bottom: 1px solid #e1e0d9; font-variant-numeric: tabular-nums; }}
  .callout {{ background: #fcfcfb; border-left: 3px solid #2a78d6; padding: 0.8rem 1rem; margin: 1rem 0; border-radius: 0 6px 6px 0; }}
  .callout.risk {{ border-left-color: #d03b3b; }}
  ul.narrative li {{ margin-bottom: 0.6rem; }}
  .audit-pass {{ color: #0ca30c; font-weight: 600; }}
  .audit-fail {{ color: #d03b3b; font-weight: 600; }}
  footer {{ color: #898781; font-size: 0.8rem; margin-top: 3rem; }}
  header.page-head {{ display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 0.5rem; }}
  nav.doc-links {{ font-size: 0.85rem; }}
  nav.doc-links a {{ color: #2a78d6; text-decoration: none; margin-left: 1rem; }}
  nav.doc-links a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<div class="wrap">

<header class="page-head">
  <h1>Imprint Management P&amp;L &mdash; Narrative Walkthrough</h1>
  <nav class="doc-links">
    <a href="dashboard.html">Executive dashboard &rarr;</a>
    <a href="pitch_deck.html">How this was built &rarr;</a>
  </nav>
</header>
<p class="subtitle">Consolidated across 10 merchant programs &middot; Q3 2026 &ndash; Q2 2028 &middot; Base Case scenario &middot; the full written narrative and story, with the live filterable P&amp;L in <a href="dashboard.html">dashboard.html</a></p>

<div class="stat-row">
  <div class="stat-tile"><div class="label">8Q Gross Revenue</div><div class="value">{fmt_money(headline_revenue)}</div></div>
  <div class="stat-tile"><div class="label">8Q Gross Profit</div><div class="value">{fmt_money(headline_gp)}</div></div>
  <div class="stat-tile"><div class="label">8Q Contribution Profit</div><div class="value">{fmt_money(headline_cp)}</div></div>
  <div class="stat-tile"><div class="label">Avg Contribution Margin</div><div class="value">{headline_margin*100:.1f}%</div></div>
  <div class="stat-tile"><div class="label">Portfolio LTV/CAC (3yr, 15% hurdle)</div><div class="value {"neg" if portfolio_ltv_cac<1 else "pos"}">{portfolio_ltv_cac:.2f}x</div></div>
</div>

<h2>Consolidated P&amp;L Trend</h2>
<img class="chart" src="{charts['pnl_trend']}">
<img class="chart" src="{charts['margin_trend']}">
{pnl_table_html}

<h2>Merchant Contribution &mdash; Winners &amp; Drags</h2>
<p><strong>{top_merchant['Merchant']}</strong> is the strongest contributor ({fmt_money(top_merchant['Contribution Profit'])} contribution profit, {top_merchant['Contribution Margin %']*100:.1f}% margin) over the forecast window; <strong>{bottom_merchant['Merchant']}</strong> is the clearest drag ({fmt_money(bottom_merchant['Contribution Profit'])}, negative margin).</p>
<img class="chart" src="{charts['merchant_ranking']}">
{merchant_table_html}

<h2>Cohort Views</h2>
<p>Vintage curves show how each cohort's per-account economics evolve with age (Quarters Since Book). Merchant 1 (largest by revenue) shown below &mdash; darker lines are older vintages, lighter lines are newer.</p>
<img class="chart" src="{charts['cohort_curves']}">
<img class="chart" src="{charts['balance_age_mix']}">

<h2>LTV / CAC</h2>
<p>LTV = discounted (15% annual hurdle) cumulative Contribution Profit per account over a standardized 12-quarter (3-year) post-booking window, so vintages of different ages compare on equal footing. CAC = acquisition-family costs (marketing, origination, sign-on bonus, KYC/AML, added features, acquisition bounties) per new account.</p>
<div class="callout risk">
<strong>Key finding:</strong> LTV/CAC is sharply divergent by FICO tier &mdash; and inverted from what you'd naively expect. Better credit tiers are <em>less</em> profitable to acquire, not more.
</div>
<img class="chart" src="{charts['ltv_cac_fico']}">
{df_to_html_table(lcf[["FICO Bucket","LTV/Account","CAC/Account","LTV/CAC"]], money_cols=["LTV/Account","CAC/Account"], x_cols=["LTV/CAC"])}
<p>Exceptional and Very Good FICO tiers run <em>negative</em> LTV/CAC: these customers spend heavily (driving high interchange and a disproportionately high rewards cost, since rewards scale with spend) but revolve less, generating comparatively little interest income &mdash; the portfolio's largest revenue line. Poor and Fair FICO customers carry much higher charge-off rates, but a materially higher APR/yield on the balances they do revolve more than compensates.</p>

<h2>By Merchant</h2>
{ltv_cac_table_html}

<h2>Independent Audit</h2>
<p>{len(audit) - n_fail}/{len(audit)} automated checks passed. Checks are recomputed via separate code paths from source, not by re-calling the forecasting pipeline's own functions.</p>
<table class="datatable"><thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody>{audit_rows}</tbody></table>

<h2>Narrative</h2>
<p>See <code>BUILD_LOG.md</code> for the full methodology defense, assumption log, and AI-collaboration notes. Headline points:</p>
<ul class="narrative">
  <li><strong>Biggest risk #1 &mdash; thin-history extrapolation.</strong> Merchants 9 and 10 have only 4 and 2 quarters of actual history. Their frontbook growth and maturation curves lean on pooled cross-merchant patterns rather than their own observed behavior &mdash; defensible, but the least-tested assumption in the model.</li>
  <li><strong>Biggest risk #2 &mdash; FICO-tier reward economics.</strong> The negative LTV/CAC on Exceptional/Very Good tiers implies acquisition and rewards spend on the best-credit segment may be structurally mispriced relative to the revenue it generates &mdash; worth validating against real unit economics before acting on it.</li>
  <li><strong>Biggest risk #3 &mdash; held-flat rates into a changing macro environment.</strong> Every rate (yield, loss rate, interchange, rewards) is held at its most recently observed level. A rate-environment shift over the 2-year horizon isn't modeled.</li>
  <li><strong>Where better data would help:</strong> Fee Revenue and Other Credits have no strong empirical driver in this dataset (best correlations ~0.47 and ~0.19 respectively) &mdash; both are carried on a weak proxy driver and flagged rather than asserted with confidence.</li>
</ul>

<footer>Generated by 09_build_report.py from combined_actuals_forecast.parquet &middot; see scripts/ for the full pipeline.</footer>
</div>
</body>
</html>"""

    out_path = OUT_DIR / "narrative_report.html"
    out_path.write_text(html)
    print(f"Wrote narrative report -> {out_path}")


if __name__ == "__main__":
    main()
