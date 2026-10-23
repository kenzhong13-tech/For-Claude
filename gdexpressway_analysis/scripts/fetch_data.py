"""Download market data and filings for 粤高速A (000429.SZ) and A-share expressway peers.

Runs on a GitHub Actions runner (open internet); outputs land in gdexpressway_analysis/data/raw/:
- Eastmoney daily prices (unadjusted and back-adjusted) for 粤高速A and 15 expressway peers; CSI 300, CSI Dividend,
  SZSE Component and sector indices (Shenwan, CSI, Eastmoney board); China/US government bond yields and LPR (akshare)
- Yahoo Finance daily prices as a cross-check, plus the B share (200429.SZ) and Yuexiu Transport (1052.HK)
- Eastmoney financial statements, main indicators, dividends, valuation history, research reports and news (akshare)
- cninfo announcement list for 000429 with the text of periodic reports and key announcements, and the first
  40 pages of the peers' latest annual and interim reports (pdftotext)
"""
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request

import akshare as ak
import pandas as pd
import yfinance as yf

OUT = "gdexpressway_analysis/data/raw"
for sub in ("", "em", "fin", "yahoo", "cninfo", "peers_cninfo"):
    os.makedirs(os.path.join(OUT, sub), exist_ok=True)
START, END = "20140101", "20261024"
PEERS = {  # A-share code -> name
    "000429": "粤高速A", "600377": "宁沪高速", "001965": "招商公路", "600350": "山东高速", "600548": "深高速",
    "600012": "皖通高速", "601107": "四川成渝", "600269": "赣粤高速", "600033": "福建高速", "000900": "现代投资",
    "600035": "楚天高速", "600020": "中原高速", "000828": "东莞控股", "601518": "吉林高速", "601188": "龙江交通",
    "600368": "五洲交通",
}
INDICES = {"000300": "沪深300", "000922": "中证红利", "399001": "深证成指", "000001": "上证指数", "399324": "深证红利"}
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def log(*a):
    print(*a, flush=True)


def save(df, *path):
    df.to_csv(os.path.join(OUT, *path), index=False)
    log("saved", "/".join(path), len(df))


def tryit(label, fn, *path, pause=0.8):
    try:
        df = fn()
        if df is not None and len(df):
            save(df, *path)
        else:
            log("empty", label)
    except Exception as e:  # noqa: BLE001
        log("ERR", label, repr(e)[:300])
    time.sleep(pause)


def market(code):
    return "SH" if code.startswith("6") else "SZ"


# ---------- Eastmoney prices ----------
for code in PEERS:
    for adj in ("", "hfq"):
        tryit(f"price {code} {adj}", lambda: ak.stock_zh_a_hist(symbol=code, period="daily", start_date=START,
                                                                 end_date=END, adjust=adj, timeout=60),
              "em", f"{code}_{adj or 'raw'}.csv")
for code, name in INDICES.items():
    tryit(f"index {code}", lambda: ak.index_zh_a_hist(symbol=code, period="daily", start_date=START, end_date=END),
          "em", f"idx_{code}.csv")
    if not os.path.exists(os.path.join(OUT, "em", f"idx_{code}.csv")):
        pre = "sh" if code.startswith("000") else "sz"
        tryit(f"index em {code}", lambda: ak.stock_zh_index_daily_em(symbol=pre + code, start_date=START, end_date=END),
              "em", f"idx_{code}.csv")

# sector indices: Shenwan, CSI and Eastmoney boards whose names mention expressways / roads
try:
    for fn_name in ("sw_index_second_info", "sw_index_third_info"):
        info = getattr(ak, fn_name)()
        save(info, "em", f"{fn_name}.csv")
        name_col = next(c for c in info.columns if "名称" in c)
        code_col = next(c for c in info.columns if "代码" in c)
        for code, name in info[[code_col, name_col]].values.tolist():
            if re.search("公路|高速|铁路", str(name)):
                c = str(code).split(".")[0]
                tryit(f"sw {c} {name}", lambda: ak.index_hist_sw(symbol=c, period="day"), "em", f"sw_{c}.csv")
except Exception as e:  # noqa: BLE001
    log("ERR sw", repr(e)[:300])
try:
    csi = ak.index_csindex_all()
    save(csi, "em", "csindex_all.csv")
    name_col = next(c for c in csi.columns if "简称" in c or "名称" in c)
    code_col = next(c for c in csi.columns if "代码" in c)
    for code, name in csi[[code_col, name_col]].values.tolist():
        if re.search("公路|高速|交通运输|红利低波", str(name)):
            c = str(code)
            tryit(f"csi {c} {name}", lambda: ak.stock_zh_index_daily_em(symbol="csi" + c, start_date=START, end_date=END),
                  "em", f"csi_{c}.csv")
except Exception as e:  # noqa: BLE001
    log("ERR csi", repr(e)[:300])
try:
    boards = ak.stock_board_industry_name_em()
    save(boards, "em", "em_boards.csv")
    for name in boards["板块名称"].tolist():
        if re.search("公路|铁路|交通", str(name)):
            tryit(f"board {name}", lambda: ak.stock_board_industry_hist_em(symbol=name, start_date=START, end_date=END,
                                                                          period="日k", adjust=""),
                  "em", f"board_{name}.csv")
except Exception as e:  # noqa: BLE001
    log("ERR boards", repr(e)[:300])

# rates
tryit("bond yields", lambda: ak.bond_zh_us_rate(start_date=START), "em", "bond_zh_us_rate.csv")
tryit("lpr", lambda: ak.macro_china_lpr(), "em", "lpr.csv")

# ---------- Eastmoney / Sina fundamentals ----------
for code in PEERS:
    em = market(code) + code
    tryit(f"is {code}", lambda: ak.stock_profit_sheet_by_report_em(symbol=em), "fin", f"is_{code}.csv")
    tryit(f"bs {code}", lambda: ak.stock_balance_sheet_by_report_em(symbol=em), "fin", f"bs_{code}.csv")
    tryit(f"cf {code}", lambda: ak.stock_cash_flow_sheet_by_report_em(symbol=em), "fin", f"cf_{code}.csv")
    tryit(f"ind {code}", lambda: ak.stock_financial_analysis_indicator_em(symbol=f"{code}.{market(code)}", indicator="按报告期"),
          "fin", f"ind_{code}.csv")
    tryit(f"div {code}", lambda: ak.stock_fhps_detail_em(symbol=code), "fin", f"div_{code}.csv")
    tryit(f"value {code}", lambda: ak.stock_value_em(symbol=code), "fin", f"value_{code}.csv")
    try:
        info = ak.stock_individual_info_em(symbol=code)
        save(info, "fin", f"info_{code}.csv")
    except Exception as e:  # noqa: BLE001
        log("ERR info", code, repr(e)[:200])
    time.sleep(0.8)
tryit("research", lambda: ak.stock_research_report_em(symbol="000429"), "fin", "research_000429.csv")
tryit("news", lambda: ak.stock_news_em(symbol="000429"), "fin", "news_000429.csv")
tryit("holders", lambda: ak.stock_main_stock_holder(stock="000429"), "fin", "holders_000429.csv")
tryit("sina div", lambda: ak.stock_history_dividend_detail(symbol="000429", indicator="分红"), "fin", "div_sina_000429.csv")
tryit("b share", lambda: ak.stock_zh_b_daily(symbol="sz200429", start_date=START, end_date=END), "em", "200429_raw.csv")

# ---------- Yahoo Finance cross-check ----------
yt = [f"{c}.{'SS' if c.startswith('6') else 'SZ'}" for c in PEERS] + ["200429.SZ", "000300.SS", "399001.SZ", "1052.HK",
                                                                       "CNY=X", "HKDCNY=X"]
for t in yt:
    try:
        df = yf.download(t, start="2014-01-01", end="2026-10-24", auto_adjust=False, progress=False, threads=False)
        if df is not None and len(df):
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.to_csv(os.path.join(OUT, "yahoo", re.sub(r"[^A-Za-z0-9]", "_", t) + ".csv"))
            log("yahoo", t, len(df))
    except Exception as e:  # noqa: BLE001
        log("yahoo ERR", t, repr(e)[:200])
    time.sleep(1.5)
try:
    json.dump(yf.Ticker("000429.SZ").info, open(os.path.join(OUT, "yahoo", "info_000429.json"), "w"), default=str, indent=1)
except Exception as e:  # noqa: BLE001
    log("yahoo info ERR", repr(e)[:200])


# ---------- cninfo announcements ----------
def http(url, data=None, timeout=90):
    hdr = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    if data is not None:
        hdr.update({"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Origin": "http://www.cninfo.com.cn",
                    "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search"})
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=hdr), timeout=timeout) as r:
        return r.read()


def cninfo_list(code, org, start, end, category=""):
    items, page = [], 1
    while page < 120:
        form = {"pageNum": page, "pageSize": 30, "column": "szse", "tabName": "fulltext", "plate": "",
                "stock": f"{code},{org}", "searchkey": "", "secid": "", "category": category, "trade": "",
                "seDate": f"{start}~{end}", "sortName": "", "sortType": "", "isHLtitle": "true"}
        js = json.loads(http("http://www.cninfo.com.cn/new/hisAnnouncement/query", urllib.parse.urlencode(form).encode()))
        anns = js.get("announcements") or []
        items += anns
        if not js.get("hasMore") or not anns:
            break
        page += 1
        time.sleep(0.6)
    for it in items:
        it["announcementTitle"] = re.sub("<[^>]+>", "", it.get("announcementTitle") or "")
        it["date"] = time.strftime("%Y-%m-%d", time.gmtime((it.get("announcementTime") or 0) / 1000 + 8 * 3600))
    return items


def pdf_text(it, folder, prefix="", last_page=0):
    title = re.sub(r"[\\/:*?\"<>|\s]+", "_", it["announcementTitle"])[:60]
    path = os.path.join(folder, f"{prefix}{it['date']}_{title}.txt")
    if os.path.exists(path):
        return
    open("/tmp/doc.pdf", "wb").write(http("https://static.cninfo.com.cn/" + it["adjunctUrl"], timeout=180))
    cmd = ["pdftotext", "-layout", "-enc", "UTF-8"] + (["-l", str(last_page)] if last_page else []) + ["/tmp/doc.pdf", path]
    subprocess.run(cmd, check=True, timeout=300)
    log("saved", path, os.path.getsize(path))


try:
    orgs = {s["code"]: s["orgId"] for s in json.loads(http("http://www.cninfo.com.cn/new/data/szse_stock.json"))["stockList"]}
    log("cninfo orgIds", {c: orgs.get(c) for c in PEERS})
except Exception as e:  # noqa: BLE001
    orgs = {}
    log("ERR cninfo orgIds", repr(e)[:300])

KEEP = re.compile(r"(年度报告|季度报告|收购|购买|出售|重大资产|关联交易|扩建|收费|分红|利润分配|权益分派|业绩预告|业绩快报|"
                  r"投资|增资|债券|中期票据|融资券|减值|诉讼|补偿|特许经营|回购|增持|减持|估值提升|市值管理|规划|经营数据)")
SKIP = re.compile(r"(摘要|英文|English|提示性|法律意见|核查意见|独立董事|监事会|决议|通知|更正|补充|问询|回复|保荐|"
                  r"持续督导|取消|延期|候选人|辞职|聘任|章程|制度|规则|内部控制|社会责任|ESG|可持续发展|鉴证|审计报告|"
                  r"专项说明|专项报告|评估报告|备查|自查|承诺|会计师|事务所|资金占用|担保)", re.I)
try:
    items = cninfo_list("000429", orgs.get("000429", "gssz0000429"), "2014-01-01", "2026-10-24")
    json.dump(items, open(os.path.join(OUT, "cninfo", "announcements.json"), "w"), ensure_ascii=False, indent=1)
    log("cninfo 000429 items", len(items))
    picked = [it for it in items if it["date"] >= "2019-01-01" and KEEP.search(it["announcementTitle"])
              and not SKIP.search(it["announcementTitle"]) and (it.get("adjunctUrl") or "").upper().endswith(".PDF")]
    log("picked", len(picked))
    for it in picked[:160]:
        try:
            pdf_text(it, os.path.join(OUT, "cninfo"))
        except Exception as e:  # noqa: BLE001
            log("pdf ERR", it.get("adjunctUrl"), repr(e)[:200])
        time.sleep(0.4)
except Exception as e:  # noqa: BLE001
    log("ERR cninfo 000429", repr(e)[:300])

# peers: latest annual and interim reports (operating data, toll roads and concession terms sit in the first pages)
for code, name in PEERS.items():
    if code == "000429" or code not in orgs:
        continue
    try:
        items = cninfo_list(code, orgs[code], "2025-01-01", "2026-10-24", category="category_ndbg_szsh;category_bndbg_szsh")
        docs = [it for it in items if re.search(r"(2025年年度报告|2026年半年度报告)", it["announcementTitle"])
                and not re.search("摘要|英文|English|更正|补充", it["announcementTitle"])]
        log("cninfo", code, name, len(items), "docs", len(docs))
        for it in docs[:2]:
            try:
                pdf_text(it, os.path.join(OUT, "peers_cninfo"), prefix=f"{code}_", last_page=45)
            except Exception as e:  # noqa: BLE001
                log("peer pdf ERR", code, repr(e)[:200])
            time.sleep(0.4)
    except Exception as e:  # noqa: BLE001
        log("ERR cninfo peer", code, repr(e)[:300])
log("done")
