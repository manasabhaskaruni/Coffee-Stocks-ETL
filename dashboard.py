"""Selection-driven dashboard for the ICE certified coffee stocks CSV.

    pip install dash plotly pandas
    python dashboard.py                              # reads ice_certified_coffee_stocks.csv
    python dashboard.py --csv other.csv --port 8060

What you see depends on what you pick:

  1. ONE DATE + category
        -> every port x origin combination reported on that date (table + heatmap).
  2. DATE RANGE + category (no port / origin picked)
        -> that category across the whole range (total, plus summary stats).
  3. DATE RANGE + category + port and/or origin
        -> only the picked port / origin / port+origin combination(s) across the range,
           with summary stats for each.

Notes on the data
  * A combination that a report does not list means "no bags", so it counts as 0.
  * Only days with an ICE report are used, so holidays are gaps, not zeros.
  * Categories are never added together (some are daily flows, some are stock levels).
"""
import argparse
import itertools
import sys

import pandas as pd

FLOW_CATS = ("grading_passed", "grading_failed")        # per report day
CAT_ORDER = ["certified", "grading_passed", "grading_failed", "grading_pending",
             "flagged_for_rebagging", "valid_cert", "non_tenderable", "suspended"]
NO_ORIGIN = "(not reported)"
ALL_LABEL = "All ports & origins"
DEFAULT_DAYS = 90

LABELS = {
    "certified": "Certified stock",
    "grading_passed": "Bags that passed grading",
    "grading_failed": "Bags that failed grading",
    "grading_pending": "Bags waiting for grading",
    "flagged_for_rebagging": "Bags flagged for rebagging",
    "valid_cert": "Valid certified stock",
    "non_tenderable": "Non-tenderable stock",
    "suspended": "Suspended stock",
}
EXPLAIN = {
    "certified": "Coffee sitting in ICE-approved warehouses, as shown in each daily report.",
    "grading_passed": "Bags that passed quality grading on each report day.",
    "grading_failed": "Bags that failed quality grading on each report day.",
    "grading_pending": "Bags still waiting to be graded, as of each report.",
    "flagged_for_rebagging": "Bags flagged for rebagging, as of each report.",
    "valid_cert": "Lots with a valid certificate, as of each report.",
    "non_tenderable": "Lots that cannot be tendered, as of each report.",
    "suspended": "Lots that are suspended, as of each report.",
}


# --------------------------------------------------------------------------------------
# Data preparation (pure pandas)
# --------------------------------------------------------------------------------------
def load_data(path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["report_date", "as_of_date"])
    df["origin"] = df["origin"].fillna(NO_ORIGIN)
    return df


def ordered_categories(d: pd.DataFrame) -> list:
    cats = d["stock_category"].unique()
    return sorted(cats, key=lambda c: CAT_ORDER.index(c) if c in CAT_ORDER else len(CAT_ORDER))


def has_origin(d: pd.DataFrame) -> bool:
    return bool((d["origin"] != NO_ORIGIN).any())


def report_dates(d, start, end) -> pd.DatetimeIndex:
    """Real report dates in [start, end] (independent of port/origin picks)."""
    x = d[(d.report_date >= start) & (d.report_date <= end)]
    return pd.DatetimeIndex(sorted(x["report_date"].unique()))


def combo_series(d, dates, category, ports=None, origins=None) -> pd.DataFrame:
    """date x group table of one category.

    Nothing picked          -> one column: everything added together.
    Ports and/or origins    -> one column per picked port / origin / port+origin combo.
    A picked combo with no rows still gets a column of zeros.
    """
    s = d[d.stock_category == category]
    if ports:
        s = s[s.port_name.isin(ports)]
    if origins:
        s = s[s.origin.isin(origins)]

    dims = [c for c, sel in (("port_name", ports), ("origin", origins)) if sel]
    if not dims:
        w = s.groupby("report_date")["quantity"].sum().to_frame(ALL_LABEL)
        return w.reindex(dates, fill_value=0).reindex(columns=[ALL_LABEL], fill_value=0)

    s = s.assign(group=[" | ".join(r) for r in s[dims].astype(str).itertuples(index=False)])
    w = s.pivot_table(index="report_date", columns="group", values="quantity",
                      aggfunc="sum", fill_value=0)
    expected = [" | ".join(c) for c in itertools.product(*[(ports if dim == "port_name" else origins)
                                                           for dim in dims])]
    return w.reindex(index=dates, columns=expected, fill_value=0)


def range_stats(w: pd.DataFrame, flow: bool) -> pd.DataFrame:
    """Summary numbers per group over the range."""
    rows = []
    for g in w.columns:
        s = w[g]
        if s.empty:
            continue
        row = {"Group": g}
        if flow:
            row.update({"Total in range": int(s.sum()), "Average per report": round(float(s.mean())),
                        "Highest day": int(s.max())})
        else:
            row.update({"First report": int(s.iloc[0]), "Latest report": int(s.iloc[-1]),
                        "Change": int(s.iloc[-1] - s.iloc[0]), "Lowest": int(s.min()),
                        "Highest": int(s.max())})
        row["Peak date"] = f"{s.idxmax():%d %b %Y}"
        rows.append(row)
    return pd.DataFrame(rows)


def date_combos(d, category, date) -> pd.DataFrame:
    """Every port x origin combination reported for one category on one date."""
    s = d[(d.stock_category == category) & (d.report_date == date)]
    return (s.groupby(["port_name", "origin"], as_index=False)["quantity"].sum()
             .sort_values("quantity", ascending=False).reset_index(drop=True))


def date_matrix(d, category, date) -> pd.DataFrame:
    """origin x port for one date; all-zero rows/columns removed."""
    s = d[(d.stock_category == category) & (d.report_date == date)]
    m = s.pivot_table(index="origin", columns="port_name", values="quantity",
                      aggfunc="sum", fill_value=0)
    return m.loc[(m != 0).any(axis=1), (m != 0).any(axis=0)]


def nearest_reports(dates, date):
    """(latest report on/before date, earliest report on/after date); None if absent."""
    before = [x for x in dates if x <= date]
    after = [x for x in dates if x >= date]
    return (max(before) if before else None), (min(after) if after else None)


# --------------------------------------------------------------------------------------
# Figures (plotly imported lazily)
# --------------------------------------------------------------------------------------
def empty_figure(message):
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.update_layout(xaxis={"visible": False}, yaxis={"visible": False}, height=250,
                      annotations=[{"text": message, "showarrow": False, "x": 0.5, "y": 0.5,
                                    "xref": "paper", "yref": "paper", "font": {"size": 15}}])
    return fig


def time_series_figure(w, flow, title, unit):
    import plotly.express as px
    if w.empty or w.shape[1] == 0:
        return empty_figure("No report days in this range")
    long = (w.rename_axis("report_date").reset_index()
             .melt(id_vars="report_date", var_name="group", value_name="value"))
    kw = dict(x="report_date", y="value", color="group", title=title,
              labels={"value": unit.capitalize(), "group": "", "report_date": "Report date"})
    if flow:
        fig = px.bar(long, barmode="group", **kw)
    else:
        fig = px.line(long, markers=len(w) <= 60, **kw)
    fig.update_layout(legend_title_text="", hovermode="x unified")
    return fig


def date_figure(m, title, unit):
    import plotly.express as px
    if m.empty:
        return empty_figure("No bags reported for this category on this date")
    if list(m.index) == [NO_ORIGIN]:                      # Robusta: ports only
        s = m.iloc[0]
        return px.bar(x=s.index, y=s.values, title=title,
                      labels={"x": "Port", "y": unit.capitalize()})
    return px.imshow(m, text_auto=True, aspect="auto", color_continuous_scale="Blues", title=title,
                     labels={"x": "Port", "y": "Origin", "color": unit.capitalize()})


# --------------------------------------------------------------------------------------
# Dash app
# --------------------------------------------------------------------------------------
def build_app(df: pd.DataFrame):
    from dash import Dash, Input, Output, dash_table, dcc, html
    from dash.exceptions import PreventUpdate

    app = Dash(__name__)
    coffees = sorted(df.coffee_type.unique())
    SHOW, HIDE = {"marginBottom": "16px"}, {"display": "none"}

    def control(label, component, box_id=None):
        props = {"id": box_id} if box_id else {}
        return html.Div([html.Label(label, style={"fontWeight": "600", "fontSize": "14px"}),
                         component], style=SHOW, **props)

    sidebar = html.Div([
        html.H3("ICE coffee stocks", style={"marginTop": 0}),
        control("1. Coffee", dcc.RadioItems(id="coffee", options=coffees, value=coffees[0], inline=True)),
        control("2. What do you want to see?", dcc.Dropdown(id="category", clearable=False)),
        control("3. One date or a range?", dcc.RadioItems(
            id="mode", value="range", inline=True,
            options=[{"label": "Date range", "value": "range"},
                     {"label": "One date", "value": "single"}])),
        html.Div(control("Date range", dcc.DatePickerRange(id="range", display_format="DD MMM YYYY")),
                 id="range_box"),
        html.Div(control("Date", dcc.DatePickerSingle(id="single", display_format="DD MMM YYYY")),
                 id="single_box"),
        html.Div([
            html.Div("Optional: narrow the range to some ports / origins. Pick both to see "
                     "port + origin combinations.",
                     style={"fontSize": "12px", "color": "#555", "marginBottom": "8px"}),
            control("Ports (empty = all)", dcc.Dropdown(id="ports", multi=True)),
            control("Origins (empty = all)", dcc.Dropdown(id="origins", multi=True), box_id="origin_box"),
        ], id="filter_box"),
    ], style={"width": "300px", "minWidth": "300px", "padding": "16px", "background": "#f5f6f8",
              "height": "100vh", "overflowY": "auto", "boxSizing": "border-box"})

    main = html.Div([
        html.Div(id="kpis", style={"fontWeight": "600", "fontSize": "15px", "marginBottom": "2px"}),
        html.Div(id="note", style={"color": "#555", "fontSize": "13px", "marginBottom": "8px"}),
        dcc.Graph(id="fig"),
        html.Div(id="table", style={"marginTop": "12px"}),
    ], style={"flex": "1", "padding": "16px", "height": "100vh", "overflowY": "auto"})

    app.layout = html.Div([sidebar, main],
                          style={"display": "flex", "fontFamily": "Arial, sans-serif"})

    # ---- reset controls when the coffee changes ---------------------------------------
    @app.callback(
        Output("category", "options"), Output("category", "value"),
        Output("ports", "options"), Output("ports", "value"),
        Output("origins", "options"), Output("origins", "value"),
        Output("origin_box", "style"),
        Output("range", "min_date_allowed"), Output("range", "max_date_allowed"),
        Output("range", "start_date"), Output("range", "end_date"),
        Output("single", "min_date_allowed"), Output("single", "max_date_allowed"),
        Output("single", "date"),
        Input("coffee", "value"))
    def on_coffee(coffee):
        d = df[df.coffee_type == coffee]
        cats = ordered_categories(d)
        lo, hi = d.report_date.min(), d.report_date.max()
        start = max(lo, hi - pd.Timedelta(days=DEFAULT_DAYS))
        return ([{"label": LABELS.get(c, c), "value": c} for c in cats], cats[0],
                sorted(d.port_name.unique()), [],
                sorted(set(d.origin) - {NO_ORIGIN}), [],
                SHOW if has_origin(d) else HIDE,
                lo.date(), hi.date(), start.date(), hi.date(),
                lo.date(), hi.date(), hi.date())

    # ---- show only the date picker that matches the mode -------------------------------
    @app.callback(
        Output("range_box", "style"), Output("single_box", "style"), Output("filter_box", "style"),
        Input("mode", "value"))
    def on_mode(mode):
        return (HIDE, {}, HIDE) if mode == "single" else ({}, HIDE, {})

    # ---- main view ---------------------------------------------------------------------
    @app.callback(
        Output("kpis", "children"), Output("note", "children"),
        Output("fig", "figure"), Output("table", "children"),
        Input("coffee", "value"), Input("category", "value"), Input("mode", "value"),
        Input("range", "start_date"), Input("range", "end_date"), Input("single", "date"),
        Input("ports", "value"), Input("origins", "value"))
    def update(coffee, category, mode, start, end, single, ports, origins):
        d = df[df.coffee_type == coffee]
        if not category or category not in set(d.stock_category):
            raise PreventUpdate                      # controls still refreshing after coffee change
        unit, name = d["unit"].iloc[0], LABELS.get(category, category)
        flow = category in FLOW_CATS
        note = EXPLAIN.get(category, "")

        def table(frame):
            if frame.empty:
                return ""
            return dash_table.DataTable(
                data=frame.to_dict("records"), columns=[{"name": c, "id": c} for c in frame.columns],
                page_size=15, sort_action="native",
                style_header={"fontWeight": "bold", "background": "#eef3fb"},
                style_cell={"padding": "6px", "fontFamily": "Arial", "fontSize": "13px",
                            "textAlign": "left"})

        # ---------- ONE DATE: all port x origin combos ----------
        if mode == "single":
            if not single:
                raise PreventUpdate
            date = pd.Timestamp(single)
            all_dates = sorted(d.report_date.unique())
            if date not in set(all_dates):
                before, after = nearest_reports(pd.DatetimeIndex(all_dates), date)
                hint = " / ".join(f"{lbl}: {x:%d %b %Y}" for lbl, x in
                                  (("previous report", before), ("next report", after)) if x is not None)
                return (f"No ICE report on {date:%d %b %Y}", f"Try another date. Nearest: {hint}",
                        empty_figure("No report on this date"), "")
            combos = date_combos(d, category, date)
            total = int(combos["quantity"].sum())
            kpis = (f"{name} on {date:%d %b %Y}  |  total: {total:,} {unit}  |  "
                    f"{len(combos)} port/origin combinations reported")
            note += " Combinations not listed in the report are 0."
            fig = date_figure(date_matrix(d, category, date),
                              f"{name}: port and origin on {date:%d %b %Y}", unit)
            show = combos.rename(columns={"port_name": "Port", "origin": "Origin",
                                          "quantity": unit.capitalize()})
            if not has_origin(d):
                show = show.drop(columns="Origin")
            return kpis, note, fig, table(show)

        # ---------- DATE RANGE: total, or picked port/origin combos ----------
        if not (start and end):
            raise PreventUpdate
        start, end = pd.Timestamp(start), pd.Timestamp(end)
        dates = report_dates(d, start, end)
        if len(dates) == 0:
            return ("No ICE reports in this range", note, empty_figure("No report days in this range"), "")
        w = combo_series(d, dates, category, ports, origins if has_origin(d) else None)
        what = ("all ports & origins" if list(w.columns) == [ALL_LABEL]
                else f"{len(w.columns)} selected group(s)")
        kpis = (f"{name}  |  {dates.min():%d %b %Y} to {dates.max():%d %b %Y}  |  "
                f"{len(dates)} reports  |  showing {what}")
        title = f"{name} ({unit})" + ("" if list(w.columns) == [ALL_LABEL] else ": selected combinations")
        return (kpis, note, time_series_figure(w, flow, title, unit), table(range_stats(w, flow)))

    return app


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="ice_certified_coffee_stocks.csv")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)
    build_app(load_data(args.csv)).run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())