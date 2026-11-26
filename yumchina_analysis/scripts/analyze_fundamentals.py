"""Fundamentals for 百胜中国 (Yum China): financials, cash and debt, shareholder returns, valuation, sensitivity and
the Hong Kong restaurant peer table. Writes data/processed/fundamentals.json (the skeleton's keys plus extras).

Sources
- Company (USD, US GAAP): SEC XBRL companyfacts. For each fiscal year the value from the latest filing is used, so
  2017 is the ASC 606 restated figure (revenue $7,769m rather than $7,144m as first reported) and growth is like for
  like. Long-term bank deposits and notes, the bridge loan and the cost lines come from the 10-K / 10-Q text (cited
  next to each number). Operating KPIs come from the quarterly press releases (ops_kpis.json).
- Peers (RMB): Eastmoney HK indicators for revenue, profit, ROE, margins and BPS, for every company in RMB; market cap
  and price from Yahoo in HKD, converted with CNY per HKD for P/E and P/B. P/E uses each company's own trailing
  twelve months (last full year + latest interim or nine-month period - the same period a year earlier).
- Global quick-service peers: Yahoo info (USD, their own fiscal years).
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
sys.path.insert(0, os.path.join(ROOT, "..", "report_kit"))
import finlib as fl  # noqa: E402
import marketlib as ml  # noqa: E402

M = 1e6
TARGET = "9987"
PEERS = {"6862": "海底捞", "9658": "特海国际", "9922": "九毛九", "520": "呷哺呷哺", "1405": "达势股份", "999": "小菜园",
         "6831": "绿茶集团", "9869": "海伦司", "538": "味千(中国)", "341": "大家乐集团", "2150": "奈雪的茶", "2555": "茶百道",
         "2097": "蜜雪集团", "1364": "古茗", "2589": "沪上阿姨"}
GLOBAL = {"YUM": "Yum! Brands", "MCD": "麦当劳", "SBUX": "星巴克", "QSR": "Restaurant Brands", "DPZ": "达美乐（美国）", "CMG": "Chipotle",
          "LKNCY": "瑞幸咖啡"}

# ---- figures transcribed from the filings text (USD million) --------------------------------------------------
# Long-term bank deposits and notes (balance sheet): 10-Q 2026-09-30 (filed 2026-11-05); 10-K 2025 (filed 2026-02-27) for
# 2025 and 2024; 10-K 2024 (filed 2025-02-27) for 2023
LT_DEPOSITS = {"2026-09-30": 670, "2025-12-31": 678, "2024-12-31": 1088, "2023-12-31": 1265}
# Short-term borrowings at 2026-09-30: bridge loan CNH 8,400m ($1,252m, ~1.9%, up to 12 months, to fund the Pizza Hut
# brand acquisition) + other RMB bank borrowings $297m; weighted average rate 1.8% (10-Q Note 9)
BRIDGE_LOAN = {"amount": 1252, "other": 297, "rate": 0.019, "weighted_rate": 0.018, "currency": "CNH 8,400 百万", "term": "最长 12 个月",
               "facilities_available": 2846}
# Company restaurant cost structure, nine months to 2026-09-30 (10-Q income statement): company sales and cost lines
COSTS_9M26 = {"company_sales": 9171, "food_paper": 2892, "payroll": 2468, "occupancy_other": 2215, "ga": 431, "total_revenue": 9886}
# Pizza Hut brand acquisition (8-K 2026-06-16): consideration and LTM licence fees to Yum! Brands (net of tax)
PH_DEAL = {"price": 1200, "ltm_license_fee_net": 62, "ph_revenue_2025": 2300, "ph_op_2025": 183, "ph_stores_q1": 4375,
           "margin_uplift_pp": 2.8, "closing": "2026-08-07"}
# Guidance and targets (8-K 2026-11-03 outlook; 2025 Investor Day 8-K 2025-11-17; Pizza Hut deal 8-K 2026-06-16)
GUIDANCE = [
    {"item": "2026 年门店总数", "value": "超过 20,500 家（净新增超过 2,400 家，此前目标约 1,900 家）", "src": "2026 年三季报"},
    {"item": "2026 年新店加盟比例", "value": "肯德基、必胜客均为 40%–50%", "src": "2026 年三季报"},
    {"item": "2026 年资本开支", "value": "约 6–7 亿美元", "src": "2026 年三季报"},
    {"item": "2026 年股东回报", "value": "15 亿美元（2024–2026 年每年约 15 亿美元）", "src": "2026 年三季报 / 2025 投资者日"},
    {"item": "2027 年起股东回报", "value": "约 100% 的自由现金流（扣除子公司对少数股东的分红），2027–2028 年平均每年约 9 亿至 10 亿美元以上", "src": "2025 投资者日"},
    {"item": "2026–2028 年增长目标", "value": "同店销售指数 100–102；系统销售额中高个位数复合增长；经营利润高个位数复合增长；摊薄每股收益和每股自由现金流两位数复合增长", "src": "2025 投资者日"},
    {"item": "门店长期目标", "value": "2030 年超过 30,000 家；肯德基 2028 年超过 17,000 家、经营利润超过 100 亿元人民币；必胜客 2028 年超过 6,000 家、2029 年经营利润较 2024 年翻倍", "src": "2025 投资者日 / 必胜客收购公告"},
]
BROKERS = [  # third-party, dated
    {"broker": "大华继显", "date": "2026-11-05", "rating": "买入", "target": 513.7, "ccy": "HKD", "note": "上调 2026 年盈利预测 2%",
     "url": "https://wap.stockstar.com/detail/IG2026110500010748"},
    {"broker": "华创证券", "date": "2026-11-06", "rating": "推荐", "target": 481.93, "ccy": "HKD", "note": "2027 年 18 倍市盈率",
     "url": "https://news.10jqka.com.cn/20261106/c681536276.shtml"},
    {"broker": "海通国际", "date": "2026-10-08", "rating": "优于大市", "target": 379.6, "ccy": "HKD", "note": "三季报前，2027 年 15 倍市盈率",
     "url": "https://wap.stockstar.com/detail/IG2026100800013637"},
]
INDUSTRY = [
    {"label": "餐饮市场规模", "value": "2025 年全国餐饮收入 57,982 亿元，同比 +3.2%（2024 年 +5.3%），占社会消费品零售总额 11.6%（国家统计局）。",
     "url": "https://finance.eastmoney.com/a/202601193623640618.html"},
    {"label": "2026 年放缓", "value": "2026 年 1—10 月餐饮收入 47,203 亿元，同比 +2.2%；10 月单月 +0.7%。同期社会消费品零售总额 +1.0%（国家统计局）。",
     "url": "https://www.stats.gov.cn/sj/zxfb/202611/t20261116_1965839.html"},
    {"label": "西式快餐", "value": "2024 年西式快餐市场规模 2,975 亿元，同比 +11.0%，增速在小吃快餐细分赛道中最高；2025 年 3 月全国西式快餐门店 32.5 万家（红餐产业研究院，第三方）。",
     "url": "https://news.qq.com/rain/a/20250401A02X3M00"},
    {"label": "竞争格局", "value": "2024 年西式快餐营收前五的企业合计份额约 44%；中式汉堡品牌塔斯汀 2024 年 3 月至 2025 年 2 月净增 2,000 余家门店，总数超过 9,000 家（红餐，第三方）。",
     "url": "https://pdf.dfcfw.com/pdf/H3_AP202504041651199029_1.pdf"},
    {"label": "外卖补贴", "value": "2025 年外卖平台补贴形成高基数，公司称 2026 年三季度同店销售承压主要受去年同期平台补贴与 8 月天气影响（公司电话会，媒体报道）。",
     "url": "https://cj.sina.com.cn/articles/view/2868676035/aafc85c302001zb6e"},
]
SOURCES = [
    {"label": "百胜中国 2026 年三季度业绩新闻稿（8-K，2026-11-03）", "url": "https://www.sec.gov/Archives/edgar/data/0001673358/000119312526444429/yumc-ex99_1.htm"},
    {"label": "百胜中国 2026 年三季度 10-Q（2026-11-05）", "url": "https://www.sec.gov/Archives/edgar/data/0001673358/000119312526448295/yumc-20260930.htm"},
    {"label": "百胜中国 2025 年 10-K（2026-02-27）", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001673358&type=10-K"},
    {"label": "收购必胜客中国内地品牌所有权（8-K，2026-06-16）", "url": "https://ir.yumchina.com/node/18121/pdf"},
    {"label": "必胜客品牌收购完成（2026-08-07）", "url": "https://yumchinaholdingsinc.gcs-web.com/news-releases/news-release-details/yum-china-completes-acquisition-ownership-pizza-hut-brand"},
    {"label": "2025 投资者日：RGM 3.0 与三年财务目标（8-K，2025-11-17）", "url": "https://www.sec.gov/Archives/edgar/data/1673358/000119312525283928/d723391dex991.htm"},
    {"label": "2023 投资者日：RGM 2.0（2023-09-14）", "url": "https://ir.yumchina.com/news-releases/news-release-details/yum-china-unveils-rgm-20-strategy-and-introduces-3-year"},
    {"label": "港股转为主要上市并纳入港股通（2022-10-24）", "url": "https://yumchinaholdingsinc.gcs-web.com/news-releases/news-release-details/yum-china-announces-primary-listing-hong-kong-stock-exchange-and"},
    {"label": "纳入恒生中国企业指数（格隆汇，2025-11）", "url": "https://m.gelonghui.com/news/5123142"},
    {"label": "港交所股票期权每日市场报告（2026-11-26，无 9987 期权类别）", "url": "https://www.hkex.com.hk/eng/stat/dmstat/dayrpt/dqe261126.htm"},
]


def rnd(x, d=4):
    try:
        return None if x is None or not math.isfinite(float(x)) else round(float(x), d)
    except (TypeError, ValueError):
        return None


# ================================================================ company: XBRL with the latest filed value per period
facts = json.load(open(os.path.join(RAW, "sec", "companyfacts.json")))["facts"]["us-gaap"]


def latest_fy(tag, unit="USD"):
    """{fiscal year end: value} for full-year duration facts, taking the value from the most recent filing."""
    out = {}
    for v in facts.get(tag, {}).get("units", {}).get(unit, []):
        if "start" in v and 350 <= (pd.Timestamp(v["end"]) - pd.Timestamp(v["start"])).days <= 380:
            if v["end"] not in out or v["filed"] > out[v["end"]][1]:
                out[v["end"]] = (v["val"], v["filed"])
    return {k: x[0] for k, x in sorted(out.items())}


def latest_instant(tag, unit="USD"):
    out = {}
    for v in facts.get(tag, {}).get("units", {}).get(unit, []):
        if "start" not in v and (v["end"] not in out or v["filed"] > out[v["end"]][1]):
            out[v["end"]] = (v["val"], v["filed"])
    return {k: x[0] for k, x in sorted(out.items())}


FY = {k: latest_fy(t) for k, t in {"revenue": "Revenues", "op": "OperatingIncomeLoss", "ni": "NetIncomeLoss", "cfo": "NetCashProvidedByUsedInOperatingActivities",
                                    "capex": "PaymentsToAcquirePropertyPlantAndEquipment", "div": "PaymentsOfDividendsCommonStock",
                                    "buyback": "PaymentsForRepurchaseOfCommonStock", "dna": "DepreciationAndAmortization",
                                    "div_nci": "PaymentsOfDividendsMinorityInterest", "ni_nci": "NetIncomeLossAttributableToNoncontrollingInterest"}.items()}
FY["eps"] = latest_fy("EarningsPerShareDiluted", "USD/shares")
FY["dps"] = latest_fy("CommonStockDividendsPerShareDeclared", "USD/shares")
INST = {k: latest_instant(t) for k, t in {"cash": "CashAndCashEquivalentsAtCarryingValue", "sti": "ShortTermInvestments", "stb": "ShortTermBorrowings",
                                           "lease": "OperatingLeaseLiability", "equity": "StockholdersEquity", "nci": "MinorityInterest",
                                           "assets": "Assets", "liab": "Liabilities"}.items()}
q_all, _ = fl.sec_periods(os.path.join(RAW, "sec", "companyfacts.json"))
ops = {q["p"]: q for q in json.load(open(os.path.join(OUT, "ops_kpis.json")))["quarters"]}

annual = []
for y in range(2017, 2026):
    e = f"{y}-12-31"
    g = lambda k: FY[k].get(e)  # noqa: E731
    p = f"{y - 1}-12-31"
    rev, op, ni = g("revenue"), g("op"), g("ni")
    adj_q = [ops.get(f"{y}-{md}", {}).get("adj_op_mn") for md in ("03-31", "06-30", "09-30", "12-31")]
    adj = sum(adj_q) if all(v is not None for v in adj_q) else None
    eq0, eq1 = INST["equity"].get(p), INST["equity"].get(e)
    q4 = ops.get(e, {})
    annual.append({"y": y, "revenue": rnd(rev / M, 1), "revenue_yoy": rnd(rev / FY["revenue"][p] - 1) if FY["revenue"].get(p) else None,
                   "op": rnd(op / M, 1), "opm": rnd(op / rev), "adj_op": rnd(adj, 1), "adj_opm": rnd(adj * M / rev) if adj else None,
                   "np": rnd(ni / M, 1), "np_yoy": rnd(ni / FY["ni"][p] - 1) if FY["ni"].get(p) else None, "eps": g("eps"), "dps": g("dps"),
                   "roe": rnd(ni / ((eq0 + eq1) / 2)) if eq0 and eq1 else None, "ocf": rnd(g("cfo") / M, 1), "capex": rnd(g("capex") / M, 1),
                   "fcf": rnd((g("cfo") - g("capex")) / M, 1), "dividends": rnd((g("div") or 0) / M, 1), "buybacks": rnd((g("buyback") or 0) / M, 1),
                   "returns": rnd(((g("div") or 0) + (g("buyback") or 0)) / M, 1), "stores": q4.get("stores"),
                   "np_nci": rnd((g("ni_nci") or 0) / M, 1)})
# quarters since 2023 with KPIs
quarters = []
for e, v in sorted(q_all.items()):
    if e < "2023-01-01" or not pd.Timestamp(e).is_quarter_end or v.get("revenue") is None:
        continue
    k = ops.get(e, {})
    quarters.append({"p": e, "label": k.get("label"), "revenue": rnd(v["revenue"] / M, 1), "op": rnd(v.get("op_income", np.nan) / M, 1),
                     "opm": rnd(v.get("op_income", np.nan) / v["revenue"]), "adj_op": k.get("adj_op_mn"), "np": rnd(v.get("net_income", np.nan) / M, 1),
                     "rm": k.get("rm"), "sssg": k.get("sssg"), "sst": k.get("sst"), "sys_growth": k.get("sys_growth"), "net_new": k.get("net_new"),
                     "stores": k.get("stores"), "delivery_pct": k.get("delivery_pct")})
for i, qq in enumerate(quarters):  # year-on-year growth of revenue and operating profit
    prev = next((x for x in quarters if x["p"] == f"{int(qq['p'][:4]) - 1}{qq['p'][4:]}"), None)
    if prev is None:
        v0 = q_all.get(f"{int(qq['p'][:4]) - 1}{qq['p'][4:]}", {})
        prev = {"revenue": (v0.get("revenue") or np.nan) / M, "op": (v0.get("op_income") or np.nan) / M}
    qq["revenue_yoy"] = rnd(qq["revenue"] / prev["revenue"] - 1) if prev.get("revenue") else None
    qq["op_yoy"] = rnd(qq["op"] / prev["op"] - 1) if prev.get("op") else None

# ================================================================ balance sheet, cash and debt
bal_dates = [f"{y}-12-31" for y in range(2023, 2026)] + ["2026-09-30"]  # years with long-term deposits known
balance = []
for e in bal_dates:
    cash, sti, stb = INST["cash"].get(e), INST["sti"].get(e), INST["stb"].get(e, 0)
    ltd = LT_DEPOSITS.get(e)
    tot_cash = (cash or 0) + (sti or 0) + (ltd or 0)
    balance.append({"p": e[:7], "cash": rnd(cash / M, 1) if cash else None, "sti": rnd(sti / M, 1) if sti else None,
                    "lt_deposits": ltd, "cash_total": rnd(tot_cash / M if ltd is None else (cash + sti) / M + ltd, 1),
                    "debt": rnd(stb / M, 1), "lease": rnd(INST["lease"].get(e, np.nan) / M, 1) if INST["lease"].get(e) else None,
                    "net_cash": rnd(((cash or 0) + (sti or 0) - stb) / M + (ltd or 0), 1), "equity": rnd(INST["equity"].get(e, np.nan) / M, 1),
                    "nci": rnd(INST["nci"].get(e, np.nan) / M, 1), "debt_asset": rnd(INST["liab"].get(e, np.nan) / INST["assets"].get(e, np.nan)),
                    "lt_deposits_known": ltd is not None})
last = balance[-1]
ttm = lambda key: sum((q_all[e].get(key) or 0) for e in ("2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"))  # noqa: E731
op_ttm, ni_ttm = ttm("op_income") / M, ttm("net_income") / M
dna_ttm = ttm("dna") / M if all(q_all[e].get("dna") is not None for e in ("2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30")) else FY["dna"]["2025-12-31"] / M
ebitda_ttm = op_ttm + dna_ttm
cfo_ttm, capex_ttm = ttm("cfo") / M, ttm("capex") / M
solvency = {"date": "2026-09-30", "cash_total": last["cash_total"], "debt": last["debt"], "net_cash": last["net_cash"], "lease": last["lease"],
            "ebitda_ttm": rnd(ebitda_ttm, 1), "op_ttm": rnd(op_ttm, 1), "net_cash_to_ebitda": rnd(last["net_cash"] / ebitda_ttm, 2),
            "debt_to_ebitda": rnd(last["debt"] / ebitda_ttm, 2), "lease_adj_net_debt": rnd(last["lease"] - last["net_cash"], 1),
            "lease_adj_nd_ebitdar": None, "bridge": BRIDGE_LOAN, "cfo_ttm": rnd(cfo_ttm, 1), "capex_ttm": rnd(capex_ttm, 1),
            "fcf_ttm": rnd(cfo_ttm - capex_ttm, 1), "returns_9m26": rnd((sum((q_all[e].get("dividends_paid") or 0) + (q_all[e].get("buybacks") or 0)
                                                                         for e in ("2026-03-31", "2026-06-30", "2026-09-30"))) / M, 1)}
solvency["interest_on_bridge_annual"] = rnd(BRIDGE_LOAN["amount"] * BRIDGE_LOAN["rate"], 1)

# ================================================================ valuation (USD line and HK line)
yinfo = fl.load_info(os.path.join(RAW, "yahoo", "YUMC_info.json"))
hinfo = fl.load_info(os.path.join(RAW, "yahoo", "9987_HK_info.json"))
px_us = ml.read_series(os.path.join(RAW, "yahoo", "YUMC.csv"), "Date", "Close")
px_hk = ml.read_series(os.path.join(RAW, "yahoo", "9987_HK.csv"), "Date", "Close")
fx_hkd = float(ml.read_series(os.path.join(RAW, "yahoo", "HKD_X.csv"), "Date", "Close").iloc[-1])
fx_cny_hkd = float(ml.read_series(os.path.join(RAW, "yahoo", "HKDCNY_X.csv"), "Date", "Close").iloc[-1])
shares = float(yinfo.get("sharesOutstanding")) / M
price_us, price_hk = float(px_us.iloc[-1]), float(px_hk.iloc[-1])
mcap = shares * price_hk / fx_hkd  # HK close of 2026-11-26 in USD
eps_ttm = FY["eps"]["2025-12-31"] - 2.11 + 2.48  # 2025 FY diluted EPS 2.51 - 9M 2025 2.11 + 9M 2026 2.48 (press releases / XBRL)
dps_fwd = 0.29 * 4
ev = mcap + last["debt"] - last["cash_total"] + last["nci"]
pe_hist = pd.read_csv(os.path.join(RAW, "fin", "valuation_baidu_市盈率TTM.csv"))
pe_hist = pd.Series(pe_hist["value"].values, index=pd.to_datetime(pe_hist["date"])).dropna()
valuation = {"date_hk": str(px_hk.index[-1].date()), "date_us": str(px_us.index[-1].date()), "price_hk": price_hk, "price_us": price_us,
             "fx_hkd_per_usd": rnd(fx_hkd, 4), "shares_mn": rnd(shares, 1), "mcap_usd_mn": rnd(mcap, 0), "mcap_hkd_mn": rnd(mcap * fx_hkd, 0),
             "eps_ttm": rnd(eps_ttm, 2), "pe_ttm": rnd(price_hk / fx_hkd / eps_ttm, 2), "pe_fwd_consensus": rnd(yinfo.get("forwardPE"), 2),
             "pb": rnd(mcap / last["equity"], 2), "ev_usd_mn": rnd(ev, 0), "ev_ebitda": rnd(ev / ebitda_ttm, 2),
             "dy_fwd": rnd(dps_fwd / (price_hk / fx_hkd)), "dps_quarter": 0.29, "shareholder_yield_2026": rnd(1500 / mcap),
             "fcf_yield": rnd((cfo_ttm - capex_ttm) / mcap), "pe_pct": rnd(ml.percentile_rank(pe_hist), 3), "pe_hist_median": rnd(pe_hist.median(), 2),
             "pe_hist_min": rnd(pe_hist.min(), 2), "pe_hist_max": rnd(pe_hist.max(), 2), "pe_hist_start": str(pe_hist.index[0].date()),
             "target_mean_hk": rnd(hinfo.get("targetMeanPrice"), 1), "n_analysts_hk": hinfo.get("numberOfAnalystOpinions"),
             "target_mean_us": rnd(yinfo.get("targetMeanPrice"), 2), "target_high_us": yinfo.get("targetHighPrice"), "target_low_us": yinfo.get("targetLowPrice"),
             "n_analysts_us": yinfo.get("numberOfAnalystOpinions"), "broker_targets": BROKERS,
             "pe_series": {"date": [str(d.date()) for d in pe_hist.index], "pe": [rnd(v, 2) for v in pe_hist]}}
valuation["upside_consensus_hk"] = rnd(valuation["target_mean_hk"] / price_hk - 1) if valuation["target_mean_hk"] else None

# ================================================================ sensitivity (illustrative)
cs_ttm = COSTS_9M26["company_sales"] / 9 * 12  # annualised company sales
fp_share = COSTS_9M26["food_paper"] / COSTS_9M26["company_sales"]
pay_share = COSTS_9M26["payroll"] / COSTS_9M26["company_sales"]
occ_share = COSTS_9M26["occupancy_other"] / COSTS_9M26["company_sales"]
flow_through = 1 - fp_share - 0.10 - pay_share / 3  # incremental same-store sales: food & paper, ~10% rider/variable other, ~1/3 of payroll
sens = [
    {"label": "同店销售", "change": "±1 个百分点", "basis": f"年化公司餐厅收入 {cs_ttm:,.0f} 百万美元 × 增量利润率约 {flow_through:.0%}（扣食品包装 {fp_share:.1%}、约 10% 骑手及变动费用、约三分之一人工）",
     "op": rnd(cs_ttm * 0.01 * flow_through, 1)},
    {"label": "食品和包装成本", "change": "±1%", "basis": f"食品和包装占公司餐厅收入 {fp_share:.1%}", "op": rnd(-cs_ttm * fp_share * 0.01, 1)},
    {"label": "人民币兑美元", "change": "±1%", "basis": "收入、成本均为人民币，按美元报告：经营利润同比例变动（折算影响）", "op": rnd(op_ttm * 0.01, 1)},
    {"label": "必胜客特许费节省", "change": "全年", "basis": "收购前 12 个月向 Yum! Brands 支付的必胜客特许费（税后）约 6,200 万美元", "op": PH_DEAL["ltm_license_fee_net"]},
    {"label": "过桥贷款利息", "change": "全年", "basis": "12.52 亿美元 × 约 1.9%", "op": rnd(-solvency["interest_on_bridge_annual"], 1)},
]
for s_ in sens:
    s_["share_of_op"] = rnd(s_["op"] / op_ttm) if s_.get("op") is not None else None
# empirical check: quarterly year-on-year change in adjusted OP margin against same-store sales growth (2019-2026)
rows = []
for e, k in ops.items():
    if e < "2019-01-01" or k.get("sssg") is None or k.get("adj_op_mn") is None:
        continue
    e0 = f"{int(e[:4]) - 1}{e[4:]}"
    k0 = ops.get(e0, {})
    if k0.get("adj_op_mn") is None or e not in q_all or e0 not in q_all:
        continue
    m1 = k["adj_op_mn"] / (q_all[e]["revenue"] / M)
    m0 = k0["adj_op_mn"] / (q_all[e0]["revenue"] / M)
    rows.append({"p": e, "sssg": k["sssg"], "d_margin": m1 - m0})
dfm = pd.DataFrame(rows)
mm = sm.OLS(dfm["d_margin"], sm.add_constant(dfm["sssg"])).fit(cov_type="HC1")
ex = dfm[~pd.to_datetime(dfm["p"]).dt.year.isin([2020, 2021, 2022])]
mm2 = sm.OLS(ex["d_margin"], sm.add_constant(ex["sssg"])).fit(cov_type="HC1")
sens_emp = {"n": int(len(dfm)), "slope_pp_per_pp": rnd(mm.params["sssg"], 3), "t": rnd(mm.tvalues["sssg"], 2), "r2": rnd(mm.rsquared, 3),
            "n_ex": int(len(ex)), "slope_ex": rnd(mm2.params["sssg"], 3), "t_ex": rnd(mm2.tvalues["sssg"], 2), "r2_ex": rnd(mm2.rsquared, 3),
            "points": [{"p": r["p"], "sssg": rnd(r["sssg"], 3), "d_margin": rnd(r["d_margin"], 4)} for r in rows]}

# ================================================================ HK restaurant peers (RMB, Eastmoney + Yahoo)
def last_periods(ind):
    """Latest annual report date, latest report date, and the same period a year earlier (for TTM)."""
    ann = [d for d in ind.index if ind.loc[d, "annual"]]
    fy = ann[-1]
    latest = ind.index[-1]
    prior = f"{int(latest[:4]) - 1}{latest[4:]}"
    return fy, latest, prior if prior in ind.index and latest != fy else None


peers = []
for code, name in [(TARGET, "百胜中国")] + list(PEERS.items()):
    ind = fl.hk_indicators(os.path.join(RAW, "fin", f"ind_{int(code):05d}.csv"))
    info = fl.load_info(os.path.join(RAW, "yahoo", f"{int(code):04d}_HK_info.json"))
    fy, latest, prior = last_periods(ind)
    g = lambda d, c, s=1.0: fl._g(ind, d, c, s)  # noqa: E731
    np_ttm = g(fy, "HOLDER_PROFIT") + (g(latest, "HOLDER_PROFIT") - g(prior, "HOLDER_PROFIT") if prior else 0)
    rev_ttm = g(fy, "OPERATE_INCOME") + (g(latest, "OPERATE_INCOME") - g(prior, "OPERATE_INCOME") if prior else 0)
    mcap_hkd = info.get("marketCap")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    bps = g(latest, "BPS")
    row = {"code": code, "name": name, "fy": fy, "latest": latest, "mcap_hkd": rnd(mcap_hkd / M, 0) if mcap_hkd else None,
           "mcap_cny": rnd(mcap_hkd * fx_cny_hkd / M, 0) if mcap_hkd else None, "price": price,
           "revenue": rnd(g(fy, "OPERATE_INCOME", 1 / M), 0), "revenue_yoy": rnd(g(fy, "OPERATE_INCOME_YOY", 0.01)),
           "np": rnd(g(fy, "HOLDER_PROFIT", 1 / M), 0), "np_yoy": rnd(g(fy, "HOLDER_PROFIT_YOY", 0.01)), "roe": rnd(g(fy, "ROE_AVG", 0.01)),
           "gross_margin": rnd(g(fy, "GROSS_PROFIT_RATIO", 0.01)), "net_margin": rnd(g(fy, "NET_PROFIT_RATIO", 0.01)),
           "rev_latest_yoy": rnd(g(latest, "OPERATE_INCOME_YOY", 0.01)) if latest != fy else None,
           "np_latest_yoy": rnd(g(latest, "HOLDER_PROFIT_YOY", 0.01)) if latest != fy else None,
           "pe_ttm": rnd(mcap_hkd * fx_cny_hkd / np_ttm, 2) if mcap_hkd and np_ttm and np_ttm > 0 else None,
           "ps_ttm": rnd(mcap_hkd * fx_cny_hkd / rev_ttm, 2) if mcap_hkd and rev_ttm else None,
           "pb": rnd(price * fx_cny_hkd / bps, 2) if price and bps else None,
           "debt_asset": rnd(g(latest, "DEBT_ASSET_RATIO", 0.01)),
           "pe_fwd": rnd(info.get("forwardPE"), 2), "target_upside": rnd(info["targetMeanPrice"] / price - 1) if info.get("targetMeanPrice") and price else None,
           "n_analysts": info.get("numberOfAnalystOpinions"), "net_cash_cny": None}
    if code == TARGET:  # the company's own TTM P/E from US GAAP diluted EPS is the headline figure; keep Eastmoney's for comparability
        row["pe_ttm_usd_basis"] = valuation["pe_ttm"]
    peers.append(row)
peer_ranks = {}
# dividend yields are left out: Yahoo's trailing yield for HK names mixes currencies and special dividends (9987 shows 0.3%)
for k in ("revenue", "mcap_cny", "revenue_yoy", "np_yoy", "roe", "net_margin", "rev_latest_yoy", "np_latest_yoy", "pe_ttm", "pb", "ps_ttm"):
    vals = sorted([(p[k], p["code"]) for p in peers if p.get(k) is not None], reverse=True)
    pos = [c for _, c in vals].index(TARGET) + 1 if any(c == TARGET for _, c in vals) else None
    peer_ranks[k] = {"rank": pos, "of": len(vals)}
peer_medians = {k: rnd(float(np.nanmedian([p[k] for p in peers if p.get(k) is not None and p["code"] != TARGET])))
                for k in ("revenue_yoy", "np_yoy", "roe", "net_margin", "pe_ttm", "pb", "ps_ttm", "rev_latest_yoy", "np_latest_yoy")}
peer_mcap_total = sum(p["mcap_cny"] for p in peers if p.get("mcap_cny"))
peer_rev_total = sum(p["revenue"] for p in peers if p.get("revenue"))

# global quick-service restaurant companies (Yahoo info, USD)
global_rows = []
for t, nm in [("YUMC", "百胜中国")] + list(GLOBAL.items()):
    i = fl.load_info(os.path.join(RAW, "yahoo", f"{t}_info.json"))
    if not i:
        continue
    global_rows.append({"code": t, "name": nm, "mcap_usd_bn": rnd((i.get("marketCap") or 0) / 1e9, 1), "pe_ttm": rnd(i.get("trailingPE"), 1),
                        "pe_fwd": rnd(i.get("forwardPE"), 1), "ev_ebitda": rnd(i.get("enterpriseToEbitda"), 1), "op_margin": rnd(i.get("operatingMargins")),
                        "rev_growth_q": rnd(i.get("revenueGrowth")), "dy": rnd(i.get("trailingAnnualDividendYield") or 0.0)})

# southbound (Stock Connect) holdings
sb = pd.read_csv(os.path.join(RAW, "fin", "southbound_holdings.csv"))
southbound = {"date": sb["持股日期"].iloc[-1], "shares_mn": rnd(sb["持股数量"].iloc[-1] / M, 2), "pct": rnd(sb["持股数量占A股百分比"].iloc[-1] / 100, 4),
              "start_date": sb["持股日期"].iloc[0], "start_pct": rnd(sb["持股数量占A股百分比"].iloc[0] / 100, 4)}

res = {"currency": "USD", "unit_label": "百万美元", "annual": annual, "quarters": quarters, "balance": balance, "solvency": solvency,
       "valuation": valuation, "sensitivity": sens, "sensitivity_empirical": sens_emp, "costs_9m26": COSTS_9M26, "pizza_hut": PH_DEAL,
       "guidance": GUIDANCE, "peers": peers, "peer_ranks": peer_ranks, "peer_medians": peer_medians, "peer_mcap_total_cny": rnd(peer_mcap_total, 0),
       "peer_rev_total_cny": rnd(peer_rev_total, 0), "global_peers": global_rows, "southbound": southbound, "industry": INDUSTRY, "sources": SOURCES,
       "fx": {"hkd_per_usd": rnd(fx_hkd, 4), "cny_per_hkd": rnd(fx_cny_hkd, 4)}}
ml.dump_json(res, os.path.join(OUT, "fundamentals.json"))
print(json.dumps(ml.clean({k: res[k] for k in ("solvency", "sensitivity", "sensitivity_empirical", "peer_ranks", "peer_medians", "southbound")}), ensure_ascii=False, indent=0)[:5000])
print(json.dumps(ml.clean({k: v for k, v in valuation.items() if k not in ("pe_series", "broker_targets")}), ensure_ascii=False))
for a in annual:
    print(a)
for p in peers:
    print({k: p[k] for k in ("code", "name", "fy", "latest", "mcap_cny", "revenue", "revenue_yoy", "np_yoy", "roe", "net_margin", "rev_latest_yoy", "np_latest_yoy", "pe_ttm", "pb")})
