"""
06_pnl_rollup.py

Builds:
  1. The consolidated quarterly Imprint Management P&L (all merchants rolled
     up), Q3 2026 - Q2 2028, following the hierarchy required by the brief:
     Gross Revenue -> Cost of Sales -> Gross Profit/Margin% -> Contribution
     Profit/Margin% -> CAC/CAC-per-account -> LTV -> LTV/CAC. Also produces
     the same table split by Merchant, for the "who's a winner/drag" cut.

  2. Cohort-level LTV/CAC, using a discounted (NPV-style) cumulative
     contribution profit per account over a standardized 12-quarter
     (3-year) post-booking window for every cohort, so young and old
     vintages compare on an equal basis.

P&L hierarchy (see line_item_classification.csv):
    Gross Revenue     = Family == 'Revenue'
    Cost of Sales     = Family in {'Contra revenue', 'Losses'}
                        + Expense Category in {Rewards, Royalties, Rebates,
                          Transaction Costs, Servicing, Fraud Losses}
                        (funding costs, net charge-offs, transaction costs,
                        rewards, rebates, royalties, fraud, servicing --
                        exactly the brief's list)
    Gross Profit      = Gross Revenue + Cost of Sales (Cost of Sales is
                        already stored negative)
    Operating Expense = Expense Category in {Operating Expense, Other}
                        (Program Support, Other Credits -- ongoing costs
                        that aren't Cost of Sales and aren't acquisition)
    Contribution Profit = Gross Profit + Operating Expense
    CAC               = Expense Category == Acquisition (+ Marketing,
                        excluding Partner Signing Bonus), at QSB=0 only,
                        i.e. costs incurred for accounts booked *this*
                        quarter -- divided by that quarter's New Accounts.

LTV methodology (see BUILD_LOG.md for the full defense):
    For every cohort, sum discounted Contribution Profit per account (not
    Gross Profit -- LTV should reflect the ongoing cost structure a
    customer actually carries, consistent with the Contribution Profit
    definition above) over QSB 0-11 (12 quarters / 3 years post-booking).
    Quarterly discount rate implied by a 15% annual hurdle rate.
    Cohorts whose window runs past the Q2 2028 forecast cutoff (Vintage
    Index > 10) are extended using the same chain-ladder-style
    development-factor technique as the driver forecast, applied directly
    to the Contribution-Profit-per-Account series pooled across all
    available cohorts -- this is flagged explicitly as an extrapolation
    assumption, not hidden.
"""
import pandas as pd
import numpy as np
from pathlib import Path

from pnl_utils import classify_pnl_bucket, add_pnl_bucket

OUT_DIR = Path(__file__).resolve().parent.parent / "output"

ANNUAL_HURDLE_RATE = 0.15
QUARTERLY_DISCOUNT_RATE = (1 + ANNUAL_HURDLE_RATE) ** 0.25 - 1
LTV_WINDOW_QUARTERS = 12  # 3 years post-booking, QSB 0-11

FORECAST_START_IDX = 14
FORECAST_END_IDX = 21


def load():
    df = pd.read_parquet(OUT_DIR / "combined_actuals_forecast.parquet")
    return df


# ---------------------------------------------------------------------------
# P&L hierarchy aggregation
# ---------------------------------------------------------------------------

def build_pnl(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    """group_cols e.g. ['Report Date Index'] or ['Report Date Index','Merchant']."""
    bucketed = add_pnl_bucket(df)

    subtotals = bucketed[bucketed["PnL Bucket"] != "Excluded"].groupby(group_cols + ["PnL Bucket"])["Value"].sum().unstack("PnL Bucket").fillna(0)
    for col in ["Gross Revenue", "Cost of Sales", "Operating Expense", "Acquisition Cost"]:
        if col not in subtotals.columns:
            subtotals[col] = 0.0

    subtotals["Gross Profit"] = subtotals["Gross Revenue"] + subtotals["Cost of Sales"]
    subtotals["Gross Margin %"] = subtotals["Gross Profit"] / subtotals["Gross Revenue"]
    subtotals["Contribution Profit"] = subtotals["Gross Profit"] + subtotals["Operating Expense"]
    subtotals["Contribution Margin %"] = subtotals["Contribution Profit"] / subtotals["Gross Revenue"]

    new_accts = df[(df["Line Item"] == "New Accounts")].groupby(group_cols)["Value"].sum().rename("New Accounts")
    subtotals = subtotals.join(new_accts)
    subtotals["CAC"] = subtotals["Acquisition Cost"]
    subtotals["CAC / New Account"] = -subtotals["CAC"] / subtotals["New Accounts"]  # positive $ cost per account

    return subtotals.reset_index()


# ---------------------------------------------------------------------------
# LTV / CAC at cohort level
# ---------------------------------------------------------------------------

def cohort_contribution_profit_per_account(df: pd.DataFrame) -> pd.DataFrame:
    """Contribution Profit at (Merchant, Vintage Index, FICO Bucket, QSB),
    divided by that cohort's New Accounts (its own original size)."""
    bucketed = add_pnl_bucket(df)
    cols = ["Merchant", "Vintage Index", "FICO Bucket", "QSB"]

    cp = bucketed[bucketed["PnL Bucket"].isin(["Gross Revenue", "Cost of Sales", "Operating Expense"])]
    cp = cp.groupby(cols)["Value"].sum().rename("Contribution Profit").reset_index()

    new_accts = df[(df["Line Item"] == "New Accounts") & (df["QSB"] == 0)].groupby(
        ["Merchant", "Vintage Index", "FICO Bucket"]
    )["Value"].sum().rename("New Accounts")

    cp = cp.merge(new_accts, on=["Merchant", "Vintage Index", "FICO Bucket"], how="left")
    cp["CP per Account"] = cp["Contribution Profit"] / cp["New Accounts"]
    return cp


# Contribution Profit per Account is a SIGNED quantity that legitimately
# crosses zero (negative at QSB=0 from acquisition costs, positive once a
# cohort matures) -- a multiplicative chain-ladder factor is the wrong tool
# for it. A first attempt used the same development-factor technique as the
# driver forecast (04/05), pooled + clipped the same way; that masked the
# original root cause (Partner Signing Bonus leaking into Contribution
# Profit via a Category-based, not Model-Role-based, bucketing bug -- now
# fixed in pnl_utils.py) but did NOT fix the underlying instability: even
# with clean data, Merchant 7's genuinely-observed QSB0->1/1->2/2->3 factors
# are 3.47x/3.14x/1.95x -- each individually plausible for a near-zero-crossing
# per-account $ figure, but compounding several of them in a row for a
# brand-new cohort (only QSB=0 observed) multiplied out to 40x+ LTV/CAC,
# caught by a parallel independent audit. Multiplicative factors are the
# right tool for the driver forecast (volumes/balances that don't cross
# zero); they are the wrong tool here.
#
# Fix: extend a thin cohort's curve using the PORTFOLIO'S OBSERVED LEVEL at
# each QSB (a level fill, not a compounding growth factor) -- pooled at
# Merchant grain, falling back to the global cross-merchant level for any
# QSB a given merchant hasn't lived long enough to observe itself. This
# can't runaway multiplicatively because nothing is ever multiplied by
# anything: a missing QSB is filled with "what did this kind of cohort
# typically look like at that age," not "grow the last known value by X%."
MATURE_QSB_FALLBACK = True  # kept as a named toggle so the intent reads at the call site


def build_cp_population_curve(cp: pd.DataFrame) -> tuple:
    """Returns (per_merchant_curve: {merchant: Series indexed by QSB},
    global_curve: Series indexed by QSB) of mean CP-per-Account -- used to
    fill in any QSB a cohort hasn't lived long enough to observe."""
    per_merchant = {
        merchant: sub.groupby("QSB")["CP per Account"].mean().sort_index()
        for merchant, sub in cp.groupby("Merchant")
    }
    global_curve = cp.groupby("QSB")["CP per Account"].mean().sort_index()
    return per_merchant, global_curve


def extend_cp_curve(cp_series: pd.Series, merchant: str, per_merchant_curve: dict, global_curve: pd.Series, target_max_qsb: int) -> pd.Series:
    """cp_series indexed by QSB (0..known_max, may be sparse/short). Fills
    every missing QSB up to target_max_qsb with the merchant's own
    population-average level at that age, falling back to the global
    cross-merchant level if this merchant has no observations at that QSB
    either (thin-history merchants, or QSBs beyond what anyone has lived)."""
    series = cp_series.copy()
    merchant_curve = per_merchant_curve.get(merchant, pd.Series(dtype=float))
    for qsb in range(0, target_max_qsb + 1):
        if qsb in series.index:
            continue
        if qsb in merchant_curve.index:
            series.loc[qsb] = merchant_curve.loc[qsb]
        elif qsb in global_curve.index:
            series.loc[qsb] = global_curve.loc[qsb]
        elif len(merchant_curve):
            series.loc[qsb] = merchant_curve.iloc[-1]
        elif len(global_curve):
            series.loc[qsb] = global_curve.iloc[-1]
        else:
            series.loc[qsb] = 0.0
    return series.sort_index()


def build_ltv_cac(df: pd.DataFrame) -> pd.DataFrame:
    cp = cohort_contribution_profit_per_account(df)
    per_merchant_curve, global_curve = build_cp_population_curve(cp)

    target_max_qsb = LTV_WINDOW_QUARTERS - 1  # QSB 0..11

    acq_costs = df[df["Model Role"] == "Acquisition-Cost"]
    acq_costs = acq_costs[acq_costs["Line Item"] != "Partner Signing Bonus"]
    cac_by_cohort = acq_costs.groupby(["Merchant", "Vintage Index", "FICO Bucket"])["Value"].sum().rename("Total Acq Cost")
    new_accts = df[(df["Line Item"] == "New Accounts") & (df["QSB"] == 0)].groupby(
        ["Merchant", "Vintage Index", "FICO Bucket"]
    )["Value"].sum().rename("New Accounts")
    cac_df = pd.concat([cac_by_cohort, new_accts], axis=1).dropna()
    cac_df["CAC per Account"] = -cac_df["Total Acq Cost"] / cac_df["New Accounts"]

    records = []
    for (merchant, vintage_idx, fico), sub in cp.groupby(["Merchant", "Vintage Index", "FICO Bucket"]):
        series = sub.set_index("QSB")["CP per Account"].sort_index()
        series = extend_cp_curve(series, merchant, per_merchant_curve, global_curve, target_max_qsb)
        window = series.loc[0:target_max_qsb]
        discount_factors = 1 / (1 + QUARTERLY_DISCOUNT_RATE) ** window.index.to_series().values
        ltv = float((window.values * discount_factors).sum())

        cac_row = cac_df.loc[(merchant, vintage_idx, fico)] if (merchant, vintage_idx, fico) in cac_df.index else None
        cac_per_acct = float(cac_row["CAC per Account"]) if cac_row is not None else np.nan

        records.append({
            "Merchant": merchant, "Vintage Index": vintage_idx, "FICO Bucket": fico,
            "New Accounts": float(sub["New Accounts"].iloc[0]) if not sub["New Accounts"].isna().all() else np.nan,
            "LTV per Account": ltv,
            "CAC per Account": cac_per_acct,
            "LTV/CAC": ltv / cac_per_acct if cac_per_acct and cac_per_acct > 0 else np.nan,
            "extrapolated_beyond_qsb": max(0, target_max_qsb - sub["QSB"].max()),
        })

    return pd.DataFrame(records)


def index_to_quarter(idx: int) -> str:
    year = 2023 + idx // 4
    qtr = idx % 4 + 1
    return f"Q{qtr} {year}"


def main():
    df = load()

    print(f"Quarterly discount rate implied by {ANNUAL_HURDLE_RATE:.0%} annual hurdle: {QUARTERLY_DISCOUNT_RATE:.3%}")

    print("\nBuilding consolidated quarterly P&L (all merchants)...")
    pnl_consolidated = build_pnl(df, ["Report Date Index", "Scenario"])
    pnl_consolidated["Report Date"] = pnl_consolidated["Report Date Index"].apply(index_to_quarter)
    pnl_consolidated.to_csv(OUT_DIR / "pnl_consolidated.csv", index=False)
    print(pnl_consolidated[pnl_consolidated["Report Date Index"] >= FORECAST_START_IDX][
        ["Report Date", "Gross Revenue", "Cost of Sales", "Gross Profit", "Gross Margin %",
         "Contribution Profit", "Contribution Margin %", "New Accounts", "CAC", "CAC / New Account"]
    ].to_string(index=False))

    print("\nBuilding P&L by Merchant (forecast period only)...")
    pnl_by_merchant = build_pnl(df[df["Report Date Index"] >= FORECAST_START_IDX], ["Merchant"])
    pnl_by_merchant = pnl_by_merchant.sort_values("Contribution Profit", ascending=False)
    pnl_by_merchant.to_csv(OUT_DIR / "pnl_by_merchant.csv", index=False)
    print(pnl_by_merchant[["Merchant", "Gross Revenue", "Gross Profit", "Contribution Profit", "Contribution Margin %"]].to_string(index=False))

    print("\nBuilding cohort-level LTV/CAC...")
    ltv_cac = build_ltv_cac(df)
    ltv_cac.to_csv(OUT_DIR / "ltv_cac_by_cohort.csv", index=False)

    portfolio_ltv = np.average(ltv_cac["LTV per Account"], weights=ltv_cac["New Accounts"])
    portfolio_cac = np.average(ltv_cac["CAC per Account"].fillna(0), weights=ltv_cac["New Accounts"])
    print(f"\nPortfolio-weighted LTV/account: ${portfolio_ltv:,.0f}")
    print(f"Portfolio-weighted CAC/account: ${portfolio_cac:,.0f}")
    print(f"Portfolio LTV/CAC: {portfolio_ltv/portfolio_cac:.2f}x")

    by_merchant_ltv = ltv_cac.groupby("Merchant").apply(
        lambda g: pd.Series({
            "LTV/Account": np.average(g["LTV per Account"], weights=g["New Accounts"]),
            "CAC/Account": np.average(g["CAC per Account"].fillna(0), weights=g["New Accounts"]),
        }), include_groups=False
    )
    by_merchant_ltv["LTV/CAC"] = by_merchant_ltv["LTV/Account"] / by_merchant_ltv["CAC/Account"]
    by_merchant_ltv = by_merchant_ltv.sort_values("LTV/CAC", ascending=False)
    by_merchant_ltv.to_csv(OUT_DIR / "ltv_cac_by_merchant.csv")
    print("\nLTV/CAC by Merchant:")
    print(by_merchant_ltv.to_string())


if __name__ == "__main__":
    main()
