"""
07_cohort_views.py

The required "Cohort Views" deliverable: shows how the portfolio evolves by
vintage, using both actuals and forecast. Produces the data tables the HTML
report (08) charts directly -- this script does the aggregation, 08 does
the visual presentation.

Views produced:
  1. Contribution Profit per Account by QSB, one line per Vintage, for the
     two largest merchants -- the classic "are newer vintages performing
     better or worse than older ones at the same age" cohort curve.
  2. LTV/CAC by Vintage (across all merchants) -- is unit economics
     improving or deteriorating as the portfolio matures/grows?
  3. LTV/CAC by FICO Bucket -- the Exceptional-vs-Poor finding from the
     build (rewards-heavy high-FICO segment nets negative once contribution
     profit and CAC are both accounted for).
  4. Portfolio composition over time: Outstanding Balance by Vintage-age
     bucket (how much of the book is "young" vs "seasoned"), since the
     margin-compression risk in BUILD_LOG.md is about a growing share of
     young, not-yet-revolving accounts.
"""
import pandas as pd
import numpy as np
from pathlib import Path

from pnl_utils import classify_pnl_bucket

OUT_DIR = Path(__file__).resolve().parent.parent / "output"


def load():
    df = pd.read_parquet(OUT_DIR / "combined_actuals_forecast.parquet")
    ltv_cac = pd.read_csv(OUT_DIR / "ltv_cac_by_cohort.csv")
    return df, ltv_cac


def cp_per_account_by_vintage(df: pd.DataFrame, merchant: str) -> pd.DataFrame:
    sub = df[df["Merchant"] == merchant].copy()
    sub["PnL Bucket"] = sub.apply(classify_pnl_bucket, axis=1)
    cp = sub[sub["PnL Bucket"].isin(["Gross Revenue", "Cost of Sales", "Operating Expense"])]
    cp = cp.groupby(["Vintage Index", "QSB"])["Value"].sum().rename("Contribution Profit").reset_index()

    new_accts = sub[(sub["Line Item"] == "New Accounts")].groupby("Vintage Index")["Value"].sum().rename("New Accounts")
    cp = cp.merge(new_accts, on="Vintage Index")
    cp["CP per Account"] = cp["Contribution Profit"] / cp["New Accounts"]
    return cp


def ltv_cac_by_vintage(ltv_cac: pd.DataFrame) -> pd.DataFrame:
    g = ltv_cac.groupby("Vintage Index").apply(
        lambda x: pd.Series({
            "LTV/Account": np.average(x["LTV per Account"], weights=x["New Accounts"]),
            "CAC/Account": np.average(x["CAC per Account"].fillna(0), weights=x["New Accounts"]),
            "New Accounts": x["New Accounts"].sum(),
        }), include_groups=False
    )
    g["LTV/CAC"] = g["LTV/Account"] / g["CAC/Account"]
    return g.reset_index()


def ltv_cac_by_fico(ltv_cac: pd.DataFrame) -> pd.DataFrame:
    g = ltv_cac.groupby("FICO Bucket").apply(
        lambda x: pd.Series({
            "LTV/Account": np.average(x["LTV per Account"], weights=x["New Accounts"]),
            "CAC/Account": np.average(x["CAC per Account"].fillna(0), weights=x["New Accounts"]),
        }), include_groups=False
    )
    g["LTV/CAC"] = g["LTV/Account"] / g["CAC/Account"]
    return g.reset_index()


def balance_by_cohort_age(df: pd.DataFrame) -> pd.DataFrame:
    """Outstanding Balance split into age buckets (young <=4Q, mid 5-8Q,
    seasoned 9Q+) by Report Date -- shows the mix shift toward younger
    vintages that drives the margin-compression risk."""
    sub = df[df["Line Item"] == "Outstanding Balance"].copy()

    def age_bucket(qsb):
        if qsb <= 4:
            return "Young (0-4Q)"
        if qsb <= 8:
            return "Mid (5-8Q)"
        return "Seasoned (9Q+)"

    sub["Age Bucket"] = sub["QSB"].apply(age_bucket)
    return sub.groupby(["Report Date Index", "Age Bucket"])["Value"].sum().unstack("Age Bucket").fillna(0)


def main():
    df, ltv_cac = load()

    # 1. CP per account by vintage, for the two largest merchants by revenue
    revenue_by_merchant = df[df["Family"] == "Revenue"].groupby("Merchant")["Value"].sum().sort_values(ascending=False)
    top_2 = revenue_by_merchant.head(2).index.tolist()
    print(f"Top 2 merchants by revenue: {top_2}")

    for m in top_2:
        cp = cp_per_account_by_vintage(df, m)
        fname = f"cohort_cp_per_account_{m.replace(' ', '_').lower()}.csv"
        cp.to_csv(OUT_DIR / fname, index=False)
        print(f"  -> {fname} ({len(cp)} rows)")

    # 2. LTV/CAC by vintage
    lcv = ltv_cac_by_vintage(ltv_cac)
    lcv.to_csv(OUT_DIR / "cohort_ltv_cac_by_vintage.csv", index=False)
    print("\nLTV/CAC by Vintage:")
    print(lcv.to_string(index=False))

    # 3. LTV/CAC by FICO
    lcf = ltv_cac_by_fico(ltv_cac)
    lcf.to_csv(OUT_DIR / "cohort_ltv_cac_by_fico.csv", index=False)
    print("\nLTV/CAC by FICO Bucket:")
    print(lcf.to_string(index=False))

    # 4. Balance age-mix over time
    age_mix = balance_by_cohort_age(df)
    age_mix.to_csv(OUT_DIR / "cohort_balance_age_mix.csv")
    age_mix_pct = age_mix.div(age_mix.sum(axis=1), axis=0)
    print("\nOutstanding Balance age mix (% of total), first/last actual, first/last forecast:")
    print(age_mix_pct.iloc[[0, 13, 14, -1]].to_string())


if __name__ == "__main__":
    main()
