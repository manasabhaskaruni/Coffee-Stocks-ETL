import time
import requests
from pathlib import Path
from datetime import date, timedelta

BASE = "https://www.ice.com/publicdocs/futures_us_reports/coffee/"
PREFIX = "coffee_cert_stock_"
OUT = Path("data/arabica")
OUT.mkdir(parents=True, exist_ok=True)

BATCH_SIZE = 20
BATCH_PAUSE = 180
XLS_MAGIC = b"\xd0\xcf\x11\xe0"

session = requests.Session()
session.headers["User-Agent"] = "Mozilla/5.0"


def fetch(d):
    target = OUT / f"{PREFIX}{d:%Y%m%d}.xls"

    if target.exists():
        return "cached"

    url = f"{BASE}{PREFIX}{d:%Y%m%d}.xls"

    while True:
        try:
            r = session.get(url, timeout=30)
        except requests.RequestException as e:
            print(f"{d} -> error: {e}")
            time.sleep(60)
            continue

        if r.status_code == 200 and r.content[:4] == XLS_MAGIC:
            target.write_bytes(r.content)
            print(f"{d} -> downloaded")
            return "ok"

        if r.status_code == 429:
            print(f"{d} -> 429, waiting 3 minutes...")
            time.sleep(BATCH_PAUSE)
            continue

        print(f"{d} -> HTTP {r.status_code}")
        return "missing"


end = date.today() - timedelta(days=1)
start = end - timedelta(days=365)

dates = []

d = start
while d <= end:
    if d.weekday() < 5:
        dates.append(d)
    d += timedelta(days=1)


todo = [
    d for d in dates
    if not (OUT / f"{PREFIX}{d:%Y%m%d}.xls").exists()
]

print(f"Already downloaded: {len(dates) - len(todo)}")
print(f"Files to download: {len(todo)}")

results = []

for i in range(0, len(todo), BATCH_SIZE):

    batch = todo[i:i + BATCH_SIZE]

    print(
        f"\nDownloading batch "
        f"{i + 1}-{min(i + BATCH_SIZE, len(todo))} "
        f"of {len(todo)}"
    )

    for d in batch:
        results.append((d, fetch(d)))

    done = min(i + BATCH_SIZE, len(todo))
    print(f"Batch completed: {done}/{len(todo)}")

    if done < len(todo):
        print("Waiting 3 minutes...")
        time.sleep(BATCH_PAUSE)


ok = [d for d, s in results if s == "ok"]
bad = [d for d, s in results if s == "missing"]

print(f"Downloaded: {len(ok)}")
print(f"Missing: {len(bad)}")

if bad:
    print("\nMissing dates:")
    for d in bad:
        print(d)