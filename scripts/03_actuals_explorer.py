"""
03_actuals_explorer.py

THROWAWAY gut-check tool. Not a shipped deliverable. Produces a handful of
quick PNGs to your own eyeball before committing to curve/rate assumptions
in 04/05. Deliberately unpolished — spend under an hour here.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "output"
SCRATCH_DIR = OUT_DIR / "_scratch_explorer"
SCRATCH_DIR.mkdir(exist_ok=True)
CLEAN_PATH = OUT_DIR / "clean_actuals.parquet"


def load():
    return pd.read_parquet(CLEAN_PATH)


def plot_driver_by_merchant_over_time(df, line_item, fname):
    sub = df[df["Line Item"] == line_item].groupby(["Merchant", "Report Date Index"])["Value"].sum().unstack("Merchant")
    sub = sub.sort_index()
    fig, ax = plt.subplots(figsize=(9, 5))
    sub.plot(ax=ax)
    ax.set_title(f"{line_item} by Merchant over Report Date")
    ax.set_xlabel("Report Date Index (0 = Q1 2023)")
    fig.tight_layout()
    fig.savefig(SCRATCH_DIR / fname)
    plt.close(fig)


def plot_maturation_curve(df, line_item, merchant, fname):
    """Overlay each vintage's trajectory by QSB for one merchant/line item —
    the exact vintage-triangle-as-curves view that informs curve-fitting."""
    sub = df[(df["Line Item"] == line_item) & (df["Merchant"] == merchant)]
    sub = sub.groupby(["Vintage", "QSB"])["Value"].sum().unstack("Vintage")
    fig, ax = plt.subplots(figsize=(9, 5))
    sub.plot(ax=ax, marker="o", markersize=3)
    ax.set_title(f"{merchant}: {line_item} by QSB, one line per Vintage")
    ax.set_xlabel("Quarters Since Book")
    fig.tight_layout()
    fig.savefig(SCRATCH_DIR / fname)
    plt.close(fig)


def plot_rate_curve(df, numerator_item, denom_item, merchant, fname):
    """Rate = numerator / denominator by QSB, one line per vintage — checks
    whether a rate is genuinely flat (safe to hold flat in forecast) or still
    curving with vintage age (needs a maturation-adjusted rate)."""
    num = df[(df["Line Item"] == numerator_item) & (df["Merchant"] == merchant)].groupby(["Vintage", "QSB"])["Value"].sum()
    den = df[(df["Line Item"] == denom_item) & (df["Merchant"] == merchant)].groupby(["Vintage", "QSB"])["Value"].sum()
    rate = (num / den).unstack("Vintage")
    fig, ax = plt.subplots(figsize=(9, 5))
    rate.plot(ax=ax, marker="o", markersize=3)
    ax.set_title(f"{merchant}: {numerator_item} / {denom_item} by QSB")
    ax.set_xlabel("Quarters Since Book")
    fig.tight_layout()
    fig.savefig(SCRATCH_DIR / fname)
    plt.close(fig)


def main():
    df = load()

    # 1. Portfolio-level driver trends
    plot_driver_by_merchant_over_time(df, "New Accounts", "new_accounts_by_merchant.png")
    plot_driver_by_merchant_over_time(df, "Outstanding Balance", "outstanding_balance_by_merchant.png")
    plot_driver_by_merchant_over_time(df, "Net Transaction Volume", "ntv_by_merchant.png")

    # 2. Maturation curve shape check on the merchant with the most history
    plot_maturation_curve(df, "Outstanding Balance", "Merchant 1", "m1_outstanding_balance_by_qsb.png")
    plot_maturation_curve(df, "In-Month Active Accounts", "Merchant 1", "m1_active_accounts_by_qsb.png")

    # 3. Rate stability checks — do loss rate / yield actually flatten by QSB,
    # or keep curving? This determines whether "hold flat" is defensible.
    plot_rate_curve(df, "Charge Offs", "Outstanding Balance", "Merchant 1", "m1_loss_rate_by_qsb.png")
    plot_rate_curve(df, "Interest Revenue", "Revolve Balance", "Merchant 1", "m1_yield_by_qsb.png")

    print(f"Wrote gut-check charts -> {SCRATCH_DIR}")
    print("Review these before locking curve/rate assumptions in 04_curve_library.py.")


if __name__ == "__main__":
    main()
