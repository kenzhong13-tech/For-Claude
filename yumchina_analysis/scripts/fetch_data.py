"""Download market data, options and filings for 百胜中国 (Yum China, HKEX: 9987 / NYSE: YUMC) and its peers.

Built from the stock-analysis-report skill's fetch template (MARKET = "HK"), plus what this report needs on top:
  yahoo/      daily prices for 9987.HK, the NYSE line YUMC, 15 HK restaurant peers, indices, FX, global QSR peers;
              Yahoo info and statements; dividends; earnings dates; hourly (730 days) and 5-minute (60 days) bars
  options/    YUMC option chain snapshot (Yahoo, every expiry) and CBOE delayed quotes; attempts at implied-volatility
              history (alphaquery, Barchart); HKEX stock-option class list and the latest HKEX stock-options daily report
  sec/        SEC companyfacts (XBRL), submissions, recent 10-K / 10-Q and every 8-K exhibit-99 press release since 2016
  filings/    HKEXnews announcement list for 9987 (titles and dates) and the latest results announcements
  peers_filings/  each peer's latest annual and interim results (first 30 pages)
  fin/        Eastmoney HK indicators and statements for 9987 and peers; ET Net profit forecasts; Baidu valuation history
  macro/      China retail sales, CPI, consumer confidence (Eastmoney via akshare); NBS catering revenue if reachable
Runs on GitHub Actions (.github/workflows/fetch-market-data.yml); every source logs and continues on failure.
"""
import gzip
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "report_kit"))
import fetchlib as fl  # noqa: E402

# ============================================================ CONFIG
SLUG = os.path.basename(os.path.dirname(HERE))          # yumchina_analysis
OUT = os.path.join(SLUG, "data", "raw")
MARKET = "HK"
TARGET = "9987"
US_LINE = "YUMC"                                        # the same common stock, listed on the NYSE
PEERS = {"6862": "海底捞", "9658": "特海国际", "9922": "九毛九", "520": "呷哺呷哺", "1405": "达势股份", "999": "小菜园",
         "6831": "绿茶集团", "9869": "海伦司", "538": "味千(中国)", "341": "大家乐集团", "2150": "奈雪的茶", "2555": "茶百道",
         "2097": "蜜雪集团", "1364": "古茗", "2589": "沪上阿姨"}
GLOBAL_PEERS = ["YUM", "MCD", "SBUX", "QSR", "DPZ", "CMG", "LKNCY"]
START, END = "2016-01-01", "2026-11-27"                 # END exclusive: HK 2026-11-26 is complete; US was shut for Thanksgiving
SEC_CIK, SEC_CONTACT = "1673358", "research@example.com"  # SEC wants a descriptive User-Agent (never the user's own email)
SEC_FORMS = {"n10q": 3, "n10k": 2, "since8k": "2016-10-01"}  # every 8-K press release since the spin-off
FILINGS_SINCE = "2020-01-01"                            # HK listing: September 2020
MAX_FILINGS, MAX_PEER_DOCS = 4, 2                       # results are also in the SEC 8-Ks, so few HK PDFs
EXTRA_YAHOO = [US_LINE, "2800.HK", "2828.HK", "^GSPC", "^SP500TR", "^VIX", "^TNX", "CNH=X", "HKD=X", "^VHSI",
               "CHIQ", "KWEB", "MCHI", "HDL", "CHA"] + GLOBAL_PEERS
KEEP_HK = r"(RESULTS|DIVIDEND|BUY-BACK|REPURCHASE|INSIDE INFORMATION|VOLUNTARY ANNOUNCEMENT|ACQUISITION|DISPOSAL|INVESTOR DAY)"
SKIP_HK = r"(NOTIFICATION LETTER|PROXY FORM|NOTICE OF|NEXT DAY DISCLOSURE|MONTHLY RETURN|POLL RESULTS|FORM OF|LIST OF DIRECTORS)"
UA = fl.UA

for sub in ("yahoo", "options", "sec", "fin", "filings", "peers_filings", "macro"):
    os.makedirs(os.path.join(OUT, sub), exist_ok=True)
tk = lambda c: f"{int(c):04d}.HK"  # noqa: E731
now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
fl.log("run started", now_utc)


def save_bytes(path, data):
    open(path, "wb").write(data)
    fl.log("saved", path, len(data))


def attempt(label, url, path, headers=None, opener=None, limit=None):
    """GET url and keep the raw response (or the error) for inspection; returns the bytes or None."""
    try:
        if opener is not None:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            data = opener.open(req, timeout=60).read()
        else:
            data = fl.http(url, headers=headers, timeout=60)
        save_bytes(path, data[:limit] if limit else data)
        return data
    except Exception as e:  # noqa: BLE001
        fl.log("ERR", label, repr(e)[:200])
        open(path + ".err", "w").write(f"{url}\n{e!r}\n")
        return None


# ============================================================ prices and Yahoo extras
import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402

INDICES = ["^HSI", "^HSCE", "^IRX", "CNY=X", "HKDCNY=X"]
fl.yahoo_prices([tk(TARGET)] + [tk(c) for c in PEERS] + INDICES + EXTRA_YAHOO, START, END, os.path.join(OUT, "yahoo"))
fl.yahoo_extras(tk(TARGET), os.path.join(OUT, "yahoo"))
fl.yahoo_extras(US_LINE, os.path.join(OUT, "yahoo"))
fl.yahoo_infos([tk(c) for c in PEERS] + GLOBAL_PEERS, os.path.join(OUT, "yahoo"))
for t in (tk(TARGET), US_LINE):
    base = os.path.join(OUT, "yahoo", fl.yahoo_file(t)[:-4])
    try:
        yf.Ticker(t).dividends.to_csv(base + "_dividends.csv")
        fl.log("dividends", t)
    except Exception as e:  # noqa: BLE001
        fl.log("dividends ERR", t, repr(e)[:200])
    for period, interval in (("730d", "1h"), ("60d", "5m")):
        try:
            df = yf.download(t, period=period, interval=interval, auto_adjust=False, progress=False, threads=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.to_csv(f"{base}_{interval}.csv")
            fl.log("intraday", t, interval, len(df))
        except Exception as e:  # noqa: BLE001
            fl.log("intraday ERR", t, interval, repr(e)[:200])
        time.sleep(2)
try:  # all past earnings dates with release times (Yahoo keeps about ten years)
    yf.Ticker(US_LINE).get_earnings_dates(limit=48).to_csv(os.path.join(OUT, "yahoo", "YUMC_earnings_dates_all.csv"))
    fl.log("earnings dates all ok")
except Exception as e:  # noqa: BLE001
    fl.log("earnings dates all ERR", repr(e)[:200])

# ============================================================ options and implied volatility
OPT = os.path.join(OUT, "options")
try:  # Yahoo option chain, every expiry
    t = yf.Ticker(US_LINE)
    rows = []
    for ex in t.options:
        ch = t.option_chain(ex)
        for typ, d in (("call", ch.calls), ("put", ch.puts)):
            d = d.copy()
            d["type"], d["expiry"] = typ, ex
            rows.append(d)
        time.sleep(0.5)
    oc = pd.concat(rows)
    oc["snapshot_utc"] = now_utc
    oc.to_csv(os.path.join(OPT, "yumc_options_yahoo.csv"), index=False)
    fl.log("yahoo options rows", len(oc), "expiries", len(t.options))
except Exception as e:  # noqa: BLE001
    fl.log("yahoo options ERR", repr(e)[:200])
for kind in ("options", "quotes"):  # CBOE delayed quotes: full chain with IV and greeks, and the underlying with IV30
    attempt(f"cboe {kind}", f"https://cdn.cboe.com/api/global/delayed_quotes/{kind}/YUMC.json", os.path.join(OPT, f"cboe_{kind}_YUMC.json"))

# implied-volatility history, route 1: alphaquery (chart data behind its option-statistics pages)
for ident in ("iv-mean", "iv-call", "iv-put", "hv-close"):
    attempt(f"alphaquery {ident}", f"https://www.alphaquery.com/data/option-statistic-chart?ticker=YUMC&perType=30-Day&identifier={ident}",
            os.path.join(OPT, f"alphaquery_{ident}.json"))
    time.sleep(1)
attempt("alphaquery page", "https://www.alphaquery.com/stock/YUMC/volatility-option-statistics/30-day/iv-mean",
        os.path.join(OPT, "alphaquery_page.html"))

# route 2: Barchart (needs the XSRF cookie from a page visit)
try:
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    attempt("barchart page", "https://www.barchart.com/stocks/quotes/YUMC/volatility-charts", os.path.join(OPT, "barchart_page.html"),
            opener=opener, limit=400000)
    xsrf = next((urllib.parse.unquote(c.value) for c in cj if c.name == "XSRF-TOKEN"), "")
    fl.log("barchart xsrf", bool(xsrf))
    H = {"X-XSRF-TOKEN": xsrf, "Accept": "application/json", "Referer": "https://www.barchart.com/stocks/quotes/YUMC/volatility-charts"}
    cands = {
        "hist_iv": "https://www.barchart.com/proxies/core-api/v1/historical/get?symbol=YUMC&fields=tradeTime.format(Y-m-d),impliedVolatility,"
                   "historicVolatility,ivRank,ivPercentile&type=eod&orderBy=tradeTime&orderDir=desc&limit=3000&raw=1",
        "options_hist": "https://www.barchart.com/proxies/core-api/v1/options-historical/get?symbol=YUMC&fields=date,impliedVolatility,"
                        "historicVolatility&orderBy=date&orderDir=desc&limit=3000&raw=1",
        "quote": "https://www.barchart.com/proxies/core-api/v1/quotes/get?symbols=YUMC&fields=symbol,lastPrice,impliedVolatility,"
                 "historicVolatility30d,ivRank1y,ivPercentile1y,optionsImpliedVolatilityRank1y&raw=1",
    }
    for k, u in cands.items():
        attempt(f"barchart {k}", u, os.path.join(OPT, f"barchart_{k}.json"), headers=H, opener=opener)
        time.sleep(1.5)
except Exception as e:  # noqa: BLE001
    fl.log("barchart ERR", repr(e)[:200])

# HKEX: is there a 9987 stock-option class? Class list page and the latest stock-options daily report
attempt("hkex option classes", "https://www.hkex.com.hk/Products/Listed-Derivatives/Single-Stock/Stock-Options?sc_lang=en",
        os.path.join(OPT, "hkex_stock_option_classes.html"))
day = date.fromisoformat(END) - timedelta(days=1)
for _ in range(12):
    if day.weekday() < 5:
        data = attempt(f"hkex dqe {day}", f"https://www.hkex.com.hk/eng/stat/dmstat/dayrpt/dqe{day:%y%m%d}.htm",
                       os.path.join(OPT, f"hkex_dqe{day:%y%m%d}.htm"))
        if data:
            gzip.open(os.path.join(OPT, f"hkex_dqe{day:%y%m%d}.htm.gz"), "wb").write(data)
            os.remove(os.path.join(OPT, f"hkex_dqe{day:%y%m%d}.htm"))
            text = data.decode("latin-1")
            hits = [m.start() for m in re.finditer(r"YUM", text)]
            fl.log("hkex dqe", day, "bytes", len(data), "YUM hits", len(hits))
            break
    day -= timedelta(days=1)

# ============================================================ SEC (US filer: XBRL facts, 10-K / 10-Q, 8-K press releases)
fl.sec_company(SEC_CIK, os.path.join(OUT, "sec"), SEC_CONTACT, **SEC_FORMS)

# ============================================================ Eastmoney HK, ET Net, Baidu (akshare)
try:
    import akshare as ak

    def hk_report(c5, kind):
        try:  # akshare >= 1.20: symbol = code, indicator = statement, period = 年度 / 报告期
            return ak.stock_financial_hk_report_em(symbol=c5, indicator=kind, period="报告期")
        except TypeError:  # older versions: stock = code, symbol = statement
            return ak.stock_financial_hk_report_em(stock=c5, symbol=kind, indicator="报告期")

    for code in [TARGET] + list(PEERS):
        c5 = f"{int(code):05d}"
        fl.tryit(f"ind {c5}", lambda: ak.stock_financial_hk_analysis_indicator_em(symbol=c5, indicator="报告期"), os.path.join(OUT, "fin", f"ind_{c5}.csv"))
        fl.tryit(f"is {c5}", lambda: hk_report(c5, "利润表"), os.path.join(OUT, "fin", f"is_{c5}.csv"))
        fl.tryit(f"bs {c5}", lambda: hk_report(c5, "资产负债表"), os.path.join(OUT, "fin", f"bs_{c5}.csv"))
    c5 = f"{int(TARGET):05d}"
    fl.tryit("cf target", lambda: hk_report(c5, "现金流量表"), os.path.join(OUT, "fin", f"cf_{c5}.csv"))
    for ind in ("评级总览", "去年度业绩表现", "综合盈利预测", "盈利预测概览"):
        fl.tryit(f"forecast {ind}", lambda: ak.stock_hk_profit_forecast_et(symbol=c5, indicator=ind), os.path.join(OUT, "fin", f"forecast_{ind}.csv"))
    for ind in ("市盈率(TTM)", "市净率", "总市值"):
        fl.tryit(f"baidu {ind}", lambda: ak.stock_hk_valuation_baidu(symbol=c5, indicator=ind, period="全部"),
                 os.path.join(OUT, "fin", f"valuation_baidu_{re.sub(r'[^A-Za-z0-9一-龥]', '', ind)}.csv"))
    fl.tryit("dividend payout", lambda: ak.stock_hk_dividend_payout_em(symbol=c5), os.path.join(OUT, "fin", "dividend_payout_em.csv"))
    for kind in ("growth", "scale", "valuation"):
        fl.tryit(f"{kind} comparison", lambda: getattr(ak, f"stock_hk_{kind}_comparison_em")(symbol=c5), os.path.join(OUT, "fin", f"{kind}_comparison_em.csv"))
    fl.tryit("southbound holdings", lambda: ak.stock_hsgt_individual_em(symbol=c5), os.path.join(OUT, "fin", "southbound_holdings.csv"))
    # China consumption data
    fl.tryit("retail sales", ak.macro_china_consumer_goods_retail, os.path.join(OUT, "macro", "retail_sales.csv"))
    fl.tryit("consumer confidence", ak.macro_china_consumer_confidence, os.path.join(OUT, "macro", "consumer_confidence.csv"))
    fl.tryit("cpi", ak.macro_china_cpi, os.path.join(OUT, "macro", "cpi.csv"))
except Exception as ex:  # noqa: BLE001
    fl.log("akshare ERR", repr(ex)[:300])

# NBS: catering revenue (餐饮收入) sits under the retail-sales tree of the monthly database; walk the tree and keep the series
try:
    NBS = "https://data.stats.gov.cn/easyquery.htm"
    tree = {}

    def nbs_tree(node):
        body = urllib.parse.urlencode({"id": node, "dbcode": "hgyd", "wdcode": "zb", "m": "getTree"}).encode()
        kids = json.loads(fl.http(NBS, data=body, timeout=40))
        tree[node] = kids
        return kids

    found = []
    for k in nbs_tree("A07"):
        for g in (nbs_tree(k["id"]) if k.get("isParent") else []):
            if re.search("餐饮|社会消费品零售", g.get("name", "")):
                found.append(g)
        time.sleep(0.5)
    json.dump(tree, open(os.path.join(OUT, "macro", "nbs_tree_A07.json"), "w"), ensure_ascii=False, indent=1)
    for g in found[:6]:
        q = urllib.parse.urlencode({"m": "QueryData", "dbcode": "hgyd", "rowcode": "zb", "colcode": "sj", "wds": "[]",
                                    "dfwds": json.dumps([{"wdcode": "zb", "valuecode": g["id"]}, {"wdcode": "sj", "valuecode": "LAST150"}]),
                                    "k1": str(int(time.time() * 1000))})
        attempt(f"nbs {g['id']}", f"{NBS}?{q}", os.path.join(OUT, "macro", f"nbs_{g['id']}.json"))
        time.sleep(1)
except Exception as ex:  # noqa: BLE001
    fl.log("ERR nbs", repr(ex)[:300])

# ============================================================ HKEXnews: announcement list and a few results PDFs; peers' results
try:
    yr = int(END[:4])
    ranges = [(f"{y}0101", f"{min(y + 2, yr)}1231") for y in range(int(FILINGS_SINCE[:4]), yr + 1, 3)]
    items = fl.hkex_list(TARGET, ranges)
    json.dump(items, open(os.path.join(OUT, "filings", "announcements.json"), "w"), ensure_ascii=False, indent=1)
    fl.log("hkex items", len(items))
    n_saved = 0
    for it in fl.by_priority(items, "TITLE", r"RESULTS"):
        title = " ".join(str(it.get(k) or "") for k in ("TITLE", "SHORT_TEXT", "LONG_TEXT"))
        if n_saved >= MAX_FILINGS:
            break
        if it["url"].lower().endswith(".pdf") and re.search(KEEP_HK, title, re.I) and not re.search(SKIP_HK, title, re.I):
            n_saved += 1
            try:
                fl.hkex_save_text(it, os.path.join(OUT, "filings"))
            except Exception as ex:  # noqa: BLE001
                fl.log("pdf ERR", it["url"], repr(ex)[:200])
            time.sleep(0.5)
    for code in PEERS:
        try:
            res = [it for it in fl.hkex_list(code, [(f"{yr - 1}0101", END.replace("-", ""))])
                   if re.search(r"(ANNUAL|INTERIM) RESULTS", it.get("TITLE") or "", re.I) and it["url"].lower().endswith(".pdf")]
            for it in res[:MAX_PEER_DOCS]:
                fl.hkex_save_text(it, os.path.join(OUT, "peers_filings"), prefix=f"{int(code):04d}_", last_page=30)
        except Exception as ex:  # noqa: BLE001
            fl.log("peer HKEX ERR", code, repr(ex)[:200])
except Exception as ex:  # noqa: BLE001
    fl.log("ERR HKEX", repr(ex)[:300])
fl.log("done", datetime.now(timezone.utc).strftime("%H:%M UTC"))
