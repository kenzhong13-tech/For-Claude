"""Download market data and filings for 3SBio (1530.HK) and its Hong Kong innovative-drug peers.

Runs on a GitHub Actions runner (open internet); outputs land in 3sbio_analysis/data/raw/:
- Yahoo Finance daily prices for 3SBio, peers, indices and sector ETFs; Yahoo company info
- Eastmoney HK index history and financial indicators (via akshare), FRED NASDAQ HK Health Care index
- HKEXnews announcement lists and text of key filings for 3SBio, and recent results announcements for peers
"""
import json
import os
import re
import time
import urllib.request

import pandas as pd
import yfinance as yf
from pdfminer.high_level import extract_text

OUT = "3sbio_analysis/data/raw"
for sub in ("", "hkex", "peers_hkex", "info", "ak"):
    os.makedirs(os.path.join(OUT, sub), exist_ok=True)
START, END = "2018-01-01", "2026-10-24"
PEERS = {  # HKEX code -> name
    "1530": "3SBio", "1276": "Hengrui", "6160": "BeOne", "1801": "Innovent", "9926": "Akeso", "3692": "Hansoh",
    "1093": "CSPC", "1177": "Sino Biopharm", "6990": "Kelun-Biotech", "1877": "Junshi", "9995": "RemeGen",
    "2096": "Simcere", "0013": "HUTCHMED", "9688": "Zai Lab", "9606": "Duality Bio", "2162": "Keymed",
}
OTHER = ["^HSI", "^HSCE", "^IRX", "CNY=X", "XBI", "688336.SS", "600276.SS",
         # sector ETFs and index candidates (not all exist on Yahoo)
         "3069.HK", "2820.HK", "159506.SZ", "159316.SZ", "159567.SZ", "513120.SS", "513060.SS", "^HSHCI", "^HSBIO"]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def log(*a):
    print(*a, flush=True)


def get(url, headers=UA, timeout=90):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return r.read()


def fname(t):
    return re.sub(r"[^A-Za-z0-9]", "_", t.replace("^", "IDX_"))


def yahoo(code):
    return f"{int(code):04d}.HK"


# ---------- prices ----------
for t in [yahoo(c) for c in PEERS] + OTHER:
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
        time.sleep(3 * (attempt + 1))

# ---------- Yahoo company info ----------
for c in PEERS:
    t = yahoo(c)
    try:
        json.dump(yf.Ticker(t).info, open(os.path.join(OUT, "info", f"{fname(t)}.json"), "w"), default=str, indent=1)
    except Exception as e:  # noqa: BLE001
        log("info ERR", t, e)
    time.sleep(1)
tk = yf.Ticker("1530.HK")
for attr in ["income_stmt", "balance_sheet", "cashflow", "dividends"]:
    try:
        getattr(tk, attr).to_csv(os.path.join(OUT, f"sbio_{attr}.csv"))
    except Exception as e:  # noqa: BLE001
        log(attr, "ERR", e)

# ---------- FRED: NASDAQ Hong Kong Health Care index ----------
for sid in ("NASDAQNQHK20", "NASDAQNQHK20T"):
    try:
        open(os.path.join(OUT, f"FRED_{sid}.csv"), "wb").write(get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"))
        log("fred", sid, "ok")
    except Exception as e:  # noqa: BLE001
        log("fred ERR", sid, e)

# ---------- akshare (Eastmoney): HK sector indices and financial indicators ----------
try:
    import akshare as ak

    try:
        spot = ak.stock_hk_index_spot_em()
        spot.to_csv(os.path.join(OUT, "ak", "hk_index_list.csv"), index=False)
        name_col = next(c for c in spot.columns if "名称" in c)
        code_col = next(c for c in spot.columns if "代码" in c)
        hits = spot[spot[name_col].astype(str).str.contains("医|药|生物|健康")]
        log("ak index candidates", hits[[code_col, name_col]].values.tolist())
        for code, name in hits[[code_col, name_col]].values.tolist():
            try:
                d = ak.stock_hk_index_daily_em(symbol=str(code))
                d.to_csv(os.path.join(OUT, "ak", f"hkidx_{code}.csv"), index=False)
                log("ak index", code, name, len(d))
            except Exception as e:  # noqa: BLE001
                log("ak index ERR", code, e)
            time.sleep(1)
    except Exception as e:  # noqa: BLE001
        log("ak index list ERR", e)
    for c in PEERS:
        code = f"{int(c):05d}"
        for ind in ("报告期", "年度"):
            try:
                d = ak.stock_financial_hk_analysis_indicator_em(symbol=code, indicator=ind)
                d.to_csv(os.path.join(OUT, "ak", f"ind_{code}_{'period' if ind == '报告期' else 'year'}.csv"), index=False)
                log("ak indicators", code, ind, len(d))
            except Exception as e:  # noqa: BLE001
                log("ak indicators ERR", code, ind, e)
            time.sleep(1)
        try:
            d = ak.stock_financial_hk_report_em(stock=code, symbol="利润表", indicator="报告期")
            d.to_csv(os.path.join(OUT, "ak", f"is_{code}.csv"), index=False)
            log("ak income", code, len(d))
        except Exception as e:  # noqa: BLE001
            log("ak income ERR", code, e)
        time.sleep(1)
except Exception as e:  # noqa: BLE001
    log("akshare unavailable", e)


# ---------- HKEXnews ----------
def hkex_list(code, ranges):
    raw = get(f"https://www1.hkexnews.hk/search/prefix.do?&callback=callback&lang=EN&type=A&name={int(code):05d}&market=SEHK").decode()
    sid = re.search(r'"stockId"\s*:\s*(\d+)', raw).group(1)
    items = []
    for frm, to in ranges:
        url = ("https://www1.hkexnews.hk/search/titleSearchServlet.do?sortDir=0&sortByOptions=DateTime&category=0"
               f"&market=SEHK&stockId={sid}&documentType=-1&fromDate={frm}&toDate={to}&title=&searchType=0"
               "&t1code=-2&t2Gcode=-2&t2code=-2&rowRange=1000&lang=E")
        js = json.loads(get(url))
        items += json.loads(js["result"]) if isinstance(js.get("result"), str) else (js.get("result") or [])
        time.sleep(1)
    return items


def save_pdf_text(it, folder, prefix="", maxpages=0):
    d = it.get("DATE_TIME", "")[:10]
    dd = f"{d[6:10]}-{d[3:5]}-{d[0:2]}" if len(d) == 10 else "unknown"
    slug = re.sub(r"[^A-Za-z0-9]+", "_", (it.get("TITLE") or "doc"))[:60].strip("_")
    path = os.path.join(folder, f"{prefix}{dd}_{slug}.txt")
    if os.path.exists(path):
        return
    pdf = get("https://www1.hkexnews.hk" + it["FILE_LINK"])
    open("/tmp/doc.pdf", "wb").write(pdf)
    text = extract_text("/tmp/doc.pdf", maxpages=maxpages)
    open(path, "w").write(text)
    log("saved", path, len(text))


KEEP = re.compile(r"(ANNUAL RESULTS|INTERIM RESULTS|PROFIT ALERT|POSITIVE PROFIT|PLACING|INSIDE INFORMATION|"
                  r"VOLUNTARY ANNOUNCEMENT|LICENS|COLLABORATION|BUY-BACK|REPURCHASE|SPIN-OFF|"
                  r"FINAL DIVIDEND|SPECIAL DIVIDEND|PROFIT WARNING|BUSINESS UPDATE)", re.I)
SKIP = re.compile(r"(NOTIFICATION LETTER|PROXY FORM|NOTICE OF|NEXT DAY DISCLOSURE|MONTHLY RETURN|POLL RESULTS|"
                  r"FORM OF|LIST OF DIRECTORS)", re.I)
try:
    items = hkex_list("1530", (("20190101", "20211231"), ("20220101", "20241231"), ("20250101", "20261023")))
    json.dump(items, open(os.path.join(OUT, "hkex", "announcements.json"), "w"), ensure_ascii=False, indent=1)
    log("HKEX 1530 items", len(items))
    for it in items:
        title = " ".join(str(it.get(k) or "") for k in ("TITLE", "SHORT_TEXT", "LONG_TEXT"))
        if not (it.get("FILE_LINK") or "").lower().endswith(".pdf") or not KEEP.search(title) or SKIP.search(title):
            continue
        if it.get("DATE_TIME", "")[6:10] < "2021":
            continue
        try:
            save_pdf_text(it, os.path.join(OUT, "hkex"))
        except Exception as e:  # noqa: BLE001
            log("pdf ERR", it.get("FILE_LINK"), e)
        time.sleep(0.5)
except Exception as e:  # noqa: BLE001
    log("HKEX 1530 ERR", e)

# peers: latest annual and interim results announcements (first pages hold the highlights)
for c, name in PEERS.items():
    if c == "1530":
        continue
    try:
        items = hkex_list(c, (("20250101", "20261023"),))
        res = [it for it in items if re.search(r"(ANNUAL|INTERIM) RESULTS", it.get("TITLE") or "", re.I)
               and (it.get("FILE_LINK") or "").lower().endswith(".pdf")]
        log("HKEX", c, name, len(items), "results docs", len(res))
        for it in res[:4]:
            try:
                save_pdf_text(it, os.path.join(OUT, "peers_hkex"), prefix=f"{int(c):04d}_", maxpages=30)
            except Exception as e:  # noqa: BLE001
                log("peer pdf ERR", c, e)
            time.sleep(0.5)
    except Exception as e:  # noqa: BLE001
        log("HKEX peer ERR", c, e)
log("done")
