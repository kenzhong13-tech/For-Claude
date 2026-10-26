"""Download helpers for the fetch scripts (run on a GitHub Actions runner or any machine with open internet).

Every helper logs and swallows its own errors so one failed source never stops the rest of the run; read the
Actions log afterwards to see what is missing. Known-good endpoints and parameters as of 2026:
- Yahoo Finance via yfinance (all markets; A-share stocks work, A-share indices do not - use CSI's site via akshare)
- akshare: Eastmoney *datacenter* endpoints (statements, dividends, valuation history, research, news) work from
  GitHub runners; Eastmoney *quote* endpoints (push2 / push2his: stock_zh_a_hist, index_zh_a_hist ...) refuse them
- cninfo (A-share filings), HKEXnews (HK filings), SEC EDGAR (US filings, needs a User-Agent with contact info), FRED
"""
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def log(*a):
    print(*a, flush=True)


def http(url, data=None, headers=None, timeout=90):
    hdr = {"User-Agent": UA, "Accept": "*/*"}
    hdr.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=hdr), timeout=timeout) as r:
        return r.read()


def save_df(df, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)
    log("saved", path, len(df))


def tryit(label, fn, path, pause=0.8):
    """Run fn() -> DataFrame and save it to path; log and continue on any error."""
    try:
        df = fn()
        if df is not None and len(df):
            save_df(df, path)
        else:
            log("empty", label)
    except Exception as e:  # noqa: BLE001
        log("ERR", label, repr(e)[:300])
    time.sleep(pause)


# ---------------------------------------------------------------- Yahoo Finance
def yahoo_file(ticker):
    return "".join(ch if ch.isalnum() else "_" for ch in ticker.replace("^", "IDX_")) + ".csv"


def yahoo_prices(tickers, start, end, outdir, tries=3):
    """Daily OHLC + Adj Close (auto_adjust=False keeps both) to outdir/<ticker file>.csv. end is exclusive."""
    import pandas as pd
    import yfinance as yf
    os.makedirs(outdir, exist_ok=True)
    for t in tickers:
        for attempt in range(tries):
            try:
                df = yf.download(t, start=start, end=end, auto_adjust=False, progress=False, threads=False)
                if df is not None and len(df):
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    df.to_csv(os.path.join(outdir, yahoo_file(t)))
                    log("yahoo", t, len(df), str(df.index.min())[:10], str(df.index.max())[:10])
                    break
                log("yahoo empty", t)
            except Exception as e:  # noqa: BLE001
                log("yahoo ERR", t, repr(e)[:200])
            time.sleep(3 * (attempt + 1))
        time.sleep(1.0)


def yahoo_extras(ticker, outdir, options=False):
    """Company info, statements, earnings dates and (optionally) the option chain for one ticker."""
    import pandas as pd
    import yfinance as yf
    os.makedirs(outdir, exist_ok=True)
    tk = yf.Ticker(ticker)
    base = os.path.join(outdir, yahoo_file(ticker)[:-4])
    try:
        json.dump(tk.info, open(base + "_info.json", "w"), default=str, indent=1)
    except Exception as e:  # noqa: BLE001
        log("info ERR", ticker, repr(e)[:200])
    for attr in ("income_stmt", "balance_sheet", "cashflow", "quarterly_income_stmt", "quarterly_balance_sheet", "quarterly_cashflow"):
        try:
            getattr(tk, attr).to_csv(f"{base}_{attr}.csv")
        except Exception as e:  # noqa: BLE001
            log(attr, "ERR", repr(e)[:200])
    try:
        tk.get_earnings_dates(limit=16).to_csv(base + "_earnings_dates.csv")
    except Exception as e:  # noqa: BLE001
        log("earnings dates ERR", repr(e)[:200])
    if options:
        try:
            rows = []
            for ex in tk.options[:10]:
                ch = tk.option_chain(ex)
                for typ, d in (("call", ch.calls), ("put", ch.puts)):
                    d = d.copy()
                    d["type"], d["expiry"] = typ, ex
                    rows.append(d)
            pd.concat(rows).to_csv(base + "_options.csv", index=False)
            log("options rows", sum(len(r) for r in rows))
        except Exception as e:  # noqa: BLE001
            log("options ERR", repr(e)[:200])


# ---------------------------------------------------------------- FRED / Stooq (US rates and fallbacks)
def fred(series_ids, outdir):
    os.makedirs(outdir, exist_ok=True)
    for sid in series_ids:
        try:
            open(os.path.join(outdir, f"fred_{sid}.csv"), "wb").write(http(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"))
            log("fred", sid)
        except Exception as e:  # noqa: BLE001
            log("fred ERR", sid, repr(e)[:200])


# ---------------------------------------------------------------- SEC EDGAR
def sec_headers(contact):
    return {"User-Agent": f"research-script {contact}", "Accept-Encoding": "identity"}


def sec_company(cik, outdir, contact="research@example.com", n10q=6, n10k=2, since8k="2024-01-01"):
    """companyfacts (XBRL), submissions, and text of recent 10-K / 10-Q / 8-K exhibit 99 press releases."""
    from bs4 import BeautifulSoup
    os.makedirs(outdir, exist_ok=True)
    H = sec_headers(contact)
    cik10 = f"{int(cik):010d}"
    try:
        open(os.path.join(outdir, "companyfacts.json"), "wb").write(http(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json", headers=H))
        log("companyfacts ok")
    except Exception as e:  # noqa: BLE001
        log("companyfacts ERR", repr(e)[:200])
    try:
        subs = json.loads(http(f"https://data.sec.gov/submissions/CIK{cik10}.json", headers=H))
        json.dump(subs, open(os.path.join(outdir, "submissions.json"), "w"), indent=1)
        rec = subs["filings"]["recent"]
        filings = [dict(zip(rec.keys(), vals)) for vals in zip(*rec.values())]
    except Exception as e:  # noqa: BLE001
        log("submissions ERR", repr(e)[:200])
        return

    def text(raw):
        soup = BeautifulSoup(raw, "lxml")
        for tag in soup(["script", "style"]):
            tag.decompose()
        for tr in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            tr.replace_with(" | ".join(c for c in cells if c) + "\n")
        return re.sub(r"\n\s*\n+", "\n\n", soup.get_text("\n"))

    def save(f, url, label):
        try:
            name = f"{f['filingDate']}_{f['form'].replace('/', '-')}_{label}.txt"
            open(os.path.join(outdir, name), "w").write(text(http(url, headers=H)))
            log("saved", name)
        except Exception as e:  # noqa: BLE001
            log("doc ERR", url, repr(e)[:200])
        time.sleep(0.3)

    seen = {"10-K": 0, "10-Q": 0}
    for f in filings:
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{f['accessionNumber'].replace('-', '')}"
        form = f["form"]
        if form in seen and seen[form] < (n10k if form == "10-K" else n10q):
            seen[form] += 1
            save(f, f"{base}/{f['primaryDocument']}", "main")
        elif form == "8-K" and f["filingDate"] >= since8k:
            try:
                idx = json.loads(http(f"{base}/index.json", headers=H))
                for item in idx["directory"]["item"]:
                    n = item["name"].lower()
                    if re.search(r"ex-?99", n) and n.endswith((".htm", ".html")):
                        save(f, f"{base}/{item['name']}", "ex99_" + re.sub(r"[^a-z0-9]", "", n)[:30])
            except Exception as e:  # noqa: BLE001
                log("index ERR", base, repr(e)[:200])


# ---------------------------------------------------------------- cninfo (Shanghai / Shenzhen filings)
CNINFO_Q = "http://www.cninfo.com.cn/new/hisAnnouncement/query"


def cninfo_org_ids():
    """{code: orgId} for all A-shares (the query API needs 'code,orgId')."""
    js = json.loads(http("http://www.cninfo.com.cn/new/data/szse_stock.json"))
    return {s["code"]: s["orgId"] for s in js["stockList"]}


def cninfo_list(code, org, start, end, category=""):
    """Announcement list (dicts with announcementTitle, adjunctUrl, date). category e.g.
    'category_ndbg_szsh' (annual), 'category_bndbg_szsh' (interim), 'category_yjdbg_szsh;category_sjdbg_szsh' (quarterly)."""
    hdr = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Origin": "http://www.cninfo.com.cn",
           "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search", "Accept": "application/json, text/plain, */*"}
    items, page = [], 1
    while page < 150:
        form = {"pageNum": page, "pageSize": 30, "column": "szse", "tabName": "fulltext", "plate": "", "stock": f"{code},{org}",
                "searchkey": "", "secid": "", "category": category, "trade": "", "seDate": f"{start}~{end}",
                "sortName": "", "sortType": "", "isHLtitle": "true"}
        js = json.loads(http(CNINFO_Q, urllib.parse.urlencode(form).encode(), hdr))
        anns = js.get("announcements") or []
        items += anns
        if not js.get("hasMore") or not anns:
            break
        page += 1
        time.sleep(0.6)
    for it in items:
        it["announcementTitle"] = re.sub("<[^>]+>", "", it.get("announcementTitle") or "")
        it["date"] = time.strftime("%Y-%m-%d", time.gmtime((it.get("announcementTime") or 0) / 1000 + 8 * 3600))
        it["url"] = "https://static.cninfo.com.cn/" + (it.get("adjunctUrl") or "")
    return items


def pdf_to_text(pdf_bytes, path, last_page=0):
    """Text of a PDF with poppler's pdftotext -layout (keeps table columns); falls back to pdfminer."""
    tmp = "/tmp/_doc.pdf"
    open(tmp, "wb").write(pdf_bytes)
    try:
        cmd = ["pdftotext", "-layout", "-enc", "UTF-8"] + (["-l", str(last_page)] if last_page else []) + [tmp, path]
        subprocess.run(cmd, check=True, timeout=300)
    except Exception:  # noqa: BLE001
        from pdfminer.high_level import extract_text
        open(path, "w").write(extract_text(tmp, maxpages=last_page or 0))
    log("saved", path, os.path.getsize(path))


def cninfo_save_text(it, folder, prefix="", last_page=0):
    os.makedirs(folder, exist_ok=True)
    title = re.sub(r"[\\/:*?\"<>|\s]+", "_", it["announcementTitle"])[:60]
    path = os.path.join(folder, f"{prefix}{it['date']}_{title}.txt")
    if not os.path.exists(path):
        pdf_to_text(http(it["url"], timeout=180), path, last_page)


# ---------------------------------------------------------------- HKEXnews (Hong Kong filings)
def hkex_list(code, ranges):
    """Announcements for an HK code over [(YYYYMMDD, YYYYMMDD)] ranges (keep each range under ~1000 items)."""
    raw = http(f"https://www1.hkexnews.hk/search/prefix.do?&callback=callback&lang=EN&type=A&name={int(code):05d}&market=SEHK").decode()
    sid = re.search(r'"stockId"\s*:\s*(\d+)', raw).group(1)
    items = []
    for frm, to in ranges:
        url = ("https://www1.hkexnews.hk/search/titleSearchServlet.do?sortDir=0&sortByOptions=DateTime&category=0"
               f"&market=SEHK&stockId={sid}&documentType=-1&fromDate={frm}&toDate={to}&title=&searchType=0"
               "&t1code=-2&t2Gcode=-2&t2code=-2&rowRange=1000&lang=E")
        js = json.loads(http(url))
        items += json.loads(js["result"]) if isinstance(js.get("result"), str) else (js.get("result") or [])
        time.sleep(1)
    for it in items:
        d = (it.get("DATE_TIME") or "")[:10]  # dd/mm/yyyy
        it["date"] = f"{d[6:10]}-{d[3:5]}-{d[0:2]}" if len(d) == 10 else ""
        it["url"] = "https://www1.hkexnews.hk" + (it.get("FILE_LINK") or "")
    return items


def hkex_save_text(it, folder, prefix="", last_page=0):
    os.makedirs(folder, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", (it.get("TITLE") or "doc"))[:60].strip("_")
    path = os.path.join(folder, f"{prefix}{it['date']}_{slug}.txt")
    if not os.path.exists(path):
        pdf_to_text(http(it["url"], timeout=180), path, last_page)
