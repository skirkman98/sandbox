"""
pnl_utils.py

Shared P&L bucketing logic used by 05_pnl_rollup.py and 06_cohort_views.py.
Previously duplicated near-verbatim in both files -- pulled out after the
duplication let the same bug ship in both places at once (see BUILD_LOG.md:
Partner Signing Bonus was keyed off Category, not Model Role, so it leaked
into Contribution Profit via the "Operating Expense" bucket in both copies).

Model Role is checked FIRST and is authoritative for anything the model
already has an explicit opinion on (Acquisition-Cost, Excluded-Metric,
Driver) -- Family/Category (accounting taxonomy) only decides the bucket
for the remaining Rate-Derived $ lines. This is deliberately more defensive
than keying off Category alone: a line item's Model Role is set once in
04/05's forecasting logic and must stay consistent with how it's treated in
the P&L, whereas Category is a looser accounting label that doesn't by
itself guarantee CAC/Acquisition-Cost items are kept out of Contribution
Profit.
"""


def classify_pnl_bucket(row) -> str:
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
        if cat in ("Acquisition", "Marketing"):
            return "Acquisition Cost"
    return "Excluded"


def add_pnl_bucket(df):
    df = df.copy()
    df["PnL Bucket"] = df.apply(classify_pnl_bucket, axis=1)
    return df
