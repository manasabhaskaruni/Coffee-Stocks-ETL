"""Parser for ICE Report 173 (Robusta stock report CSV: Stock_Report_RC_YYYYMMDD_HHMMSS.csv)."""
import re
from pathlib import Path

import pandas as pd

# Source column -> category name in the final CSV (unit: lots)
ROBUSTA_COLUMNS = {
    "LotsWithValCert": "valid_cert",
    "LotsNonTend": "non_tenderable",
    "LotsSuspended": "suspended",
}
ROBUSTA_CATS = list(ROBUSTA_COLUMNS.values())

NAME_RE = re.compile(r"_(\d{8})_(\d{6})\.csv$", re.I)


def robusta_report_date(path: Path) -> pd.Timestamp:
    """Stock_Report_RC_YYYYMMDD_HHMMSS.csv -> report date."""
    m = NAME_RE.search(path.name)
    if not m:
        raise ValueError(f"{path.name}: file name does not match Stock_Report_RC_YYYYMMDD_HHMMSS.csv")
    return pd.to_datetime(m.group(1), format="%Y%m%d")


def _int(s) -> int:
    s = str(s).replace(",", "").strip()
    return int(float(s)) if s and s != "nan" else 0


def _parse_cutoff(series: pd.Series) -> pd.Series:
    s = series.str.strip()
    for fmt in ("%d-%b-%y", "%d-%b-%Y"):
        try:
            return pd.to_datetime(s, format=fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognised CutOffDate format: {sorted(s.unique())[:3]}")


def parse_robusta(path: Path, report_date):
    """Return (cells, grand_totals, as_of).

    cells: port_code, stock_category, quantity
    grand_totals: {stock_category: GrandTotal value}
    """
    df = pd.read_csv(path, sep=None, engine="python", dtype=str)
    df.columns = df.columns.str.strip()
    missing = {"Commodity", "CutOffDate", "PortId", *ROBUSTA_COLUMNS} - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}")

    is_total = df["Commodity"].fillna("").str.strip().eq("GrandTotal")
    if is_total.sum() != 1:
        raise ValueError(f"{path.name}: expected exactly one GrandTotal row")
    grand = {ROBUSTA_COLUMNS[c]: _int(df.loc[is_total, c].iloc[0]) for c in ROBUSTA_COLUMNS}

    body = df[~is_total].dropna(subset=["PortId"])
    as_of = _parse_cutoff(body["CutOffDate"]).unique()
    if len(as_of) != 1:
        raise ValueError(f"{path.name}: expected one CutOffDate, got {list(as_of)}")

    long = body.melt(id_vars=["PortId"], value_vars=list(ROBUSTA_COLUMNS),
                     var_name="stock_category", value_name="quantity")
    long["quantity"] = long["quantity"].map(_int)
    long["stock_category"] = long["stock_category"].map(ROBUSTA_COLUMNS)
    long["port_code"] = long["PortId"].str.strip()
    return long[["port_code", "stock_category", "quantity"]], grand, as_of[0]