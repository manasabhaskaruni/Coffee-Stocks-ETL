
# Data Parsing and Standardization

## 1. Overview

After the raw ICE reports have been downloaded, the next step is to read the reports and convert their contents into a structured format.

The Arabica and Robusta reports are not in the same format:

- Arabica reports are Excel (`.xls`) files and contain multiple sections for different stock categories, origins and ports.
- Robusta reports are CSV files and contain stock categories as separate columns, along with port information and a `GrandTotal` row.

Because of these differences, separate parsers are used:

- `parse_arabica.py` → processes ICE Report 42
- `parse_robusta.py` → processes ICE Report 173
- `ports.py` → converts ICE port codes into readable port names

The main purpose of the parsing stage is to take the source-specific report structures and turn them into clean, structured records that can later be combined into a common dataset.

The overall flow is:

```text
Raw ICE Reports
      │
      ├── Arabica .xls
      │       ↓
      │  parse_arabica.py
      │
      └── Robusta .csv
              ↓
        parse_robusta.py
              │
              ▼
        Structured data
              │
              ▼
           ports.py
              │
              ▼
       Standardized locations
              │
              ▼
         transform.py
```

---

# 2. Arabica Parser – `parse_arabica.py`

## 2.1 Purpose

`parse_arabica.py` is responsible for reading one Arabica ICE Report 42 Excel file and extracting the useful information from it.

The Arabica report is not a simple table.

It contains multiple sections, such as:

- Total Bags Certified
- Bags Passed Grading
- Bags Failed Grading
- Pending Grading Report
- Flagged for Rebagging

The parser identifies these sections and converts the information into structured rows.

It also extracts the totals shown by the original ICE report. These totals are important because they are later used by `validate.py` to check whether the final dataset still matches the original report.

---

# 2.2 Arabica stock categories

The parser defines five categories:

```text
certified
grading_passed
grading_failed
grading_pending
flagged_for_rebagging
```

These names are used consistently throughout the final dataset.

The corresponding sections in the ICE report are:

| ICE Report Section | Final Category |
|---|---|
| Total Bags Certified | `certified` |
| Bags Passed Grading | `grading_passed` |
| Bags Failed Grading | `grading_failed` |
| Pending Grading Report | `grading_pending` |
| Flagged for Rebagging | `flagged_for_rebagging` |

This mapping is stored in the `SECTIONS` dictionary.

This is useful because the source report uses human-readable section names, while the final dataset needs consistent machine-friendly category names.

---

# 2.3 Why Transition Bags Certified is not a separate category

The Arabica report also contains information about **Transition Bags Certified**.

However, this is intentionally not included as a separate stock category.

The reason is that transition bags are already included within **Total Bags Certified**.

If transition bags were added as another category, the same stock could be counted twice.

Therefore:

```text
Total Bags Certified
        │
        └── already includes Transition Bags Certified
```

The pipeline keeps only:

```text
certified
```

for this overall certified stock figure.

This is an important business decision in the parsing stage because it prevents double counting.

---

# 2.4 Converting quantities into numbers

The `_num()` function is used to convert values from the Excel report into integers.

ICE values may appear in formats such as:

```text
3,23,264
1234.0
blank
NaN
```

The function removes commas and converts the value into an integer.

For example:

```text
"3,23,264" → 323264
"1234.0"   → 1234
blank      → 0
NaN        → 0
```

The comma removal also handles the digit grouping used in the source report.

The result is always an integer quantity, which is important because stock quantities are later used for aggregation and validation.

---

# 2.5 Getting the report date

The `arabica_report_date()` function gets the report date from the filename.

The expected filename contains a date in `YYYYMMDD` format.

For example:

```text
coffee_cert_stock_20261001.xls
```

contains:

```text
20261001
```

which is converted to:

```text
2026-10-01
```

This date represents the date associated with the report file.

If a filename does not contain an eight-digit date, the parser raises an error rather than silently using an incorrect date.

---

# 2.6 Reading the Excel report

The `parse_arabica()` function reads the Excel file using pandas.

The report is read with:

```text
header=None
```

because the ICE report does not have a single standard header row at the top.

Instead, it contains titles, sections, headers, data rows and totals at different positions.

Therefore, the parser reads the sheet as raw cells first and then identifies the required information based on the report structure.

---

# 2.7 Finding the "As of" date

The report contains an `As of` date inside its content.

The parser searches the first column for text matching an `As of` date.

For example, if the report says:

```text
As of: October 1, 2026
```

the parser extracts:

```text
2026-10-01
```

This date is returned separately as `as_of`.

There are therefore two useful date concepts:

### Report date

The date obtained from the filename.

### As-of date

The date stated inside the report itself.

Keeping both dates is useful because they come from two different parts of the source and can be compared or used for analysis.

---

# 2.8 Finding the different report sections

The parser goes through the Excel rows and checks whether the text in the first column matches one of the known section names.

For example:

```text
Total Bags Certified
```

is mapped to:

```text
certified
```

Similarly:

```text
Bags Passed Grading
```

becomes:

```text
grading_passed
```

This allows the parser to identify where each stock category starts.

---

# 2.9 Finding the port headers

Once a section is found, the parser looks at the next few rows to identify the header containing the port codes.

For example, the report may contain:

```text
ANT   BAR   HA/BR   HOU   MIAMI   NOLA   NY   VA   Total
```

The parser identifies the individual port columns while treating `Total` separately.

The port codes are kept at this stage because they are later converted into readable names using `ports.py`.

---

# 2.10 Reading origin and port quantities

Inside an Arabica section, the report generally has:

```text
Origin | Port 1 | Port 2 | Port 3 | ... | Total
```

The parser reads each origin row and creates structured records for the cells that are actually present in the report.

For example, conceptually:

```text
Origin: Brazil
Port: Antwerp
Category: certified
Quantity: 10000
```

becomes one structured record.

Another cell might become:

```text
Origin: Brazil
Port: New York
Category: certified
Quantity: 5000
```

This continues for all origins, ports and categories found in the report.

---

# 2.11 Empty cells are not treated as reported cells

An important decision in the parser is that empty cells are not added to the `cells` output.

For example:

```text
Brazil | 1000 | blank | 500
```

does not create a row for the blank cell.

The parser records only the values that are actually present in the source report.

This distinction is important because **parsing and zero-filling are separate responsibilities**.

The parser represents what the source report actually contains.

Later, `transform.py` decides which missing combinations should be represented as zero in the final panel.

---

# 2.12 Collecting Arabica report totals

The parser does more than extract individual data cells.

It also extracts the totals already provided by the ICE report.

These totals are stored separately in the `totals` DataFrame.

There are three types of totals:

```text
port
origin
category
```

### Port totals

The `Total in Bags` row provides the total quantity for each port.

For example:

```text
Antwerp → 50,000
New York → 75,000
Miami   → 40,000
```

These values are later used by `validate.py` to independently check whether the final CSV contains the same totals.

### Origin totals

The `Total` column provides the total for each origin.

For example:

```text
Brazil     → 100,000
Colombia   → 50,000
Honduras   → 25,000
```

These are also retained for reconciliation.

### Category totals

The final total row of each block provides the overall total for that category.

For example:

```text
certified → 260,364
```

This becomes:

```text
dimension = category
name = ALL
reported_total = 260364
```

This allows the validation stage to compare the total quantity calculated from the final dataset against the total originally reported by ICE.

---

# 2.13 Handling missing Passed and Failed sections

There is a special case for:

```text
Bags Passed Grading
Bags Failed Grading
```

These are daily-flow categories.

Sometimes the report does not contain a normal data block for one of these categories. Instead, the report explicitly says something such as:

```text
No Bags Passed Today
```

or:

```text
No Bags Failed Today
```

The parser recognizes these messages.

If the corresponding block is missing but the report explicitly states that there were no bags, the parser records:

```text
reported total = 0
```

This is important.

There is a difference between:

> "The report says there were zero bags."

and:

> "The report information could not be found."

The parser only creates a zero when ICE explicitly indicates that no bags were reported.

If the block is missing and there is no corresponding "No Bags..." message, the parser raises an error instead.

This prevents an unexpected source-format change from silently becoming zero data.

---

# 2.14 Required Certified section

The `certified` section is treated as mandatory.

If the parser cannot find the Certified block, it raises an error.

This is because certified stock is the main information being collected from the Arabica report.

Failing early is safer than producing a partially populated dataset that appears valid.

---

# 2.15 Arabica parser output

The function returns three objects:

```text
cells
totals
as_of
```

### `cells`

Contains the actual source data cells:

```text
origin
port_code
stock_category
quantity
```

Example:

```text
Brazil | ANT | certified | 10000
Brazil | NY  | certified | 5000
Colombia | ANT | certified | 7000
```

### `totals`

Contains totals directly reported by ICE:

```text
stock_category
dimension
name
reported_total
```

For example:

```text
certified | port     | ANT      | 50000
certified | origin   | Brazil   | 100000
certified | category | ALL      | 260364
```

### `as_of`

Contains the date stated inside the report.

---

# 3. Robusta Parser – `parse_robusta.py`

## 3.1 Purpose

`parse_robusta.py` processes the CSV reports collected from ICE Report 173.

The Robusta report has a different structure from Arabica.

Instead of having separate sections for each category, the Robusta CSV contains stock categories as individual columns.

The parser converts these columns into rows so that the data can be handled in a common structure later.

---

# 3.2 Robusta source categories

The source contains these columns:

```text
LotsWithValCert
LotsNonTend
LotsSuspended
```

These are mapped to the final category names:

| Source Column | Final Category |
|---|---|
| `LotsWithValCert` | `valid_cert` |
| `LotsNonTend` | `non_tenderable` |
| `LotsSuspended` | `suspended` |

The mapping is stored in `ROBUSTA_COLUMNS`.

The final category list is:

```text
valid_cert
non_tenderable
suspended
```

The unit for Robusta is later set to **lots**.

---

# 3.3 Getting the Robusta report date

Robusta filenames follow this pattern:

```text
Stock_Report_RC_YYYYMMDD_HHMMSS.csv
```

For example:

```text
Stock_Report_RC_20261001_153000.csv
```

The `robusta_report_date()` function extracts:

```text
20261001
```

and converts it into:

```text
2026-10-01
```

The time portion is not used as the report date.

The function also validates the filename pattern. If the filename does not follow the expected structure, an error is raised.

---

# 3.4 Reading the CSV

The Robusta parser reads the CSV using pandas.

The parser uses automatic separator detection:

```text
sep=None
engine="python"
```

This makes the reading slightly more flexible if the exact CSV delimiter varies.

All columns are initially read as strings.

The column names are then stripped of unnecessary spaces.

---

# 3.5 Checking required columns

Before processing the data, the parser checks that the expected columns exist.

The required columns include:

```text
Commodity
CutOffDate
PortId
LotsWithValCert
LotsNonTend
LotsSuspended
```

If any required column is missing, the parser raises an error.

This prevents the parser from continuing with an incomplete or unexpectedly changed report.

---

# 3.6 Identifying the GrandTotal row

The Robusta report contains a special row where:

```text
Commodity = GrandTotal
```

The parser expects **exactly one** such row.

This row provides the overall quantity for each Robusta stock category.

For example:

```text
GrandTotal
LotsWithValCert → 12345
LotsNonTend     → 500
LotsSuspended   → 100
```

The parser extracts these values into a dictionary:

```text
valid_cert      → 12345
non_tenderable  → 500
suspended       → 100
```

These totals are later used by `validate.py` for category-level reconciliation.

This is the Robusta equivalent of using the category totals available in the Arabica report.

---

# 3.7 Removing the GrandTotal row from detailed data

The `GrandTotal` row is used for validation, but it is not treated as a normal port-level record.

Therefore, after extracting its values, the parser removes that row from the main body of the data.

The remaining rows represent actual port records.

This prevents the grand total from being accidentally included in the detailed stock quantities and counted twice.

---

# 3.8 Validating the CutOffDate

The Robusta report contains a `CutOffDate`.

The parser accepts two possible date formats:

```text
DD-Mon-YY
DD-Mon-YYYY
```

For example:

```text
01-Oct-26
01-Oct-2026
```

Both are converted into a standard pandas date.

The parser then checks that there is exactly one unique `CutOffDate` in the report.

If multiple different cutoff dates are found, the parser raises an error.

This protects the dataset from combining records that actually belong to different reporting dates.

---

# 3.9 Removing rows without a PortId

The parser removes rows that do not contain a `PortId`.

The reason is that the detailed Robusta dataset is organized by port.

Rows without a port identifier cannot be assigned to a specific location, so they are not included in the detailed `cells` output.

The separate `GrandTotal` row has already been handled independently.

---

# 3.10 Converting category columns into rows

One of the most important transformations in the Robusta parser is converting the three category columns into rows.

The source may look conceptually like:

```text
PortId | LotsWithValCert | LotsNonTend | LotsSuspended
AMS    | 1000            | 50          | 10
HAM    | 2000            | 100         | 20
LIV    | 500             | 25          | 5
```

The parser converts this into:

```text
PortId | stock_category  | quantity
AMS    | valid_cert      | 1000
AMS    | non_tenderable  | 50
AMS    | suspended       | 10
HAM    | valid_cert      | 2000
HAM    | non_tenderable  | 100
HAM    | suspended       | 20
LIV    | valid_cert      | 500
LIV    | non_tenderable  | 25
LIV    | suspended       | 5
```

This is called converting the data from **wide format to long format**.

The benefit is that the final dataset can use one consistent column:

```text
stock_category
```

instead of having a separate column for every category.

---

# 3.11 Converting quantities to integers

The `_int()` function converts the source values into integers.

It handles:

```text
"1,234" → 1234
"1234.0" → 1234
blank → 0
nan → 0
```

This ensures that stock quantities have a consistent numeric representation.

---

# 3.12 Standardizing port codes

The source provides port identifiers such as:

```text
AMS
HAM
LIV
ROT
```

These codes are retained in the parser as:

```text
port_code
```

They are not immediately converted to names.

The conversion is handled centrally by `ports.py`.

This separation keeps the Robusta parser focused on reading the source file rather than mixing source parsing with location naming.

---

# 3.13 Robusta parser output

The parser returns:

```text
cells
grand_totals
as_of
```

### `cells`

Contains:

```text
port_code
stock_category
quantity
```

Example:

```text
AMS | valid_cert | 1000
AMS | suspended  | 10
HAM | valid_cert | 2000
```

### `grand_totals`

Contains the category-level totals from the `GrandTotal` row.

Example:

```text
valid_cert → 3500
non_tenderable → 175
suspended → 35
```

### `as_of`

Contains the report's `CutOffDate`.

---

# 4. Port Mapping – `ports.py`

## 4.1 Purpose

The ICE reports use short port codes rather than full location names.

For example:

```text
ANT
NY
AMS
HAM
```

These codes are useful in the source data but are less readable in the final analysis dataset.

`ports.py` provides a central mapping from these ICE codes to readable names.

---

# 4.2 Port code mapping

The mapping contains both Arabica and Robusta ports.

### Arabica examples

```text
ANT   → Antwerp
BAR   → Barcelona
HA/BR → Hamburg/Bremen
HOU   → Houston
MIAMI → Miami
NOLA  → New Orleans
NY    → New York
VA    → Virginia
```

### Robusta examples

```text
AMS → Amsterdam
BRE → Bremen
FEL → Felixstowe
HAM → Hamburg
LEH → Le Havre
LIV → Liverpool
LON → London
ROT → Rotterdam
TRI → Trieste
NOR → Norfolk
```

Keeping these mappings in one file avoids duplicating the same mapping logic in multiple parsers or transformation functions.

---

# 4.3 `map_port()` function

The `map_port()` function receives a port code and looks for it in the `PORT_NAMES` dictionary.

For example:

```text
map_port("AMS")
```

returns:

```text
Amsterdam
```

Similarly:

```text
map_port("NY")
```

returns:

```text
New York
```

The function also removes leading and trailing spaces before performing the lookup.

---

# 4.4 Handling unknown port codes

The mapping is designed so that an unknown port code does not cause the entire pipeline to fail.

If a code is not present in `PORT_NAMES`, the function:

1. records the unknown code in `UNMAPPED_PORTS`
2. returns the original code

For example, if ICE introduces a new code:

```text
XYZ
```

and it has not yet been added to the mapping, the final value remains:

```text
XYZ
```

instead of causing the extraction or transformation to fail.

At the same time, the code is recorded in:

```text
UNMAPPED_PORTS
```

so that it can be reviewed later.

This is a practical approach because a new source location should not automatically cause the entire ETL pipeline to stop.

---

# 5. Why the parsers are separate

Arabica and Robusta are kept in separate parser files because their source structures are fundamentally different.

### Arabica

```text
Excel report
   ↓
Multiple sections
   ↓
Origins × Ports
   ↓
Different stock categories
   ↓
Port / Origin / Category totals
```

### Robusta

```text
CSV report
   ↓
Port rows
   ↓
Category columns
   ↓
GrandTotal row
   ↓
Wide → Long conversion
```

Trying to force both reports through the same parser would make the code much more complicated and less reliable.

Instead, each parser understands its own source format and produces a predictable structured output.

---

# 6. How the two parsers support a common final dataset

Even though the source formats are different, the parsers extract information that can be standardized later.

The information can be thought of as:

```text
Arabica:
origin + port + category + quantity

Robusta:
port + category + quantity
```

The transformation stage then adds the remaining common information such as:

```text
report_date
as_of_date
coffee_type
port_name
unit
```

This allows both coffee types to be combined into one final DataFrame.

The final structure is:

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

For Arabica, the `origin` field is populated.

For Robusta, there is no origin dimension in the source report, so `origin` is intentionally left blank.

---

# 7. How parsing connects to validation

An important part of the parser design is that it preserves the totals reported by ICE.

For Arabica, the parser retains:

```text
Port totals
Origin totals
Category totals
```

For Robusta, the parser retains:

```text
Category GrandTotals
```

These values are not simply discarded after parsing.

They are later used by `validate.py` to independently compare the final CSV against the original report totals.

The validation flow is therefore:

```text
ICE Report
    │
    ├── Detailed values
    │       ↓
    │   Parser
    │       ↓
    │   Final CSV
    │
    └── Reported totals
            ↓
       Validation
            ↓
       Compare both
```

This provides stronger confidence in the final dataset because the pipeline is not only checking whether the data has the correct format; it is also checking whether the calculated totals still agree with the source.

---

# 8. Overall result of the parsing stage

The resulting structured data is now ready for the **transformation stage**, where the pipeline creates the complete time-series/panel structure, fills appropriate missing combinations with zero, adds coffee type and units, maps port names, and combines Arabica and Robusta into one consolidated DataFrame.