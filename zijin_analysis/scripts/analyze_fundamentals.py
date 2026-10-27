"""Financials, solvency, valuation and peer comparison for 紫金矿业（601899.SH） -> data/processed/fundamentals.json.

From the stock-analysis-report skill's fundamentals template (MARKET = "A").
Writes the standard keys the skeleton page reads (see assets/fundamentals.example.json):
  currency, unit_label, annual, balance, solvency, valuation, peers, peer_ranks, peer_medians, industry, sources
plus anything company-specific you add (segments, assets, pipeline, debt stack, scenarios, debt path ...).

Where the numbers come from (files saved by fetch_data.py under data/raw/):
- A-shares: Eastmoney statements, indicators, dividends and valuation for the company AND every peer (fin/*.csv).
- HK: Eastmoney HK indicators (fin/ind_<5-digit>.csv) for growth, margins, ROE, BPS; Yahoo info for market cap,
  debt, cash, EBITDA and analyst targets (yahoo/<code>_HK_info.json). Cash, debt and cash flows of the company come
  from its results announcement (filings/*.txt): put them in BALANCE_MANUAL / ANNUAL_PATCH with the source.
- US: SEC XBRL companyfacts (filings/companyfacts.json) for the company; Yahoo info for peers (growth fields are the
  latest quarter year-on-year: say so in the table).
Every hand-typed number gets a comment naming the document.
"""
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
FIN = os.path.join(RAW, "fin")
OUT = os.path.join(ROOT, "data", "processed")
sys.path.insert(0, os.path.join(ROOT, "..", "report_kit"))
warnings.simplefilter("ignore", pd.errors.PerformanceWarning)  # wide Eastmoney statement files
M = 1e6

# ============================================================ CONFIG (edit)
MARKET = "A"                             # "A", "HK" or "US"
TARGET = "601899"
NAMES = {"601899": "紫金矿业",            # company first, then the 13 peers of analyze_market.py (赤峰黄金 left out)
         "600547": "山东黄金", "600489": "中金黄金", "000975": "山金国际", "002155": "湖南黄金", "601069": "西部黄金",
         "002237": "恒邦股份", "001337": "四川黄金",
         "600362": "江西铜业", "000630": "铜陵有色", "603993": "洛阳钼业", "601168": "西部矿业", "000878": "云南铜业", "603979": "金诚信"}
YEARS = list(range(2016, 2026))          # complete fiscal years for the annual table
LAST_FY = "2025-12-31"                   # latest full fiscal year (peer comparison)
LAST_BS = "2026-09-30"                   # latest balance sheet date (2026 third-quarter report)
HALF = ("2026-09-30", "2025-09-30")      # first nine months of 2026 vs 2025 (A-share Q3 reports are due by 31 October)
INDUSTRY = [                             # [{"label", "value", "url"}] - sourced industry facts
    {"label": "全球黄金需求（2025）", "value": "5,002 吨，首次超过 5,000 吨，金额 5,550 亿美元（+45%）；LBMA 年均金价 3,431 美元/盎司（+44%），全年 53 次创历史新高；投资需求 2,175 吨（+84%），央行购金 863 吨（世界黄金协会，2026-01-29）。",
     "url": "https://www.gold.org/news-and-events/press-releases/gold-investment-rockets-2025-setting-new-high-uncertainty-bites"},
    {"label": "全球黄金供给（2025）", "value": "矿产金 3,671.6 吨（+1%），总供给 5,002 吨（+1%），回收金 1,404 吨（世界黄金协会）。紫金 2025 年矿产金 89.5 吨，约占全球矿产金的 2.4%。",
     "url": "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-full-year-2025/supply"},
    {"label": "中国黄金（2025）", "value": "国内原料产金 381.3 吨（+1.1%），黄金消费 950.1 吨（−3.6%），其中金条金币 504.2 吨（+35%）首次超过首饰（363.8 吨，−31.6%）；大型黄金集团境外矿山产金约 90 吨（+25%）（中国黄金协会，2026-02-05）。",
     "url": "https://www.news.cn/fortune/20260205/ece7fdf17ebd4f38ae8b763151a5bcef/c.html"},
    {"label": "央行购金（2026）", "value": "2026 年 1–8 月全球央行净购金约 170 吨，中国人民银行三季度增持 63 吨；世界黄金协会预计 2026 年央行购金约 850 吨，与 2025 年接近。",
     "url": "https://www.gold.org/goldhub/gold-focus/2026/10/china-gold-market-update-q3-ends-strong-official-gold-buying"},
    {"label": "铜", "value": "国际铜研究小组（ICSG）统计，受事故及品位下降影响，2025 年全球矿产铜产量增速约 1%（紫金 2025 年年报引述）；Grasberg 和卡莫阿事故使 2026 年供给继续偏紧。LME 三个月期铜 2026 年 1 月盘中创 14,527.5 美元/吨纪录，10 月 27 日收于约 14,480 美元/吨。",
     "url": "https://static.cninfo.com.cn/finalpage/2026-03-21/1225550242.PDF"},
    {"label": "紫金的行业地位", "value": "公司称矿产金产量位居上市矿企中国领先、全球前五，矿产铜连续 3 年超百万吨、位居全球前四；2025 年末保有金资源量约 4,610 吨、铜约 1.1 亿吨（2025 年年报）。",
     "url": "https://static.cninfo.com.cn/finalpage/2026-03-21/1225550242.PDF"},
]
SOURCES = [                              # [{"label", "url"}] - documents the narrative relies on
    {"label": "紫金矿业 2025 年年度报告（2026-03-21）", "url": "https://static.cninfo.com.cn/finalpage/2026-03-21/1225550242.PDF"},
    {"label": "紫金矿业 2026 年半年度报告（2026-08-22）", "url": "https://static.cninfo.com.cn/finalpage/2026-08-22/1225550244.PDF"},
    {"label": "紫金矿业 2026 年第三季度报告（2026-10-24）", "url": "https://static.cninfo.com.cn/finalpage/2026-10-24/1225620996.PDF"},
    {"label": "三年（2026–2028 年）主要矿产品产量规划和 2035 年远景目标（2026-02-09）", "url": "https://static.cninfo.com.cn/finalpage/2026-02-09/1224972233.PDF"},
    {"label": "未来三年（2026–2028 年度）股东分红回报规划（2026-04-22）", "url": "https://static.cninfo.com.cn/finalpage/2026-04-22/1225141515.PDF"},
    {"label": "2026 年中期利润分配方案（2026-07-11）", "url": "https://static.cninfo.com.cn/finalpage/2026-07-11/1225419752.PDF"},
    {"label": "15 亿美元零息可转换公司债券（2026-01-30）", "url": "https://static.cninfo.com.cn/finalpage/2026-01-30/1224957529.PDF"},
    {"label": "A 股回购方案与实施结果（2026-03-21、2026-04-15）", "url": "https://static.cninfo.com.cn/finalpage/2026-03-21/1225023654.PDF"},
    {"label": "标普将紫金评级展望调整为正面（SCMP，2026-05）", "url": "https://www.scmp.com/business/china-business/article/3354940/chinas-zijin-mining-outlook-raised-positive-stronger-output-and-cost-edge-sp"},
    {"label": "美联储 2026 年 9 月加息（CNBC，2026-09-16）", "url": "https://www.cnbc.com/2026/09/16/fed-rate-decision-september-2026.html"},
    {"label": "上海金价 3 月 23 日暴跌（Mysteel）", "url": "https://www.mysteel.net/analysis/5117107-shanghai-gold-drops-below-yuan-1-000g-amid-plunge-in-international-prices"},
    {"label": "金价 2026 年回落与美联储预期（21 财经，2026-07-01）", "url": "https://m.21jingji.com/article/20260701/herald/8f79f45ce4cb90bd55a03266aa792b96.html"},
    {"label": "LME 铜价 2026 年创纪录（finanzen.ch，2026-08-26）", "url": "https://images.finanzen.ch/nachrichten/rohstoffe/copper-price-notches-another-record-before-retreating-as-squeeze-eases-15902038"},
]
BROKER_TARGETS = [                       # [{"broker", "market", "rating", "target", "date", "url"}] - third-party, dated (A: 元, H: 港元)
    {"broker": "高盛", "market": "H", "rating": "买入", "target": 51.0, "date": "2026-04-25", "url": "https://finance.sina.com.cn/stock/hkstock/hkgg/2026-04-25/doc-inhvsqpe7300026.shtml"},
    {"broker": "花旗", "market": "H", "rating": "买入", "target": 51.8, "date": "2026-07-06", "url": "https://finance.sina.com.cn/stock/hkstock/hkgg/2026-07-06/doc-inifvuxz8786382.shtml"},
    {"broker": "美银证券", "market": "A", "rating": "买入", "target": 39.0, "date": "2026-07-13", "url": "https://stock.10jqka.com.cn/20260713/c678126431.shtml"},
    {"broker": "摩根士丹利", "market": "A", "rating": "增持", "target": 58.0, "date": "2026-08-12", "url": "https://stock.10jqka.com.cn/20260812/c678891840.shtml"},
    {"broker": "摩根士丹利", "market": "H", "rating": "增持", "target": 60.0, "date": "2026-10-26", "url": "http://hkstock.cnfol.com/shichangfenxi/20261026/32407830.shtml"},
    {"broker": "美银证券", "market": "H", "rating": "买入", "target": 43.0, "date": "2026-07-13", "url": "https://stock.10jqka.com.cn/20260713/c678126431.shtml"},
]
# A-shares
PRIOR_YEAR_AS_REPORTED = {}              # {year: {"revenue": .., "np": .., "np_adj": ..}} when the provider shows restated comparatives
CAPITALISED_INTEREST = {"2025-12-31": 1001.28}  # 2025 annual report, note on finance costs: 减：利息资本化金额 1,001,282,570 元
EBITDA_ONE_OFFS = {}                     # {"2025-12-31": 310.0} one-off gains inside EBITDA (recurring ratios strip them)
# HK
FX_REPORT_PER_TRADE = None               # CNY per HKD (Eastmoney HK figures are in RMB); None = latest HKDCNY=X, else CNY=X / 7.80
BALANCE_MANUAL = []                      # [{"p": "2026-06", "cash": .., "debt": .., "net_debt": .., "debt_asset": .., "current_ratio": ..}]
ANNUAL_PATCH = {}                        # {2025: {"capex": .., "dps": ..}} figures the indicator file lacks
# US
SEC_SINCE = "2021-01-01"                 # first fiscal year end to show


def ratio(a, b):
    return None if b in (0, None) or a is None or np.isnan(a) or np.isnan(b) else a / b - 1


# ============================================================ A-shares (Eastmoney)
def build_a():
    def load(kind, code):
        df = pd.read_csv(os.path.join(FIN, f"{kind}_{code}.csv"))
        df["d"] = df["REPORT_DATE"].astype(str).str[:10]
        return df

    def val(df, d, col):
        r = df[df["d"] == d]
        if not len(r) or col not in df.columns:
            return np.nan
        return float(pd.to_numeric(r[col], errors="coerce").iloc[0])

    def nz(v):
        return 0.0 if v is None or (isinstance(v, float) and np.isnan(v)) else v

    debt_cols = ("SHORT_LOAN", "NONCURRENT_LIAB_1YEAR", "LONG_LOAN", "BOND_PAYABLE", "SHORT_BOND_PAYABLE")
    da_cols = ("FA_IR_DEPR", "IA_AMORTIZE", "LPE_AMORTIZE", "USERIGHT_ASSET_AMORTIZE")

    def company_year(i, b, f, ind, d):
        """Key figures (RMB million) for one report date."""
        rev = val(i, d, "TOTAL_OPERATE_INCOME") / M
        debt = sum(nz(val(b, d, c)) for c in debt_cols) / M
        cash = val(b, d, "MONETARYFUNDS") / M
        da = sum(nz(val(f, d, c)) for c in da_cols) / M
        ie = nz(val(i, d, "FE_INTEREST_EXPENSE")) / M
        return {"revenue": rev, "gross_margin": 1 - val(i, d, "OPERATE_COST") / M / rev if rev else None,
                "np": val(i, d, "PARENT_NETPROFIT") / M, "np_adj": val(i, d, "DEDUCT_PARENT_NETPROFIT") / M,
                "roe": val(ind, d, "ROEJQ") / 100, "ocf": val(f, d, "NETCASH_OPERATE") / M, "capex": val(f, d, "CONSTRUCT_LONG_ASSET") / M,
                "ebit": val(i, d, "TOTAL_PROFIT") / M + ie, "ebitda": val(i, d, "TOTAL_PROFIT") / M + ie + da, "interest_exp": ie,
                "debt": debt, "cash": cash, "net_debt": debt - cash, "minority_equity": nz(val(b, d, "MINORITY_EQUITY")) / M,
                "perpetual": nz(val(b, d, "PERPETUAL_BOND")) / M,
                "debt_asset": val(b, d, "TOTAL_LIABILITIES") / val(b, d, "TOTAL_ASSETS"),
                "current_ratio": val(b, d, "TOTAL_CURRENT_ASSETS") / val(b, d, "TOTAL_CURRENT_LIAB")}

    def dps_for(code, year):
        """Cash DPS declared for a fiscal year (interim + final), from stock_fhps_detail_em (per 10 shares)."""
        dv = pd.read_csv(os.path.join(FIN, f"div_{code}.csv"))
        rp = dv["报告期"].astype(str).str[:10]
        return float(dv[rp.isin([f"{year}-06-30", f"{year}-12-31"])]["现金分红-现金分红比例"].sum()) / 10

    i, b, f, ind = (load(k, TARGET) for k in ("is", "bs", "cf", "ind"))
    annual = []
    for y in YEARS:
        cur, prev = company_year(i, b, f, ind, f"{y}-12-31"), company_year(i, b, f, ind, f"{y - 1}-12-31")
        prev.update(PRIOR_YEAR_AS_REPORTED.get(y, {}))
        annual.append({"y": y, **{k: cur[k] for k in ("revenue", "gross_margin", "np", "np_adj", "roe", "ocf", "capex")},
                       "revenue_yoy": ratio(cur["revenue"], prev["revenue"]), "np_yoy": ratio(cur["np"], prev["np"]),
                       "np_adj_yoy": ratio(cur["np_adj"], prev["np_adj"]), "dps": dps_for(TARGET, y) or None})
    # year ends of the annual table, then every report date after the last full year (Q1, H1, Q3)
    bal_dates = sorted({d for d in b["d"] if (d[5:] == "12-31" and d >= f"{YEARS[0]}-12-31") or LAST_FY < d <= LAST_BS})
    balance = []
    for d in bal_dates:
        c = company_year(i, b, f, ind, d)
        balance.append({"p": d[:4] if d[5:] == "12-31" else d[:7], **{k: c[k] for k in ("cash", "debt", "net_debt", "debt_asset", "current_ratio")}})
    last = company_year(i, b, f, ind, LAST_BS)
    fy = company_year(i, b, f, ind, LAST_FY)
    ebitda_rec = fy["ebitda"] - EBITDA_ONE_OFFS.get(LAST_FY, 0.0)
    interest_all = fy["interest_exp"] + CAPITALISED_INTEREST.get(LAST_FY, 0.0)
    solvency = {"date": LAST_BS, "net_debt": last["net_debt"], "ebitda": fy["ebitda"], "ebitda_recurring": ebitda_rec,
                # reported EBITDA keeps the company on the same basis as the peer table; the recurring version strips one-offs
                "nd_ebitda": last["net_debt"] / fy["ebitda"], "nd_ebitda_recurring": last["net_debt"] / ebitda_rec,
                # EBIT / (expensed + capitalised interest); capitalised interest sits in the notes, not the income statement
                "interest_cover": fy["ebit"] / interest_all if interest_all else None}
    vv = pd.read_csv(os.path.join(FIN, f"value_{TARGET}.csv"))
    v_last = vv.iloc[-1]
    price, mcap = float(v_last["当日收盘价"]), float(v_last["总市值"]) / M
    pe_hist, pb_hist = pd.to_numeric(vv["PE(TTM)"], errors="coerce").dropna(), pd.to_numeric(vv["市净率"], errors="coerce").dropna()
    dps_fy = dps_for(TARGET, int(LAST_FY[:4]))
    ev = mcap + last["net_debt"] + last["minority_equity"] + last["perpetual"]  # claims on the consolidated EBITDA
    valuation = {"date": str(v_last["数据日期"])[:10], "price": price, "mcap": mcap, "ev": ev,
                 "pe_ttm": float(v_last["PE(TTM)"]), "pb": float(v_last["市净率"]),
                 "pe_pct": float((pe_hist <= pe_hist.iloc[-1]).mean()), "pb_pct": float((pb_hist <= pb_hist.iloc[-1]).mean()),
                 "ev_ebitda": ev / fy["ebitda"], "ev_ebitda_recurring": ev / ebitda_rec,
                 "dy": dps_fy / price if dps_fy else None, "dps": dps_fy or None}
    peers = []
    for code, name in NAMES.items():
        try:
            pi, pb_, pf, pind = (load(k, code) for k in ("is", "bs", "cf", "ind"))
            pv = pd.read_csv(os.path.join(FIN, f"value_{code}.csv")).iloc[-1]
        except FileNotFoundError as e:
            print("missing data for", code, name, e)
            continue
        c1 = company_year(pi, pb_, pf, pind, LAST_FY)
        c0 = company_year(pi, pb_, pf, pind, f"{int(LAST_FY[:4]) - 1}{LAST_FY[4:]}")
        bs_date = max(d for d in pb_["d"] if d <= LAST_BS)  # peers whose latest quarter is not out yet use the one before
        cb = company_year(pi, pb_, pf, pind, bs_date)
        dps = dps_for(code, int(LAST_FY[:4]))
        row = {"code": code, "name": name, "mcap": float(pv["总市值"]) / M, "price": float(pv["当日收盘价"]),
               "revenue": c1["revenue"], "revenue_yoy": ratio(c1["revenue"], c0["revenue"]), "np": c1["np"], "np_yoy": ratio(c1["np"], c0["np"]),
               "np_adj_yoy": ratio(c1["np_adj"], c0["np_adj"]), "roe": c1["roe"], "gross_margin": c1["gross_margin"],
               "pe_ttm": float(pv["PE(TTM)"]), "pb": float(pv["市净率"]), "dy": dps / float(pv["当日收盘价"]) if dps else 0.0,
               "payout": dps * float(pv["总股本"]) / M / c1["np"] if dps and c1["np"] else None,
               "net_debt": cb["net_debt"], "nd_ebitda": cb["net_debt"] / c1["ebitda"] if c1["ebitda"] else None, "debt_asset": cb["debt_asset"],
               "bs_date": bs_date}
        if HALF:
            # the latest interim both years have: first nine months where the Q3 report is out, otherwise the first half
            pair = next(((a, b) for a, b in (HALF, ("2026-06-30", "2025-06-30")) if a in set(pi["d"]) and b in set(pi["d"])), None)
            if pair:
                h1, h0 = company_year(pi, pb_, pf, pind, pair[0]), company_year(pi, pb_, pf, pind, pair[1])
                row.update({"rev_h_yoy": ratio(h1["revenue"], h0["revenue"]), "np_h_yoy": ratio(h1["np"], h0["np"]),
                            "np_adj_h_yoy": ratio(h1["np_adj"], h0["np_adj"]), "h_basis": "9M" if pair[0] == HALF[0] else "H1"})
        peers.append(row)
    return {"currency": "CNY", "unit_label": "百万元", "annual": annual, "balance": balance, "solvency": solvency,
            "valuation": valuation, "peers": peers}


# ============================================================ Hong Kong (Eastmoney HK indicators + Yahoo info)
def hk_fx():
    """CNY per HKD from the downloaded FX series (latest close), unless set in CONFIG."""
    if FX_REPORT_PER_TRADE:
        return FX_REPORT_PER_TRADE
    for f, scale in (("HKDCNY_X.csv", 1.0), ("CNY_X.csv", 1 / 7.80)):  # HKD is pegged at 7.75-7.85 per USD
        path = os.path.join(RAW, "yahoo", f)
        if os.path.exists(path):
            close = pd.to_numeric(pd.read_csv(path)["Close"], errors="coerce").dropna()
            if len(close):
                return float(close.iloc[-1]) * scale
    raise SystemExit("no HKDCNY=X / CNY=X series in data/raw/yahoo: set FX_REPORT_PER_TRADE")


def build_hk():
    import finlib as fl
    fx = hk_fx()
    yf_info = lambda c: fl.load_info(os.path.join(RAW, "yahoo", f"{int(c):04d}_HK_info.json"))  # noqa: E731
    ind_of = lambda c: fl.hk_indicators(os.path.join(FIN, f"ind_{int(c):05d}.csv"))  # noqa: E731
    ind = ind_of(TARGET)
    annual = [{**r, **ANNUAL_PATCH.get(r["y"], {})} for r in fl.hk_annual_rows(ind, YEARS[0])]
    peers = []
    for code, name in NAMES.items():
        try:
            peers.append(fl.hk_peer_row(code, name, ind_of(code), yf_info(code), LAST_FY, HALF, fx))
        except FileNotFoundError as e:
            print("missing data for", code, name, e)
    me = next(p for p in peers if p["code"] == TARGET)
    info = yf_info(TARGET)
    bal = BALANCE_MANUAL[-1] if BALANCE_MANUAL else {}
    solvency = {"date": LAST_BS, "net_debt": bal.get("net_debt"), "nd_ebitda": me["nd_ebitda"], "source": "Yahoo totalDebt / totalCash / ebitda; check against the results announcement"}
    valuation = {"date": LAST_BS, "price": me["price"], "mcap": me["mcap"], "pe_ttm": me["pe_ttm"], "pb": me["pb"], "dy": me["dy"],
                 "ev": (me["mcap"] + (bal["net_debt"] / fx)) if bal.get("net_debt") is not None and me["mcap"] else None, "fx_cny_per_hkd": fx,
                 "consensus_target": info.get("targetMeanPrice"), "n_analysts": info.get("numberOfAnalystOpinions")}
    # Eastmoney HK amounts are in RMB even for USD / HKD reporters (CURRENCY names the original reporting currency)
    return {"currency": "CNY", "unit_label": "百万元", "trading_currency": "HKD", "reporting_currency": str(ind["CURRENCY"].iloc[-1]),
            "annual": annual, "balance": BALANCE_MANUAL, "solvency": solvency, "valuation": valuation, "peers": peers}


# ============================================================ US (SEC XBRL + Yahoo info)
def build_us():
    import finlib as fl
    q, a = fl.sec_periods(os.path.join(RAW, "filings", "companyfacts.json"))
    annual = fl.sec_annual_rows(a, SEC_SINCE)
    balance = fl.sec_balance_rows(q, SEC_SINCE, fy_md=max(a)[5:])  # fiscal year ends + the latest quarter
    info = fl.load_info(os.path.join(RAW, "yahoo", f"{TARGET}_info.json"))
    peers = [fl.yahoo_peer_row(c, n, fl.load_info(os.path.join(RAW, "yahoo", f"{c}_info.json"))) for c, n in NAMES.items()]
    last_q = q[max(e for e, v in q.items() if v.get("assets") is not None)]
    fy_end = max(a)
    fy = a[fy_end]  # the latest fiscal year: its tags are more complete than quarterly ones (D&A, interest)
    da = fl.da_of(fy)
    ebitda = ((fy.get("op_income") or 0) + (da or 0)) / M
    debt = fl._debt(last_q)
    cash = (last_q.get("cash") or 0) + (last_q.get("short_investments") or 0)
    net_debt = (debt - cash) / M if debt is not None else None
    interest = abs(fy.get("interest_exp_debt") or 0) / M
    solvency = {"date": max(e for e, v in q.items() if v.get("assets") is not None), "net_debt": net_debt,
                "ebitda_fy": ebitda, "fy_end": fy_end, "da_missing": da is None,
                "nd_ebitda": net_debt / ebitda if net_debt is not None and ebitda > 0 else None,
                "interest_cover": (fy.get("op_income") or 0) / M / interest if interest else None}
    mcap = info.get("marketCap", 0) / M if info.get("marketCap") else None
    valuation = {"date": solvency["date"], "price": info.get("currentPrice"), "mcap": mcap, "pe_ttm": info.get("trailingPE"),
                 "pe_fwd": info.get("forwardPE"), "pb": info.get("priceToBook"), "dy": info.get("trailingAnnualDividendYield") or 0.0,
                 "ev": mcap + net_debt if mcap is not None and net_debt is not None else None,
                 "ev_ebitda": (mcap + net_debt) / ebitda if mcap is not None and net_debt is not None and ebitda > 0 else None,
                 "consensus_target": info.get("targetMeanPrice"), "n_analysts": info.get("numberOfAnalystOpinions")}
    return {"currency": "USD", "unit_label": "百万美元", "annual": annual, "balance": balance, "solvency": solvency,
            "valuation": valuation, "peers": peers, "quarterly": {e: {k: (x / M if isinstance(x, (int, float)) else x) for k, x in v.items()} for e, v in q.items() if e >= SEC_SINCE}}


res = {"A": build_a, "HK": build_hk, "US": build_us}[MARKET]()
res["valuation"]["broker_targets"] = BROKER_TARGETS
peers = res["peers"]


def rank(key, code=TARGET, descending=True):
    vals = sorted([(p[key], p["code"]) for p in peers if p.get(key) is not None], reverse=descending)
    return next((k + 1 for k, (_, c) in enumerate(vals) if c == code), None), len(vals)


res["peer_ranks"] = {k: dict(zip(("rank", "of"), rank(k))) for k in ("roe", "revenue_yoy", "np_yoy", "np_adj_yoy", "pe_ttm", "pb", "dy", "mcap", "revenue")}
res["peer_ranks"]["nd_ebitda_lowest"] = dict(zip(("rank", "of"), rank("nd_ebitda", descending=False)))
res["peer_medians"] = {k: float(np.nanmedian([p[k] for p in peers if p.get(k) is not None])) for k in ("pe_ttm", "pb", "dy", "nd_ebitda", "roe", "revenue_yoy")
                       if any(p.get(k) is not None for p in peers)}
res["peer_mcap_total"] = sum(p["mcap"] for p in peers if p.get("mcap"))
res["industry"], res["sources"] = INDUSTRY, SOURCES
# ---- add company-specific blocks below (segments, assets, pipeline, debt stack, scenarios, debt path, ...) ----
GA = json.load(open(os.path.join(OUT, "gold_analysis.json"), encoding="utf-8"))  # run analyze_gold.py first

# Mine output. Gold t, copper 万吨, zinc + lead 万吨, silver t, lithium carbonate equivalent 万吨.
# 2017-2021: annual reports 2018-2021 (矿产金 / 矿产铜 / 锌精矿含锌 + 铅精矿含铅 / 矿山产银); 2022-2023: 2023 annual report, which
# restated 2022 to add the equity output of associates (玉龙铜矿, 万城商务); 2024-2025: 2025 annual report (卡莫阿 on an equity
# basis); 2026 first nine months: 2026 Q3 report table (一) (zinc only, lead not given); 2026 guidance and 2028 plan: announcement
# 临2026-012 of 2026-02-09 (three-year plan 2026-2028).
PRODUCTION = [
    ("2017", 37.5, 20.8, 30.6, 238.1, None), ("2018", 36.5, 24.9, 31.4, 220.9, None), ("2019", 40.8, 37.0, 40.8, 263.2, None),
    ("2020", 40.5, 45.3, 37.8, 298.7, None), ("2021", 47.5, 58.4, 43.4, 309.0, None), ("2022", 56.4, 90.6, 45.4, 395.8, None),
    ("2023", 67.7, 100.7, 46.7, 412.0, 0.29), ("2024", 72.9, 106.8, 45.1, 435.8, None), ("2025", 89.5, 108.5, 39.9, 439.0, 2.55),
    ("2026 前三季度", 70.1, 81.6, 25.8, 348.4, 7.9),
]
PLAN = [("2026 指引", 105, 120, 40, 520, 12, 105, 120), ("2028 规划", "130–140", "150–160", "40–45", "600–700", "27–32", 135, 155)]
res["production"] = ([{"p": p, "gold": g, "copper": c, "zinc": z, "silver": sv, "lce": l, "chart": p[2:] if len(p) == 4 else None}
                      for p, g, c, z, sv, l in PRODUCTION]
                     + [{"p": p, "gold": g, "copper": c, "zinc": z, "silver": sv, "lce": l, "plan": True, "chart": p[2:4] + "E",
                         "gold_chart": gc, "copper_chart": cc} for p, g, c, z, sv, l, gc, cc in PLAN])
res["production_note"] = ("口径：矿山产量；2022 年起铜、锌含参股的玉龙铜矿等权益产量（2023 年年报重述），卡莫阿铜矿按权益计；2026 年前三季度锌不含铅。"
                          "来源：2018–2025 年年报、2026 年三季报、2026-02-09 三年产量规划公告。")


def wavg(rows):
    """Volume-weighted price and unit cost across product forms: rows = [(volume, price, unit cost)]."""
    vol = sum(v for v, _, _ in rows)
    return sum(v * p for v, p, _ in rows) / vol, sum(v * c for v, _, c in rows) / vol, vol


def gp(rows, scale):
    """Gross profit in 亿元 from [(volume, price, unit cost)]; scale converts volume x price into 元 (1000 for kg x 元/g)."""
    return sum(v * (p - c) for v, p, c in rows) * scale / 1e8


# Sales volume, price ex VAT and unit cost of sales by product, consolidated mines only (经营成果 / 成本及毛利率 tables).
# Gold kg and 元/g (bullion, concentrate); copper t and 元/t (concentrate, SX-EW cathode, electrolytic cathode); zinc t; silver kg;
# iron ore 万t; lithium salt and concentrate t (LCE); smelting gold kg, copper t, zinc t.
UNIT = {
    "2023": {"src": "2023 年年报", "au": [(33673, 433.09, 286.09), (33034, 378.60, 158.83)],
             "cu": [(640890, 49406, 19998), (95999, 56354, 29862), (73848, 59590, 43098)],
             "zn": [(414879, 11855, 9266)], "ag": [(411403, 3.50, 1.72)], "fe": [(210.19, 584, 230.97)], "li": [],
             "sm_au": [(248366, 447.95, 445.30)], "sm_cu": [(724835, 60333, 58467)], "sm_zn": [(333555, 19160, 17805)], "is": "2023-12-31"},
    "2024": {"src": "2025 年年报（2024 年列）", "au": [(38087, 533.39, 287.16), (29699, 504.30, 158.15)],
             "cu": [(620407, 56342, 19139), (80919, 63180, 32602), (122991, 65894, 35673)],
             "zn": [(386444, 14921, 8735)], "ag": [(424145, 4.74, 1.85)], "fe": [(63.40, 694, 184.59)], "li": [],
             "sm_au": [(228212, 549.93, 547.46)], "sm_cu": [(745326, 66227, 64872)], "sm_zn": [(363292, 20785, 19823)], "is": "2024-12-31"},
    "2025": {"src": "2025 年年报", "au": [(49074, 810.17, 333.87), (34087, 730.98, 190.83)],
             "cu": [(666158, 63613, 22362), (95499, 69665, 32931), (123286, 71422, 36421)],
             "zn": [(352470, 14999, 9921)], "ag": [(430254, 6.88, 2.12)], "fe": [(111.35, 660, 255.35)], "li": [],
             "sm_au": [(162950, 772.15, 764.16)], "sm_cu": [(697678, 71621, 70128)], "sm_zn": [(403324, 20327, 20747)], "is": "2025-12-31"},
    "2026 前三季度": {"src": "2026 年三季报表（二）", "au": [(40663, 995.77, 356.96), (26130, 903.25, 207.60)],
                  "cu": [(547769, 84545, 25075), (69930, 91828, 37904), (87208, 92327, 38870)],
                  "zn": [(254468, 18392, 9941)], "ag": [(342961, 12.81, 2.34)], "fe": [], "li": [(33602, 127719, 48416), (29455, 69107, 15202)],
                  "sm_au": [], "sm_cu": [(496567, 92687, 91794)], "sm_zn": [(257763, 21880, 22932)], "is": "2026-09-30"},
}
UNIT_EXTRA = {"2022": {"au": [(27326, 385.71, 251.43), (33495, 354.64, 143.09)],      # 2023 annual report, 2022 column
                       "cu": [(617691, 47527, 18852), (96334, 55311, 23847), (24665, 63581, 29591)]},
              "2026 Q3": {"au": [(13239, 916.39, 376.99), (9374, 799.50, 222.71)],    # 2026 Q3 report table (三)
                          "cu": [(193938, 88049, 26160), (23085, 94046, 40509), (28089, 96122, 39621)]}}
unit = []
for y in ("2022", "2023", "2024", "2025", "2026 前三季度", "2026 Q3"):
    d = UNIT.get(y) or UNIT_EXTRA[y]
    ap, ac, akg = wavg(d["au"])
    cp, cc, ct = wavg(d["cu"])
    unit.append({"y": y, "au_price": ap, "au_cost": ac, "au_gm": 1 - ac / ap, "au_kg": akg, "cu_price": cp, "cu_cost": cc, "cu_gm": 1 - cc / cp, "cu_t": ct})
res["unit_econ"] = unit
res["global_note"] = ("美股为美元计的日收益，对标普 500、COMEX 黄金、COMEX 铜做三因子回归（2024 年以来，HAC 标准误）；市盈率为 Yahoo 口径（TTM）。"
                      "巴里克 2025 年 5 月起代码由 GOLD 改为 B。与紫金的人民币口径、上海交易时段不完全可比。")
res["unit_note"] = ("金为金锭与金精矿、铜为铜精矿、电积铜与电解铜按销量加权（不含税售价与单位销售成本），仅含控股矿山。"
                    "来源：2023、2025 年年报“成本及毛利率分析”，2026 年三季报。")

# Gross profit by business. Mine and smelting lines from the unit tables; "其他" = consolidated gross profit (revenue - operating
# cost, Eastmoney income statement) minus those lines: trading, lithium before 2026, potash (藏格矿业 from May 2025), 龙净环保 and
# other businesses, net of internal eliminations.
inc = pd.read_csv(os.path.join(FIN, f"is_{TARGET}.csv"))
inc["d"] = inc["REPORT_DATE"].astype(str).str[:10]
mix_rows = []
for y, d in UNIT.items():
    r = inc[inc["d"] == d["is"]].iloc[0]
    total = (float(r["TOTAL_OPERATE_INCOME"]) - float(r["OPERATE_COST"])) / 1e8
    parts = [gp(d["au"], 1000), gp(d["cu"], 1), gp(d["zn"], 1) + gp(d["ag"], 1000) + gp(d["fe"], 1e4), gp(d["li"], 1),
             gp(d["sm_au"], 1000) + gp(d["sm_cu"], 1) + gp(d["sm_zn"], 1)]
    mix_rows.append({"label": y.replace(" 前三季度", " 1–9月"), "v": [round(x, 1) for x in parts] + [round(total - sum(parts), 1)], "total": total})
res["gp_mix"] = {"parts": [{"name": "矿产金", "cls": "f4"}, {"name": "矿产铜", "cls": "f8"}, {"name": "锌、银、铁", "cls": "f3"},
                           {"name": "锂", "cls": "f7"}, {"name": "冶炼加工", "cls": "fmid"}, {"name": "其他（含贸易、钾肥、环保）", "cls": "f1"}],
                 "rows": mix_rows,
                 "caption": "各业务毛利占集团毛利的比例（亿元见悬停）；2023–2025 年锂计入“其他”。按控股矿山的销量 ×（售价 − 单位成本）计算"}

# Quarterly results against metal prices: single-quarter revenue and attributable profit from the cumulative statements
cum = inc.set_index(pd.to_datetime(inc["d"]))[["TOTAL_OPERATE_INCOME", "PARENT_NETPROFIT"]].apply(pd.to_numeric, errors="coerce").sort_index() / 1e8
cum = cum[cum.index.month.isin([3, 6, 9, 12])]
single = cum - cum.groupby(cum.index.year).shift(1).fillna(0)
qprice = dict(zip(GA["quarterly"]["q"], zip(GA["quarterly"]["gold"], GA["quarterly"]["cu"])))
quarters = []
for dte in single.index[-8:]:
    q = f"{dte.year}Q{(dte.month - 1) // 3 + 1}"
    prev = dte - pd.DateOffset(years=1)
    prev = single.index[single.index.to_period("Q") == prev.to_period("Q")]
    rv, npf = single.loc[dte, "TOTAL_OPERATE_INCOME"], single.loc[dte, "PARENT_NETPROFIT"]
    rv0, np0 = (single.loc[prev[0], "TOTAL_OPERATE_INCOME"], single.loc[prev[0], "PARENT_NETPROFIT"]) if len(prev) else (None, None)
    quarters.append({"q": q, "rev": rv, "np": npf, "rev_yoy": rv / rv0 - 1 if rv0 else None, "np_yoy": npf / np0 - 1 if np0 else None,
                     "gold": qprice.get(q, (None, None))[0], "cu": qprice.get(q, (None, None))[1]})
res["quarters"] = quarters

# Cash generation and uses (RMB million): operating cash flow, capex, dividends and interest paid (分配股利、利润或偿付利息支付的现金)
cf = pd.read_csv(os.path.join(FIN, f"cf_{TARGET}.csv"))
cf["d"] = cf["REPORT_DATE"].astype(str).str[:10]
cash_uses = []
for d in [f"{y}-12-31" for y in range(2019, 2026)] + [LAST_BS]:
    r = cf[cf["d"] == d].iloc[0]
    ocf, capex, divi = (float(r[c]) / M for c in ("NETCASH_OPERATE", "CONSTRUCT_LONG_ASSET", "ASSIGN_DIVIDEND_PORFIT"))
    cash_uses.append({"y": d[:4] if d.endswith("12-31") else "2026 前三季度", "ocf": ocf, "capex": capex, "fcf": ocf - capex, "div_int": divi})
res["cash_uses"] = cash_uses

# Debt detail at the latest balance sheet (RMB 亿元)
bsd = pd.read_csv(os.path.join(FIN, f"bs_{TARGET}.csv"))
bsd["d"] = bsd["REPORT_DATE"].astype(str).str[:10]
rb = bsd[bsd["d"] == LAST_BS].iloc[0]
g = lambda c: float(pd.to_numeric(rb.get(c), errors="coerce") or 0) / 1e8  # noqa: E731
res["debt_detail"] = {"date": LAST_BS, "short_loan": g("SHORT_LOAN"), "current_lt": g("NONCURRENT_LIAB_1YEAR"), "long_loan": g("LONG_LOAN"),
                      "bonds": g("BOND_PAYABLE"), "cash": g("MONETARYFUNDS"), "fin_assets": g("TRADE_FINASSET_NOTFVTPL"),
                      "equity_parent": g("TOTAL_PARENT_EQUITY"), "minority": g("MINORITY_EQUITY")}

# Profit sensitivity to metal prices (illustrative). Annualised Q3 2026 sales of the consolidated mines at Q3 realised prices
# (2026 Q3 report table (三)); profit change after the 9M 2026 effective tax rate and the parent's share of net profit.
r9 = inc[inc["d"] == LAST_BS].iloc[0]
tax_rate = float(r9["INCOME_TAX"]) / float(r9["TOTAL_PROFIT"])
parent_share = float(r9["PARENT_NETPROFIT"]) / float(r9["NETPROFIT"])
k = (1 - tax_rate) * parent_share
q3np = next(q["np"] for q in quarters if q["q"] == "2026Q3")
base_np = q3np * 4
q3 = UNIT_EXTRA["2026 Q3"]
rev_au = gp([(v, p, 0) for v, p, _ in q3["au"]], 1000) * 4
rev_cu = gp([(v, p, 0) for v, p, _ in q3["cu"]], 1) * 4
SIDE = {"ag": [(117729, 10.64, 0)], "zn": [(82571, 20169, 0)], "li": [(11581, 121902, 0), (15189, 61718, 0)]}  # Q3 table (三)
rev_ag, rev_zn, rev_li = gp(SIDE["ag"], 1000) * 4, gp(SIDE["zn"], 1) * 4, gp(SIDE["li"], 1) * 4
q3_gold, q3_cu = GA["quarterly"]["gold"][-1], GA["quarterly"]["cu"][-1]
spot_gold, spot_cu, usdcny = GA["meta"]["gold_last"], GA["meta"]["cu_last"], GA["meta"]["usdcny_last"]
au_t = sum(v for v, _, _ in q3["au"]) * 4 / 1000   # tonnes a year
cu_wt = sum(v for v, _, _ in q3["cu"]) * 4 / 1e4   # 万吨 a year
rows = [{"label": "金价", "volume": f"{au_t:.0f} 吨", "price": f"{spot_gold:.0f} 元/克", "rev": rev_au},
        {"label": "铜价", "volume": f"{cu_wt:.0f} 万吨", "price": f"{spot_cu:,.0f} 元/吨", "rev": rev_cu},
        {"label": "金价与铜价同时", "volume": "—", "price": "—", "rev": rev_au + rev_cu},
        {"label": "碳酸锂", "volume": f"{sum(v for v, _, _ in SIDE['li']) * 4 / 1e4:.1f} 万吨", "price": "—", "rev": rev_li},
        {"label": "白银", "volume": f"{SIDE['ag'][0][0] * 4 / 1000:.0f} 吨", "price": "—", "rev": rev_ag},
        {"label": "锌", "volume": f"{SIDE['zn'][0][0] * 4 / 1e4:.0f} 万吨", "price": "—", "rev": rev_zn}]
for r_ in rows:
    r_.update({"d_pretax": r_["rev"] * 0.10, "d_np": r_["rev"] * 0.10 * k, "share": r_["rev"] * 0.10 * k / base_np})


def np_at(gold_px, cu_px):
    """Annualised attributable profit (亿元) at given SGE gold (元/克) and SHFE copper (元/吨) prices, scaled from Q3 2026."""
    return base_np + rev_au * (gold_px / q3_gold - 1) * k + rev_cu * (cu_px / q3_cu - 1) * k


GOLD_LV, CU_LV = [700, 800, round(spot_gold), round(q3_gold), 1050], [85000, 95000, round(q3_cu), 120000]
grid_rows = [{"label": f"{gx:,} 元/克（≈ ${gx * 31.1035 / usdcny:,.0f}/oz）", "base": gx == round(q3_gold), "values": [np_at(gx, cx) for cx in CU_LV]}
             for gx in GOLD_LV]
res["sensitivity"] = {
    "tax_rate": tax_rate, "parent_share": parent_share, "k": k, "base_np": base_np, "q3_np": q3np, "q3_gold": q3_gold, "q3_cu": q3_cu,
    "spot_gold": spot_gold, "spot_cu": spot_cu, "np_at_spot": np_at(spot_gold, spot_cu), "rev_au": rev_au, "rev_cu": rev_cu, "rows": rows,
    "grid": {"caption": "年化归母净利润情景（亿元，示意）：行 = 上海金价，列 = 沪铜价格；高亮为 2026 年三季度均价",
             "corner": "金价 \\ 铜价", "cols": [f"{c:,} 元/吨" for c in CU_LV], "base_col": CU_LV.index(round(q3_cu)), "rows": grid_rows},
    "note": (f"示意测算，不是盈利预测。以 2026 年三季度归母净利润 {q3np:.1f} 亿元 × 4 = {base_np:.0f} 亿元为基数；控股矿山三季度金、铜销量与不含税售价"
             f"年化后，金约 {rev_au:.0f} 亿元、铜约 {rev_cu:.0f} 亿元收入；价格变动全部计入利润，按前三季度实际税率 {tax_rate:.1%} 与归母占比 {parent_share:.1%} 换算。"
             "未计入随金价变化的权益金（会使金价敏感性略高估）、卡莫阿等联营企业通过投资收益的贡献（会使铜价敏感性略低估）、产量增长和成本变化。")}

# Valuation extras: trailing dividends paid, H share, Zijin Gold International stake, consensus EPS (Eastmoney research list)
dv = pd.read_csv(os.path.join(FIN, f"div_{TARGET}.csv"))
dv["rp"] = dv["报告期"].astype(str).str[:10]
paid_12m = dv[pd.to_datetime(dv["除权除息日"], errors="coerce") > pd.Timestamp(res["valuation"]["date"]) - pd.DateOffset(years=1)]
dps_ttm = float(paid_12m["现金分红-现金分红比例"].sum()) / 10
hk = GA["zgi"]["hkdcny"]
hdf = pd.read_csv(os.path.join(RAW, "yahoo", "2899_HK.csv"))
hdf = hdf[pd.to_datetime(hdf.iloc[:, 0], errors="coerce") <= pd.Timestamp(res["valuation"]["date"])]
h_close = float(pd.to_numeric(hdf["Close"], errors="coerce").dropna().iloc[-1])
zgi_stake_cny = GA["zgi"]["mcap_hkd"] / 1e8 * 0.85 * hk if GA["zgi"]["mcap_hkd"] else None
rr = pd.read_csv(os.path.join(FIN, f"research_{TARGET}.csv"))
rr["日期"] = pd.to_datetime(rr["日期"])
recent = rr[rr["日期"] >= pd.Timestamp(res["valuation"]["date"]) - pd.DateOffset(days=120)].sort_values("日期").drop_duplicates("机构", keep="last")
cons = {f"eps_{y}": float(np.nanmedian(pd.to_numeric(recent[f"{y}-盈利预测-收益"], errors="coerce"))) for y in (2026, 2027, 2028)}
cons.update({"n": int(len(recent)), "since": str((pd.Timestamp(res["valuation"]["date"]) - pd.DateOffset(days=120)).date()),
             "brokers": recent["机构"].tolist(), "ratings": recent["东财评级"].value_counts().to_dict()})
for y in (2026, 2027, 2028):
    cons[f"pe_{y}"] = res["valuation"]["price"] / cons[f"eps_{y}"]
shares = res["valuation"]["mcap"] / res["valuation"]["price"]  # 百万股 (A + H)
res["valuation"].update({"dps_ttm": dps_ttm, "dy_ttm": dps_ttm / res["valuation"]["price"], "h_price_hkd": h_close, "hkdcny": hk,
                         "ah_premium": res["valuation"]["price"] / (h_close * hk) - 1, "shares_m": shares,
                         "zgi_stake_cny": zgi_stake_cny, "zgi_stake_share": zgi_stake_cny / (res["valuation"]["mcap"] / 100) if zgi_stake_cny else None,
                         "consensus": cons, "pe_at_spot": res["valuation"]["mcap"] / 100 / res["sensitivity"]["np_at_spot"],
                         "pe_q3_annualised": res["valuation"]["mcap"] / 100 / base_np})

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "fundamentals.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, ensure_ascii=False, indent=1, default=float)
print(json.dumps({k: res[k] for k in ("solvency", "valuation", "peer_ranks", "peer_medians")}, ensure_ascii=False, indent=1, default=float))
for a in res["annual"]:
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in a.items()})
