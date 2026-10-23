"""Download market data (Yahoo Finance) and HKEXnews announcements for Pop Mart (9992.HK).

Runs on a GitHub Actions runner (open internet); outputs land in popmart_analysis/data/raw/.
"""
import json
import os
import re
import time
import urllib.request

import pandas as pd
import yfinance as yf
from pdfminer.high_level import extract_text

OUT = "popmart_analysis/data/raw"
HK_DIR = os.path.join(OUT, "hkex")
os.makedirs(HK_DIR, exist_ok=True)
START, END = "2020-12-01", "2026-10-22"
TICKERS = ["9992.HK", "^HSI", "HSTECH.HK", "^HSCE", "^GSPC", "^IRX", "9896.HK", "6181.HK", "2097.HK",
           "7832.T", "HAS", "MAT", "2020.HK", "MCHI", "CNY=X"]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def log(*a):
    print(*a, flush=True)


def get(url, headers=UA, timeout=90):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return r.read()


def fname(t):
    return re.sub(r"[^A-Za-z0-9]", "_", t.replace("^", "IDX_"))


# ---------- prices ----------
for t in TICKERS:
    for attempt in range(3):
        try:
            df = yf.download(t, start=START, end=END, auto_adjust=False, progress=False, threads=False)
            if df is not None and len(df):
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.to_csv(os.path.join(OUT, f"{fname(t)}.csv"))
                log("yahoo", t, len(df), df.index.min(), df.index.max())
                break
        except Exception as e:  # noqa: BLE001
            log("yahoo ERR", t, e)
        time.sleep(4 * (attempt + 1))

# ---------- Yahoo fundamentals ----------
pm = yf.Ticker("9992.HK")
try:
    json.dump(pm.info, open(os.path.join(OUT, "popmart_info.json"), "w"), default=str, indent=1)
except Exception as e:  # noqa: BLE001
    log("info ERR", e)
for attr in ["income_stmt", "balance_sheet", "cashflow", "quarterly_income_stmt", "quarterly_balance_sheet",
             "quarterly_cashflow"]:
    try:
        getattr(pm, attr).to_csv(os.path.join(OUT, f"popmart_{attr}.csv"))
    except Exception as e:  # noqa: BLE001
        log(attr, "ERR", e)
for attr in ["dividends", "splits"]:
    try:
        getattr(pm, attr).to_csv(os.path.join(OUT, f"popmart_{attr}.csv"))
    except Exception as e:  # noqa: BLE001
        log(attr, "ERR", e)

# ---------- HKEXnews announcements ----------
try:
    raw = get("https://www1.hkexnews.hk/search/prefix.do?&callback=callback&lang=EN&type=A&name=09992&market=SEHK").decode()
    sid = re.search(r'"stockId"\s*:\s*(\d+)', raw).group(1)
    log("HKEX stockId", sid)
    items = []
    for frm, to in (("20200101", "20221231"), ("20230101", "20241231"), ("20250101", "20261022")):
        url = ("https://www1.hkexnews.hk/search/titleSearchServlet.do?sortDir=0&sortByOptions=DateTime&category=0"
               f"&market=SEHK&stockId={sid}&documentType=-1&fromDate={frm}&toDate={to}&title=&searchType=0"
               "&t1code=-2&t2Gcode=-2&t2code=-2&rowRange=1000&lang=E")
        js = json.loads(get(url))
        part = json.loads(js["result"]) if isinstance(js.get("result"), str) else (js.get("result") or [])
        log("HKEX", frm, to, len(part))
        items += part
        time.sleep(1)
    json.dump(items, open(os.path.join(HK_DIR, "announcements.json"), "w"), ensure_ascii=False, indent=1)
except Exception as e:  # noqa: BLE001
    log("HKEX search ERR", e)
    items = []

KEEP = re.compile(r"(ANNUAL RESULTS|INTERIM RESULTS|BUSINESS UPDATE|OPERATIONAL UPDATE|PROFIT ALERT|PLACING|"
                  r"INSIDE INFORMATION|VOLUNTARY ANNOUNCEMENT|BUY-BACK|REPURCHASE|SHARE AWARD|CONNECTED TRANSACTION|"
                  r"FINAL DIVIDEND|SPECIAL DIVIDEND|PROFIT WARNING|UNAUDITED)", re.I)
n = 0
for it in items:
    title = (it.get("TITLE") or "") + " " + (it.get("SHORT_TEXT") or "") + " " + (it.get("LONG_TEXT") or "")
    link = it.get("FILE_LINK") or ""
    if not link.lower().endswith(".pdf") or not KEEP.search(title):
        continue
    if re.search(r"(NOTIFICATION LETTER|CIRCULAR|PROXY FORM|NOTICE OF|NEXT DAY DISCLOSURE|MONTHLY RETURN)", title, re.I):
        continue
    d = it.get("DATE_TIME", "")[:10]
    dd = f"{d[6:10]}-{d[3:5]}-{d[0:2]}" if len(d) == 10 else "unknown"
    slug = re.sub(r"[^A-Za-z0-9]+", "_", (it.get("TITLE") or "doc"))[:60].strip("_")
    path = os.path.join(HK_DIR, f"{dd}_{slug}.txt")
    if os.path.exists(path):
        continue
    try:
        pdf = get("https://www1.hkexnews.hk" + link)
        tmp = "/tmp/doc.pdf"
        open(tmp, "wb").write(pdf)
        text = extract_text(tmp)
        open(path, "w").write(text)
        n += 1
        log("saved", path, len(text))
    except Exception as e:  # noqa: BLE001
        log("pdf ERR", link, e)
    time.sleep(0.5)
log("done, pdfs:", n)
