"""
10_export_dashboard_data.py

Exports a compact, pre-aggregated dataset for the interactive executive
dashboard (11_build_dashboard.py). The dashboard needs to filter by
Merchant x Vintage x FICO x Scenario and recompute the P&L live in the
browser -- so this script does the one aggregation step that's expensive
in Python (rolling 192K raw line-item rows up to P&L buckets) and ships
the result as a small embedded JSON array. Everything downstream (summing
a filtered subset, deriving margins/ratios from summed dollars) happens in
JS at view-time, which is the only correct way to do it -- margins and
LTV/CAC must be derived from summed dollar components, never averaged as
pre-computed percentages, or filtering would silently produce wrong numbers.

Ships as TWO arrays at different grains -- deliberately not merged into one:
  - `rows`: one row per (Merchant, Vintage Index, FICO Bucket, Report Date
    Index, Scenario) -- 6,860 rows, the P&L bucket dollar totals + New
    Accounts. This is the flow grain: values are meaningful to sum across
    a filtered range of report dates.
  - `cohorts`: one row per (Merchant, Vintage Index, FICO Bucket) -- LTV$/
    CAC$ from the cohort-level LTV table. This is a snapshot grain: each
    cohort's LTV/CAC is a single fact about that cohort, not a per-quarter
    flow. Keeping it in a separate array with its own grain makes it
    structurally impossible to double/N-count a cohort's LTV by summing
    across multiple report-date rows -- an earlier version merged it onto
    every row of `rows` and did exactly that (caught by a JS-side test
    harness before shipping: Poor-FICO LTV/CAC came out 3.66x instead of
    the correct 2.97x).

Both are small enough to filter/aggregate client-side with plain JS over a
few thousand array elements -- no charting library or WebGL needed per the
data-visualization skill's rendering thresholds (SVG is fine well under
1,000 rendered elements per chart; this dataset is the pre-render source,
not what gets drawn).
"""
import json
import pandas as pd
from pathlib import Path

from pnl_utils import add_pnl_bucket

OUT_DIR = Path(__file__).resolve().parent.parent / "output"


def index_to_quarter(idx: int) -> str:
    year = 2023 + idx // 4
    qtr = idx % 4 + 1
    return f"Q{qtr} {year}"


def main():
    df = pd.read_parquet(OUT_DIR / "combined_actuals_forecast.parquet")
    df = add_pnl_bucket(df)

    group_cols = ["Merchant", "Vintage Index", "FICO Bucket", "Report Date Index", "Scenario"]
    bucketed = df[df["PnL Bucket"] != "Excluded"].groupby(group_cols + ["PnL Bucket"])["Value"].sum().unstack("PnL Bucket").fillna(0)
    for col in ["Gross Revenue", "Cost of Sales", "Operating Expense", "Acquisition Cost"]:
        if col not in bucketed.columns:
            bucketed[col] = 0.0
    bucketed = bucketed.reset_index()

    new_accts = df[df["Line Item"] == "New Accounts"].groupby(group_cols)["Value"].sum().rename("New Accounts").reset_index()
    merged = bucketed.merge(new_accts, on=group_cols, how="left")
    merged["New Accounts"] = merged["New Accounts"].fillna(0)

    # LTV$/CAC$ live in a SEPARATE cohort-grain array (one row per
    # Merchant x Vintage x FICO), not merged onto the Report-Date-grain
    # `rows` array below. LTV/CAC is a cohort-level figure -- if it were
    # merged onto every Report Date/Scenario row of that cohort (as an
    # earlier version of this script did), summing across a multi-quarter
    # filter view would count the same cohort's LTV/CAC N times (once per
    # quarter it appears in), inflating the ratio. Keeping it in its own
    # array with its own (m,v,f) grain makes that bug structurally
    # impossible rather than relying on every consumer to remember to dedupe.
    ltv_cac = pd.read_csv(OUT_DIR / "ltv_cac_by_cohort.csv")
    ltv_cac["LTV $"] = ltv_cac["LTV per Account"] * ltv_cac["New Accounts"]
    ltv_cac["CAC $"] = ltv_cac["CAC per Account"] * ltv_cac["New Accounts"]

    cohort_records = []
    for _, row in ltv_cac.iterrows():
        cohort_records.append({
            "m": row["Merchant"],
            "v": int(row["Vintage Index"]),
            "f": row["FICO Bucket"],
            "na": round(float(row["New Accounts"]), 2),
            "ltv": round(float(row["LTV $"]), 2),
            "cac": round(float(row["CAC $"]), 2),
        })

    merged["Vintage"] = merged["Vintage Index"].apply(index_to_quarter)
    merged["Report Date"] = merged["Report Date Index"].apply(index_to_quarter)

    records = []
    for _, row in merged.iterrows():
        records.append({
            "m": row["Merchant"],                    # merchant
            "v": int(row["Vintage Index"]),           # vintage index
            "vq": row["Vintage"],                     # vintage quarter label
            "f": row["FICO Bucket"],                  # FICO bucket
            "r": int(row["Report Date Index"]),       # report date index
            "rq": row["Report Date"],                 # report date quarter label
            "s": row["Scenario"],                     # Actual / Base Case
            "gr": round(float(row["Gross Revenue"]), 2),
            "cos": round(float(row["Cost of Sales"]), 2),
            "opex": round(float(row["Operating Expense"]), 2),
            "acq": round(float(row["Acquisition Cost"]), 2),
            "na": round(float(row["New Accounts"]), 2),
        })

    fico_order = ["Poor (300-579)", "Fair (580-669)", "Good (670-739)", "Very Good (740-799)", "Exceptional (800-850)"]
    merchants = sorted(df["Merchant"].unique(), key=lambda m: int(m.split()[-1]))
    vintages = sorted(merged[["Vintage Index", "Vintage"]].drop_duplicates().values.tolist(), key=lambda x: x[0])
    report_dates = sorted(merged[["Report Date Index", "Report Date"]].drop_duplicates().values.tolist(), key=lambda x: x[0])

    payload = {
        "rows": records,
        "cohorts": cohort_records,
        "dims": {
            "merchants": merchants,
            "ficoBuckets": fico_order,
            "vintages": [{"idx": v, "label": q} for v, q in vintages],
            "reportDates": [{"idx": r, "label": q} for r, q in report_dates],
        },
        "forecastStartIdx": 14,
    }

    out_path = OUT_DIR / "dashboard_data.json"
    with open(out_path, "w") as f:
        json.dump(payload, f, separators=(",", ":"))

    print(f"Wrote {len(records):,} rows -> {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
