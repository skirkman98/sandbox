"""
01_ingest_clean.py

Loads the raw case study data dump, applies the renames/derived fields agreed
in the build plan, joins the line item classification, and validates the
result. Produces a single clean parquet/csv that every downstream script
reads from — no other script should touch the raw CSV directly.

Renames:
    Booked Quarter   -> Vintage
    Quarter On Book  -> Report Date

Adds:
    Vintage Index / Report Date Index : integer quarter index (Q1 2023 = 0)
    Quarters Since Book (QSB)         : Report Date Index - Vintage Index
"""
import re
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUT_DIR.mkdir(exist_ok=True)

RAW_PATH = DATA_DIR / "case_study_data.csv"
CLASS_PATH = DATA_DIR / "line_item_classification.csv"
CLEAN_PATH = OUT_DIR / "clean_actuals.parquet"


def quarter_to_index(q: str) -> int:
    """'Q1 2023' -> 0, 'Q2 2023' -> 1, ... (Q1 2023 defined as period 0)."""
    m = re.match(r"Q(\d) (\d{4})", q.strip())
    if not m:
        raise ValueError(f"Unrecognized quarter format: {q!r}")
    qtr, year = int(m.group(1)), int(m.group(2))
    return (year - 2023) * 4 + (qtr - 1)


def parse_value(v) -> float:
    """Parse '$5,297,700', '(1,234)', '5,279', '12%' style strings into floats.
    Parenthesized values are negative (accounting convention); the brief also
    states cost line items are already stored as negative numbers directly,
    so this only needs to handle the parenthesis case defensively.
    """
    if pd.isna(v):
        return float("nan")
    s = str(v).strip()
    if s == "" or s == "-":
        # Accounting convention for zero (used e.g. where a one-time acquisition
        # cost or a charge-off simply doesn't apply at that QSB/grain).
        return 0.0
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = s.replace("$", "").replace(",", "").replace("%", "")
    try:
        f = float(s)
    except ValueError:
        raise ValueError(f"Could not parse value: {v!r}")
    return -f if neg else f


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(RAW_PATH, dtype=str)
    expected_cols = {"Merchant", "Booked Quarter", "Quarter On Book", "FICO Bucket", "Line Item", "Value"}
    missing = expected_cols - set(df.columns)
    if missing:
        raise ValueError(f"Raw data missing expected columns: {missing}")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={"Booked Quarter": "Vintage", "Quarter On Book": "Report Date"})

    df["Value"] = df["Value"].apply(parse_value)

    df["Vintage Index"] = df["Vintage"].apply(quarter_to_index)
    df["Report Date Index"] = df["Report Date"].apply(quarter_to_index)
    df["QSB"] = df["Report Date Index"] - df["Vintage Index"]

    if (df["QSB"] < 0).any():
        bad = df.loc[df["QSB"] < 0, ["Merchant", "Vintage", "Report Date"]].drop_duplicates()
        raise ValueError(f"Found Report Date before Vintage (impossible) in {len(bad)} cohort(s):\n{bad}")

    return df


def join_classification(df: pd.DataFrame) -> pd.DataFrame:
    cls = pd.read_csv(CLASS_PATH)
    merged = df.merge(cls, on="Line Item", how="left", validate="many_to_one")
    unclassified = merged.loc[merged["Model Role"].isna(), "Line Item"].unique()
    if len(unclassified):
        raise ValueError(f"Line items missing from classification file: {list(unclassified)}")
    return merged


def validate(df: pd.DataFrame) -> None:
    n_line_items = df["Line Item"].nunique()
    n_merchants = df["Merchant"].nunique()
    n_fico = df["FICO Bucket"].nunique()
    print(f"Rows: {len(df):,}")
    print(f"Merchants: {n_merchants} | FICO buckets: {n_fico} | Line items: {n_line_items}")
    vintage_min = df.loc[df["Vintage Index"].idxmin(), "Vintage"]
    vintage_max = df.loc[df["Vintage Index"].idxmax(), "Vintage"]
    rd_min = df.loc[df["Report Date Index"].idxmin(), "Report Date"]
    rd_max = df.loc[df["Report Date Index"].idxmax(), "Report Date"]
    print(f"Vintage range: {vintage_min} .. {vintage_max}")
    print(f"Report Date range: {rd_min} .. {rd_max}")
    print(f"QSB range: {df['QSB'].min()} .. {df['QSB'].max()}")

    assert n_line_items == 34, f"Expected 34 line items, found {n_line_items}"
    assert n_merchants == 10, f"Expected 10 merchants, found {n_merchants}"
    assert n_fico == 5, f"Expected 5 FICO buckets, found {n_fico}"

    dupe_keys = ["Merchant", "Vintage", "Report Date", "FICO Bucket", "Line Item"]
    dupes = df.duplicated(subset=dupe_keys, keep=False)
    if dupes.any():
        raise ValueError(f"Found {dupes.sum()} duplicate rows on key {dupe_keys}")

    if df["Value"].isna().any():
        n_nan = df["Value"].isna().sum()
        print(f"WARNING: {n_nan} rows have unparseable/missing Value — inspect before modeling.")


def main():
    raw = load_raw()
    df = clean(raw)
    df = join_classification(df)
    validate(df)
    df.to_parquet(CLEAN_PATH, index=False)
    print(f"\nWrote clean actuals -> {CLEAN_PATH}")


if __name__ == "__main__":
    main()
