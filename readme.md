# Coffee Stocks ETL

This project downloads ICE Arabica and Robusta stock reports, parses and combines them into a consistent CSV, validates the result, and provides a Dash dashboard for exploring it.

## Quick start

Run commands from the repository root.

### 1. Create and activate a virtual environment

**Windows (PowerShell):**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, open Command Prompt and run:

```bat
.venv\Scripts\activate.bat
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Robusta extraction uses Playwright to open Chromium. Install its browser once:

```bash
python -m playwright install chromium
```

### 3. Download raw reports

Download Arabica reports for weekdays in the recent one-year range:

```bash
python extract_arabica.py
```

Files are saved under `data/arabica/`. Existing files are kept rather than downloaded again.

Robusta extraction requires a browser interaction to capture ICE's report request:

```bash
python extract_robusta.py
```

In the opened browser, accept any ICE banner or disclaimer, choose **Stock Figures**, select a short date range, and click the search button. The script captures the request and then indexes and downloads reports for approximately the past year to `data/robusta/`. Keep the browser open until the script finishes.

If raw reports are already present in those directories, skip extraction and continue.

### 4. Run the ETL pipeline

```bash
python main.py
```

The pipeline parses both sets of reports, transforms and combines the data, validates it against the source reports, and writes `ice_certified_coffee_stocks.csv` in the repository root. If validation finds errors, it reports them and does not write the CSV unless `--force` is provided.

### 5. Open the dashboard

After the CSV has been created:

```bash
python dashboard.py
```

Open the local URL printed in the terminal (by default, <http://127.0.0.1:8050>). Stop the dashboard with **Ctrl+C**.

## Common commands

### ETL options

```text
python main.py [--arabica-dir DIR] [--robusta-dir DIR] [--output FILE]
               [--force] [--days N | --start YYYY-MM-DD [--end YYYY-MM-DD]]
```

Examples:

```bash
#default 
python main.py 

# Use custom input folders and output file
python main.py --arabica-dir data/arabica --robusta-dir data/robusta --output stocks.csv

# Validate the most recent 30 days
python main.py --days 30

# Validate a date range
python main.py --start 2026-01-01 --end 2026-03-31

# Write the CSV even if validation reports errors
python main.py --force
```

`--days`, `--start`, and `--end` limit the validation window only; the pipeline still processes and writes all available data. Use `--days` or a date range, not both. `--force` does not suppress validation messages; it only allows the CSV to be written despite errors.

### Validate an existing CSV separately

```bash
# Validate the default CSV, using raw reports for total reconciliation
python -m src.validate

# Validate a different CSV
python -m src.validate --csv "file_name"

# Validate only a date window
python -m src.validate --days 30
python -m src.validate --start 2026-01-01 --end 2026-03-31
```

```powershell
# Specify custom CSV and raw report locations
python -m src.validate --csv stocks.csv `
  --arabica-dir data/arabica --robusta-dir data/robusta
```

The last example uses PowerShell line continuation. In Command Prompt or macOS/Linux, put the command on one line or use the shell's line-continuation character. The standalone validator returns a non-zero exit code when it finds errors. It also compares totals with the raw ICE reports when those source files are available; some reconciliation checks are skipped when they are not.

### Dashboard options

```text
python dashboard.py [--csv FILE] [--host HOST] [--port PORT] [--debug]
```

Examples:

```bash
python dashboard.py 
python dashboard.py --csv "file_name" --port 8060
```

## Project map

| Area | What it does | Start here |
|---|---|---|
| Extraction | Downloads raw ICE Arabica and Robusta reports | [`extract_arabica.py`](extract_arabica.py), [`extract_robusta.py`](extract_robusta.py), [extraction guide](docs/extraction.md) |
| Parsing | Reads the source Excel/CSV report formats | [`src/parse_arabica.py`](src/parse_arabica.py), [`src/parse_robusta.py`](src/parse_robusta.py), [parser guide](docs/parser.md) |
| Transformation | Builds consistent panels and combines coffee types | [`src/transform.py`](src/transform.py), [transformation guide](docs/transform.md) |
| Validation | Checks schema, duplicates, date coverage, and reported totals | [`src/validate.py`](src/validate.py), [validation guide](docs/validate.md) |
| Pipeline entry point | Orchestrates parsing, transformation, validation, and CSV output | [`main.py`](main.py), [pipeline guide](docs/main.md) |
| Dashboard | Explores the resulting CSV with interactive charts and filters | [`dashboard.py`](dashboard.py), [dashboard guide](docs/dashboard.md) |
| Port names | Maps ICE port codes to readable names | [`src/ports.py`](src/ports.py) |
| Dependencies | Python packages used by the project | [`requirements.txt`](requirements.txt) |

