# Validation – `validate.py`

## Purpose

`validate.py` performs automated **data-quality checks** on the final `ice_certified_coffee_stocks.csv`.

It checks both:

1. **Structure and consistency** of the final CSV.
2. **Numerical correctness** by comparing the CSV totals with totals printed in the original ICE reports.

There are **six checks**. Errors cause the validation to fail, while missing business days are reported as warnings because public holidays can explain them.

The file can also be run independently:

```text
python -m src.validate
python -m src.validate --days 30
python -m src.validate --start 2026-01-01 --end 2026-03-31
```

---

# 1. Important Constants

### `FINAL_COLS`

Imported from `transform.py`. It defines the required final columns:

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

### `KEY`

```text
report_date + coffee_type + origin + port_name + stock_category
```

This identifies one unique stock record.

For Robusta, `origin` is blank, but the blank value still forms part of the key.

### `EXPECTED_UNIT`

```text
Arabica → bags
Robusta → lots
```

### `EXPECTED_CATS`

Contains the expected categories for each coffee type:

```text
Arabica:
certified
grading_passed
grading_failed
grading_pending
flagged_for_rebagging

Robusta:
valid_cert
non_tenderable
suspended
```

### `MAX_LINES_PER_CHECK = 10`

If a check finds many problems, only the first 10 are printed. A message shows how many additional issues exist.

---

# 2. Validation Window

The validation can run on the complete CSV or only a selected date range.

### `add_window_args()`

Adds:

- `--days` → validate the last N days up to the latest report date.
- `--start` → starting report date.
- `--end` → ending report date.

### `window_from_args()`

Prevents using `--days` together with `--start`/`--end`.

The user must choose either:

```text
--days
```

or:

```text
--start + --end
```

### `select_window()`

Filters both:

- the final CSV, and
- the original report totals

to the same date range.

For `--days N`, the latest report date in the CSV is used as the end date, and `N-1` days are subtracted to determine the start.

This ensures reconciliation compares the same period on both sides.

---

# 3. Collecting Original ICE Report Totals

## `collect_reported_totals()`

The reconciliation checks need the totals printed in the original ICE reports.

Therefore, the raw files are parsed again.

### Arabica

For every:

```text
coffee_cert_stock_*.xls*
```

file, the function:

- gets the report date from the filename,
- runs `parse_arabica()`,
- gets its `totals`,
- labels them as `Arabica`.

Arabica provides three types of source totals:

1. **Port total** → from the report's `Total in Bags` row.
2. **Origin total** → from the `Total` column.
3. **Category total** → total for the complete category block.

### Robusta

For every:

```text
Stock_Report_RC_*.csv
```

file, the function:

- gets the report date from the filename,
- runs `parse_robusta()`,
- gets its `GrandTotal` values,
- converts them into category totals.

Robusta only provides **category totals** for reconciliation because its source report does not provide the same Arabica-style port and origin totals.

### Unreadable raw files

If a raw file cannot be parsed, it is skipped while collecting totals. `main.py`/the validation result can therefore still identify missing source totals through the later checks.

Finally, Arabica port codes are converted to the same readable names used in the final CSV using `map_port()`.

---

# 4. The Six Checks

## Check 1 – `check_structure()`

This checks whether the final CSV has the correct **basic structure and valid values**.

It checks:

### Schema

The columns must exactly match `FINAL_COLS`, including their order.

### Null values

These columns cannot contain nulls:

```text
report_date
as_of_date
coffee_type
port_name
stock_category
quantity
unit
```

`origin` is intentionally not included because:

- Arabica must have an origin.
- Robusta intentionally has a blank origin.

### Quantity

`quantity` must:

- be an integer column,
- never be negative.

### Coffee type

Only:

```text
Arabica
Robusta
```

are allowed.

### Stock categories

Each coffee type must use only its expected categories.

### Units

- Arabica must use `bags`.
- Robusta must use `lots`.

### Origin rule

- Arabica → origin cannot be missing.
- Robusta → origin must be blank.

### Categories per date

For every coffee type and report date, all expected categories must be present.

So this catches a date where, for example, Arabica has only 4 of its required 5 categories.

**This is an error check because later validation assumes the final structure is valid.**

---

## Check 2 – `check_no_duplicate_keys()`

This checks that there is only one row for each:

```text
report_date
+ coffee_type
+ origin
+ port_name
+ stock_category
```

A duplicate means the same stock cell appears more than once.

For example:

```text
2026-10-01 | Arabica | Brazil | Antwerp | certified
```

should occur only once.

If duplicates exist, the check returns the number of duplicate rows.

This is an **error** because duplicates could cause stock quantities to be counted twice.

---

# 5. Reconciliation Checks

The next three checks compare the final CSV with the totals from the original ICE reports.

The common helper `_reconcile()` performs the actual comparison.

It:

1. Selects the required type of source total.
2. Sums the `quantity` in the final CSV at the same level.
3. Matches the calculated CSV total with the source report total.
4. Reports any difference.

A missing CSV value is treated as `0` before comparison.

The comparison uses:

```text
coffee_type + report_date + stock_category
```

and, when required, also port or origin.

This prevents Arabica and Robusta values from being mixed together.

---

## Check 3 – `check_port_totals_match_report()`

### What it checks

For each:

```text
date + stock category + port
```

it compares:

**CSV quantity total**

against:

**Arabica report's `Total in Bags` value for that port.**

### Why only Arabica?

The Arabica report provides port-level totals.

The Robusta parser only extracts `GrandTotal` values at category level, so there is no equivalent Robusta port total available to compare.

Therefore, this check effectively applies to **Arabica**.

Example:

```text
Arabica | 2026-10-01 | certified | Antwerp
CSV total     = 25,000
Report total  = 25,000
```

Passes.

If they differ, it is an error.

---

## Check 4 – `check_origin_totals_match_report()`

### What it checks

For each:

```text
date + stock category + origin
```

it compares:

**CSV quantity total**

against:

**Arabica report's `Total` column for that origin.**

### Why only Arabica?

Arabica reports stock by origin.

Robusta does not have an origin dimension, so its `origin` is intentionally blank.

Therefore, this check applies to **Arabica only**.

Example:

```text
Arabica | 2026-10-01 | certified | Brazil
CSV total     = 100,000
Report total  = 100,000
```

Passes.

A difference indicates that the final data does not reconcile with the source origin total.

---

## Check 5 – `check_category_totals_match_report()`

### What it checks

For each:

```text
date + coffee type + stock category
```

it sums all quantities in the final CSV and compares the result with the source report's category total.

### Arabica

It compares against the total of the corresponding Arabica report block.

### Robusta

It compares against the `GrandTotal` value from the Robusta report.

Therefore, **this check applies to both Arabica and Robusta**.

Example:

```text
Robusta | 2026-10-01 | valid_cert
CSV total     = 500,000 lots
GrandTotal    = 500,000 lots
```

Passes.

### Additional missing-report safeguard

The check also compares the dates present in the CSV with dates for which source report totals were found.

If the CSV contains a date but no corresponding source totals were found, it reports:

```text
no report totals found for this date
```

This prevents a date from appearing to pass simply because there was no source total available to compare against.

---

# 6. Check 6 – `check_date_coverage()`

This checks whether there are missing **business days** between the earliest and latest report dates for each coffee type.

It uses Pandas business-day dates.

For example:

```text
Monday
Tuesday
Wednesday
Friday
```

would identify Thursday as missing.

However, this is only a **warning**, not an error.

The reason is that ICE reports may not exist on public holidays or other non-reporting days.

The message includes:

- number of missing business days,
- date range checked,
- up to the first 10 missing dates.

---

# 7. `CHECKS`

The six checks are stored together with their severity:

```text
Check                         Severity
------------------------------------------------
check_structure              error
check_no_duplicate_keys      error
check_port_totals...         error
check_origin_totals...       error
check_category_totals...     error
check_date_coverage          warning
```

An **error** means the CSV should fail validation.

A **warning** means the data can still be published, but the issue should be reviewed.

---

# 8. `run_checks()`

This is the main function that executes the checks.

It first applies the requested validation window.

If no data exists in the selected window, it returns an error.

For reconciliation checks, source report totals are required.

If they are unavailable, those checks are marked:

```text
SKIPPED
```

instead of falsely passing.

The checks run in order.

If the structure check fails, later checks are stopped because they depend on a valid structure.

Otherwise, all applicable checks continue.

Each result contains:

```text
name
severity
status
issues
```

where status can be:

```text
PASS
FAIL
WARN
SKIPPED
```

---

# 9. `summarize()`

Separates the results into two lists:

- errors
- warnings

Only failed checks contribute to the error list, and only warning checks contribute to the warning list.

This is used to determine the final exit status.

---

# 10. `format_report()`

Creates a readable validation report.

It prints each check with its status:

```text
[PASS   ] check_structure
[PASS   ] check_no_duplicate_keys
[FAIL   ] check_category_totals_match_report
```

Only the first 10 issues for a check are displayed.

If there are more, it prints how many additional issues were found.

---

# 11. `main()`

`main()` makes `validate.py` runnable from the command line.

Default files/directories are:

```text
CSV:
ice_certified_coffee_stocks.csv

Arabica:
data/arabica

Robusta:
data/robusta
```

It:

1. Reads the final CSV.
2. Parses `report_date` and `as_of_date` as dates.
3. Collects totals from the original reports.
4. Gets the requested validation window.
5. Runs all applicable checks.
6. Prints the validation report.
7. Prints the total number of errors and warnings.
8. Returns exit code `1` if there is any error, otherwise `0`.

Therefore:

```text
0 → validation successful
1 → validation failed
```

This allows the validation step to be used in an automated pipeline.

---

# 12. Overall Validation Flow

```text
Final CSV
   │
   ├── Structure check
   ├── Duplicate check
   │
   └── Compare with original ICE reports
          │
          ├── Arabica port totals
          ├── Arabica origin totals
          └── Arabica + Robusta category totals
          
   └── Business-day coverage warning
                │
                ▼
          PASS / FAIL / WARN
```

### In simple terms

The important design choice is that the validation does **not rely only on the final CSV**. The reconciliation checks go back to the original ICE reports and compare the final calculated totals with the source-reported totals. This gives an independent check that the extraction, parsing, and transformation did not change the numbers.