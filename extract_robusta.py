import json, time
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright   # pip install playwright ; playwright install chromium

ROOT = "https://www.ice.com"
PAGE = f"{ROOT}/report/173"
OUT = Path("data/robusta"); OUT.mkdir(parents=True, exist_ok=True)
CHUNK_DAYS = 31
SKIP = {"cookie", "host", "content-length", "origin", "referer", "user-agent",
        "connection", "accept-encoding", "accept-language"}

captured = {}

def on_request(req):
    if req.method == "POST" and "/reports/173/results" in req.url:
        captured["headers"] = req.headers
        captured["body"] = req.post_data

JS_POST = """async ([url, headers, body]) => {
    const r = await fetch(url, {method: 'POST', headers, body, credentials: 'include'});
    return {status: r.status, text: await r.text()};
}"""
JS_GET = """async (url) => {
    const r = await fetch(url, {credentials: 'include'});
    return {status: r.status, text: await r.text()};
}"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.on("request", on_request)
    page.goto(PAGE)

    print("\nIn the browser window: accept any banners/disclaimer, choose 'Stock Figures',")
    print("pick a short date range and click the search button.")
    print("Waiting up to 5 minutes for the results request...\n")
    t0 = time.time()
    while "body" not in captured and time.time() - t0 < 300:
        page.wait_for_timeout(500)
    if "body" not in captured:
        raise SystemExit("No results request seen.")

    hdrs = {k: v for k, v in captured["headers"].items()
            if k.lower() not in SKIP and not k.lower().startswith(("sec-", ":"))}
    print("Request body the browser sent:", captured["body"])
    print("Extra headers it sent (no cookies):", hdrs)
    hdrs = {"Content-Type": "application/x-www-form-urlencoded"}

    def get_rows(start, end):
        body = f"reportType=Stock+Figures&startDate={start}&endDate={end}"
        res = page.evaluate(JS_POST, [f"{ROOT}/marketdata/api/reports/173/results", hdrs, body])
        if res["status"] != 200:
            raise RuntimeError(f"{start}..{end} -> {res['status']}: {res['text'][:200]}")
        return json.loads(res["text"])["datasets"]["reports"]["rows"]

    files = {}
    end = date.today(); 
    cur = end - timedelta(days=365)
    while cur <= end:
        ce = min(cur + timedelta(days=CHUNK_DAYS - 1), end)
        for row in get_rows(cur.isoformat(), ce.isoformat()):
            for item in row.get("reportList", []):
                u = item.get("url", "")
                if item.get("type") == "download" and u.lower().endswith((".csv", ".xls", ".xlsx")):
                    files.setdefault(row["reportDate"], []).append(u)
        print(cur, "..", ce, "ok")
        cur = ce + timedelta(days=1)
        time.sleep(2)

    (OUT / "index.json").write_text(json.dumps(files, indent=2))
    print(len(files), "dates indexed ->", OUT / "index.json")

    for d, urls in sorted(files.items()):
        for u in dict.fromkeys(urls):
            target = OUT / Path(u).name
            if target.exists():
                continue
            while True:
                res = page.evaluate(JS_GET, ROOT + u)
                if res["status"] == 429:
                    print("429, waiting 300s"); time.sleep(300); continue
                if res["status"] == 200:
                    target.write_text(res["text"], encoding="utf-8"); print(d, "->", target.name)
                else:
                    print(d, "-> HTTP", res["status"])
                break
            time.sleep(1.5)
    browser.close()