# Transformation – `transform.py`

## Purpose

`transform.py` converts the data produced by the Arabica and Robusta parsers into one **complete, consistent, analysis-ready DataFrame**.

The parsers keep the cells that are actually present in the reports. This file:

- creates the required combinations,
- fills missing expected quantities with `0`,
- maps ICE port codes to readable names,
- adds coffee type and unit,
- and combines Arabica and Robusta into one final structure.

---

## 1. Imports and Final Columns

The file uses **Pandas** for DataFrame operations.

It imports:

- `ARABICA_CATS` and `CERTIFIED` from `parse_arabica.py`
- `ROBUSTA_CATS` from `parse_robusta.py`
- `map_port` from `ports.py`

`ARABICA_CATS` and `ROBUSTA_CATS` provide the expected stock categories, while `CERTIFIED` is used as the reference structure for Arabica.

```text id="1z6k2y"
FINAL_COLS = [
    "report_date",
    "as_of_date",
    "coffee_type",
    "origin",
    "port_name",
    "stock_category",
    "quantity",
    "unit"
]
```

This defines the exact columns and order expected in the final dataset. `validate.py` also uses this same definition when checking the final CSV.

---

## 2. `_panel()` – Common Panel Builder

`_panel()` is used to build the Robusta panel.

It receives:

- `parsed` – parsed source data
- `combo_cols` – the dimensions used to form a combination, such as `port_code`
- `cats` – the expected stock categories

This makes the function reusable for creating a complete category grid.

### Duplicate check

The function creates a unique key:

```text
report_date + as_of_date + combination columns + stock_category
```

If the same key occurs more than once, it raises:

```text
duplicate cells in parsed data - a block was parsed twice
```

This prevents accidental double counting.

### Creating the complete grid

First, it gets the unique date/dimension combinations from the parsed data.

For Robusta this means:

```text
date + as_of_date + port
```

It then performs a **cross join** with all expected categories.

For example:

```text
AMS × valid_cert
AMS × non_tenderable
AMS × suspended
```

This creates every expected port/category combination.

The grid is then left-joined with the actual parsed values.

If a combination was not present in the source, its quantity is missing. The function changes that missing value to `0` and converts quantity to integer.

Finally, `map_port()` converts the ICE `port_code` into a readable `port_name`.

So `_panel()` follows this rule:

> **Every port present for a date gets every expected category; an unreported category is represented by quantity 0.**

---

## 3. `build_arabica_panel()` – Arabica Transformation

Arabica needs separate logic because its report contains both **origin and port**, and the different stock-category sections may not contain the same cells.

The input contains:

```text
report_date
as_of_date
origin
port_code
stock_category
quantity
```

### Duplicate check

An Arabica cell is uniquely identified by:

```text
report_date + as_of_date + origin + port_code + stock_category
```

Duplicate cells cause an error instead of being silently combined.

### Certified combinations

The function identifies all report dates and uses the `certified` category as the reference.

For each date, it gets the unique:

```text
origin × port
```

combinations from the certified block.

This is used because certified stock provides the main expected structure of Arabica stock for that date.

### Handling missing categories

The function checks these categories one by one:

```text
grading_passed
grading_failed
grading_pending
flagged_for_rebagging
```

`certified` is skipped because it is already the reference block.

For every other category, the code finds which report dates contain data for that category.

If a category has data on a date, its reported cells are kept **exactly as parsed**.

If the entire category block is missing for a date, the function creates zero rows using that date's certified `origin × port` combinations.

For example:

```text
Certified:
Brazil    | Antwerp
Brazil    | New Orleans
Colombia  | Antwerp
```

If `grading_failed` is completely missing for that date, it creates:

```text
Brazil    | Antwerp       | grading_failed | 0
Brazil    | New Orleans   | grading_failed | 0
Colombia  | Antwerp       | grading_failed | 0
```

This is different from replacing individual missing cells with zero. **Only a completely missing category block is zero-filled using the certified structure.**

The original parsed data and the newly created zero rows are then combined.

Quantity is converted to integer, ports are mapped to readable names, and the following metadata is added:

```text
coffee_type = Arabica
unit = bags
```

---

## 4. `build_robusta_panel()` – Robusta Transformation

Robusta contains:

```text
report_date
as_of_date
port_code
stock_category
quantity
```

There is no origin dimension.

The function calls `_panel()` with:

```text
port_code
```

and the three Robusta categories:

```text
valid_cert
non_tenderable
suspended
```

Therefore, for each report date, it creates:

```text
every port in that date's file
×
all three stock categories
```

Missing combinations receive quantity `0`.

The function then adds:

```text
coffee_type = Robusta
unit = lots
origin = blank
```

The blank origin is intentional because the Robusta source does not provide origin information.

An important point is that Robusta ports come from **each date's own file**. The transformation does not assume that every date has the same ports.

---

## 5. `combine()` – Creating the Final Dataset

`combine()` receives the completed Arabica and Robusta panels.

First, it removes inputs that are either:

- `None`, or
- empty DataFrames.

The remaining DataFrames are concatenated into one DataFrame.

Only `FINAL_COLS` are retained, ensuring both coffee types have exactly the same final structure.

The data is then sorted by:

1. `coffee_type`
2. `report_date`
3. `origin`
4. `port_name`
5. `stock_category`

`na_position="first"` places missing values first during sorting. This mainly affects Robusta because its `origin` is intentionally blank.

Finally, the index is reset so the consolidated DataFrame has a clean sequential index.

---

## 6. Overall Flow

```text
Parsed Arabica
      ↓
Check duplicates
      ↓
Use certified origin × port combinations
      ↓
Zero-fill completely missing category blocks
      ↓
Map port names
      ↓
Add Arabica / bags
      ↓
Arabica Panel


Parsed Robusta
      ↓
Check duplicates
      ↓
Create port × category grid
      ↓
Fill missing cells with 0
      ↓
Map port names
      ↓
Add Robusta / lots / blank origin
      ↓
Robusta Panel

        ↓
     combine()
        ↓
One consolidated DataFrame
        ↓
    validate.py
```


The resulting DataFrame is passed to `validate.py`, where its schema, duplicates, categories, quantities, date coverage, and reported totals are checked.