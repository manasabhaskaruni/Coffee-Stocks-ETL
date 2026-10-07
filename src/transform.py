"""Build the zero-filled panels and the final consolidated DataFrame."""
import pandas as pd

from src.parse_arabica import ARABICA_CATS, CERTIFIED
from src.parse_robusta import ROBUSTA_CATS
from src.ports import map_port

FINAL_COLS = ["report_date", "as_of_date", "coffee_type", "origin",
              "port_name", "stock_category", "quantity", "unit"]


def _panel(parsed: pd.DataFrame, combo_cols: list, cats: list) -> pd.DataFrame:
    """Robusta: per date, every port in that file x every category; unreported cells are 0."""
    key = ["report_date", "as_of_date", *combo_cols, "stock_category"]
    if parsed.duplicated(key).any():
        raise ValueError("duplicate cells in parsed data - a block was parsed twice")
    combos = parsed[["report_date", "as_of_date", *combo_cols]].drop_duplicates()
    grid = combos.merge(pd.DataFrame({"stock_category": cats}), how="cross")
    out = grid.merge(parsed, how="left", on=key)
    out["quantity"] = out["quantity"].fillna(0).astype(int)
    out["port_name"] = out["port_code"].map(map_port)
    return out


def build_arabica_panel(parsed: pd.DataFrame) -> pd.DataFrame:
    """parsed: report_date, as_of_date, origin, port_code, stock_category, quantity
    (only the cells that appear in the reports).

    Rules, per report date:
      * certified:  every origin x port cell of the certified block.
      * passed / failed / pending / flagged_for_rebagging, block HAS data:
            exactly the cells that block lists (its origins x its header ports), as reported.
      * the same categories, block EMPTY or missing ("No Bags Passed Today", blank section):
            every origin x port combination of that date's certified block, with quantity 0.
    """
    key = ["report_date", "as_of_date", "origin", "port_code", "stock_category"]
    if parsed.duplicated(key).any():
        raise ValueError("duplicate cells in parsed data - a block was parsed twice")

    day = ["report_date", "as_of_date"]
    all_days = parsed[day].drop_duplicates()
    combos = (parsed[parsed.stock_category == CERTIFIED][day + ["origin", "port_code"]]
              .drop_duplicates())

    zero_blocks = []
    for cat in ARABICA_CATS:
        if cat == CERTIFIED:
            continue
        has_data = parsed.loc[parsed.stock_category == cat, day].drop_duplicates()
        empty_days = (all_days.merge(has_data, how="left", on=day, indicator=True)
                      .query("_merge == 'left_only'")[day])
        zero_blocks.append(empty_days.merge(combos, on=day)
                           .assign(stock_category=cat, quantity=0))

    out = pd.concat([parsed, *zero_blocks], ignore_index=True)
    out["quantity"] = out["quantity"].astype(int)
    out["port_name"] = out["port_code"].map(map_port)
    out["coffee_type"], out["unit"] = "Arabica", "bags"
    return out


def build_robusta_panel(parsed: pd.DataFrame) -> pd.DataFrame:
    """parsed: report_date, as_of_date, port_code, stock_category, quantity.
    Ports come from each date's own file."""
    out = _panel(parsed, ["port_code"], ROBUSTA_CATS)
    out["coffee_type"], out["unit"], out["origin"] = "Robusta", "lots", pd.NA
    return out


def combine(arabica, robusta) -> pd.DataFrame:
    frames = [f for f in (arabica, robusta) if f is not None and len(f)]
    df = pd.concat(frames, ignore_index=True)[FINAL_COLS]
    return (df.sort_values(["coffee_type", "report_date", "origin", "port_name", "stock_category"],
                           na_position="first")
              .reset_index(drop=True))