
# Data Extraction

## 1. Overview

The first step of the ICE Certified Coffee Stocks ETL pipeline is to collect the historical source reports from the Intercontinental Exchange (ICE) website.

The case study provides two source reports:

- **Arabica:** ICE Report 42
- **Robusta:** ICE Report 173

The requirement was to collect approximately one year of historical stock data and use it as the input for the remaining ETL process.

During the extraction process, the two ICE reports were found to behave differently. Because of this, different extraction approaches were used for Arabica and Robusta.

For Arabica, the historical report files were available through a predictable public file path, so the files could be downloaded directly using Python.

For Robusta, the report results were not directly accessible in the same way. A direct request to the report endpoint returned an HTTP 409 response. Therefore, a browser-based approach using Playwright was used to interact with the ICE report page and retrieve the available report download information.

The two extraction scripts are:

- `extract_arabica.py`
- `extract_robusta.py`

Both scripts have the same overall purpose: **collect the raw ICE reports and save them locally so that the parsing stage can process them later.**

---

# 2. Arabica Data Extraction

## 2.1 Source

The Arabica data comes from **ICE Report 42**.

The report provides certified coffee stock information, including information by port and origin and different stock categories.

The historical report files are available as Excel files with a predictable naming pattern:

`coffee_cert_stock_YYYYMMDD.xls`

For example:

`coffee_cert_stock_20251007.xls`

The extraction script uses this predictable pattern to construct the download URL for each date.

---

## 2.2 Extraction approach

The Arabica extraction is handled by `extract_arabica.py`.

The script uses the Python `requests` library to download the files directly from ICE.

The base location is defined once:

```text
https://www.ice.com/publicdocs/futures_us_reports/coffee/
```

The script then creates the filename using the required date.

For example, for October 7, 2025, it constructs:

```text
coffee_cert_stock_20251007.xls
```

and combines it with the base URL to create the complete download location.

This approach avoids manually downloading hundreds of individual reports.

---

## 2.3 Selecting the historical date range

The script automatically creates a date range covering approximately one year.

The end date is yesterday:

```text
today - 1 day
```

The start date is calculated as:

```text
end date - 365 days
```

Only weekdays are selected.

This is because the ICE stock reports are associated with business/trading days, so weekends do not need to be requested.

For example, if the end date is a weekday, the script creates a list similar to:

```text
Monday
Tuesday
Wednesday
Thursday
Friday
Monday
Tuesday
...
```

Saturday and Sunday are skipped.

This allows the extraction to automatically cover the required historical period without manually entering every date.

---

## 2.4 Local storage

The downloaded Arabica reports are stored under:

```text
data/arabica/
```

The output filename is based on the report date.

For example:

```text
data/arabica/coffee_cert_stock_20251007.xls
data/arabica/coffee_cert_stock_20251008.xls
data/arabica/coffee_cert_stock_20251009.xls
```

The folder is created automatically if it does not already exist.

---

## 2.5 Verifying that the downloaded file is actually an Excel file

The script does not rely only on the HTTP status code.

A successful HTTP response does not always mean that the expected report was returned. Therefore, the script also checks the first four bytes of the response.

The expected Excel file signature is:

```text
D0 CF 11 E0
```

This helps distinguish a valid `.xls` file from an unexpected response such as an error page.

Only when both conditions are satisfied does the script save the file:

1. HTTP status is `200`
2. The file begins with the expected Excel file signature

This provides an additional basic protection against saving an invalid response as a report file.

---

## 2.6 Handling HTTP 429

While downloading a large number of reports, ICE may temporarily limit the number of requests.

This is known as:

**HTTP 429 – Too Many Requests**

The script handles this situation by waiting for three minutes before trying the same request again.

This is important because the extraction is intended to be reliable rather than simply sending requests as quickly as possible.

---

## 2.7 Batch downloading

The script processes the pending files in batches.

The batch size is:

```text
20 files
```

After each batch, the script waits:

```text
180 seconds
```

which is three minutes.

The basic process is:

```text
Download 20 files
       ↓
Wait 3 minutes
       ↓
Download next 20 files
       ↓
Wait 3 minutes
       ↓
Continue until complete
```

This reduces the request rate and helps avoid repeated rate-limit responses from the source website.

---

## 2.8 Handling temporary network errors

If a network-related request error occurs, the script does not immediately terminate.

Instead, it prints the error, waits for one minute, and then tries the request again.

This provides some resilience against temporary network problems.

---

## 2.9 Extraction result

At the end of the extraction, the script reports:

- how many files were already available locally
- how many files needed to be downloaded
- how many files were successfully downloaded
- which dates could not be downloaded

This makes it easier to verify whether the expected historical period was successfully collected.

The extracted files are then available for the next stage of the pipeline, where `parse_arabica.py` reads and interprets their contents.

---

# 3. Robusta Data Extraction

## 3.1 Source

The Robusta data comes from **ICE Report 173**.

The required report selection is:

```text
Stock Figures
```

Unlike the Arabica report, the Robusta report did not provide a simple predictable file path that could be used to download all historical reports directly.

---

# 3.2 Why a different extraction method was required

Initially, the Robusta report was investigated using its report endpoint.

However, making the request directly outside the ICE website's browser context resulted in:

```text
HTTP 409
```

Therefore, simply using Python `requests` in the same way as Arabica was not reliable for Robusta.

The ICE website was already able to make the required request when the report was used normally through the browser.

Therefore, instead of trying to reproduce the entire website interaction manually, the extraction script uses **Playwright** to open the ICE report page in a real browser context.

This allows the script to work with the same browser session that the ICE website itself uses.

---

# 3.3 Browser-based extraction

The Robusta extraction is handled by:

```text
extract_robusta.py
```

The script uses Playwright to launch Chromium and open:

```text
ICE Report 173
```

The browser is launched in visible mode rather than completely in the background.

This is intentional because the first part of the process requires the user to interact with the report page.

The user is asked to:

1. Accept any cookie or disclaimer banners if displayed.
2. Select **Stock Figures**.
3. Select a short date range.
4. Click the search button.

The purpose of this initial interaction is to allow the ICE website itself to generate the correct report request.

---

# 3.4 Capturing the request generated by the ICE website

The script attaches a request listener to the browser page.

It looks specifically for a `POST` request whose URL contains:

```text
/reports/173/results
```

When this request occurs, the script captures:

- the request headers
- the request body

The request body is important because it shows how the ICE website asks the backend for the selected report information.

The captured request is then used by the script to reproduce the report query inside the same browser session.

This means the script is not guessing the request format. It observes the request that the ICE website itself generated.

---

# 3.5 Using the browser session

After capturing the request, the script performs the report request from inside the browser using JavaScript `fetch`.

The important part here is:

```text
credentials: 'include'
```

This allows the browser request to use the current browser session.

This was important because the direct request outside the browser had returned HTTP 409, while the browser session could successfully access the report data.

The script sends a request containing:

```text
reportType=Stock Figures
startDate=<start date>
endDate=<end date>
```

and receives the report results as JSON.

---

# 3.6 Processing the historical period in chunks

The Robusta extraction covers approximately one year.

Instead of requesting the entire year in one request, the script divides the period into **31-day chunks**.

For example:

```text
Chunk 1 → Day 1 to Day 31
Chunk 2 → Day 32 to Day 62
Chunk 3 → Day 63 to Day 93
...
```

For every chunk, the script sends a request to the ICE report endpoint.

The returned JSON contains report information and download links.

Processing the data in smaller chunks makes the extraction more manageable and avoids depending on a single very large historical request.

A two-second pause is also added between chunks.

---

# 3.7 Finding the downloadable reports

The response contains report information inside the returned JSON structure.

The script looks through each report and its `reportList`.

It selects entries where:

- the item type is `download`
- the URL ends with a supported file extension

The supported extensions are:

```text
.csv
.xls
.xlsx
```

For every report date, the corresponding download URL is collected.

The result is stored in a dictionary where the report date points to its available download URLs.

---

# 3.8 Creating an index of the reports

Before downloading all the files, the script saves the collected information to:

```text
data/robusta/index.json
```

This file acts as an index of the available Robusta reports.

Conceptually, it looks like:

```text
Report Date
    ↓
Download URL(s)
```

For example:

```text
2026-09-30
    → report download URL

2026-10-01
    → report download URL
```

Keeping this information in a separate index is useful because the script first discovers which reports are available and then downloads them.

---

# 3.9 Downloading the Robusta reports

Once all report URLs have been collected, the script goes through the index and downloads the files.

The filename is taken from the URL itself.

The files are saved under:

```text
data/robusta/
```

If a file already exists, it is skipped.

This provides the same benefit as the Arabica extraction: the extraction process can be run again without unnecessarily downloading files that have already been collected.

---

# 3.10 Handling HTTP 429 for Robusta

The Robusta extraction also handles HTTP 429 responses.

If ICE returns:

```text
429 Too Many Requests
```

the script waits for:

```text
300 seconds
```

which is five minutes.

After waiting, it tries the download again.

This is important when downloading a large number of historical files because the source may temporarily restrict repeated requests.

---

# 3.11 Extraction result

The final result of the Robusta extraction is a collection of raw report files under:

```text
data/robusta/
```

along with:

```text
data/robusta/index.json
```

These raw files are later processed by `parse_robusta.py`.

---


# 4. Why the extraction stage is kept separate from parsing

The extraction scripts are responsible only for **getting the raw reports and storing them locally**.

They do not try to interpret all the coffee-stock information.

The next stage, handled by `parse_arabica.py` and `parse_robusta.py`, is responsible for reading those raw reports and converting their different layouts into structured data.

This separation makes the pipeline easier to understand and maintain.

The overall flow is:

```text
ICE Website
    ↓
Extraction
    ↓
Raw Arabica / Robusta files
    ↓
Parsing
    ↓
Structured records
    ↓
Transformation
    ↓
Consolidated dataset
    ↓
Validation
```

This also makes the process reproducible. Once the raw files have been downloaded, the parsing and transformation stages can be run locally without repeatedly accessing the ICE website.

---

# 5. Extraction limitations and considerations

The extraction process depends on the current behavior of the ICE website.

For Arabica, the extraction depends on the availability and naming pattern of the public `.xls` files.

For Robusta, the extraction depends on the report page and the browser-generated request because the direct endpoint was returning HTTP 409.

The Robusta extraction therefore requires an initial browser interaction to establish the required session and generate the report request.

The scripts also include delays and retry behavior because ICE may return HTTP 429 when too many requests are made in a short period.

These behaviors are documented rather than hidden because they are part of the practical extraction methodology used for this case study.

---

# 6. Final outcome of the extraction stage

At the end of this stage, the project has approximately one year of raw ICE reports stored locally:

```text
data/
├── arabica/
│   ├── coffee_cert_stock_YYYYMMDD.xls
│   ├── coffee_cert_stock_YYYYMMDD.xls
│   └── ...
│
└── robusta/
    ├── Stock_Report_RC_YYYYMMDD_HHMMSS.csv
    ├── Stock_Report_RC_YYYYMMDD_HHMMSS.csv
    ├── index.json
    └── ...
```

These files form the raw input for the parsing stage.

The extraction stage does not yet produce the final analysis-ready dataset. Its purpose is to reliably collect and preserve the source reports so that the following stages can clean, standardize, transform and validate the data.