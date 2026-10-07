"""Automated data-quality checks (six checks, each a small named function).

Each check returns a list of problem descriptions (empty list = pass).
`run_checks` is used by main.py and also works standalone:

    python -m src.validate                              # whole CSV
    python -m src.validate --days 30                    # last 30 days up to the latest report
    python -m src.validate --start 2026-01-01 --end 2026-03-31

The reconciliation checks compare the CSV with the totals printed in the original ICE
reports, so the raw files are re-read to collect those totals.
"""
import argparse
import sys
from collections import namedtuple
from pathlib import Path

import pandas as pd

from src.parse_arabica import ARABICA_CATS, arabica_report_date, parse_arabica
from src.parse_robusta import ROBUSTA_CATS, parse_robusta, robusta_report_date
from src.ports import map_port
from src.transform import FINAL_COLS

CheckResult = namedtuple("CheckResult", "name severity status issues")

KEY = ["report_date", "coffee_type", "origin", "port_name", "stock_category"]
EXPECTED_UNIT = {"Arabica": "bags", "Robusta": "lots"}
EXPECTED_CATS = {"Arabica": ARABICA_CATS, "Robusta": ROBUSTA_CATS}
MAX_LINES_PER_CHECK = 10


# --------------------------------------------------------------------------------------
# Validation window
# --------------------------------------------------------------------------------------
def add_window_args(parser: argparse.ArgumentParser) -> None:
    """--days / --start / --end, shared by main.py and the standalone command."""
    g = parser.add_argument_group("validation window (default: all data in the CSV)")
    g.add_argument("--days", type=int, help="validate only the last N days up to the latest report date")
    g.add_argument("--start", help="validate from this report date (YYYY-MM-DD)")
    g.add_argument("--end", help="validate up to this report date (YYYY-MM-DD)")


def window_from_args(args) -> dict:
    if args.days is not None and (args.start or args.end):
        raise SystemExit("use either --days or --start/--end, not both")
    return {"days": args.days, "start": args.start, "end": args.end}


def select_window(df, reported, days=None, start=None, end=None):
    """Restrict the data and the report totals to a range of report dates."""
    if days is not None:
        end_ts = df["report_date"].max()
        start_ts = end_ts - pd.Timedelta(days=days - 1)
    else:
        start_ts = pd.Timestamp(start) if start else df["report_date"].min()
        end_ts = pd.Timestamp(end) if end else df["report_date"].max()
    df = df[(df["report_date"] >= start_ts) & (df["report_date"] <= end_ts)]
    if reported is not None and len(reported):
        reported = reported[(reported["report_date"] >= start_ts) & (reported["report_date"] <= end_ts)]
    return df, reported


# --------------------------------------------------------------------------------------
# Collecting the totals printed in the original reports
# --------------------------------------------------------------------------------------
def collect_reported_totals(arabica_dir, robusta_dir) -> pd.DataFrame:
    """Columns: coffee_type, report_date, stock_category, dimension, name, reported_total.

    Arabica: per port ('Total in Bags' row), per origin ('Total' column), per category.
    Robusta: per category (GrandTotal row). Unreadable files are skipped here; main.py
    reports them as parse errors.
    """
    frames = []
    for f in sorted(Path(arabica_dir).glob("coffee_cert_stock_*.xls*")):
        try:
            rd = arabica_report_date(f)
            _, totals, _ = parse_arabica(f)
        except Exception:
            continue
        frames.append(totals.assign(coffee_type="Arabica", report_date=rd))
    for f in sorted(Path(robusta_dir).glob("Stock_Report_RC_*.csv")):
        try:
            rd = robusta_report_date(f)
            _, grand, _ = parse_robusta(f, rd)
        except Exception:
            continue
        frames.append(pd.DataFrame(
            [(cat, "category", "ALL", v) for cat, v in grand.items()],
            columns=["stock_category", "dimension", "name", "reported_total"],
        ).assign(coffee_type="Robusta", report_date=rd))
    cols = ["coffee_type", "report_date", "stock_category", "dimension", "name", "reported_total"]
    if not frames:
        return pd.DataFrame(columns=cols)
    out = pd.concat(frames, ignore_index=True)[cols]
    is_port = out.dimension == "port"
    out.loc[is_port, "name"] = out.loc[is_port, "name"].map(map_port)
    return out.drop_duplicates(["coffee_type", "report_date", "stock_category", "dimension", "name"])


# --------------------------------------------------------------------------------------
# The six checks
# --------------------------------------------------------------------------------------
def check_structure(df):
    """1. Schema, nulls, integer non-negative quantity, units, allowed categories, origin
    rule, and that every date has all of its categories."""
    if list(df.columns) != FINAL_COLS:
        return [f"expected columns {FINAL_COLS}, got {list(df.columns)}"]
    issues = []
    for col in ["report_date", "as_of_date", "coffee_type", "port_name",
                "stock_category", "quantity", "unit"]:
        n = int(df[col].isna().sum())
        if n:
            issues.append(f"{n} null values in '{col}'")
    if not pd.api.types.is_integer_dtype(df["quantity"]):
        issues.append(f"quantity is not an integer column (dtype {df['quantity'].dtype})")
    elif (df["quantity"] < 0).any():
        issues.append(f"{int((df['quantity'] < 0).sum())} negative quantities")

    for coffee, g in df.groupby("coffee_type"):
        if coffee not in EXPECTED_CATS:
            issues.append(f"unexpected coffee_type '{coffee}'")
            continue
        bad = set(g["stock_category"]) - set(EXPECTED_CATS[coffee])
        if bad:
            issues.append(f"{coffee}: unexpected categories {sorted(bad)}")
        if (g["unit"] != EXPECTED_UNIT[coffee]).any():
            issues.append(f"{coffee}: unit is not '{EXPECTED_UNIT[coffee]}'")
        if coffee == "Arabica" and g["origin"].isna().any():
            issues.append("Arabica rows with missing origin")
        if coffee == "Robusta" and g["origin"].notna().any():
            issues.append("Robusta rows should have a blank origin")
        per_date = g.groupby("report_date")["stock_category"].nunique()
        short = per_date[per_date != len(EXPECTED_CATS[coffee])]
        issues += [f"{coffee} {d:%F}: only {n} of {len(EXPECTED_CATS[coffee])} categories present"
                   for d, n in short.items()]
    return issues


def check_no_duplicate_keys(df):
    """2. One row per date + coffee + origin + port + category (a blank origin counts as a value)."""
    n = int(df.duplicated(KEY).sum())
    return [f"{n} duplicate rows on {KEY}"] if n else []


def _reconcile(df, reported, dimension, column=None):
    """Compare CSV sums with the reported totals of one dimension (port/origin/category)."""
    rep = reported[reported.dimension == dimension]
    keys = ["coffee_type", "report_date", "stock_category"]
    if dimension == "category":
        got = df.groupby(keys)["quantity"].sum().rename("csv_total").reset_index()
        got["name"] = "ALL"
    else:
        got = (df.groupby(keys + [column])["quantity"].sum().rename("csv_total")
                 .reset_index().rename(columns={column: "name"}))
    m = rep.merge(got, how="left", on=keys + ["name"])
    m["csv_total"] = m["csv_total"].fillna(0).astype("int64")
    m["reported_total"] = m["reported_total"].astype("int64")
    bad = m[m.csv_total != m.reported_total]
    return [f"{r.coffee_type} {r.report_date:%F} {r.stock_category} {dimension} '{r.name}': "
            f"csv {r.csv_total} != report {r.reported_total}" for r in bad.itertuples()]


def check_port_totals_match_report(df, reported):
    """3. Per date + category + port: CSV total equals the report's 'Total in Bags' row (Arabica)."""
    return _reconcile(df, reported, "port", "port_name")


def check_origin_totals_match_report(df, reported):
    """4. Per date + category + origin: CSV total equals the report's 'Total' column (Arabica)."""
    return _reconcile(df, reported, "origin", "origin")


def check_category_totals_match_report(df, reported):
    """5. Per date + category: CSV total equals the report's grand total (Arabica block total,
    Robusta GrandTotal). Also flags CSV dates for which no source report total was found,
    so a date can never go unchecked silently."""
    issues = _reconcile(df, reported, "category")
    seen = set(map(tuple, reported[["coffee_type", "report_date"]].drop_duplicates().values))
    csv_dates = set(map(tuple, df[["coffee_type", "report_date"]].drop_duplicates().values))
    issues += [f"{c} {d:%F}: no report totals found for this date (raw file missing?)"
               for c, d in sorted(csv_dates - seen)]
    return issues


def check_date_coverage(df):
    """6. Time-series completeness: business days without a report inside the validated
    range (public holidays are expected, so this is a warning to review)."""
    issues = []
    for coffee, g in df.groupby("coffee_type"):
        have = set(g["report_date"])
        missing = [d for d in pd.bdate_range(min(have), max(have)) if d not in have]
        if missing:
            shown = ", ".join(f"{d:%F}" for d in missing[:10])
            issues.append(f"{coffee}: {len(missing)} business days without a report"
                          f" ({min(have):%F} to {max(have):%F}): {shown}"
                          f"{' ...' if len(missing) > 10 else ''}")
    return issues


# (function, severity, needs the reported totals)
#   error   -> blocks the CSV / non-zero exit code
#   warning -> published, but worth a look
CHECKS = [
    (check_structure,                     "error",   False),
    (check_no_duplicate_keys,             "error",   False),
    (check_port_totals_match_report,      "error",   True),
    (check_origin_totals_match_report,    "error",   True),
    (check_category_totals_match_report,  "error",   True),
    (check_date_coverage,                 "warning", False),
]


def run_checks(df, reported=None, days=None, start=None, end=None):
    """Run all checks on the chosen window (default: everything). `reported` comes from
    collect_reported_totals (or None, which skips the reconciliation checks)."""
    have_reported = reported is not None and len(reported) > 0
    df, reported = select_window(df, reported, days, start, end)
    if df.empty:
        return [CheckResult("select_window", "error", "FAIL", ["no data in the selected window"])]
    results = []
    for fn, severity, needs_reported in CHECKS:
        if needs_reported and not have_reported:
            results.append(CheckResult(fn.__name__, severity, "SKIPPED",
                                       ["no report totals available (raw files not found)"]))
            continue
        issues = fn(df, reported) if needs_reported else fn(df)
        status = "PASS" if not issues else ("FAIL" if severity == "error" else "WARN")
        results.append(CheckResult(fn.__name__, severity, status, issues))
        if fn is check_structure and issues:   # later checks assume a valid structure
            break
    return results


def summarize(results):
    """Flatten into (errors, warnings) message lists."""
    errors = [f"{r.name}: {m}" for r in results if r.status == "FAIL" for m in r.issues]
    warnings = [f"{r.name}: {m}" for r in results if r.status == "WARN" for m in r.issues]
    return errors, warnings


def format_report(results):
    lines = []
    for r in results:
        lines.append(f"[{r.status:<7}] {r.name}")
        for m in r.issues[:MAX_LINES_PER_CHECK]:
            lines.append(f"            - {m}")
        if len(r.issues) > MAX_LINES_PER_CHECK:
            lines.append(f"            ... and {len(r.issues) - MAX_LINES_PER_CHECK} more")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate a finished ICE coffee stocks CSV.")
    ap.add_argument("--csv", type=Path, default=Path("ice_certified_coffee_stocks.csv"))
    ap.add_argument("--arabica-dir", type=Path, default=Path("data/arabica"))
    ap.add_argument("--robusta-dir", type=Path, default=Path("data/robusta"))
    add_window_args(ap)
    args = ap.parse_args(argv)

    df = pd.read_csv(args.csv, parse_dates=["report_date", "as_of_date"])
    reported = collect_reported_totals(args.arabica_dir, args.robusta_dir)
    results = run_checks(df, reported, **window_from_args(args))
    print("\n".join(format_report(results)))
    errors, warnings = summarize(results)
    print(f"\n{len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())