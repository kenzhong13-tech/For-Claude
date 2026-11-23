"""Download market data and filings for 上海电力（600021.SH） and its A-share power-generation peers, plus coal prices
and national power demand for the sensitivity analysis.

From the stock-analysis-report skill's fetch template. Runs on GitHub Actions (.github/workflows/fetch-market-data.yml);
everything lands in shpower_analysis/data/raw/:
  yahoo/<ticker>.csv   prices for the stock, peers, international coal futures, FX (Date, Adj Close, Close, ...)
  idx/csindex_<code>.csv   CSI indices incl. total-return versions; idx/sw_<code>.csv Shenwan power indices
  power/               thermal-coal spot and futures prices, coking coal, monthly power consumption (全社会用电量)
  rates/               bond_zh_us_rate.csv (China/US government yields)
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
MARKET = "A"                                            # "A", "HK" or "US"
TARGET = "600021"
PEERS = {  # A-share power generators: the large national groups' listed arms, then regional generators, then SPIC's 吉电股份
    "600011": "华能国际", "600027": "华电国际", "600795": "国电电力", "601991": "大唐发电",
    "600023": "浙能电力", "600642": "申能股份", "000539": "粤电力A", "000027": "深圳能源", "000543": "皖能电力",
    "600578": "京能电力", "600863": "内蒙华电", "002608": "江苏国信", "600483": "福能股份", "000875": "吉电股份",
}
START, END = "2014-01-01", "2026-11-24"                 # END exclusive for Yahoo; use tomorrow's date
SEC_CIK, SEC_CONTACT = "", "research@example.com"       # US only; SEC wants a descriptive User-Agent (never the user's own email)
SEC_FORMS = {"n10q": 6, "n10k": 2, "since8k": "2024-01-01"}  # how many 10-Q / 10-K and which 8-K press releases to convert
FILINGS_SINCE = "2019-01-01"
MAX_FILINGS, MAX_PEER_DOCS = 140, 2                     # caps on PDFs converted to text (they dominate run time)
EXTRA_YAHOO = ["MTF=F", "NCF=F", "2380.HK"]             # Rotterdam and Newcastle coal futures; 中国电力 (SPIC's HK power arm)
CSINDEX = ["000300", "H00300", "000922", "H00922", "000995", "H00995"]  # CSI 300, CSI Dividend, CSI All Share Utilities
# keep / skip patterns for which filings to convert to text (titles)
KEEP_CN = r"(年度报告|半年度报告|季度报告|业绩预|业绩快报|发电量|上网电价|经营数据|收购|出售|转让|重大资产|重组|关联交易|分红|利润分配|权益分派|回购|增持|减持|股权激励|向特定对象|非公开发行|定增|可转换|投资|项目|规划|诉讼|仲裁|处罚|问询|巴基斯坦|土耳其|K-Electric|KE公司)"
SKIP_CN = r"(摘要|英文|English|提示性|法律意见|核查意见|独立董事|监事会|决议|通知|更正|补充|保荐|持续督导|取消|延期|候选人|辞职|聘任|章程|制度|规则|内部控制|社会责任|ESG|可持续发展|鉴证|审计报告|专项说明|评估报告|备查|自查|承诺|担保|超短期融资券|短期融资券|中期票据|公司债券|发行结果|兑付|付息|跟踪评级|日常关联交易|预计)"
KEEP_HK = r"(ANNUAL RESULTS|INTERIM RESULTS|QUARTERLY|PROFIT ALERT|POSITIVE PROFIT|PROFIT WARNING|PLACING|INSIDE INFORMATION|VOLUNTARY ANNOUNCEMENT|LICENS|COLLABORATION|ACQUISITION|DISPOSAL|BUY-BACK|REPURCHASE|SPIN-OFF|DIVIDEND|BUSINESS UPDATE)"
SKIP_HK = r"(NOTIFICATION LETTER|PROXY FORM|NOTICE OF|NEXT DAY DISCLOSURE|MONTHLY RETURN|POLL RESULTS|FORM OF|LIST OF DIRECTORS)"

for sub in ("yahoo", "idx", "power", "rates", "fin", "filings", "peers_filings"):
    os.makedirs(os.path.join(OUT, sub), exist_ok=True)
tk = lambda c: (f"{c}.{'SS' if c[0] in '69' else 'SZ'}" if MARKET == "A" else f"{int(c):04d}.HK" if MARKET == "HK" else c)  # noqa: E731

# ============================================================ prices (Yahoo, all markets)
INDICES = {"A": [], "HK": ["^HSI", "^HSCE", "^IRX", "CNY=X", "HKDCNY=X"], "US": ["^GSPC", "^SP500TR", "^VIX", "^IRX", "^TNX", "SPY", "QQQ"]}[MARKET]
fl.yahoo_prices([tk(TARGET)] + [tk(c) for c in PEERS] + INDICES + EXTRA_YAHOO + (["CNY=X", "HKDCNY=X"] if MARKET == "A" else []),
                START, END, os.path.join(OUT, "yahoo"))
fl.yahoo_extras(tk(TARGET), os.path.join(OUT, "yahoo"), options=(MARKET == "US"))
if MARKET in ("HK", "US"):  # peer valuation / profitability snapshot for the peer table (A-shares use Eastmoney instead)
    fl.yahoo_infos([tk(c) for c in PEERS], os.path.join(OUT, "yahoo"))

# ============================================================ coal prices and power demand
# Thermal coal is the main fuel cost of coal-fired generators. The ZCE thermal-coal futures stopped trading in 2022, so the
# domestic price comes from spot series (99qh / 100ppi, Qinhuangdao-type 5500 kcal coal) with futures and coking coal as
# context; Yahoo's Rotterdam and Newcastle futures are the international prices. 全社会用电量 is national power demand.
try:
    import akshare as ak
    s, e = START.replace("-", ""), END.replace("-", "")
    P = lambda name: os.path.join(OUT, "power", f"{name}.csv")  # noqa: E731
    fl.tryit("society electricity", lambda: ak.macro_china_society_electricity(), P("society_electricity"))
    for sym in ("ZC0", "JM0", "J0"):
        fl.tryit(f"sina main {sym}", lambda: ak.futures_main_sina(symbol=sym, start_date=s, end_date=e), P(f"main_{sym}"))
    names = []
    try:
        table = ak.spot_price_table_qh()
        fl.save_df(table, P("qh_spot_table"))
        names = [n for n in table["品种名称"].astype(str) if "煤" in n or "焦炭" in n]
    except Exception as ex:  # noqa: BLE001
        fl.log("ERR qh table", repr(ex)[:200])
    for n in names or ["动力煤", "焦煤", "焦炭"]:
        fl.tryit(f"qh spot {n}", lambda: ak.spot_price_qh(symbol=n), P(f"qh_spot_{n}"))
    if not os.path.exists(P("qh_spot_动力煤")):  # fallback: 100ppi spot table, sampled weekly (one page per date)
        import pandas as pd
        rows, t0 = [], time.time()
        for d in pd.date_range("2016-01-01", END, freq="W-FRI"):
            if time.time() - t0 > 900 or (len(rows) == 0 and d > pd.Timestamp("2016-03-31")):
                break
            try:
                df = ak.futures_spot_price(date=d.strftime("%Y%m%d"), symbols="ZC")
                if df is not None and len(df):
                    rows.append(df.assign(sample_date=d.date()))
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.3)
        if rows:
            fl.save_df(pd.concat(rows), P("100ppi_ZC_weekly"))
        fl.log("100ppi ZC weeks", len(rows))
except Exception as ex:  # noqa: BLE001
    fl.log("ERR coal and power", repr(ex)[:300])

# ============================================================ market-specific sources
if MARKET == "A":
    import akshare as ak
    s, e = START.replace("-", ""), END.replace("-", "")
    for code in CSINDEX:  # CSI's own site; Yahoo's A-share index series are unreliable
        fl.tryit(f"csindex {code}", lambda: ak.stock_zh_index_hist_csindex(symbol=code, start_date=s, end_date=e), os.path.join(OUT, "idx", f"csindex_{code}.csv"))
    fl.tryit("bond yields", lambda: ak.bond_zh_us_rate(start_date=s), os.path.join(OUT, "rates", "bond_zh_us_rate.csv"))
    # Shenwan industry indices whose names match the sector, for checking the equal-weight peer index
    SW_PATTERN = r"电力|发电|火电|水电|风电|光伏|核电|热力"  # edit
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
        picked = fl.by_priority(picked, "announcementTitle", r"年度报告|季度报告|业绩预|业绩快报|发电量")  # periodic reports first
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
        for it in fl.by_priority(items, "TITLE", r"RESULTS|ANNUAL REPORT|INTERIM REPORT|PROFIT ALERT|PROFIT WARNING"):
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
