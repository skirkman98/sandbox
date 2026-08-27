"""
02_gap_analysis.py

Throwaway diagnostic pass over the cleaned actuals. Answers the questions
that determine build decisions in 04/05:
  - Is Merchant x FICO x QSB cell coverage dense enough to fit curves at
    that granularity, or do we need to pool to Merchant-level?
  - Does the given "CAC / New Account" reference line reconcile against our
    own computed CAC (sum of Acquisition-Cost line items / New Accounts)?
  - Any sign anomalies (e.g. a "Revenue" family row that's negative, or an
    "Expense" family row that's positive) that would indicate a
    classification mistake before it propagates into the model?

Prints findings to stdout; does not produce a shipped artifact.
"""
import pandas as pd
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "output"
CLEAN_PATH = OUT_DIR / "parquet" / "clean_actuals.parquet"


def load():
    return pd.read_parquet(CLEAN_PATH)


def coverage_by_merchant_fico_qsb(df: pd.DataFrame):
    print("\n=== Cohort coverage: distinct Vintages observed per Merchant x FICO ===")
    # Count distinct vintages per (Merchant, FICO) - this tells us how many
    # independent cohort observations we have to average into a curve shape
    # at that grain. A handful of vintages per FICO cell is thin.
    piv = (
        df[["Merchant", "FICO Bucket", "Vintage"]]
        .drop_duplicates()
        .groupby(["Merchant", "FICO Bucket"])
        .size()
        .unstack("FICO Bucket")
        .fillna(0)
        .astype(int)
    )
    print(piv.to_string())

    thin_cells = (piv < 4).sum().sum()
    total_cells = piv.size
    print(f"\nCells with < 4 vintages of history: {thin_cells}/{total_cells}")
    print("Rule of thumb: cells below ~4 cohorts are too thin to trust a Merchant x FICO curve shape;")
    print("pool to Merchant-level (all FICO combined) for those merchants instead.")


def reconcile_cac(df: pd.DataFrame):
    print("\n=== CAC reconciliation: computed vs. given 'CAC / New Account' ===")
    acq = df[df["Model Role"] == "Acquisition-Cost"]
    # Exclude Partner Signing Bonus - it's a one-time per-merchant cost, not
    # a per-cohort acquisition cost, per the classification notes.
    acq = acq[acq["Line Item"] != "Partner Signing Bonus"]

    cost_by_cohort = (
        acq.groupby(["Merchant", "Vintage", "FICO Bucket"])["Value"].sum().rename("Total Acq Cost")
    )

    new_accts = (
        df[df["Line Item"] == "New Accounts"]
        .groupby(["Merchant", "Vintage", "FICO Bucket"])["Value"]
        .sum()
        .rename("New Accounts")
    )

    given_cac = (
        df[df["Line Item"] == "CAC / New Account"]
        .groupby(["Merchant", "Vintage", "FICO Bucket"])["Value"]
        .sum()
        .rename("Given CAC/Acct")
    )

    combo = pd.concat([cost_by_cohort, new_accts, given_cac], axis=1).dropna()
    combo["Computed CAC/Acct"] = combo["Total Acq Cost"] / combo["New Accounts"]
    combo["Diff"] = combo["Computed CAC/Acct"] - combo["Given CAC/Acct"]
    combo["Diff %"] = (combo["Diff"] / combo["Given CAC/Acct"]).abs()

    print(f"Cohorts compared: {len(combo)}")
    print(f"Median |diff %|: {combo['Diff %'].median():.2%}")
    print(f"Max |diff %|: {combo['Diff %'].max():.2%}")
    print("\nWorst 5 mismatches:")
    print(combo.sort_values("Diff %", ascending=False).head(5).to_string())


def sign_anomalies(df: pd.DataFrame):
    print("\n=== Sign anomalies by Family ===")
    # Expectation: Revenue/Volume/Balance families should be >= 0;
    # Expense/Contra revenue/Losses should be <= 0 (brief: "cost items are negative").
    expect_nonneg = {"Revenue", "Volume", "Balance"}
    expect_nonpos = {"Expense", "Contra revenue", "Losses"}

    for fam in sorted(df["Family"].dropna().unique()):
        sub = df[df["Family"] == fam]
        if fam in expect_nonneg:
            bad = sub[sub["Value"] < 0]
        elif fam in expect_nonpos:
            bad = sub[sub["Value"] > 0]
        else:
            continue
        if len(bad):
            print(f"  {fam}: {len(bad)} rows violate expected sign — line items: {sorted(bad['Line Item'].unique())}")
    print("  (No output above other than headers means no sign anomalies found.)")


def main():
    df = load()
    coverage_by_merchant_fico_qsb(df)
    reconcile_cac(df)
    sign_anomalies(df)


if __name__ == "__main__":
    main()
