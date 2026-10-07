"""Parser for ICE Report 42 (Coffee 'C' certified warehouse stock report, .xls)."""
import re
from pathlib import Path

import pandas as pd

# Arabica stock categories as they appear in the final CSV (unit: bags)
CERTIFIED = "certified"                 # TOTAL BAGS CERTIFIED (already includes transition bags)
GRADING_PASSED = "grading_passed"       # daily flow
GRADING_FAILED = "grading_failed"       # daily flow
GRADING_PENDING = "grading_pending"     # snapshot
FLAGGED = "flagged_for_rebagging"       # snapshot
ARABICA_CATS = [CERTIFIED, GRADING_PASSED, GRADING_FAILED, GRADING_PENDING, FLAGGED]

# TRANSITION BAGS CERTIFIED is intentionally absent: it is a subset of certified.
SECTIONS = {
    "total bags certified": CERTIFIED,
    "bags passed grading": GRADING_PASSED,
    "bags failed grading": GRADING_FAILED,
    "pending grading report": GRADING_PENDING,
    "flagged for rebagging": FLAGGED,
}
NO_BAGS_TEXT = {
    GRADING_PASSED: "no bags passed today",
    GRADING_FAILED: "no bags failed today",
}
FILE_RE = re.compile(r"(\d{8})")


def _num(x) -> int:
    """'3,23,264' / 1234.0 / NaN -> int (Indian digit grouping handled by stripping commas)."""
    if pd.isna(x):
        return 0
    s = str(x).replace(",", "").strip()
    return int(float(s)) if s else 0


def arabica_report_date(path: Path) -> pd.Timestamp:
    m = FILE_RE.search(path.stem)
    if not m:
        raise ValueError(f"{path.name}: no YYYYMMDD in file name")
    return pd.to_datetime(m.group(1), format="%Y%m%d")


def parse_arabica(path: Path):
    """Return (cells, totals, as_of) for one report file.

    cells:  origin, port_code, stock_category, quantity  (only cells present in the report)
    totals: the report's own totals, used for reconciliation:
            stock_category, dimension, name, reported_total where dimension is
            'port'     -> 'Total in Bags' row, one value per port code
            'origin'   -> 'Total' column, one value per origin
            'category' -> grand total of the block (name 'ALL'); also 0 for a passed/failed
                          block the report explicitly says is empty
    """
    raw = pd.read_excel(path, header=None, dtype=object)
    n, ncols = raw.shape
    col0 = raw[0].astype(str).str.strip().where(raw[0].notna(), "")
    text = " ".join(col0).lower()

    m = re.search(r"as of:\s*([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{1,2}),\s*(\d{4})", " ".join(col0), re.I)
    if not m:
        raise ValueError(f"{path.name}: 'As of' date not found")
    as_of = pd.to_datetime(f"{m.group(1)} {m.group(2)}, {m.group(3)}", format="%b %d, %Y")

    cells, totals, found = [], [], set()
    for i in range(n):
        cat = SECTIONS.get(col0.iat[i].lower())
        if cat is None:
            continue
        # header row: empty first cell, port codes after it
        h = next((r for r in range(i + 1, min(i + 5, n))
                  if col0.iat[r] == "" and pd.notna(raw.iat[r, 1])), None)
        if h is None:
            continue  # title present but block empty
        found.add(cat)
        ports = {j: str(raw.iat[h, j]).strip() for j in range(1, ncols)
                 if pd.notna(raw.iat[h, j]) and str(raw.iat[h, j]).strip().lower() != "total"}
        total_col = next((j for j in range(1, ncols) if pd.notna(raw.iat[h, j])
                          and str(raw.iat[h, j]).strip().lower() == "total"), None)
        r = h + 1
        while r < n and col0.iat[r] != "":
            label = col0.iat[r]
            if label.lower().startswith("total"):
                totals += [(cat, "port", p, _num(raw.iat[r, j])) for j, p in ports.items()]
                if total_col is not None:
                    totals.append((cat, "category", "ALL", _num(raw.iat[r, total_col])))
                break
            cells += [(label, p, cat, _num(raw.iat[r, j])) for j, p in ports.items()
                      if pd.notna(raw.iat[r, j])]   # empty cells are not reported cells
            if total_col is not None:
                totals.append((cat, "origin", label, _num(raw.iat[r, total_col])))
            r += 1

    if CERTIFIED not in found:
        raise ValueError(f"{path.name}: certified block not found")
    for cat, phrase in NO_BAGS_TEXT.items():
        if cat not in found and phrase not in text:
            raise ValueError(f"{path.name}: {cat} block missing and no '{phrase}' text")
        if cat not in found:
            totals.append((cat, "category", "ALL", 0))  # report explicitly says: no bags

    cells = pd.DataFrame(cells, columns=["origin", "port_code", "stock_category", "quantity"])
    totals = pd.DataFrame(totals, columns=["stock_category", "dimension", "name", "reported_total"])
    return cells, totals, as_of