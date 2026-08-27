"""
core_engine/12_validate_exceptional_fico.py

Day-2 TODO item 2: validate the MAGNITUDE of the already-confirmed
Exceptional-FICO negative-Contribution-Profit finding (BUILD_LOG.md's Risk
#2: Merchant 1's most mature actual cohort pays $91,497 in rewards on
$274,600 revenue -- 33% -- vs Poor-tier's $4,001 on $139,200, 2.9%).
Direction is not in question; only whether the size of the effect holds up
across more merchants or was an artifact of which one example got traced.

Diagnostic script, like core_engine/02_gap_analysis.py -- not a pipeline dependency.
Deliberately does not import pnl_utils.py / core_engine/05_pnl_rollup.py (re-implements
the bucketing rule from scratch) -- same "don't share the builder's blind
spot" discipline as core_engine/07_audit.py. Findings get written up in BUILD_LOG.md by
hand; this script only prints/computes, it doesn't fix anything itself.

Three parts:
  1. Hand-derive the Exceptional-vs-Poor rewards/revenue split for 2-3 more
     merchants beyond Merchant 1, each at ITS OWN most mature actual cohort
     (see note in most_mature_cohort() on why "QSB 13" doesn't generalize).
  2. Systematic outlier scan: cohort-level undiscounted 12Q CP/Account
     (independently recomputed, same method as core_engine/07_audit.py Check E) via
     z-score within each FICO tier, plus a scan of the Rewards rate curve
     itself for any single-QSB outlier observations.
  3. Rewards-rate sanity check: confirm the Rewards line item is correctly
     classified into Cost of Sales (not a Partner-Signing-Bonus-style
     Category/Model-Role mismatch), and check whether the rate curve behind
     it is actually FICO-tier-specific for every merchant, or a pooled
     fallback that would silently mute (or fabricate) the tier effect.
"""
import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "output"

EXCEPTIONAL = "Exceptional (800-850)"
POOR = "Poor (300-579)"
FICO_ORDER = ["Poor (300-579)", "Fair (580-669)", "Good (670-739)", "Very Good (740-799)", "Exceptional (800-850)"]


def classify_pnl_bucket(row):
    """Independently re-implemented (not imported) from pnl_utils.py --
    same rule, separate code path, per this project's audit discipline."""
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


def load_combined():
    df = pd.read_parquet(OUT_DIR / "parquet" / "combined_actuals_forecast.parquet")
    df["Bucket"] = df.apply(classify_pnl_bucket, axis=1)
    return df


# ---------------------------------------------------------------------------
# 1. Hand-derived magnitude check, 2-3 more merchants
# ---------------------------------------------------------------------------

def most_mature_cohort(actuals, merchant):
    """The 'QSB 13' Merchant 1 comparison doesn't generalize literally --
    Merchant 1 is the only merchant with actual history back to Vintage
    Index 0, so it's the only one that ever reaches QSB 13 in the actuals
    (14 quarters of history, QSB 13 = Vintage 0 seen at Report Date Index
    13). Merchants 4/5/7 launched 5/6/8 quarters later, so their own oldest
    vintage tops out at QSB 8/7/5 respectively. The fair analog is each
    merchant's OWN most mature observed cohort, not a fixed QSB."""
    sub = actuals[actuals["Merchant"] == merchant]
    oldest_vintage = sub["Vintage Index"].min()
    max_qsb = sub[sub["Vintage Index"] == oldest_vintage]["QSB"].max()
    return int(oldest_vintage), int(max_qsb)


def hand_derive(actuals, merchant, vintage_idx, qsb, fico):
    cohort = actuals[
        (actuals["Merchant"] == merchant)
        & (actuals["Vintage Index"] == vintage_idx)
        & (actuals["QSB"] == qsb)
        & (actuals["FICO Bucket"] == fico)
    ]
    revenue = cohort[cohort["Bucket"] == "Gross Revenue"]["Value"].sum()
    rewards = cohort[cohort["Line Item"] == "Rewards"]["Value"].sum()
    cp = cohort[cohort["Bucket"].isin(["Gross Revenue", "Cost of Sales", "Operating Expense"])]["Value"].sum()
    return float(revenue), float(rewards), float(cp)


def run_hand_derivations(df):
    print("=" * 78)
    print("1. HAND-DERIVED EXCEPTIONAL-TIER MAGNITUDE -- MORE MERCHANTS")
    print("=" * 78)
    actuals = df[df["Scenario"] == "Actual"]
    # Merchant 1 recomputed too, as a baseline continuity check against the
    # figure already published in BUILD_LOG.md -- not one of the "2-3 more".
    merchants = ["Merchant 1", "Merchant 4", "Merchant 5", "Merchant 7"]
    rows = []
    for m in merchants:
        v, qsb = most_mature_cohort(actuals, m)
        exc_rev, exc_rewards, exc_cp = hand_derive(actuals, m, v, qsb, EXCEPTIONAL)
        poor_rev, poor_rewards, poor_cp = hand_derive(actuals, m, v, qsb, POOR)
        exc_pct = abs(exc_rewards) / exc_rev if exc_rev else float("nan")
        poor_pct = abs(poor_rewards) / poor_rev if poor_rev else float("nan")
        tag = " (baseline, already in BUILD_LOG.md)" if m == "Merchant 1" else ""
        rows.append(dict(
            merchant=m, vintage_idx=v, qsb=qsb,
            exc_revenue=exc_rev, exc_rewards=exc_rewards, exc_rewards_pct_of_rev=exc_pct, exc_cp=exc_cp,
            poor_revenue=poor_rev, poor_rewards=poor_rewards, poor_rewards_pct_of_rev=poor_pct, poor_cp=poor_cp,
        ))
        print(f"\n{m} -- most mature cohort: Vintage Index {v}, QSB {qsb}{tag}")
        print(f"  Exceptional -- Revenue ${exc_rev:>12,.0f}   Rewards ${exc_rewards:>12,.0f} ({exc_pct:6.1%} of revenue)   CP ${exc_cp:>12,.0f}")
        print(f"  Poor        -- Revenue ${poor_rev:>12,.0f}   Rewards ${poor_rewards:>12,.0f} ({poor_pct:6.1%} of revenue)   CP ${poor_cp:>12,.0f}")
        print(f"  Exceptional pays {exc_pct / poor_pct:.1f}x Poor's rewards-rate-of-revenue burden" if poor_pct else "  n/a")
    result = pd.DataFrame(rows)
    result.to_csv(OUT_DIR / "csv" / "exceptional_fico_hand_derivation.csv", index=False)
    print(f"\nWrote {OUT_DIR / 'csv' / 'exceptional_fico_hand_derivation.csv'}")
    return result


# ---------------------------------------------------------------------------
# 2. Systematic outlier scan
# ---------------------------------------------------------------------------

def recompute_cp_per_account(df):
    """Undiscounted 12Q cumulative CP/Account per cohort -- same method as
    core_engine/07_audit.py's check_e_ltv_sanity (independently re-derived here too,
    not imported, per this file's own independence discipline)."""
    cp_raw = df[df["Bucket"].isin(["Gross Revenue", "Cost of Sales", "Operating Expense"])]
    cp_raw = cp_raw.groupby(["Merchant", "Vintage Index", "FICO Bucket", "QSB"])["Value"].sum().rename("CP").reset_index()
    na = df[(df["Line Item"] == "New Accounts") & (df["QSB"] == 0)].groupby(
        ["Merchant", "Vintage Index", "FICO Bucket"]
    )["Value"].sum().rename("NA")
    cp_raw = cp_raw.merge(na, on=["Merchant", "Vintage Index", "FICO Bucket"])
    cp_raw["CP per Account"] = cp_raw["CP"] / cp_raw["NA"]
    global_curve = cp_raw.groupby("QSB").apply(lambda g: g["CP"].sum() / g["NA"].sum()).sort_index()

    records = []
    for (merchant, vintage_idx, fico), sub in cp_raw.groupby(["Merchant", "Vintage Index", "FICO Bucket"]):
        series = sub.set_index("QSB")["CP per Account"].sort_index()
        for qsb in range(0, 12):
            if qsb not in series.index:
                series.loc[qsb] = global_curve.get(qsb, global_curve.iloc[-1])
        series = series.sort_index().loc[0:11]
        records.append(dict(merchant=merchant, vintage_idx=vintage_idx, fico=fico, cp_per_account_12q=float(series.sum())))
    return pd.DataFrame(records)


def z_score_outliers(series, threshold=2.5):
    mu, sigma = series.mean(), series.std()
    if sigma == 0 or np.isnan(sigma):
        return pd.Series(False, index=series.index)
    z = (series - mu) / sigma
    return z.abs() > threshold


def run_outlier_scan(df):
    print("\n" + "=" * 78)
    print("2. SYSTEMATIC OUTLIER SCAN")
    print("=" * 78)

    # (a) Cohort-level CP/Account, z-score WITHIN each FICO tier (not
    # pooled across tiers -- Exceptional/Poor genuinely have different
    # central tendencies by design, so a global z-score would just
    # re-flag every Exceptional cohort as "outlying" relative to Poor and
    # tell us nothing new. Within-tier is the right question: are there
    # outliers even among Exceptional-tier cohorts themselves?).
    ltv = recompute_cp_per_account(df)
    print("\n(a) Cohort-level 12Q undiscounted CP/Account, z-score WITHIN each FICO tier:")
    any_outliers = False
    for fico in FICO_ORDER:
        sub = ltv[ltv["fico"] == fico]
        mask = z_score_outliers(sub["cp_per_account_12q"])
        n_out = int(mask.sum())
        print(f"  {fico:24s}  n={len(sub):3d}  mean=${sub['cp_per_account_12q'].mean():>9,.0f}  "
              f"std=${sub['cp_per_account_12q'].std():>9,.0f}  outliers(|z|>2.5): {n_out}")
        if n_out:
            any_outliers = True
            for _, r in sub[mask].iterrows():
                print(f"      OUTLIER: {r['merchant']}, Vintage {r['vintage_idx']}: ${r['cp_per_account_12q']:,.0f}")
    if not any_outliers:
        print("  -> No within-tier CP/Account outliers found at |z|>2.5 in any FICO tier.")
        print("     Outliers do NOT disproportionately cluster in Exceptional beyond its own")
        print("     tier's normal spread -- the Exceptional finding is a shift in central")
        print("     tendency for that tier, not a few outlying cohorts driving the average.")

    # (b) Rewards rate curve itself, z-score WITHIN each (Merchant, Grain
    # FICO) series across QSB -- catches a single bad observation
    # inflating/deflating an otherwise-smooth curve.
    rates = pd.read_csv(OUT_DIR / "csv" / "curve_rate_curves.csv")
    rewards = rates[rates["Line Item"] == "Rewards"]
    print("\n(b) Rewards rate curve, z-score WITHIN each (Merchant, Grain FICO) series across QSB:")
    rate_outliers = []
    for (merchant, fico), sub in rewards.groupby(["Merchant", "Grain FICO"]):
        if len(sub) < 4:
            continue  # too few points for a z-score to mean anything
        mask = z_score_outliers(sub["rate"])
        if mask.any():
            rate_outliers.append((merchant, fico, sub[mask]))
    if rate_outliers:
        for merchant, fico, hits in rate_outliers:
            for _, r in hits.iterrows():
                print(f"  OUTLIER: {merchant} / {fico}, QSB {r['QSB']}: rate={r['rate']:.4f}")
    else:
        print("  -> No single-QSB outliers found in any merchant/FICO Rewards rate series.")
        print("     The elevated Exceptional-tier rate is a level shift across the whole")
        print("     curve, not one anomalous quarter distorting an average.")


# ---------------------------------------------------------------------------
# 3. Rewards-rate assumption sanity check
# ---------------------------------------------------------------------------

def run_rewards_sanity_check(df):
    print("\n" + "=" * 78)
    print("3. REWARDS-RATE ASSUMPTION SANITY CHECK")
    print("=" * 78)

    # (a) Classification check -- confirm Rewards is NOT a
    # Partner-Signing-Bonus-style Category/Model-Role mismatch.
    cls = pd.read_csv(DATA_DIR / "line_item_classification.csv")
    rewards_row = cls[cls["Line Item"] == "Rewards"].iloc[0]
    print(f"\n(a) Classification: Family={rewards_row['Family']!r}, Category={rewards_row['Category']!r}, "
          f"Model Role={rewards_row['Model Role']!r}")
    ok = (rewards_row["Family"] == "Expense" and rewards_row["Category"] == "Rewards"
          and rewards_row["Model Role"] == "Rate-Derived")
    print("  -> Model Role is Rate-Derived (not Acquisition-Cost), Category is 'Rewards' (routes to Cost of "
          "Sales via pnl_utils.py), consistent with the case brief's own 'Rewards ... Cost of Sales per brief' "
          "note in the classification file." if ok else "  -> UNEXPECTED classification, investigate.")

    # (b) Coverage/thinness check: which merchants actually HAVE an
    # Exceptional-tier-SPECIFIC Rewards rate curve, vs. a pooled fallback
    # that collapses all FICO tiers to one blended rate.
    rates = pd.read_csv(OUT_DIR / "csv" / "curve_rate_curves.csv")
    rewards = rates[rates["Line Item"] == "Rewards"]
    pooled_merchants = set(pd.read_csv(OUT_DIR / "csv" / "pooled_merchants.csv")["pooled_merchant"])
    print(f"\n(b) FICO-tier specificity of the Rewards rate curve, by merchant:")
    print(f"    Pooled (thin-history, Grain FICO collapsed to 'ALL'): {sorted(pooled_merchants)}")
    for m in sorted(rewards["Merchant"].unique(), key=lambda x: int(x.split()[-1])):
        sub = rewards[rewards["Merchant"] == m]
        grains = sorted(sub["Grain FICO"].unique())
        n_obs = len(sub[sub["Grain FICO"] == EXCEPTIONAL]) if EXCEPTIONAL in grains else 0
        tag = "POOLED -- single rate applied to ALL FICO tiers, no Exceptional-specific rate" if grains == ["ALL"] else \
              f"FICO-specific, {n_obs} Exceptional-tier QSB observations"
        print(f"    {m:12s} {tag}")
    if pooled_merchants:
        print(f"\n  -> {len(pooled_merchants)} merchant(s) ({', '.join(sorted(pooled_merchants))}) use a single "
              "blended Rewards rate across ALL FICO tiers (thin-history pooling, see core_engine/03_curve_library.py's "
              "POOL_THRESHOLD). For these merchants, the Exceptional-FICO 'rewards-heavy' rate premium is NOT "
              "modeled -- Exceptional customers there are assumed to pay the same rewards rate as every other "
              "tier. Whatever FICO-tier variation shows up in their forecast LTV/CAC comes only from differing "
              "volume drivers (NTV, Active Accounts) by tier, not from a differentiated rate. This means the "
              "portfolio-wide Exceptional-FICO finding is driven entirely by the FICO-specific merchants; the "
              "pooled merchants dilute rather than reinforce it -- worth stating explicitly, not implying the "
              "finding holds uniformly across all 10 merchants.")

    # (c) Stability of the "held flat" rate: compare the last-observed
    # Exceptional-tier rate against the trailing few quarters, per merchant
    # with a FICO-specific curve, to see if the flat-forward value is a
    # stable plateau or a noisy single point.
    print(f"\n(c) Stability of the Exceptional-tier rate being held flat into the forecast:")
    fico_specific = [m for m in rewards["Merchant"].unique() if m not in pooled_merchants]
    for m in sorted(fico_specific, key=lambda x: int(x.split()[-1])):
        sub = rewards[(rewards["Merchant"] == m) & (rewards["Grain FICO"] == EXCEPTIONAL)].sort_values("QSB")
        if sub.empty:
            continue
        last_val = sub["rate"].iloc[-1]
        trailing = sub["rate"].iloc[-4:] if len(sub) >= 4 else sub["rate"]
        pct_dev = (trailing.max() - trailing.min()) / abs(trailing.mean()) if trailing.mean() else float("nan")
        print(f"    {m:12s} last-observed rate={last_val: .4f} (this is what's held flat forward), "
              f"trailing {len(trailing)}Q range spread={pct_dev:.1%} of mean")


def main():
    df = load_combined()
    run_hand_derivations(df)
    run_outlier_scan(df)
    run_rewards_sanity_check(df)
    print("\n" + "=" * 78)
    print("Done. See output/exceptional_fico_hand_derivation.csv for the hand-derived table.")
    print("=" * 78)


if __name__ == "__main__":
    main()
