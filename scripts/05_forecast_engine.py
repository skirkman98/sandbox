"""
05_forecast_engine.py

Projects all 10 merchants forward 8 quarters (Q3 2026 - Q2 2028, Report Date
Index 14-21) and produces one combined flat table with the same schema as
the raw actuals plus a `Scenario` column ("Actual" vs "Base Case").

BACKBOOK (existing cohorts, Vintage Index <= 13):
    For each driver, take the cohort's last actual value and roll it forward
    QSB-by-QSB using the chain-ladder development factors from
    04_curve_library.py. Beyond the oldest observed QSB (13, only Merchant 1's
    Q1 2023 vintage reaches it), no development factor is observable -- we
    hold the last known factor constant (a "tail factor" assumption, flagged
    in BUILD_LOG.md). This is the majority of the extrapolation risk in the
    whole model: most cohorts need factors well beyond what's been observed.

FRONTBOOK (new cohorts, Vintage Index 14-21, i.e. booked *during* the
forecast window):
    New Accounts sized off each merchant's trailing-4-quarter growth trend
    (capped to +/-25%/quarter to avoid runaway extrapolation), split across
    FICO buckets using the trailing-4-quarter average mix. From that seed,
    every other driver's QSB=0 level is set via the QSB=0 seed ratio
    (value-per-New-Account), then grown forward with the same development
    factors as the backbook. One engine, two different "how did this cohort
    get its size" inputs.

RATE-DERIVED $ LINES (both books):
    value = rate_curve[Line Item, Merchant, Grain FICO, QSB] x forecasted
    driver-basis value. Beyond the observed QSB range, hold the last
    available rate flat (same tail-assumption pattern as the driver factors).

ACQUISITION-COST $ LINES:
    Only fire at QSB=0 for frontbook cohorts (backbook cohorts' acquisition
    costs already happened, historically). rate_per_account x New Accounts.
"""
import pandas as pd
import numpy as np
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "output"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

FORECAST_START_IDX = 14  # Q3 2026
FORECAST_END_IDX = 21    # Q2 2028 (inclusive) -> 8 quarters
LAST_ACTUAL_IDX = 13     # Q2 2026

# Backstop clip on any single-quarter development factor used past a
# merchant's own observed range. Prevents a thin-sample/noisy factor (e.g. a
# brand-new merchant's only observed factor being its early high-growth
# ramp) from compounding into an unrealistic multi-year trajectory. See
# BUILD_LOG.md for the specific case this caught (Merchant 10 NTV).
FACTOR_CLIP = (0.7, 1.3)

FICO_BUCKETS = ["Exceptional (800-850)", "Very Good (740-799)", "Good (670-739)", "Fair (580-669)", "Poor (300-579)"]

TREND_LOOKBACK_QUARTERS = 4
GROWTH_CAP = 0.25  # cap trailing-quarter growth rate applied per forecast quarter, +/-25%


def load_all():
    actuals = pd.read_parquet(OUT_DIR / "clean_actuals_grained.parquet")
    dev_factors = pd.read_csv(OUT_DIR / "curve_dev_factors.csv")
    seeds = pd.read_csv(OUT_DIR / "curve_qsb0_seeds.csv")
    rate_curves = pd.read_csv(OUT_DIR / "curve_rate_curves.csv")
    acq_rates = pd.read_csv(OUT_DIR / "curve_acquisition_rates.csv")
    pooled = set(pd.read_csv(OUT_DIR / "pooled_merchants.csv")["pooled_merchant"])
    classification = pd.read_csv(DATA_DIR / "line_item_classification.csv")
    pooled_tail_factors = pd.read_csv(OUT_DIR / "curve_pooled_tail_factors.csv")
    pooled_tail_rates = pd.read_csv(OUT_DIR / "curve_pooled_tail_rates.csv")
    return actuals, dev_factors, seeds, rate_curves, acq_rates, pooled, classification, pooled_tail_factors, pooled_tail_rates


def grain_fico_for(merchant, fico, pooled_merchants):
    return "ALL" if merchant in pooled_merchants else fico


# ---------------------------------------------------------------------------
# Development factor / rate lookups with tail-factor fallback
# ---------------------------------------------------------------------------

def build_factor_lookup(dev_factors: pd.DataFrame) -> dict:
    """key: (Line Item, Merchant, Grain FICO) -> {qsb_from: factor}, plus the
    max qsb_from observed for that key (used for the tail-factor fallback)."""
    lookup = {}
    for key, sub in dev_factors.groupby(["Line Item", "Merchant", "Grain FICO"]):
        series = sub.set_index("qsb_from")["factor"].dropna().sort_index()
        if len(series):
            lookup[key] = series
    return lookup


def get_factor(lookup, line_item, merchant, grain_fico, qsb_from, pooled_tail_lookup=None):
    key = (line_item, merchant, grain_fico)
    series = lookup.get(key)
    if series is not None and qsb_from in series.index:
        return series.loc[qsb_from]
    # Beyond this (merchant, grain) cell's own observed range: borrow the
    # pooled late-stage factor across all merchants for this line item,
    # rather than compounding this cell's own last (often thin/noisy or
    # early-ramp) factor forever. Falls back further to 1.0 (flat) only if
    # the line item has no pooled tail factor at all.
    if pooled_tail_lookup is not None and line_item in pooled_tail_lookup:
        factor = pooled_tail_lookup[line_item]
    elif series is not None and len(series):
        factor = series.iloc[-1]
    else:
        factor = 1.0
    return float(np.clip(factor, *FACTOR_CLIP))


def build_rate_lookup(rate_curves: pd.DataFrame) -> dict:
    lookup = {}
    for key, sub in rate_curves.groupby(["Line Item", "Merchant", "Grain FICO"]):
        series = sub.set_index("QSB")["rate"].dropna().sort_index()
        if len(series):
            lookup[key] = series
    return lookup


def get_rate(lookup, line_item, merchant, grain_fico, qsb, pooled_tail_lookup=None):
    key = (line_item, merchant, grain_fico)
    series = lookup.get(key)
    if series is not None and qsb in series.index:
        return series.loc[qsb]
    # Same pooled-late-stage-tail logic as get_factor, for rates.
    if pooled_tail_lookup is not None and line_item in pooled_tail_lookup:
        return pooled_tail_lookup[line_item]
    if series is not None and len(series):
        return series.iloc[-1]
    return 0.0


def build_seed_lookup(seeds: pd.DataFrame) -> dict:
    return {
        (row["Line Item"], row["Merchant"], row["Grain FICO"]): row["seed_ratio"]
        for _, row in seeds.iterrows()
    }


def build_acq_rate_lookup(acq_rates: pd.DataFrame) -> dict:
    return {
        (row["Line Item"], row["Merchant"], row["Grain FICO"]): row["rate_per_account"]
        for _, row in acq_rates.iterrows()
    }


# ---------------------------------------------------------------------------
# Frontbook cohort sizing
# ---------------------------------------------------------------------------

def project_new_accounts(actuals: pd.DataFrame) -> pd.DataFrame:
    """For each merchant, compute a capped trailing-growth rate off New
    Accounts and project total New Accounts for each new vintage (14-21).
    FICO mix = trailing-4-quarter average share. Returns one row per
    (Merchant, Vintage Index, FICO Bucket) -> New Accounts."""
    na = actuals[actuals["Line Item"] == "New Accounts"]
    na = na[na["QSB"] == 0]  # New Accounts only ever nonzero at QSB=0

    records = []
    for merchant, sub in na.groupby("Merchant"):
        by_vintage_fico = sub.groupby(["Vintage Index", "FICO Bucket"])["Value"].sum().unstack("FICO Bucket").fillna(0)
        by_vintage_total = by_vintage_fico.sum(axis=1).sort_index()

        recent = by_vintage_total.tail(TREND_LOOKBACK_QUARTERS)
        qoq_growth = recent.pct_change().dropna()
        g = qoq_growth.mean() if len(qoq_growth) else 0.0
        g = float(np.clip(g, -GROWTH_CAP, GROWTH_CAP))

        recent_mix = by_vintage_fico.tail(TREND_LOOKBACK_QUARTERS)
        mix = (recent_mix.sum(axis=0) / recent_mix.sum(axis=0).sum()).reindex(FICO_BUCKETS).fillna(0)

        last_actual_total = by_vintage_total.loc[LAST_ACTUAL_IDX]

        for v in range(FORECAST_START_IDX, FORECAST_END_IDX + 1):
            quarters_out = v - LAST_ACTUAL_IDX
            total_v = last_actual_total * ((1 + g) ** quarters_out)
            for fico in FICO_BUCKETS:
                records.append({
                    "Merchant": merchant, "Vintage Index": v, "FICO Bucket": fico,
                    "New Accounts": total_v * mix[fico], "growth_rate_applied": g,
                })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Driver forecasting (backbook + frontbook, unified)
# ---------------------------------------------------------------------------

def forecast_drivers(actuals, factor_lookup, seed_lookup, new_accounts_frontbook, pooled_merchants, classification, pooled_tail_factors=None):
    driver_items = classification[classification["Model Role"] == "Driver"]["Line Item"].tolist()
    out_rows = []

    merchants = actuals["Merchant"].unique()

    # ---- Backbook: existing cohorts (Vintage Index <= 13) ----
    existing_cohorts = actuals[["Merchant", "Vintage Index", "FICO Bucket"]].drop_duplicates()
    for _, coh in existing_cohorts.iterrows():
        merchant, vintage_idx, fico = coh["Merchant"], coh["Vintage Index"], coh["FICO Bucket"]
        gfico = grain_fico_for(merchant, fico, pooled_merchants)

        for li in driver_items:
            if li == "New Accounts":
                continue  # structurally zero after QSB=0, nothing to forecast
            # Reset per driver item -- every line item shares the same last
            # observed QSB for a given cohort, but this must NOT carry over
            # (and get advanced) across different line items in this loop.
            last_actual_qsb = LAST_ACTUAL_IDX - vintage_idx
            cohort_data = actuals[
                (actuals["Merchant"] == merchant) & (actuals["Vintage Index"] == vintage_idx)
                & (actuals["FICO Bucket"] == fico) & (actuals["Line Item"] == li)
            ]
            last_row = cohort_data[cohort_data["QSB"] == last_actual_qsb]
            if last_row.empty:
                continue
            value = float(last_row["Value"].iloc[0])

            for report_idx in range(FORECAST_START_IDX, FORECAST_END_IDX + 1):
                target_qsb = report_idx - vintage_idx
                if target_qsb <= last_actual_qsb:
                    continue  # shouldn't happen since report_idx > LAST_ACTUAL_IDX >= vintage's last actual report
                for qsb_from in range(last_actual_qsb, target_qsb):
                    factor = get_factor(factor_lookup, li, merchant, gfico, qsb_from, pooled_tail_factors)
                    value *= factor
                out_rows.append({
                    "Merchant": merchant, "Vintage Index": vintage_idx, "FICO Bucket": fico,
                    "Report Date Index": report_idx, "QSB": target_qsb, "Line Item": li, "Value": value,
                })
                last_actual_qsb = target_qsb  # advance anchor so the next report_idx continues the chain

    # ---- Frontbook: new cohorts (Vintage Index 14-21) ----
    for _, row in new_accounts_frontbook.iterrows():
        merchant, vintage_idx, fico = row["Merchant"], row["Vintage Index"], row["FICO Bucket"]
        gfico = grain_fico_for(merchant, fico, pooled_merchants)
        new_accts = row["New Accounts"]

        out_rows.append({
            "Merchant": merchant, "Vintage Index": vintage_idx, "FICO Bucket": fico,
            "Report Date Index": vintage_idx, "QSB": 0, "Line Item": "New Accounts", "Value": new_accts,
        })

        for li in driver_items:
            if li == "New Accounts":
                continue
            seed_ratio = seed_lookup.get((li, merchant, gfico))
            if seed_ratio is None:
                continue
            value = seed_ratio * new_accts
            out_rows.append({
                "Merchant": merchant, "Vintage Index": vintage_idx, "FICO Bucket": fico,
                "Report Date Index": vintage_idx, "QSB": 0, "Line Item": li, "Value": value,
            })

            qsb_cursor = 0
            for report_idx in range(vintage_idx + 1, FORECAST_END_IDX + 1):
                target_qsb = report_idx - vintage_idx
                factor = get_factor(factor_lookup, li, merchant, gfico, qsb_cursor, pooled_tail_factors)
                value *= factor
                out_rows.append({
                    "Merchant": merchant, "Vintage Index": vintage_idx, "FICO Bucket": fico,
                    "Report Date Index": report_idx, "QSB": target_qsb, "Line Item": li, "Value": value,
                })
                qsb_cursor = target_qsb

    return pd.DataFrame(out_rows)


def forecast_rate_derived(driver_forecast: pd.DataFrame, actuals_drivers_forecast_period, rate_lookup, pooled_merchants, classification, pooled_tail_rates=None):
    """value = rate[Line Item, Merchant, Grain FICO, QSB] x driver-basis value.
    Processed in dependency order: any Rate-Derived item whose Driver Basis is
    itself another Rate-Derived item's Line Item runs last."""
    rate_items = classification[classification["Model Role"] == "Rate-Derived"].copy()
    rate_item_names = set(rate_items["Line Item"])
    rate_items["depends_on_rate_item"] = rate_items["Driver Basis"].isin(rate_item_names)
    rate_items = rate_items.sort_values("depends_on_rate_item")  # False (0) sorts first

    # All forecasted driver values (backbook + frontbook), keyed for lookup.
    driver_values = driver_forecast.set_index(
        ["Line Item", "Merchant", "Vintage Index", "FICO Bucket", "Report Date Index"]
    )["Value"]

    computed = {}  # (Line Item) -> DataFrame, so later rate items can depend on earlier ones
    out_rows = []

    for _, row in rate_items.iterrows():
        li, basis = row["Line Item"], row["Driver Basis"]

        if basis in computed:
            basis_df = computed[basis]
            basis_series = basis_df.set_index(["Merchant", "Vintage Index", "FICO Bucket", "Report Date Index"])["Value"]
        else:
            try:
                basis_series = driver_values.xs(basis, level="Line Item")
            except KeyError:
                continue

        li_rows = []
        for key, basis_val in basis_series.items():
            merchant, vintage_idx, fico, report_idx = key
            gfico = grain_fico_for(merchant, fico, pooled_merchants)
            qsb = report_idx - vintage_idx
            rate = get_rate(rate_lookup, li, merchant, gfico, qsb, pooled_tail_rates)
            li_rows.append({
                "Merchant": merchant, "Vintage Index": vintage_idx, "FICO Bucket": fico,
                "Report Date Index": report_idx, "QSB": qsb, "Line Item": li, "Value": rate * basis_val,
            })
        li_df = pd.DataFrame(li_rows)
        computed[li] = li_df
        out_rows.append(li_df)

    return pd.concat(out_rows, ignore_index=True) if out_rows else pd.DataFrame()


def forecast_acquisition_costs(new_accounts_frontbook: pd.DataFrame, acq_rate_lookup, pooled_merchants, classification):
    """Only fires at QSB=0 for frontbook cohorts."""
    acq_items = classification[
        (classification["Model Role"] == "Acquisition-Cost") & (classification["Line Item"] != "Partner Signing Bonus")
    ]["Line Item"].tolist()

    out_rows = []
    for _, row in new_accounts_frontbook.iterrows():
        merchant, vintage_idx, fico, new_accts = row["Merchant"], row["Vintage Index"], row["FICO Bucket"], row["New Accounts"]
        gfico = grain_fico_for(merchant, fico, pooled_merchants)
        for li in acq_items:
            rate = acq_rate_lookup.get((li, merchant, gfico))
            if rate is None:
                continue
            out_rows.append({
                "Merchant": merchant, "Vintage Index": vintage_idx, "FICO Bucket": fico,
                "Report Date Index": vintage_idx, "QSB": 0, "Line Item": li, "Value": rate * new_accts,
            })
    return pd.DataFrame(out_rows)


# ---------------------------------------------------------------------------

def index_to_quarter(idx: int) -> str:
    year = 2023 + idx // 4
    qtr = idx % 4 + 1
    return f"Q{qtr} {year}"


def main():
    actuals, dev_factors, seeds, rate_curves, acq_rates, pooled, classification, pooled_tail_factors_df, pooled_tail_rates_df = load_all()

    factor_lookup = build_factor_lookup(dev_factors)
    rate_lookup = build_rate_lookup(rate_curves)
    seed_lookup = build_seed_lookup(seeds)
    acq_rate_lookup = build_acq_rate_lookup(acq_rates)
    pooled_tail_factors = pooled_tail_factors_df.set_index("Line Item")["pooled_tail_factor"].to_dict()
    pooled_tail_rates = pooled_tail_rates_df.set_index("Line Item")["pooled_tail_rate"].to_dict()

    print("Sizing frontbook new cohorts...")
    new_accounts_frontbook = project_new_accounts(actuals)
    new_accounts_frontbook.to_csv(OUT_DIR / "frontbook_new_accounts.csv", index=False)
    print(new_accounts_frontbook.groupby("Merchant")["growth_rate_applied"].first().to_string())

    print("\nForecasting drivers (backbook + frontbook)...")
    driver_forecast = forecast_drivers(actuals, factor_lookup, seed_lookup, new_accounts_frontbook, pooled, classification, pooled_tail_factors)
    print(f"  {len(driver_forecast):,} driver forecast rows")

    print("Forecasting rate-derived $ lines...")
    rate_forecast = forecast_rate_derived(driver_forecast, None, rate_lookup, pooled, classification, pooled_tail_rates)
    print(f"  {len(rate_forecast):,} rate-derived forecast rows")

    print("Forecasting acquisition-cost $ lines (frontbook only)...")
    acq_forecast = forecast_acquisition_costs(new_accounts_frontbook, acq_rate_lookup, pooled, classification)
    print(f"  {len(acq_forecast):,} acquisition-cost forecast rows")

    forecast = pd.concat([driver_forecast, rate_forecast, acq_forecast], ignore_index=True)
    forecast["Vintage"] = forecast["Vintage Index"].apply(index_to_quarter)
    forecast["Report Date"] = forecast["Report Date Index"].apply(index_to_quarter)
    forecast["QSB"] = forecast["Report Date Index"] - forecast["Vintage Index"]
    forecast["Scenario"] = "Base Case"

    cls_cols = classification.set_index("Line Item")[["Family", "Category", "Model Role", "Driver Basis"]]
    forecast = forecast.join(cls_cols, on="Line Item")

    actuals_out = actuals.drop(columns=["Grain FICO"]).copy()
    actuals_out["Scenario"] = "Actual"

    combined_cols = ["Merchant", "Vintage", "Vintage Index", "Report Date", "Report Date Index", "QSB",
                      "FICO Bucket", "Line Item", "Family", "Category", "Model Role", "Driver Basis",
                      "Value", "Scenario"]
    combined = pd.concat([actuals_out[combined_cols], forecast[combined_cols]], ignore_index=True)

    combined.to_parquet(OUT_DIR / "combined_actuals_forecast.parquet", index=False)
    print(f"\nWrote combined actuals+forecast table -> {OUT_DIR / 'combined_actuals_forecast.parquet'}")
    print(f"Total rows: {len(combined):,} ({(combined['Scenario']=='Actual').sum():,} actual, {(combined['Scenario']=='Base Case').sum():,} forecast)")


if __name__ == "__main__":
    main()
