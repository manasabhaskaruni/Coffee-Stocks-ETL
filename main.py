"""ICE certified coffee stocks ETL.  Usage:  python main.py [--arabica-dir DIR] [--robusta-dir DIR]"""
import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from src.parse_arabica import arabica_report_date, parse_arabica
from src.parse_robusta import parse_robusta, robusta_report_date
from src.transform import build_arabica_panel, build_robusta_panel, combine
from src.validate import (add_window_args, collect_reported_totals, format_report,
                          run_checks, summarize, window_from_args)

log = logging.getLogger("etl")


def load_arabica(folder: Path):
    parsed, failures = [], []
    files = sorted(folder.glob("coffee_cert_stock_*.xls*"))
    for f in files:
        try:
            rd = arabica_report_date(f)
            cells, _, as_of = parse_arabica(f)
        except Exception as e:  # keep going; every bad file is reported at the end
            failures.append(f"{f.name}: {e}")
            continue
        parsed.append(cells.assign(report_date=rd, as_of_date=as_of))
    log.info("Arabica: %d/%d files parsed", len(parsed), len(files))
    panel = build_arabica_panel(pd.concat(parsed, ignore_index=True)) if parsed else None
    return panel, failures


def load_robusta(folder: Path):
    parsed, failures, seen = [], [], {}
    files = sorted(folder.glob("Stock_Report_RC_*.csv"))
    for f in files:
        try:
            rd = robusta_report_date(f)
            if rd in seen:
                raise ValueError(f"second file for {rd:%F} (already have {seen[rd]})")
            seen[rd] = f.name
            cells, _, as_of = parse_robusta(f, rd)
        except Exception as e:
            failures.append(f"{f.name}: {e}")
            continue
        parsed.append(cells.assign(report_date=rd, as_of_date=as_of))
    log.info("Robusta: %d/%d files parsed", len(parsed), len(files))
    panel = build_robusta_panel(pd.concat(parsed, ignore_index=True)) if parsed else None
    return panel, failures


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arabica-dir", type=Path, default=Path("data/arabica"))
    ap.add_argument("--robusta-dir", type=Path, default=Path("data/robusta"))
    ap.add_argument("--output", type=Path, default=Path("ice_certified_coffee_stocks.csv"))
    ap.add_argument("--force", action="store_true", help="write the CSV even if validation fails")
    add_window_args(ap)   # --days / --start / --end limit what is VALIDATED; the CSV always has all data
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    arabica, f1 = load_arabica(args.arabica_dir)
    robusta, f2 = load_robusta(args.robusta_dir)
    if arabica is None and robusta is None:
        log.error("no parsable input files found - download the raw reports first")
        return 1

    final = combine(arabica, robusta)
    results = run_checks(final, collect_reported_totals(args.arabica_dir, args.robusta_dir),
                         **window_from_args(args))
    for line in format_report(results):
        log.info(line)
    errors, warnings = summarize(results)
    errors = [f"unparsable file {m}" for m in f1 + f2] + errors
    for e in errors:
        log.error(e)
    if errors and not args.force:
        log.error("validation failed - CSV not written (use --force to override)")
        return 1
    final.to_csv(args.output, index=False, date_format="%Y-%m-%d")
    log.info("wrote %d rows to %s", len(final), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())