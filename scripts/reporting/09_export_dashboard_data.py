"""
reporting/09_export_dashboard_data.py

Exports a compact, pre-aggregated dataset for the interactive executive
dashboard (reporting/10_build_dashboard.py). The dashboard needs to filter by
Merchant x Vintage x FICO x Scenario and recompute the P&L live in the
browser -- so this script does the one aggregation step that's expensive
in Python (rolling 192K raw line-item rows up to P&L buckets) and ships
the result as a small embedded JSON array. Everything downstream (summing
a filtered subset, deriving margins/ratios from summed dollars) happens in
JS at view-time, which is the only correct way to do it -- margins and
LTV/CAC must be derived from summed dollar components, never averaged as
pre-computed percentages, or filtering would silently produce wrong numbers.

Ships THREE arrays at different grains -- deliberately not merged into one:
  - `rows`: one row per (Merchant, Vintage Index, FICO Bucket, Report Date
    Index, Scenario) -- 6,860 rows, the 4 P&L bucket dollar totals + New
    Accounts. This is the flow grain: values are meaningful to sum across
    a filtered range of report dates. Unchanged from the original build.
  - `detail` (Day 2 / TODO item 4 + 7): same grain as `rows`, but ALL 33
    summable raw line items (all 34 rows of line_item_classification.csv
    except `CAC / New Account`, an Excluded-Metric reference ratio that must
    never be summed -- see the note above SUMMABLE_ITEMS below), keyed by
    short abbreviations (see SHORT_KEYS) with a `dims.lineItemKeys` legend so
    the dashboard renders labels from data, not hardcoded JS strings. Powers
    both the full-detail P&L view (item 4) and the driver KPI tab (item 7).

    IMPORTANT, and why this isn't just `rows` with more columns: of the 33
    items, most are FLOWS (safe to sum across a filtered multi-quarter
    range, same as the existing 4 P&L buckets), but Total Accounts,
    Outstanding Balance, Revolve Balance, and EoP Interest & Fees Balance are
    STOCKS (period-end snapshots -- summing across quarters is meaningless),
    and In-Month Active Accounts is a per-quarter activity snapshot, not
    cumulative. Summing these across a multi-quarter filter would reintroduce
    the exact bug class the `cohorts` array below already exists to prevent
    (cohort-grain-vs-flow-grain N-counting) for a new set of line items. The
    `Aggregation` column in line_item_classification.csv (Flow/Stock) flags
    this; it's shipped in the `dims.lineItemKeys` legend so reporting/10_build_dashboard.py
    can enforce "never sum a Stock across quarters" at render time, and the
    detail table itself is rendered TRANSPOSED (line items as rows, quarters
    as columns) specifically so a stock is only ever summed *across entities
    within one quarter* (always valid), never across quarters.

    Also includes `bos` (Beginning Outstanding Balance), a precomputed lag
    field for item 7's Payment Rate -- a temporal join done here in Python
    (groupby + shift per cohort, spanning the actual/forecast seam correctly
    since it's keyed on the cohort, not the Scenario column) rather than in
    client-side JS, which is much more error-prone for this kind of join over
    a flat array. Not a real line item, so it's not part of SUMMABLE_ITEMS.
  - `cohorts`: one row per (Merchant, Vintage Index, FICO Bucket) -- LTV$/
    CAC$ from the cohort-level LTV table. This is a snapshot grain: each
    cohort's LTV/CAC is a single fact about that cohort, not a per-quarter
    flow. Keeping it in a separate array with its own grain makes it
    structurally impossible to double/N-count a cohort's LTV by summing
    across multiple report-date rows -- an earlier version merged it onto
    every row of `rows` and did exactly that (caught by a JS-side test
    harness before shipping: Poor-FICO LTV/CAC came out 3.66x instead of
    the correct 2.97x).

All three are small enough to filter/aggregate client-side with plain JS over
a few thousand array elements -- no charting library or WebGL needed per the
data-visualization skill's rendering thresholds (SVG is fine well under
1,000 rendered elements per chart; this dataset is the pre-render source,
not what gets drawn).
"""
import json
import math
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "output"

# Short, collision-free keys for every summable raw line item -- extends the
# existing gr/cos/opex/acq/na abbreviation convention. Manually curated (not
# auto-derived from initials) specifically to guarantee no collisions across
# all 33 at a glance, and to stay stable across reruns.
SHORT_KEYS = {
    "New Accounts": "na", "Total Accounts": "ta", "In-Month Active Accounts": "aa",
    "Net Transaction Volume": "ntv", "On-Merchant Volume": "onm", "Off-Merchant Volume": "offm",
    "Outstanding Balance": "os", "Revolve Balance": "rb", "EoP Interest & Fees Balance": "ifb",
    "Principal Payments": "pp",
    "Interest Revenue": "ir", "Interchange Revenue": "ic", "Merchant Discount Rate": "mdr",
    "Fee Revenue": "fr", "Other Revenue": "orv",
    "Cost of Funds": "cof", "Charge Offs": "cho", "Recoveries / Debt Sale": "rec",
    "3rd Party Fraud": "frd", "Rewards": "rw", "Royalties": "roy", "Rebates": "reb",
    "Payment Fees": "pf", "Servicing & Collections": "svc",
    "Program Support": "ps", "Other Credits": "ocr",
    "Marketing Expense": "mkt", "Card Origination": "cor", "Sign-On Bonus": "sob",
    "Added Features": "af", "KYC/AML and Underwriting Costs": "kyc",
    "Acquisition Bounties": "ab", "Partner Signing Bonus": "psb",
}
BEGINNING_OS_KEY = "bos"  # not a raw line item -- see docstring
BEGINNING_RB_KEY = "brb"  # Beginning Revolve Balance -- same idea, for item 7's NIM (average earning-asset base)


def detail_group(row):
    """Traditional P&L layout order per TODO item 4: Volumes & Balances,
    then Revenue, Cost of Sales, Operating Expense, Acquisition Cost --
    mirrors line_item_classification.csv's own row order (Drivers get their
    own group here rather than pnl_utils.py's "Excluded", since the detail
    view is meant to show them, not exclude them)."""
    if row["Model Role"] == "Driver":
        return "Volumes & Balances"
    if row["Model Role"] == "Acquisition-Cost":
        return "Acquisition Cost"
    fam, cat = row["Family"], row["Category"]
    if fam == "Revenue":
        return "Revenue"
    if fam in ("Contra revenue", "Losses"):
        return "Cost of Sales"
    if fam == "Expense":
        if cat in ("Rewards", "Royalties", "Rebates", "Transaction Costs", "Servicing", "Fraud Losses"):
            return "Cost of Sales"
        if cat in ("Operating Expense", "Other"):
            return "Operating Expense"
    return None


GROUP_ORDER = ["Volumes & Balances", "Revenue", "Cost of Sales", "Operating Expense", "Acquisition Cost"]


def index_to_quarter(idx: int) -> str:
    year = 2023 + idx // 4
    qtr = idx % 4 + 1
    return f"Q{qtr} {year}"


def safe_round(x, n=2):
    x = float(x)
    return round(x, n) if math.isfinite(x) else 0.0


def build_pnl_buckets(df):
    """Original 4-bucket export -- unchanged."""

    def classify_pnl_bucket(row):
        if row["Model Role"] == "Acquisition-Cost":
            return "Acquisition Cost"
        if row["Model Role"] in ("Excluded-Metric", "Driver"):
            return "Excluded"
        fam, cat = row["Family"], row["Category"]
        if fam == "Revenue":
            return "Gross Revenue"
        if fam in ("Contra revenue", "Losses"):
            return "Cost of Sales"
        if fam == "Expense":
            if cat in ("Rewards", "Royalties", "Rebates", "Transaction Costs", "Servicing", "Fraud Losses"):
                return "Cost of Sales"
            if cat in ("Operating Expense", "Other"):
                return "Operating Expense"
        return "Excluded"

    df = df.copy()
    df["PnL Bucket"] = df.apply(classify_pnl_bucket, axis=1)

    group_cols = ["Merchant", "Vintage Index", "FICO Bucket", "Report Date Index", "Scenario"]
    bucketed = df[df["PnL Bucket"] != "Excluded"].groupby(group_cols + ["PnL Bucket"])["Value"].sum().unstack("PnL Bucket").fillna(0)
    for col in ["Gross Revenue", "Cost of Sales", "Operating Expense", "Acquisition Cost"]:
        if col not in bucketed.columns:
            bucketed[col] = 0.0
    bucketed = bucketed.reset_index()

    new_accts = df[df["Line Item"] == "New Accounts"].groupby(group_cols)["Value"].sum().rename("New Accounts").reset_index()
    merged = bucketed.merge(new_accts, on=group_cols, how="left")
    merged["New Accounts"] = merged["New Accounts"].fillna(0)
    return merged


def build_detail(df, classification):
    """All 33 summable line items (excludes CAC / New Account, an
    Excluded-Metric reference ratio -- see this file's docstring), at the
    same grain as `rows`, keyed by SHORT_KEYS, plus the precomputed
    Beginning Outstanding Balance lag field."""
    summable = classification[classification["Model Role"] != "Excluded-Metric"]
    grain = ["Merchant", "Vintage Index", "FICO Bucket", "Report Date Index", "Scenario"]

    detail_df = df[df["Line Item"].isin(summable["Line Item"])]
    wide = detail_df.groupby(grain + ["Line Item"])["Value"].sum().unstack("Line Item").fillna(0)
    wide = wide.reset_index()
    wide = wide.rename(columns=SHORT_KEYS)

    # Beginning Outstanding Balance / Beginning Revolve Balance: shift within
    # each cohort, sorted by Report Date Index -- spans the actual/forecast
    # seam correctly since the groupby key is the cohort (Merchant, Vintage
    # Index, FICO Bucket), not Scenario, so a cohort's last actual quarter
    # correctly seeds its first forecast quarter's beginning balance.
    wide = wide.sort_values(["Merchant", "Vintage Index", "FICO Bucket", "Report Date Index"])
    grp = wide.groupby(["Merchant", "Vintage Index", "FICO Bucket"])
    wide[BEGINNING_OS_KEY] = grp["os"].shift(1)
    wide[BEGINNING_RB_KEY] = grp["rb"].shift(1)

    return wide


def build_line_item_legend(classification):
    """dims.lineItemKeys legend: short key -> label/family/category/
    aggregation, ordered per GROUP_ORDER/detail_group so reporting/10_build_dashboard.py
    doesn't have to re-derive the traditional P&L grouping in JS."""
    cls = classification[classification["Model Role"] != "Excluded-Metric"].copy()
    cls["group"] = cls.apply(detail_group, axis=1)
    cls["key"] = cls["Line Item"].map(SHORT_KEYS)

    groups = []
    for group_name in GROUP_ORDER:
        sub = cls[cls["group"] == group_name]
        items = [
            {"key": row["key"], "label": row["Line Item"], "aggregation": row["Aggregation"], "unit": row["Unit"]}
            for _, row in sub.iterrows()
        ]
        groups.append({"group": group_name, "items": items})

    legend = {
        row["key"]: {"label": row["Line Item"], "aggregation": row["Aggregation"], "unit": row["Unit"]}
        for _, row in cls.iterrows()
    }
    legend[BEGINNING_OS_KEY] = {"label": "Beginning Outstanding Balance", "aggregation": "Stock", "unit": "$"}
    legend[BEGINNING_RB_KEY] = {"label": "Beginning Revolve Balance", "aggregation": "Stock", "unit": "$"}
    return legend, groups


def main():
    df = pd.read_parquet(OUT_DIR / "parquet" / "combined_actuals_forecast.parquet")
    classification = pd.read_csv(DATA_DIR / "line_item_classification.csv")

    merged = build_pnl_buckets(df)

    detail_wide = build_detail(df, classification)
    line_item_keys, line_item_groups = build_line_item_legend(classification)

    # LTV$/CAC$ live in a SEPARATE cohort-grain array (one row per
    # Merchant x Vintage x FICO), not merged onto the Report-Date-grain
    # `rows` array below. LTV/CAC is a cohort-level figure -- if it were
    # merged onto every Report Date/Scenario row of that cohort (as an
    # earlier version of this script did), summing across a multi-quarter
    # filter view would count the same cohort's LTV/CAC N times (once per
    # quarter it appears in), inflating the ratio. Keeping it in its own
    # array with its own (m,v,f) grain makes that bug structurally
    # impossible rather than relying on every consumer to remember to dedupe.
    ltv_cac = pd.read_csv(OUT_DIR / "csv" / "ltv_cac_by_cohort.csv")
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

    detail_key_cols = [c for c in detail_wide.columns if c in SHORT_KEYS.values() or c in (BEGINNING_OS_KEY, BEGINNING_RB_KEY)]
    detail_records = []
    for _, row in detail_wide.iterrows():
        rec = {
            "m": row["Merchant"], "v": int(row["Vintage Index"]), "f": row["FICO Bucket"],
            "r": int(row["Report Date Index"]), "s": row["Scenario"],
        }
        for k in detail_key_cols:
            rec[k] = safe_round(row[k])
        detail_records.append(rec)

    fico_order = ["Poor (300-579)", "Fair (580-669)", "Good (670-739)", "Very Good (740-799)", "Exceptional (800-850)"]
    merchants = sorted(df["Merchant"].unique(), key=lambda m: int(m.split()[-1]))
    vintages = sorted(merged[["Vintage Index", "Vintage"]].drop_duplicates().values.tolist(), key=lambda x: x[0])
    report_dates = sorted(merged[["Report Date Index", "Report Date"]].drop_duplicates().values.tolist(), key=lambda x: x[0])

    payload = {
        "rows": records,
        "detail": detail_records,
        "cohorts": cohort_records,
        "dims": {
            "merchants": merchants,
            "ficoBuckets": fico_order,
            "vintages": [{"idx": v, "label": q} for v, q in vintages],
            "reportDates": [{"idx": r, "label": q} for r, q in report_dates],
            "lineItemKeys": line_item_keys,
            "lineItemGroups": line_item_groups,
        },
        "forecastStartIdx": 14,
    }

    out_path = OUT_DIR / "json" / "dashboard_data.json"
    with open(out_path, "w") as f:
        json.dump(payload, f, separators=(",", ":"))

    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {len(records):,} rows + {len(detail_records):,} detail rows -> {out_path} ({size_kb:.0f} KB)")
    if size_kb > 8000:
        print("  NOTE: payload exceeds ~8MB -- consider lazy-rendering the detail section rather than parsing it "
              "eagerly (see this script's docstring / TODO item 4's size discussion). Still well under a hard limit "
              "for a file:// static page at this row count, but flagging for awareness.")


if __name__ == "__main__":
    main()
