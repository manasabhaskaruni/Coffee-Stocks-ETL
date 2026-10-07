# Main Pipeline – `main.py`

## 1. Purpose

`main.py` is the **main entry point and controller** of the ICE Coffee Stocks ETL pipeline.

It connects all major stages:

```text
Raw ICE files
     ↓
Parsing
     ↓
Transformation
     ↓
Validation
     ↓
Final CSV
```

The detailed work is handled by other modules. `main.py` controls **when each stage runs, handles errors, and decides whether the final CSV should be written**.

---

## 2. Imports

`main.py` uses:

- `argparse` → command-line options
- `logging` → progress and error messages
- `Path` → file/folder paths
- `pandas` → combine parsed data
- `parse_arabica.py` → Arabica date extraction and parsing
- `parse_robusta.py` → Robusta date extraction and parsing
- `transform.py` → build panels and combine both coffee types
- `validate.py` → collect report totals and run quality checks

So `main.py` acts as the connection point between the modules.

---

## 3. `load_arabica()`

This function processes all Arabica raw reports.

### What it does

1. Finds files matching:

```text
coffee_cert_stock_*.xls*
```

2. Gets the report date from the filename using `arabica_report_date()`.
3. Sends each file to `parse_arabica()`.
4. Adds `report_date` and `as_of_date` to the parsed records.
5. If a file fails, its error is stored and processing continues.
6. Combines all successfully parsed files.
7. Sends them to `build_arabica_panel()` from `transform.py`.

### Why errors are collected

One bad daily report should not stop the entire year's data from being processed.

The function returns:

```text
Arabica panel + list of failed files
```

---

## 4. `load_robusta()`

This function performs the same overall process for Robusta.

It:

1. Finds `Stock_Report_RC_*.csv` files.
2. Extracts the report date using `robusta_report_date()`.
3. Checks that **only one Robusta file exists for each report date**.
4. Parses the file using `parse_robusta()`.
5. Adds `report_date` and `as_of_date`.
6. Records bad files and continues processing.
7. Combines successful files.
8. Builds the Robusta panel using `build_robusta_panel()`.

The duplicate-date check prevents two reports for the same day from being accidentally combined.

It returns:

```text
Robusta panel + list of failed files
```

---

# 5. `main()`

`main()` controls the complete ETL workflow.

### Step 1 – Read command-line options

The user can provide:

```text
--arabica-dir   → Arabica raw-data folder
--robusta-dir   → Robusta raw-data folder
--output        → final CSV location
--force         → write CSV even when errors exist
--days          → validate latest N days
--start/--end   → validate a specific date range
```

**Important:** `--days`, `--start`, and `--end` only control the **validation window**. They do not reduce the data processed or written to the final CSV.

---

### Step 2 – Load both datasets

```text
load_arabica()
load_robusta()
```

If neither coffee type produces any usable data, the pipeline stops because there is nothing to process.

---

### Step 3 – Combine the datasets

```python
final = combine(arabica, robusta)
```

`combine()` from `transform.py` creates one consolidated DataFrame containing both coffee types.

The final columns are:

```text
report_date
as_of_date
coffee_type
origin
port_name
stock_category
quantity
unit
```

---

### Step 4 – Collect original ICE totals

Before validation, `main.py` calls:

```python
collect_reported_totals()
```

This reads the raw reports again and collects the totals printed by ICE.

These become the **reference values** used to check whether the final CSV contains the correct quantities.

For example:

- Arabica → port, origin, and category totals
- Robusta → category `GrandTotal`

---

### Step 5 – Run validation

```python
run_checks(...)
```

The final DataFrame is checked for:

1. **Structure** – correct columns, data types, units, categories, nulls and quantities.
2. **Duplicates** – no duplicate date/coffee/origin/port/category combinations.
3. **Port totals** – mainly Arabica, because Arabica reports contain port totals.
4. **Origin totals** – Arabica only, because Robusta has no origin information.
5. **Category totals** – both Arabica and Robusta.
6. **Date coverage** – missing business days; this is a warning because holidays can explain missing dates.

Any files that could not be parsed are also treated as errors.

---

### Step 6 – Decide whether to write the CSV

By default:

```text
Validation errors
       ↓
CSV is NOT written
```

This prevents an invalid dataset from being presented as a successful output.

If the user intentionally wants the output despite errors:

```bash
python main.py --force
```

With `--force`, the CSV is written but the validation errors are still reported.

Warnings do not prevent the CSV from being written.

---

### Step 7 – Write final output

If the pipeline is allowed to write the result:

```python
final.to_csv(...)
```

The default output is:

```text
ice_certified_coffee_stocks.csv
```

The pandas index is not written, and dates are saved in:

```text
YYYY-MM-DD
```

format.

---

# 6. Error Handling

`main.py` handles errors at different levels:

| Situation | Behaviour |
|---|---|
| One raw file cannot be parsed | Record error and continue |
| Duplicate Robusta date | Record error |
| No usable Arabica and Robusta data | Stop pipeline |
| Validation warning | Report warning, continue |
| Validation error | Do not write CSV |
| `--force` used | Write CSV despite validation errors |

This makes the pipeline **fault-tolerant but still safe**.

---

# 7. Complete Connection Between Files

```text
extract_arabica.py ──→ data/arabica/
                              ↓
                       parse_arabica.py
                              ↓
                       transform.py
                              ↑
                       parse_robusta.py
                              ↑
extract_robusta.py ──→ data/robusta/
                              ↓
                       Combined DataFrame
                              ↓
                        validate.py
                              ↓
               ice_certified_coffee_stocks.csv
```


So the main responsibility of `main.py` is:

> **Parse → Transform → Validate → Decide → Write.**