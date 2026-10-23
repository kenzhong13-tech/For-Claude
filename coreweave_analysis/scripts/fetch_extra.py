"""Second data pull: T-bill/Treasury yields and CoreWeave earnings press releases (8-K Item 2.02)."""
import json
import os
import re
import time
import urllib.request

import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup

OUT = "coreweave_analysis/data/raw"
SEC_DIR = os.path.join(OUT, "sec")
H = {"User-Agent": "CRWV-research-script research@example.com", "Accept-Encoding": "identity"}
CIK = 1769628


def log(*a):
    print(*a, flush=True)


def get(url, headers=H, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return r.read()


for t in ["^IRX", "^TNX", "HYG", "LQD"]:
    for attempt in range(3):
        try:
            df = yf.download(t, start="2025-03-20", end="2026-10-22", auto_adjust=False, progress=False, threads=False)
            if len(df):
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.to_csv(os.path.join(OUT, f"{t.replace('^', 'IDX_')}.csv"))
                log("yahoo", t, len(df))
                break
        except Exception as e:  # noqa: BLE001
            log("yahoo ERR", t, e)
        time.sleep(5)


def html_to_text(raw):
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        tr.replace_with(" | ".join(c for c in cells if c) + "\n")
    return re.sub(r"\n\s*\n+", "\n\n", soup.get_text("\n"))


filings = []
recent = json.load(open(os.path.join(SEC_DIR, "submissions.json")))["filings"]["recent"]
filings += [dict(zip(recent.keys(), v)) for v in zip(*recent.values())]
try:
    older = json.loads(get(f"https://data.sec.gov/submissions/CIK{CIK:010d}-submissions-001.json"))
    filings += [dict(zip(older.keys(), v)) for v in zip(*older.values())]
except Exception as e:  # noqa: BLE001
    log("older ERR", e)

for f in filings:
    form, items = f["form"], f.get("items", "") or ""
    wanted_8k = form == "8-K" and ("2.02" in items) and f["filingDate"] >= "2025-04-01"
    wanted_10q = form == "10-Q" and f["filingDate"] < "2025-09-01"
    if not (wanted_8k or wanted_10q):
        continue
    acc = f["accessionNumber"].replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{CIK}/{acc}"
    try:
        if wanted_10q:
            names = [f["primaryDocument"]]
        else:
            idx = json.loads(get(f"{base}/index.json"))
            names = [i["name"] for i in idx["directory"]["item"]
                     if i["name"].lower().endswith((".htm", ".html")) and i["name"] != f["primaryDocument"]
                     and "index" not in i["name"].lower()]
        for n in names:
            raw = get(f"{base}/{n}")
            label = "main" if wanted_10q else "earnings_" + re.sub(r"[^a-z0-9]", "", n.lower())[:30]
            name = f"{f['filingDate']}_{form}_{label}.txt"
            open(os.path.join(SEC_DIR, name), "w").write(html_to_text(raw))
            log("saved", name)
            time.sleep(0.3)
    except Exception as e:  # noqa: BLE001
        log("ERR", base, e)
log("done")
