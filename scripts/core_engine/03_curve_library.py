"""
core_engine/03_curve_library.py

Builds the reusable "engine" that both the backbook and frontbook forecasts
in core_engine/04_forecast_engine.py draw from:

  1. Development factors (chain-ladder style) for each driver, by
     (Merchant, Grain FICO, QSB -> QSB+1). Volume-weighted ratio-of-sums
     across all vintages that have both QSB and QSB+1 observed — the
     standard actuarial vintage/loss-triangle development technique. This
     is how a cohort's known last-actual value gets projected forward
     while preserving continuity with its own anchor (no level jump).

  2. QSB=0 seed ratios for each driver (value at QSB=0 / New Accounts at
     QSB=0) — used to initialize a brand-new frontbook cohort's starting
     level for drivers other than New Accounts itself.

  3. Rate curves (chain-ladder style, ratio-of-sums) for every Rate-Derived
     line item, by (Merchant, Grain FICO, QSB): rate = line item value /
     driver-basis value. Built uniformly for every rate — a genuinely flat
     rate (e.g. yield) just falls out flat; a genuinely curving rate (e.g.
     loss rate) is captured by QSB. No line-item-specific special-casing.

  4. Acquisition-cost rates (per account, one figure per Merchant/Grain
     FICO, no QSB dimension since these are one-time-at-origination costs)
     for every Acquisition-Cost line item.

Grain (Merchant-only vs. Merchant x FICO) is decided per merchant based on
cohort count, per the gap-analysis finding: merchants with fewer than
POOL_THRESHOLD vintages of history get pooled to Merchant-level curves;
the rest get full Merchant x FICO granularity.
"""
import pandas as pd
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"
CLEAN_PATH = OUT_DIR / "parquet" / "clean_actuals.parquet"

POOL_THRESHOLD = 5  # merchants with < 5 vintages of history get pooled to Merchant-level curves


def load():
    return pd.read_parquet(CLEAN_PATH)


def merchants_needing_pooling(df: pd.DataFrame) -> set:
    n_vintages = df.groupby("Merchant")["Vintage"].nunique()
    pooled = set(n_vintages[n_vintages < POOL_THRESHOLD].index)
    print(f"Pooling to Merchant-level (thin history, < {POOL_THRESHOLD} vintages): {sorted(pooled)}")
    return pooled


def add_grain_fico(df: pd.DataFrame, pooled_merchants: set) -> pd.DataFrame:
    df = df.copy()
    df["Grain FICO"] = df["FICO Bucket"]
    df.loc[df["Merchant"].isin(pooled_merchants), "Grain FICO"] = "ALL"
    return df


def build_development_factors(df: pd.DataFrame) -> pd.DataFrame:
    """For each driver line item, chain-ladder development factors QSB->QSB+1
    at (Merchant, Grain FICO) grain. Volume-weighted: factor = sum(value at
    QSB+1) / sum(value at QSB) across vintages observed at both ages.
    """
    drivers = df[df["Model Role"] == "Driver"]
    grp = drivers.groupby(["Line Item", "Merchant", "Grain FICO", "Vintage", "QSB"])["Value"].sum().reset_index()

    # Work vintage-by-vintage so we only pair a vintage's own QSB and QSB+1
    # (never mix one vintage's QSB=3 with another vintage's QSB=4).
    pivot = grp.pivot_table(index=["Line Item", "Merchant", "Grain FICO", "Vintage"], columns="QSB", values="Value")
    max_qsb = pivot.columns.max()

    records = []
    for qsb in range(0, max_qsb):
        if qsb not in pivot.columns or (qsb + 1) not in pivot.columns:
            continue
        pair = pivot[[qsb, qsb + 1]].dropna()
        if pair.empty:
            continue
        grouped = pair.groupby(["Line Item", "Merchant", "Grain FICO"]).sum()
        grouped["factor"] = grouped[qsb + 1] / grouped[qsb]
        grouped["qsb_from"] = qsb
        records.append(grouped[["factor", "qsb_from"]].reset_index())

    result = pd.concat(records, ignore_index=True)
    result["factor"] = result["factor"].replace([float("inf"), float("-inf")], pd.NA)
    return result


def build_qsb0_seeds(df: pd.DataFrame) -> pd.DataFrame:
    """Ratio of each driver's QSB=0 value to that cohort's New Accounts,
    averaged (volume-weighted) at (Merchant, Grain FICO) grain. Used to seed
    a brand-new frontbook cohort's starting driver levels."""
    drivers = df[(df["Model Role"] == "Driver") & (df["QSB"] == 0)]
    new_accts = drivers[drivers["Line Item"] == "New Accounts"].groupby(
        ["Merchant", "Grain FICO", "Vintage"]
    )["Value"].sum().rename("New Accounts")

    other = drivers[drivers["Line Item"] != "New Accounts"].groupby(
        ["Line Item", "Merchant", "Grain FICO", "Vintage"]
    )["Value"].sum().rename("Value").reset_index()

    other = other.merge(new_accts, on=["Merchant", "Grain FICO", "Vintage"], how="left")
    grp = other.groupby(["Line Item", "Merchant", "Grain FICO"])[["Value", "New Accounts"]].sum()
    grp["seed_ratio"] = grp["Value"] / grp["New Accounts"]
    return grp[["seed_ratio"]].reset_index()


MATURE_QSB_THRESHOLD = 6  # "late-stage" cutoff used to build pooled tail factors/rates


def build_pooled_tail_factors(dev_factors: pd.DataFrame) -> pd.DataFrame:
    """Per Line Item, a single pooled 'late-stage' development factor (median
    across all Merchant x Grain FICO cells, at qsb_from >= MATURE_QSB_THRESHOLD).

    Why this exists: a merchant with only 1-3 quarters of history (e.g. the
    newest merchants) has a development-factor curve that only captures its
    early, high-growth ramp -- holding *that* factor flat forever would
    compound an early ramp-up rate into perpetuity, which is unrealistic for
    a maturing credit portfolio. Even a mature merchant's single highest-QSB
    factor is often backed by just one vintage pair (noisy). Pooling across
    merchants at the mature end of the curve borrows the steady-state decay
    shape that young merchants haven't lived long enough to show yet -- the
    same "borrow strength" logic used for thin FICO cells, applied to the
    tail instead of the whole curve.
    """
    mature = dev_factors[dev_factors["qsb_from"] >= MATURE_QSB_THRESHOLD]
    pooled = mature.groupby("Line Item")["factor"].median().rename("pooled_tail_factor").reset_index()
    return pooled


def build_pooled_tail_rates(rate_curves: pd.DataFrame) -> pd.DataFrame:
    """Same idea as build_pooled_tail_factors, for rate curves."""
    mature = rate_curves[rate_curves["QSB"] >= MATURE_QSB_THRESHOLD]
    pooled = mature.groupby("Line Item")["rate"].median().rename("pooled_tail_rate").reset_index()
    return pooled


SEASONAL_CLIP = (0.5, 1.6)  # Backstop against a pathological result -- wider than the +/-20%
# a generic anti-overfitting guard would use, because the empirical signal here is unusually
# strong and consistent (85% Q1-to-Q4 swing, 100% of the 5 merchants with >= 8 actual quarters
# agree Q4 is the peak / Q1 the trough -- see scripts/core_engine/13_seasonality_analysis.py and BUILD_LOG.md
# "Day 2 -- Seasonality"), not a thin/noisy estimate that calls for suppressing toward 1.0.

# Every Driver line item that gets its own seasonal index, independently
# measured and independently phased -- NOT all copies of the NTV index.
# Extended beyond NTV alone after a user, comparing the shipped dashboard's
# forecast-period seasonality against what the actuals actually show, caught
# that Gross Revenue's forecast swing ran bigger than the actuals' own
# swing (32.4% vs. 25.8%, measured). Root cause: Interest Revenue tracks
# Revolve Balance, which peaks in Q1 -- a full quarter OPPOSITE NTV's Q4
# peak -- so in the real actuals it partially cancels the NTV-driven
# revenue lines' swing when everything sums into Gross Revenue. Only NTV
# had a seasonal index, so that cancellation was missing from the forecast.
# Outstanding Balance and In-Month Active Accounts also have real,
# independently-confirmed seasonality (24.4% and 22.2% swings) feeding Fee
# Revenue, Cost of Funds, Charge Offs, Other Revenue, and Servicing &
# Collections -- same story, same fix. See BUILD_LOG.md "Day 2 -- Extending
# seasonality beyond NTV" for the full before/after measurement.
SEASONAL_LINE_ITEMS = ["Net Transaction Volume", "Revolve Balance", "Outstanding Balance", "In-Month Active Accounts"]


def build_seasonal_index(df: pd.DataFrame, line_item: str) -> pd.DataFrame:
    """Two-factor decomposition: driver(QSB, quarter) = f(QSB) x s(quarter_of_year).
    s() is estimated from THIS line item's own residuals after removing the
    existing QSB-based age curve -- called once per item in SEASONAL_LINE_ITEMS
    above, each getting its own independently-measured index (deliberately
    NOT sharing NTV's index across items with a different real phase -- see
    core_engine/04_forecast_engine.py for how each is applied to its own driver, and how
    that then propagates into the Rate-Derived $ lines keyed off it).
    Confirmed material and reliable by scripts/core_engine/13_seasonality_analysis.py
    (for NTV) and by direct measurement against the shipped dashboard (for
    the 3 added later) before this function was extended -- see BUILD_LOG.md
    for the full investigation both times (this isn't a build-first-check-
    later shortcut).

    Method: index each cohort's own series to its own QSB=0 value (removes
    cohort size), divide by a pooled expected age-curve at that QSB (removes
    age), collapse to ONE weighted-average residual per actual calendar
    quarter (not per cohort-row -- cohorts alive in the same calendar quarter
    aren't independent trials), then average those ~14 points by
    quarter-of-year. Pooled across ALL merchants, not per-merchant -- only
    ~4 years of history means at most ~3-4 independent observations per
    quarter-of-year bucket even pooled; splitting further by merchant would
    make an already-thin estimate thinner still.

    Normalized so the 4 multipliers average to 1.0 -- applied evenly across a
    full forecast year, this reshapes the distribution across quarters without
    changing the annualized total (checked independently in core_engine/07_audit.py).
    """
    item = df[(df["Line Item"] == line_item) & (df["Model Role"] == "Driver")]
    cohort = item.groupby(["Merchant", "Vintage Index", "QSB"])["Value"].sum().reset_index()

    qsb0 = cohort[cohort["QSB"] == 0].set_index(["Merchant", "Vintage Index"])["Value"].rename("qsb0_value")
    normalized = cohort.merge(qsb0, on=["Merchant", "Vintage Index"], how="left")
    # abs() on the weight/scale anchor -- every item in SEASONAL_LINE_ITEMS is
    # naturally non-negative, but this keeps the method usable unchanged if a
    # signed flow (e.g. Principal Payments) is ever added to the list.
    normalized = normalized[normalized["qsb0_value"].abs() > 0]
    normalized["index_val"] = normalized["Value"] / normalized["qsb0_value"]

    w = normalized.copy()
    w["weighted"] = w["index_val"] * w["qsb0_value"].abs()
    age_curve = w.groupby("QSB").agg(weighted_sum=("weighted", "sum"), weight_sum=("qsb0_value", lambda s: s.abs().sum()))
    age_curve["expected_index"] = age_curve["weighted_sum"] / age_curve["weight_sum"]

    normalized = normalized.merge(age_curve["expected_index"], on="QSB", how="left")
    normalized = normalized[normalized["QSB"] > 0]  # QSB=0 residual is trivially 1.0 by construction
    normalized["residual"] = normalized["index_val"] / normalized["expected_index"]
    normalized["Report Date Index"] = normalized["Vintage Index"] + normalized["QSB"]
    normalized["quarter_of_year"] = normalized["Report Date Index"] % 4

    w2 = normalized.copy()
    w2["weighted"] = w2["residual"] * w2["qsb0_value"].abs()
    by_report_date = w2.groupby("Report Date Index").agg(weighted_sum=("weighted", "sum"), weight_sum=("qsb0_value", lambda s: s.abs().sum()))
    by_report_date["avg_residual"] = by_report_date["weighted_sum"] / by_report_date["weight_sum"]
    by_report_date["quarter_of_year"] = by_report_date.index % 4

    by_qoy = by_report_date.groupby("quarter_of_year")["avg_residual"].mean()
    by_qoy = by_qoy / by_qoy.mean()
    by_qoy = by_qoy.clip(*SEASONAL_CLIP)
    result = by_qoy.rename("seasonal_index").reset_index()
    result["Line Item"] = line_item
    return result[["Line Item", "quarter_of_year", "seasonal_index"]]


def build_rate_curves(df: pd.DataFrame, classification: pd.DataFrame) -> pd.DataFrame:
    """Rate = line item value / its Driver Basis value, at (Merchant, Grain
    FICO, QSB) grain, ratio-of-sums (volume weighted). Built for every
    Rate-Derived line item, in dependency order (Recoveries / Debt Sale
    depends on the already-computed Charge Offs rate curve's *driver values*,
    not on another rate curve, so no special ordering is actually required —
    both are ratios against raw driver/line-item dollar values).
    """
    rate_items = classification[classification["Model Role"] == "Rate-Derived"]
    records = []
    for _, row in rate_items.iterrows():
        li = row["Line Item"]
        basis = row["Driver Basis"]

        num = df[df["Line Item"] == li].groupby(["Merchant", "Grain FICO", "QSB"])["Value"].sum().rename("num")
        den = df[df["Line Item"] == basis].groupby(["Merchant", "Grain FICO", "QSB"])["Value"].sum().rename("den")

        joined = pd.concat([num, den], axis=1).dropna()
        joined = joined[joined["den"] != 0]
        joined["rate"] = joined["num"] / joined["den"]
        joined["Line Item"] = li
        joined["Driver Basis"] = basis
        records.append(joined[["Line Item", "Driver Basis", "rate"]].reset_index())

    return pd.concat(records, ignore_index=True)


def build_acquisition_rates(df: pd.DataFrame, classification: pd.DataFrame) -> pd.DataFrame:
    """$/New-Account rate for each Acquisition-Cost line item (excluding
    Partner Signing Bonus, which is a one-time per-merchant cost handled
    separately), at (Merchant, Grain FICO) grain, no QSB dimension."""
    acq_items = classification[
        (classification["Model Role"] == "Acquisition-Cost") & (classification["Line Item"] != "Partner Signing Bonus")
    ]["Line Item"].tolist()

    new_accts = df[(df["Line Item"] == "New Accounts") & (df["QSB"] == 0)].groupby(
        ["Merchant", "Grain FICO"]
    )["Value"].sum().rename("New Accounts")

    records = []
    for li in acq_items:
        cost = df[(df["Line Item"] == li) & (df["QSB"] == 0)].groupby(["Merchant", "Grain FICO"])["Value"].sum().rename("cost")
        joined = pd.concat([cost, new_accts], axis=1).dropna()
        joined["rate_per_account"] = joined["cost"] / joined["New Accounts"]
        joined["Line Item"] = li
        records.append(joined[["Line Item", "rate_per_account"]].reset_index())

    partner_bonus = df[df["Line Item"] == "Partner Signing Bonus"].groupby("Merchant")["Value"].sum().rename("total_bonus").reset_index()
    partner_bonus["Line Item"] = "Partner Signing Bonus"

    return pd.concat(records, ignore_index=True), partner_bonus


def main():
    df = load()
    classification = pd.read_csv(Path(__file__).resolve().parent.parent.parent / "data" / "line_item_classification.csv")

    pooled = merchants_needing_pooling(df)
    df = add_grain_fico(df, pooled)

    dev_factors = build_development_factors(df)
    dev_factors.to_csv(OUT_DIR / "csv" / "curve_dev_factors.csv", index=False)
    print(f"Development factors: {len(dev_factors)} rows -> curve_dev_factors.csv")

    seasonal_index = pd.concat([build_seasonal_index(df, li) for li in SEASONAL_LINE_ITEMS], ignore_index=True)
    seasonal_index.to_csv(OUT_DIR / "csv" / "curve_seasonal_index.csv", index=False)
    for li in SEASONAL_LINE_ITEMS:
        vals = seasonal_index[seasonal_index["Line Item"] == li].sort_values("quarter_of_year")["seasonal_index"].round(3).tolist()
        print(f"Seasonal index ({li}, 0=Q1..3=Q4): {vals} -> curve_seasonal_index.csv")

    pooled_tail_factors = build_pooled_tail_factors(dev_factors)
    pooled_tail_factors.to_csv(OUT_DIR / "csv" / "curve_pooled_tail_factors.csv", index=False)
    print(f"Pooled tail factors (qsb_from >= {MATURE_QSB_THRESHOLD}): {len(pooled_tail_factors)} rows -> curve_pooled_tail_factors.csv")

    seeds = build_qsb0_seeds(df)
    seeds.to_csv(OUT_DIR / "csv" / "curve_qsb0_seeds.csv", index=False)
    print(f"QSB=0 seed ratios: {len(seeds)} rows -> curve_qsb0_seeds.csv")

    rate_curves = build_rate_curves(df, classification)
    rate_curves.to_csv(OUT_DIR / "csv" / "curve_rate_curves.csv", index=False)
    print(f"Rate curves: {len(rate_curves)} rows -> curve_rate_curves.csv")

    pooled_tail_rates = build_pooled_tail_rates(rate_curves)
    pooled_tail_rates.to_csv(OUT_DIR / "csv" / "curve_pooled_tail_rates.csv", index=False)
    print(f"Pooled tail rates (QSB >= {MATURE_QSB_THRESHOLD}): {len(pooled_tail_rates)} rows -> curve_pooled_tail_rates.csv")

    acq_rates, partner_bonus = build_acquisition_rates(df, classification)
    acq_rates.to_csv(OUT_DIR / "csv" / "curve_acquisition_rates.csv", index=False)
    partner_bonus.to_csv(OUT_DIR / "csv" / "curve_partner_signing_bonus.csv", index=False)
    print(f"Acquisition-cost rates: {len(acq_rates)} rows -> curve_acquisition_rates.csv")

    # Also persist the grain-tagged actuals + which merchants were pooled,
    # so core_engine/04_forecast_engine.py doesn't have to re-derive it.
    df.to_parquet(OUT_DIR / "parquet" / "clean_actuals_grained.parquet", index=False)
    pd.Series(sorted(pooled), name="pooled_merchant").to_csv(OUT_DIR / "csv" / "pooled_merchants.csv", index=False)


if __name__ == "__main__":
    main()
