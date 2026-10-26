"""Download market data and filings for <公司>（<代码>） and its peers.

Template from the stock-analysis-report skill. Copy to <slug>_analysis/scripts/fetch_data.py and edit CONFIG.
Runs where the internet is open (GitHub Actions via .github/workflows/fetch-market-data.yml, or a local machine);
everything lands in <slug>_analysis/data/raw/ in the layout analyze_market.py expects:
  yahoo/<ticker>.csv   prices for the stock, peers, indices, FX (Date, Adj Close, Close, High, Low, Open, Volume)
  idx/csindex_<code>.csv   CSI indices incl. total-return versions (A-shares)
  rates/               bond_zh_us_rate.csv (China/US government yields) or fred_<id>.csv (US)
  fin/                 statements, indicators, dividends, valuation history, research list, news (akshare)
  filings/, peers_filings/   text of the company's filings and peers' latest annual / interim reports
A failed source is logged and skipped; read the Actions log, then add a second script (fetch_extra.py) for gaps.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "report_kit"))
import fetchlib as fl  # noqa: E402

# ============================================================ CONFIG (edit)
SLUG = os.path.basename(os.path.dirname(HERE))          # <slug>_analysis
OUT = os.path.join(SLUG, "data", "raw")
MARKET = "US"                                            # "A", "HK" or "US"
TARGET = "MSFT"
PEERS = {"AAPL": "Apple", "GOOGL": "Alphabet"}      # 10-15 listed peers in the same market
START, END = "2024-01-01", "2026-10-27"                 # END exclusive for Yahoo; use tomorrow's date
SEC_CIK, SEC_CONTACT = "789019", "research@example.com"       # US only; SEC wants a descriptive User-Agent (never the user's own email)
SEC_FORMS = {"n10q": 1, "n10k": 1, "since8k": "2026-07-01"}  # how many 10-Q / 10-K and which 8-K press releases to convert
FILINGS_SINCE = "2026-01-01"
MAX_FILINGS, MAX_PEER_DOCS = 3, 1                     # caps on PDFs converted to text (they dominate run time)
EXTRA_YAHOO = []                                        # e.g. sector ETFs, ADRs, H-shares, commodity proxies
CSINDEX = ["000300", "H00300", "000922", "H00922"]      # A-share: CSI 300 / CSI Dividend, price and total return
# keep / skip patterns for which filings to convert to text (titles)
KEEP_CN = r"(年度报告|半年度报告|季度报告|业绩预告|业绩快报|收购|出售|重大资产|关联交易|分红|利润分配|权益分派|回购|增持|减持|股权激励|定增|发行|融资|债券|投资|规划|经营数据|诉讼|处罚|问询)"
SKIP_CN = r"(摘要|英文|English|提示性|法律意见|核查意见|独立董事|监事会|决议|通知|更正|补充|保荐|持续督导|取消|延期|候选人|辞职|聘任|章程|制度|规则|内部控制|社会责任|ESG|可持续发展|鉴证|审计报告|专项说明|评估报告|备查|自查|承诺)"
KEEP_HK = r"(ANNUAL RESULTS|INTERIM RESULTS|QUARTERLY|PROFIT ALERT|POSITIVE PROFIT|PROFIT WARNING|PLACING|INSIDE INFORMATION|VOLUNTARY ANNOUNCEMENT|LICENS|COLLABORATION|ACQUISITION|DISPOSAL|BUY-BACK|REPURCHASE|SPIN-OFF|DIVIDEND|BUSINESS UPDATE)"
SKIP_HK = r"(NOTIFICATION LETTER|PROXY FORM|NOTICE OF|NEXT DAY DISCLOSURE|MONTHLY RETURN|POLL RESULTS|FORM OF|LIST OF DIRECTORS)"

for sub in ("yahoo", "idx", "rates", "fin", "filings", "peers_filings"):
    os.makedirs(os.path.join(OUT, sub), exist_ok=True)
tk = lambda c: (f"{c}.{'SS' if c[0] in '69' else 'SZ'}" if MARKET == "A" else f"{int(c):04d}.HK" if MARKET == "HK" else c)  # noqa: E731

# ============================================================ prices (Yahoo, all markets)
INDICES = {"A": [], "HK": ["^HSI", "^HSCE", "^IRX", "CNY=X", "HKDCNY=X"], "US": ["^GSPC", "^SP500TR", "^VIX", "^IRX", "^TNX", "SPY", "QQQ"]}[MARKET]
fl.yahoo_prices([tk(TARGET)] + [tk(c) for c in PEERS] + INDICES + EXTRA_YAHOO + (["CNY=X", "HKDCNY=X"] if MARKET == "A" else []),
                START, END, os.path.join(OUT, "yahoo"))
fl.yahoo_extras(tk(TARGET), os.path.join(OUT, "yahoo"), options=(MARKET == "US"))
if MARKET in ("HK", "US"):  # peer valuation / profitability snapshot for the peer table (A-shares use Eastmoney instead)
    fl.yahoo_infos([tk(c) for c in PEERS], os.path.join(OUT, "yahoo"))

# ============================================================ market-specific sources
if MARKET == "A":
    import akshare as ak
    s, e = START.replace("-", ""), END.replace("-", "")
    for code in CSINDEX:  # CSI's own site; Yahoo's A-share index series are unreliable
        fl.tryit(f"csindex {code}", lambda: ak.stock_zh_index_hist_csindex(symbol=code, start_date=s, end_date=e), os.path.join(OUT, "idx", f"csindex_{code}.csv"))
    fl.tryit("bond yields", lambda: ak.bond_zh_us_rate(start_date=s), os.path.join(OUT, "rates", "bond_zh_us_rate.csv"))
    # Shenwan industry indices whose names match the sector, for checking the equal-weight peer index
    SW_PATTERN = r"公路|高速"  # edit
    try:
        for fn_name in ("sw_index_second_info", "sw_index_third_info"):
            info = getattr(ak, fn_name)()
            name_col = next(c for c in info.columns if "名称" in c)
            code_col = next(c for c in info.columns if "代码" in c)
            for code, name in info[[code_col, name_col]].values.tolist():
                if re.search(SW_PATTERN, str(name)):
                    c = str(code).split(".")[0]
                    fl.tryit(f"sw {c} {name}", lambda: ak.index_hist_sw(symbol=c, period="day"), os.path.join(OUT, "idx", f"sw_{c}.csv"))
    except Exception as ex:  # noqa: BLE001
        fl.log("ERR sw", repr(ex)[:200])
    mk = lambda c: "SH" if c[0] in "69" else "SZ"  # noqa: E731
    for code in [TARGET] + list(PEERS):
        F = lambda kind: os.path.join(OUT, "fin", f"{kind}_{code}.csv")  # noqa: E731
        fl.tryit(f"is {code}", lambda: ak.stock_profit_sheet_by_report_em(symbol=mk(code) + code), F("is"))
        fl.tryit(f"bs {code}", lambda: ak.stock_balance_sheet_by_report_em(symbol=mk(code) + code), F("bs"))
        fl.tryit(f"cf {code}", lambda: ak.stock_cash_flow_sheet_by_report_em(symbol=mk(code) + code), F("cf"))
        fl.tryit(f"ind {code}", lambda: ak.stock_financial_analysis_indicator_em(symbol=f"{code}.{mk(code)}", indicator="按报告期"), F("ind"))
        fl.tryit(f"div {code}", lambda: ak.stock_fhps_detail_em(symbol=code), F("div"))
        fl.tryit(f"value {code}", lambda: ak.stock_value_em(symbol=code), F("value"))
    fl.tryit("research", lambda: ak.stock_research_report_em(symbol=TARGET), os.path.join(OUT, "fin", f"research_{TARGET}.csv"))
    fl.tryit("news", lambda: ak.stock_news_em(symbol=TARGET), os.path.join(OUT, "fin", f"news_{TARGET}.csv"))
    fl.tryit("holders", lambda: ak.stock_main_stock_holder(stock=TARGET), os.path.join(OUT, "fin", f"holders_{TARGET}.csv"))
    # filings: the company's own (full text), peers' latest annual + interim reports (first 45 pages)
    try:
        orgs = fl.cninfo_org_ids()
        items = fl.cninfo_list(TARGET, orgs[TARGET], FILINGS_SINCE, END)
        json.dump(items, open(os.path.join(OUT, "filings", "announcements.json"), "w"), ensure_ascii=False, indent=1)
        picked = [it for it in items if re.search(KEEP_CN, it["announcementTitle"]) and not re.search(SKIP_CN, it["announcementTitle"])
                  and it["url"].upper().endswith(".PDF")]
        fl.log("cninfo items", len(items), "picked", len(picked))
        for it in picked[:MAX_FILINGS]:
            try:
                fl.cninfo_save_text(it, os.path.join(OUT, "filings"))
            except Exception as ex:  # noqa: BLE001
                fl.log("pdf ERR", it["url"], repr(ex)[:200])
            time.sleep(0.4)
        for code, name in PEERS.items():
            try:
                docs = [it for it in fl.cninfo_list(code, orgs[code], f"{int(END[:4]) - 1}-01-01", END, "category_ndbg_szsh;category_bndbg_szsh")
                        if not re.search("摘要|英文|English|更正|补充", it["announcementTitle"])]
                for it in docs[:MAX_PEER_DOCS]:
                    fl.cninfo_save_text(it, os.path.join(OUT, "peers_filings"), prefix=f"{code}_", last_page=45)
            except Exception as ex:  # noqa: BLE001
                fl.log("peer cninfo ERR", code, repr(ex)[:200])
    except Exception as ex:  # noqa: BLE001
        fl.log("ERR cninfo", repr(ex)[:300])

elif MARKET == "HK":
    try:
        import akshare as ak
        for code in [TARGET] + list(PEERS):
            c5 = f"{int(code):05d}"
            fl.tryit(f"ind {c5}", lambda: ak.stock_financial_hk_analysis_indicator_em(symbol=c5, indicator="报告期"), os.path.join(OUT, "fin", f"ind_{c5}.csv"))
            fl.tryit(f"is {c5}", lambda: ak.stock_financial_hk_report_em(stock=c5, symbol="利润表", indicator="报告期"), os.path.join(OUT, "fin", f"is_{c5}.csv"))
            fl.tryit(f"bs {c5}", lambda: ak.stock_financial_hk_report_em(stock=c5, symbol="资产负债表", indicator="报告期"), os.path.join(OUT, "fin", f"bs_{c5}.csv"))
    except Exception as ex:  # noqa: BLE001
        fl.log("akshare HK ERR", repr(ex)[:200])
    try:
        yr = int(END[:4])
        ranges = [(f"{y}0101", f"{min(y + 2, yr)}1231") for y in range(int(FILINGS_SINCE[:4]), yr + 1, 3)]
        items = fl.hkex_list(TARGET, ranges)
        json.dump(items, open(os.path.join(OUT, "filings", "announcements.json"), "w"), ensure_ascii=False, indent=1)
        n_saved = 0
        for it in items:
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

else:  # US
    fl.fred(["DGS3MO", "DGS10", "BAMLH0A0HYM2"], os.path.join(OUT, "rates"))
    if SEC_CIK:
        fl.sec_company(SEC_CIK, os.path.join(OUT, "filings"), SEC_CONTACT, **SEC_FORMS)
fl.log("done")
