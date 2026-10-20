"""Download market data (Yahoo Finance, with Stooq/FRED fallbacks) and SEC filings for CoreWeave (CRWV).

Runs on a GitHub Actions runner (open internet); outputs land in coreweave_analysis/data/raw/.
"""
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
os.makedirs(SEC_DIR, exist_ok=True)
START, END = "2025-03-20", "2026-10-22"
TICKERS = ["CRWV", "^GSPC", "NVDA", "NBIS", "ORCL", "^VIX", "SPY", "QQQ", "SMH", "AMZN", "MSFT", "GOOGL", "META"]
SEC_UA = "CRWV-research-script research@example.com"
CIK = "0001769628"


def log(*a):
    print(*a, flush=True)


def get(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------- prices ----------
for t in TICKERS:
    for attempt in range(4):
        try:
            df = yf.download(t, start=START, end=END, auto_adjust=False, progress=False, threads=False)
            if df is not None and len(df):
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.to_csv(os.path.join(OUT, f"{t.replace('^', 'IDX_')}.csv"))
                log("yahoo", t, len(df), df.index.min(), df.index.max())
                break
        except Exception as e:  # noqa: BLE001
            log("yahoo ERR", t, e)
        time.sleep(4 * (attempt + 1))

for name, url in {
    "stooq_crwv.csv": "https://stooq.com/q/d/l/?s=crwv.us&i=d",
    "stooq_spx.csv": "https://stooq.com/q/d/l/?s=^spx&i=d",
    "fred_sp500.csv": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500",
    "fred_dgs3mo.csv": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO",
    "fred_dgs10.csv": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10",
    "fred_bamlh0a0hym2.csv": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2",
}.items():
    try:
        data = get(url)
        open(os.path.join(OUT, name), "wb").write(data)
        log("fallback", name, len(data))
    except Exception as e:  # noqa: BLE001
        log("fallback ERR", name, e)

# ---------- Yahoo fundamentals / options ----------
crwv = yf.Ticker("CRWV")
try:
    json.dump(crwv.info, open(os.path.join(OUT, "crwv_info.json"), "w"), default=str, indent=1)
except Exception as e:  # noqa: BLE001
    log("info ERR", e)
for attr in ["quarterly_income_stmt", "quarterly_balance_sheet", "quarterly_cashflow",
             "income_stmt", "balance_sheet", "cashflow"]:
    try:
        getattr(crwv, attr).to_csv(os.path.join(OUT, f"crwv_{attr}.csv"))
    except Exception as e:  # noqa: BLE001
        log(attr, "ERR", e)
try:
    crwv.get_earnings_dates(limit=16).to_csv(os.path.join(OUT, "crwv_earnings_dates.csv"))
except Exception as e:  # noqa: BLE001
    log("earnings dates ERR", e)
try:
    rows = []
    for ex in crwv.options[:10]:
        ch = crwv.option_chain(ex)
        for typ, d in (("call", ch.calls), ("put", ch.puts)):
            d = d.copy()
            d["type"], d["expiry"] = typ, ex
            rows.append(d)
    pd.concat(rows).to_csv(os.path.join(OUT, "crwv_options.csv"), index=False)
    log("options rows", sum(len(r) for r in rows))
except Exception as e:  # noqa: BLE001
    log("options ERR", e)

# ---------- SEC EDGAR ----------
H = {"User-Agent": SEC_UA, "Accept-Encoding": "identity"}
try:
    facts = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json", H)
    open(os.path.join(SEC_DIR, "companyfacts.json"), "wb").write(facts)
    log("companyfacts", len(facts))
except Exception as e:  # noqa: BLE001
    log("companyfacts ERR", e)
try:
    subs = json.loads(get(f"https://data.sec.gov/submissions/CIK{CIK}.json", H))
    json.dump(subs, open(os.path.join(SEC_DIR, "submissions.json"), "w"), indent=1)
    rec = subs["filings"]["recent"]
    filings = [dict(zip(rec.keys(), vals)) for vals in zip(*rec.values())]
except Exception as e:  # noqa: BLE001
    log("submissions ERR", e)
    filings = []


def html_to_text(raw):
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        tr.replace_with(" | ".join(c for c in cells if c) + "\n")
    text = soup.get_text("\n")
    return re.sub(r"\n\s*\n+", "\n\n", text)


def save_doc(f, url, label):
    try:
        raw = get(url, H)
        name = f"{f['filingDate']}_{f['form'].replace('/', '-')}_{label}.txt"
        open(os.path.join(SEC_DIR, name), "w").write(html_to_text(raw))
        log("saved", name)
    except Exception as e:  # noqa: BLE001
        log("doc ERR", url, e)
    time.sleep(0.3)


cik_int = int(CIK)
seen_10q = seen_10k = 0
for f in filings:
    acc = f["accessionNumber"].replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}"
    form = f["form"]
    if form == "10-K" and seen_10k < 2:
        seen_10k += 1
        save_doc(f, f"{base}/{f['primaryDocument']}", "main")
    elif form == "10-Q" and seen_10q < 6:
        seen_10q += 1
        save_doc(f, f"{base}/{f['primaryDocument']}", "main")
    elif form in ("8-K", "424B4", "S-1/A") and f["filingDate"] >= "2025-03-01":
        try:
            idx = json.loads(get(f"{base}/index.json", H))
            time.sleep(0.2)
            for item in idx["directory"]["item"]:
                n = item["name"].lower()
                if form == "8-K" and re.search(r"ex-?99", n) and n.endswith((".htm", ".html")):
                    save_doc(f, f"{base}/{item['name']}", "ex99_" + re.sub(r"[^a-z0-9]", "", n)[:30])
        except Exception as e:  # noqa: BLE001
            log("index ERR", base, e)
log("done")
