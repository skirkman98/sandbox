"""
core_engine/13_seasonality_analysis.py

Day-2 TODO item 1: the forecast engine indexes purely by QSB (cohort age) --
there's no calendar-quarter notion anywhere in the curve/rate library, so a
real Q4 holiday spend spike or Q1 paydown dip would either be invisible to
the model or partially confounded into the age-based curve shape. This
script tests whether that pattern actually exists and is material BEFORE any
implementation is attempted -- confirm first, design/build second, per the
TODO's own instruction.

Method:
  1. Detrend Net Transaction Volume (the primary Driver Basis for 7 of the
     16 Rate-Derived line items -- a signal found here propagates
     automatically without re-deriving it 7 times) by normalizing each
     cohort's own QSB series to its own QSB=0 value, then dividing by a
     pooled expected age-curve (cross-sectional, volume-weighted across all
     cohorts observed at that QSB) -- this leaves a residual that isolates
     "bigger/smaller than a same-age cohort would typically be," independent
     of both cohort size and cohort age.
  2. Collapse to ONE portfolio-wide average residual per actual calendar
     quarter (~14 points, Report Date Index 0-13) before grouping by
     quarter-of-year -- cohorts alive in the same calendar quarter are not
     independent trials (they'd all be hit by the same seasonal effect at
     once), so testing at the raw cohort-row level would be pseudo-replicated
     and overstate confidence. ~14 quarters / 4 quarters-of-year is an honest
     n≈3-4 per bucket.
  3. Materiality threshold set BEFORE looking at results (see MaterialITY_*
     constants below), to avoid post-hoc rationalizing a fit onto noise.
  4. Per-merchant breakdown (merchants with >= 8 actual quarters: 1-4) as a
     consistency check -- a real seasonal effect should show the same sign
     in most merchants with enough history to see it, not just emerge from
     pooling.

Diagnostic only -- does not modify the pipeline. If the signal is judged
material, core_engine/03_curve_library.py/core_engine/04_forecast_engine.py get a follow-up change;
if not, this is documented in BUILD_LOG.md as investigated-and-skipped.
"""
import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUT_DIR = BASE_DIR / "output"

# Decided BEFORE looking at results.
MATERIALITY_SWING = 0.07       # max-mean minus min-mean across quarter-of-year buckets, as a fraction
MATERIALITY_MIN_MERCHANT_AGREEMENT = 0.5  # >=50% of merchants with adequate history must agree in sign
MIN_MERCHANT_QUARTERS = 8      # "adequate history" cutoff for the per-merchant consistency check

QUARTER_LABELS = {0: "Q1", 1: "Q2", 2: "Q3", 3: "Q4"}


def load_ntv():
    df = pd.read_parquet(OUT_DIR / "parquet" / "clean_actuals_grained.parquet")
    return df[(df["Line Item"] == "Net Transaction Volume") & (df["Model Role"] == "Driver")].copy()


def cohort_level_series(ntv):
    """Sum NTV to (Merchant, Vintage Index, QSB) grain (collapsing FICO --
    seasonality is a calendar-quarter/portfolio-flow effect, not expected to
    be FICO-tier-specific, and collapsing avoids further thinning an already
    small sample)."""
    return ntv.groupby(["Merchant", "Vintage Index", "QSB"])["Value"].sum().reset_index()


def normalize_to_own_qsb0(cohort_series):
    """Index each cohort's own series to its own QSB=0 value (removes scale/
    cohort-size entirely, so a big and small cohort contribute comparably)."""
    qsb0 = cohort_series[cohort_series["QSB"] == 0].set_index(["Merchant", "Vintage Index"])["Value"].rename("qsb0_value")
    merged = cohort_series.merge(qsb0, on=["Merchant", "Vintage Index"], how="left")
    merged = merged[merged["qsb0_value"] > 0]
    merged["index_val"] = merged["Value"] / merged["qsb0_value"]
    return merged


def build_expected_age_curve(normalized):
    """Pooled expected age-curve: at each QSB, the qsb0-weighted average of
    the normalized index across every cohort observed at that QSB. This is
    the age-based curve the model already effectively assumes (no calendar
    notion) -- residuals against it isolate whatever ISN'T explained by age
    alone."""
    w = normalized.copy()
    w["weighted"] = w["index_val"] * w["qsb0_value"]
    grp = w.groupby("QSB").agg(weighted_sum=("weighted", "sum"), weight_sum=("qsb0_value", "sum"))
    grp["expected_index"] = grp["weighted_sum"] / grp["weight_sum"]
    return grp["expected_index"]


def compute_residuals(normalized, expected_curve):
    normalized = normalized.merge(expected_curve.rename("expected_index"), on="QSB", how="left")
    normalized = normalized[normalized["QSB"] > 0]  # QSB=0 residual is trivially 1.0 by construction, no info
    normalized["residual"] = normalized["index_val"] / normalized["expected_index"]
    normalized["Report Date Index"] = normalized["Vintage Index"] + normalized["QSB"]
    normalized["quarter_of_year"] = normalized["Report Date Index"] % 4
    return normalized


def run():
    print("=" * 78)
    print("SEASONALITY ANALYSIS -- Net Transaction Volume")
    print("=" * 78)

    ntv = load_ntv()
    cohort_series = cohort_level_series(ntv)
    normalized = normalize_to_own_qsb0(cohort_series)
    expected_curve = build_expected_age_curve(normalized)
    residuals = compute_residuals(normalized, expected_curve)

    print(f"\nPooled expected age-curve (QSB 1-{int(expected_curve.index.max())}), first few points:")
    print(expected_curve.head(6).round(3).to_string())

    # ---- Step 1: collapse to one portfolio-wide residual per calendar quarter
    print("\n" + "-" * 78)
    print("Portfolio-wide: one weighted-average residual per ACTUAL CALENDAR QUARTER")
    print("-" * 78)
    w = residuals.copy()
    w["weighted"] = w["residual"] * w["qsb0_value"]
    by_report_date = w.groupby("Report Date Index").agg(
        weighted_sum=("weighted", "sum"), weight_sum=("qsb0_value", "sum"), n_cohorts=("residual", "size")
    )
    by_report_date["avg_residual"] = by_report_date["weighted_sum"] / by_report_date["weight_sum"]
    by_report_date["quarter_of_year"] = by_report_date.index % 4
    print(by_report_date[["avg_residual", "n_cohorts", "quarter_of_year"]].round(4).to_string())
    print(f"\nn = {len(by_report_date)} independent calendar-quarter observations (this is the honest sample size,")
    print("not the underlying cohort-row count -- see this script's docstring on pseudo-replication.)")

    # ---- Step 2: group those points by quarter-of-year
    print("\n" + "-" * 78)
    print("Grouped by quarter-of-year (Q1/Q2/Q3/Q4)")
    print("-" * 78)
    by_qoy = by_report_date.groupby("quarter_of_year")["avg_residual"].agg(["mean", "std", "count"])
    by_qoy.index = by_qoy.index.map(QUARTER_LABELS)
    print(by_qoy.round(4).to_string())

    swing = by_qoy["mean"].max() - by_qoy["mean"].min()
    print(f"\nSwing (max quarter-of-year mean - min): {swing:.1%}  (materiality threshold: {MATERIALITY_SWING:.0%})")

    # ---- Step 3: per-merchant consistency check
    print("\n" + "-" * 78)
    print(f"Per-merchant consistency check (merchants with >= {MIN_MERCHANT_QUARTERS} actual quarters)")
    print("-" * 78)
    merchant_hist = ntv.groupby("Merchant")["Report Date Index"].nunique()
    eligible = sorted(merchant_hist[merchant_hist >= MIN_MERCHANT_QUARTERS].index, key=lambda m: int(m.split()[-1]))
    print(f"Eligible merchants: {eligible}")

    per_merchant_signal = {}
    for m in eligible:
        sub = residuals[residuals["Merchant"] == m].copy()
        sub["weighted"] = sub["residual"] * sub["qsb0_value"]
        by_rd = sub.groupby("Report Date Index").agg(weighted_sum=("weighted", "sum"), weight_sum=("qsb0_value", "sum"))
        by_rd["avg_residual"] = by_rd["weighted_sum"] / by_rd["weight_sum"]
        by_rd["quarter_of_year"] = by_rd.index % 4
        by_qoy_m = by_rd.groupby("quarter_of_year")["avg_residual"].mean()
        if len(by_qoy_m) < 2:
            continue
        # Which single quarter is highest for this merchant?
        peak_q = by_qoy_m.idxmax()
        per_merchant_signal[m] = QUARTER_LABELS[peak_q]
        print(f"  {m}: quarter-of-year means -> " +
              ", ".join(f"{QUARTER_LABELS[q]}={v:.3f}" for q, v in by_qoy_m.sort_index().items()) +
              f"   (peak: {QUARTER_LABELS[peak_q]})")

    if per_merchant_signal:
        from collections import Counter
        agreement = Counter(per_merchant_signal.values())
        top_q, top_n = agreement.most_common(1)[0]
        agreement_frac = top_n / len(per_merchant_signal)
        print(f"\nMost common peak quarter across merchants: {top_q} ({top_n}/{len(per_merchant_signal)} = {agreement_frac:.0%})")
    else:
        agreement_frac = 0.0
        top_q = None

    # ---- Verdict, applying the pre-committed threshold mechanically
    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    material = swing > MATERIALITY_SWING and agreement_frac >= MATERIALITY_MIN_MERCHANT_AGREEMENT
    if material:
        print(f"MATERIAL AND RELIABLE: swing {swing:.1%} > {MATERIALITY_SWING:.0%} threshold, and {agreement_frac:.0%} of "
              f"eligible merchants agree on peak quarter ({top_q}) >= {MATERIALITY_MIN_MERCHANT_AGREEMENT:.0%} agreement bar.")
    elif swing > MATERIALITY_SWING:
        print(f"DIRECTIONAL BUT NOT CONSISTENT: portfolio-wide swing ({swing:.1%}) clears the {MATERIALITY_SWING:.0%} "
              f"threshold, but per-merchant agreement ({agreement_frac:.0%}) falls short of the "
              f"{MATERIALITY_MIN_MERCHANT_AGREEMENT:.0%} bar -- looks more like noise/portfolio-composition effects "
              "than a real, shared calendar-quarter pattern.")
    else:
        print(f"NO MATERIAL SIGNAL: portfolio-wide swing ({swing:.1%}) does not clear the {MATERIALITY_SWING:.0%} "
              "threshold set before this analysis was run.")
    print(f"\n~4 years of actuals means at most ~3-4 independent calendar-quarter-of-year observations per bucket")
    print("(see the grouped table above) -- treat any verdict here as directionally informative, not statistically")
    print("conclusive, regardless of which way it comes out.")

    by_qoy.to_csv(OUT_DIR / "csv" / "seasonality_quarter_of_year_residuals.csv")
    print(f"\nWrote {OUT_DIR / 'csv' / 'seasonality_quarter_of_year_residuals.csv'}")
    return material, swing, by_qoy


if __name__ == "__main__":
    run()
