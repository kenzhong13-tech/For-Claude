"""上海电力: operating data, power demand, coal prices and the illustrative profit sensitivity.

Reads the company's quarterly generation announcements (发电量完成情况公告, 2018 onward) from data/raw/filings, the
monthly national power consumption and coal prices from data/raw/power and data/raw/yahoo, and figures transcribed from
the annual reports (each with a comment naming the report). Writes data/processed/power_analysis.json, which
report_kit/build_report.py adds to the page as DATA.power_analysis.

usage: python shpower_analysis/scripts/analyze_power.py   (after analyze_market.py, whose sample end date it reads)
"""
import glob
import json
import os
import re
import warnings

import numpy as np
import pandas as pd

warnings.simplefilter("ignore", pd.errors.PerformanceWarning)
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
FIN = os.path.join(RAW, "fin")

# ============================================================ generation announcements
TYPES = {"coal": "煤电", "gas": "气电", "wind": "风电", "solar": "光伏发电"}


def flat(path):
    """Announcement text without whitespace and without the repeated page header."""
    t = re.sub(r"\s+", "", open(path, encoding="utf-8").read())
    return re.sub(r"\d?证券简称：上海电力证券代码：600021编号：临\d{4}-\d{3}", "", t)  # page number + header


def num(pattern, text):
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def parse_generation(path):
    name = os.path.basename(path)
    if re.search(r"1-8月|1-11月", name):
        return None
    year = int(re.search(r"_(?:\D*?)(20\d\d)年", name).group(1))
    period = "Q1" if "第一季度" in name else "H1" if "上半年" in name else "9M" if "前三季度" in name else "FY"
    t = flat(path)
    row = {"year": year, "period": period, "published": name[:10],
           "gen": num(r"完成合并口径发电量([\d.]+)亿千瓦时", t),
           "ongrid": num(r"上网电量([\d.]+)亿千瓦时", t),
           "tariff": num(r"上网电价均价（含税）([\d.]+)元/千瓦时", t),
           "market": num(r"市场(?:化)?交易(?:结算)?(?:的总)?电量([\d.]+)亿千瓦时", t),
           "cap": None, "clean_share": None}
    # capacity only from the "截至 X 月底，公司控股装机容量为 …" sentence (other sentences mention additions)
    m = re.search(r"截至\d{4}年\d{1,2}月(?:底|末)，?公司控股装机容量(?:为|达到)?([\d.]+)万千瓦(.{0,300})", t)
    if m:
        row["cap"], tail = float(m.group(1)), m.group(2)
        row["clean_share"] = num(r"清洁能源占\d?装?\d?机?规模的([\d.]+)%", tail)
    for k, cn in TYPES.items():
        row[f"gen_{k}"] = num(cn + r"完成([\d.]+)亿千瓦时", t)
        row[f"cap_{k}"] = num(cn + r"([\d.]+)万千瓦", tail) if m else None
    return row


def plants(path):
    """Plant-level generation and on-grid volume (亿千瓦时) from one announcement."""
    t = re.sub(r"[ \t]+", " ", open(path, encoding="utf-8").read())
    out = {}
    for m in re.finditer(r"([一-鿿A-Za-z0-9#]+?(?:电厂|发电厂|风电场|光伏电站|热电厂))\s+([\d.]+)\s+([\d.]+)", t):
        out[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return out


files = sorted(glob.glob(os.path.join(RAW, "filings", "*发电量完成情况公告*.txt")))
gen = pd.DataFrame([r for r in (parse_generation(f) for f in files) if r])
gen = gen.sort_values(["year", "period", "published"]).drop_duplicates(["year", "period"], keep="last").reset_index(drop=True)
order = {"Q1": 1, "H1": 2, "9M": 3, "FY": 4}
gen["q"] = gen["period"].map(order)
gen = gen.sort_values(["year", "q"]).reset_index(drop=True)

# single quarters from cumulative figures within each year
qrows = []
for y, g in gen.groupby("year"):
    prev = None
    for _, r in g.sort_values("q").iterrows():
        cur = {k: r[k] for k in ["gen", "gen_coal", "gen_gas", "gen_wind", "gen_solar", "ongrid"]}
        if prev is not None and r["q"] - prev["q"] != 1:
            prev = None  # a missing quarter: no single-quarter figure
        if r["q"] == 1 or prev is not None:
            single = {k: (cur[k] - (prev["v"][k] if prev else 0)) if cur[k] is not None and (prev is None or prev["v"][k] is not None) else None
                      for k in cur}
            qrows.append({"y": int(y), "q": int(r["q"]), "label": f"{str(y)[2:]}Q{int(r['q'])}", **single})
        prev = {"q": r["q"], "v": cur}
quarters = pd.DataFrame(qrows)
quarters["gen_yoy"] = quarters.groupby("q")["gen"].pct_change()  # same quarter a year earlier (rows are sorted by year)
quarters = quarters.sort_values(["y", "q"]).reset_index(drop=True)
for k in ("gen_coal",):
    quarters[f"{k}_yoy"] = quarters.groupby("q")[k].pct_change()
quarters = quarters.sort_values(["y", "q"]).reset_index(drop=True)

fy = gen[gen["period"] == "FY"].set_index("year")
latest = gen.iloc[-1]                                           # 2026 9M
same_ly = gen[(gen["year"] == latest["year"] - 1) & (gen["period"] == latest["period"])].iloc[0]

# ============================================================ figures from the annual reports
# 入炉标煤单价（含税，元/吨）, as reported each year (the base year is sometimes restated, so the reported change is kept too)
COAL_UNIT = {2021: (1238.48, 0.6742),   # 2021 年年度报告 管理层讨论与分析
             2022: (1461.32, 0.1786),   # 2022 年年度报告
             2023: (1157.16, -0.1865),  # 2023 年年度报告
             2024: (1072.41, -0.0732),  # 2024 年年度报告
             2025: (966.98, -0.1310)}   # 2025 年年度报告（合并口径）
# 利用小时（小时）, 发电效率情况分析 tables of the 2021-2025 annual reports (earlier years from the prior-year column)
HOURS = {"coal": {2020: 4209, 2021: 4849, 2022: 4732, 2023: 5316, 2024: 5278, 2025: 5179},
         "gas": {2020: 1992, 2021: 2540, 2023: 2506, 2024: 2513, 2025: 2040},
         "wind": {2023: 2397, 2024: 2493, 2025: 2239},
         "solar": {2024: 1175, 2025: 1140}}
# 资本性支出（亿元）, “资本性支出情况” of each annual report
CAPEX = {2018: 157.98, 2019: 97.25, 2020: 246.40, 2021: 263.18, 2022: 92.30, 2023: 135.28, 2024: 225.34, 2025: 205.43}
# 综合资金成本 at year end, 2019, 2020, 2024 and 2025 annual reports
FUNDING_COST = {2018: 0.0446, 2019: 0.0409, 2020: 0.0374, 2023: 0.0347, 2024: 0.0296, 2025: 0.0251}
# 2025 年年度报告：主营业务分地区（亿元，毛利率）, 主要控股参股公司（净利润，亿元）
REGIONS_2025 = [("上海", 136.72, 0.1156), ("江苏", 122.01, 0.3248), ("土耳其", 51.90, 0.3302), ("安徽", 35.05, 0.2860),
                ("浙江", 23.58, 0.2751), ("日本", 7.81, 0.5133), ("马耳他", 5.80, 0.2218), ("其他地区", 29.78, 0.3188)]
SUBSIDIARIES_2025 = [  # (name, business, revenue, net profit), 亿元, 100% basis
    ("国家电投集团江苏电力", "江苏火电、风电、光伏", 116.11, 19.85),
    ("土耳其 EMBA 发电（胡努特鲁电厂）", "土耳其煤电", 52.31, 12.64),
    ("中电投融和融资租赁（参股）", "融资租赁", 38.37, 12.71),
    ("上海上电漕泾发电", "上海煤电", 44.69, 5.99),
    ("上海电力能源发展（香港）", "境外项目控股", 9.42, 5.93),
    ("淮沪电力（田集二厂）", "安徽煤电联营", 29.63, 4.71),
    ("上海漕泾热电", "上海热电联供", 33.76, 3.56),
    ("上海电力新能源发展", "新能源", 21.95, 3.47),
    ("国家电投集团浙江电力", "浙江燃机、新能源", 13.80, 3.03),
    ("上海吴泾第二发电（参股）", "上海煤电", 22.26, 2.07),
    ("上海上电新达新能源", "新能源", 5.93, 1.21),
    ("上海电力日本株式会社", "日本光伏", 7.82, 1.03),
    ("上海外高桥发电", "上海煤电", 22.42, 0.002),
]
# 2025 年年度报告：成本构成（亿元）
FUEL_COST = {2024: 196.45, 2025: 169.04}       # 电力行业 燃料
DEPRECIATION_POWER = {2024: 66.31, 2025: 70.29}
OVERSEAS = {"assets_2025": 270.55, "assets_2026h1": 236.64, "profit_2025": 16.68, "profit_2024": 16.68 / 2.1061,
            "cap_2025": 213.37, "cap_2026h1": 224.58, "managed_cge": 982.75, "managed_huanghe": 121.01}
HEAT_2025 = {"heat_gj_10k": 2166.16, "heat_yoy": 0.0895, "heat_rev": 22.05}
BUDGET_2026 = {"gen": 888, "revenue": 443}       # 2025 年年度报告 经营计划
# 在建重大项目（2025 年年度报告 在建工程表；进度为工程进度）
PROJECTS = [
    ("漕泾综合能源中心二期 2×100 万千瓦", "上海", "煤电", 92.85, 0.4133, "2026 年底前首台投产（半年报：已完成锅炉水压、汽机扣盖）"),
    ("外高桥 2×100 万千瓦扩容量替代", "上海", "煤电", 81.30, 0.0858, "2027Q4–2028Q1 投产（2026-09 业绩说明会）"),
    ("江苏滨海 2×100 万千瓦扩建（滨海三期）", "江苏", "煤电", 79.36, 0.4019, "2026 年 7 月、8 月两台机组投产"),
    ("塞尔维亚黑峰风电", "塞尔维亚", "风电", 19.06, 0.7405, "在建"),
    ("七台河 31.25 万千瓦风电", "黑龙江", "风电", 24.60, 0.5998, "2026 年上半年全容量并网"),
    ("乌兰察布铁合金绿色供电一期 48.45 万千瓦", "内蒙古", "风电/光伏", 13.63, 0.4963, "在建"),
    ("奉贤 1# 50 万千瓦海上光伏", "上海", "光伏", None, None, "2025 年开工"),
    ("滨海南区 H5# 40 万千瓦、东台 H7# 20 万千瓦海上风电", "江苏", "风电", None, None, "已核准（2026-03）"),
]
CIP_MAJOR_BUDGET = 476.36                        # 在建工程重要项目预算合计（亿元）, 2025 年年度报告
CAPITALISED_INTEREST_2025 = 2.74                 # 本期利息资本化金额（亿元）, 同上

# ============================================================ power demand (全社会用电量, cumulative YTD with YoY)
el = pd.read_csv(os.path.join(RAW, "power", "society_electricity.csv"))
el["y"] = el["统计时间"].astype(str).str.split(".").str[0].astype(int)
el["m"] = el["统计时间"].astype(str).str.split(".").str[1].astype(int)
el = el[(el["y"] >= 2017)]
demand = []
for (y, m), r in el.set_index(["y", "m"]).iterrows():
    if m in (3, 6, 9, 12):
        demand.append({"y": int(y), "q": m // 3, "cum_twh": float(r["全社会用电量"]) / 1e8 * 1e4 / 1e4 if pd.notna(r["全社会用电量"]) else None,
                       "cum_yoy": float(r["全社会用电量同比"]) / 100 if pd.notna(r["全社会用电量同比"]) else None})
demand = pd.DataFrame(demand)

# company cumulative generation YoY at the same points (reported cumulative figures)
cum = []
for _, r in gen.iterrows():
    prev = gen[(gen["year"] == r["year"] - 1) & (gen["period"] == r["period"])]
    if len(prev):
        p = prev.iloc[0]
        cum.append({"y": int(r["year"]), "q": int(r["q"]), "gen_yoy": r["gen"] / p["gen"] - 1,
                    "coal_yoy": (r["gen_coal"] / p["gen_coal"] - 1) if r["gen_coal"] and p["gen_coal"] else None,
                    "clean_yoy": ((r["gen"] - r["gen_coal"]) / (p["gen"] - p["gen_coal"]) - 1) if r["gen_coal"] and p["gen_coal"] else None})
cum = pd.DataFrame(cum).merge(demand, on=["y", "q"], how="left")
both = cum.dropna(subset=["gen_yoy", "cum_yoy"])
fy_both = both[both["q"] == 4]
elasticity = {"n_fy": int(len(fy_both)),
              "corr_fy": float(np.corrcoef(fy_both["gen_yoy"], fy_both["cum_yoy"])[0, 1]) if len(fy_both) > 2 else None,
              "corr_coal_fy": float(np.corrcoef(fy_both["coal_yoy"].astype(float), fy_both["cum_yoy"])[0, 1]) if len(fy_both) > 2 else None}

# ============================================================ coal prices
def monthly(path, date_col, val_col):
    d = pd.read_csv(path)
    s = pd.Series(pd.to_numeric(d[val_col], errors="coerce").values, index=pd.to_datetime(d[date_col], errors="coerce")).dropna()
    s = s[s > 0].sort_index()
    return s.resample("ME").mean()


coal = {}
p100 = os.path.join(RAW, "power", "100ppi_coal_weekly.csv")
if os.path.exists(p100):
    d = pd.read_csv(p100)
    if len(d) and "spot_price" in d.columns:
        s = pd.Series(pd.to_numeric(d["spot_price"], errors="coerce").values, index=pd.to_datetime(d["sample_date"])).dropna()
        s = s[s > 0].sort_index()
        coal["spot_100ppi"] = s.resample("ME").mean()
coal["zc_futures"] = monthly(os.path.join(RAW, "power", "main_ZC0.csv"), "日期", "收盘价")
coal["api2_usd"] = monthly(os.path.join(RAW, "yahoo", "MTF_F.csv"), "Date", "Close")
coal["coking_futures"] = monthly(os.path.join(RAW, "power", "main_JM0.csv"), "日期", "收盘价")
coal_m = pd.DataFrame(coal)
coal_m = coal_m[coal_m.index >= "2016-01-01"]
coal_year = coal_m.groupby(coal_m.index.year).mean()

# ============================================================ profit sensitivity (illustrative, FY2025 base)
inc = pd.read_csv(os.path.join(FIN, "is_600021.csv"))
inc["d"] = inc["REPORT_DATE"].astype(str).str[:10]
row25 = inc[inc["d"] == "2025-12-31"].iloc[0]
np_total, np_parent = float(row25["NETPROFIT"]) / 1e8, float(row25["PARENT_NETPROFIT"]) / 1e8
parent_share = np_parent / np_total                          # 2025: about 52%; the rest goes to minority shareholders
tax_domestic = 0.25
k = (1 - tax_domestic) * parent_share
fy25 = fy.loc[2025]
plants_fy25 = plants(next(f for f in files if "2025年度发电量" in f))
turkey_gen = plants_fy25.get("土耳其胡努特鲁电厂", (np.nan, np.nan))[0]
dom_coal_gen = fy25["gen_coal"] - turkey_gen                  # 亿千瓦时, coal-fired generation in China
HEAT_RATE = 0.28579                                           # 千克标准煤/千瓦时：2026 年半年度报告，供电煤耗 285.79 克/千瓦时
coal_tce = dom_coal_gen * 1e8 * HEAT_RATE / 1e3 / 1e4         # 万吨标准煤
coal_price_ex_vat = COAL_UNIT[2025][0] / 1.13
coal_cost = coal_tce * 1e4 * coal_price_ex_vat / 1e8          # 亿元
ongrid = fy25["ongrid"]
power_rev = 383.18                                            # 2025 年年度报告：电力营业收入（亿元）
power_margin_var = power_rev - FUEL_COST[2025]                # revenue less fuel: what one more kWh roughly earns
debt_ib = None                                                # set below from the balance sheet
bs = pd.read_csv(os.path.join(FIN, "bs_600021.csv"))
bs["d"] = bs["REPORT_DATE"].astype(str).str[:10]


def bsv(d, col):
    r = bs[bs["d"] == d]
    return float(pd.to_numeric(r[col], errors="coerce").fillna(0).iloc[0]) / 1e8 if len(r) and col in bs.columns else 0.0


DEBT_PARTS = [("SHORT_LOAN", "短期借款"), ("NONCURRENT_LIAB_1YEAR", "一年内到期的非流动负债"),
              ("OTHER_CURRENT_LIAB", "其他流动负债（主要为超短期融资券）"), ("LONG_LOAN", "长期借款"), ("BOND_PAYABLE", "应付债券"),
              ("LEASE_LIAB", "租赁负债"), ("LONG_PAYABLE", "长期应付款（主要为应付融资租赁款）")]
debt_rows = []
for d in ("2021-12-31", "2023-12-31", "2024-12-31", "2025-12-31", "2026-09-30"):
    parts = {lab: bsv(d, col) for col, lab in DEBT_PARTS}
    total = sum(parts.values())
    cash = bsv(d, "MONETARYFUNDS")
    debt_rows.append({"date": d, **{f"p{i}": v for i, v in enumerate(parts.values())}, "total": total, "cash": cash,
                      "net": total - cash, "perpetual": bsv(d, "PERPETUAL_BOND"), "minority": bsv(d, "MINORITY_EQUITY"),
                      "equity_parent": bsv(d, "TOTAL_PARENT_EQUITY"), "receivables": bsv(d, "NOTE_ACCOUNTS_RECE"),
                      "cip": bsv(d, "CIP"), "assets": bsv(d, "TOTAL_ASSETS"), "liabilities": bsv(d, "TOTAL_LIABILITIES")})
debt_labels = [lab for _, lab in DEBT_PARTS]
debt_ib = debt_rows[-1]["total"]
sens = [
    {"label": "入炉标煤单价（境内煤电）", "change": "±10%", "basis": f"境内煤电发电量 {dom_coal_gen:.0f} 亿千瓦时 × 供电煤耗 {HEAT_RATE * 1000:.1f} 克/千瓦时× 标煤单价 {COAL_UNIT[2025][0]:.0f} 元/吨（含税）",
     "pretax": coal_cost * 0.10},
    {"label": "平均上网电价", "change": "±1 分/千瓦时（含税）", "basis": f"上网电量 {ongrid:.0f} 亿千瓦时，扣增值税",
     "pretax": ongrid * 0.01 / 1.13},
    {"label": "发电量", "change": "±1%", "basis": f"电力收入 {power_rev:.0f} 亿元减燃料成本 {FUEL_COST[2025]:.0f} 亿元",
     "pretax": power_margin_var * 0.01},
    {"label": "融资利率", "change": "±25 个基点", "basis": f"有息负债 {debt_ib:.0f} 亿元（2026-09-30，含超短融和融资租赁），假设全部随市场利率重定价",
     "pretax": debt_ib * 0.0025},
]
for s in sens:
    s["np"] = s["pretax"] * k
    s["share"] = s["np"] / np_parent

# ============================================================ quarterly profit and tax (Eastmoney, single quarters)
qp = []
for y in range(2023, 2027):
    for q, md in ((1, "03-31"), (2, "06-30"), (3, "09-30"), (4, "12-31")):
        d = f"{y}-{md}"
        r = inc[inc["d"] == d]
        if not len(r):
            continue
        cur = {c: float(pd.to_numeric(r[c], errors="coerce").iloc[0]) / 1e8 for c in
               ("TOTAL_OPERATE_INCOME", "TOTAL_PROFIT", "INCOME_TAX", "NETPROFIT", "PARENT_NETPROFIT", "DEDUCT_PARENT_NETPROFIT", "FE_INTEREST_EXPENSE")}
        if q > 1:
            pr = inc[inc["d"] == f"{y}-{('03-31', '06-30', '09-30')[q - 2]}"]
            prev = {c: float(pd.to_numeric(pr[c], errors="coerce").iloc[0]) / 1e8 for c in cur}
            cur = {c: cur[c] - prev[c] for c in cur}
        qp.append({"label": f"{str(y)[2:]}Q{q}", "rev": cur["TOTAL_OPERATE_INCOME"], "pretax": cur["TOTAL_PROFIT"], "tax": cur["INCOME_TAX"],
                   "np": cur["NETPROFIT"], "np_parent": cur["PARENT_NETPROFIT"], "np_adj": cur["DEDUCT_PARENT_NETPROFIT"],
                   "interest": cur["FE_INTEREST_EXPENSE"], "tax_rate": cur["INCOME_TAX"] / cur["TOTAL_PROFIT"] if cur["TOTAL_PROFIT"] else None,
                   "minority_share": 1 - cur["PARENT_NETPROFIT"] / cur["NETPROFIT"] if cur["NETPROFIT"] else None})
qp = pd.DataFrame(qp)
gq = quarters.set_index("label")
qp["gen"] = qp["label"].map(gq["gen"])
qp["gen_coal"] = qp["label"].map(gq["gen_coal"])

# ============================================================ valuation history and per-share figures for ordinary shareholders
val = pd.read_csv(os.path.join(FIN, "value_600021.csv"))
val.index = pd.to_datetime(val["数据日期"])
val = val.sort_index()
weekly = pd.DataFrame({"pe": pd.to_numeric(val["PE(TTM)"], errors="coerce"), "pb": pd.to_numeric(val["市净率"], errors="coerce"),
                       "mcap": pd.to_numeric(val["总市值"], errors="coerce") / 1e8})
last_day = weekly.index.to_series().resample("W-FRI").last()       # label each week with its last trading day
weekly = weekly.resample("W-FRI").last().set_axis(last_day.values).dropna(how="all")
weekly = weekly[weekly.index >= "2018-01-01"]
# 归母净利润 includes the coupon on perpetual bonds (137 亿元 outstanding), which ordinary shareholders do not receive.
# EPS from the reports (basic, after the perpetual coupon): FY2025 0.8727 (2025 年年度报告), 1-9M 2026 0.2572 and
# 1-9M 2025 1.0008 (2026 年第三季度报告); perpetual coupon 30,813.69 万元 in 2025 and 28,915.70 万元 in 1-9M 2026.
EPS = {"fy2025": 0.8727, "m9_2026": 0.2572, "m9_2025": 1.0008}
eps_ttm = EPS["fy2025"] - EPS["m9_2025"] + EPS["m9_2026"]
# ordinary equity at 2026-09-30: 归母权益 3,370,131.65 万元 less perpetual principal 1,369,506.00 万元 and accrued coupon
# 28,967.75 万元 (2026 年第三季度报告注 2); shares 2,821,875,805
common_equity = (3370131.65 - 1369506.00 - 28967.75) / 1e4
shares = 28.21875805
per_share = {"eps_ttm": eps_ttm, "eps_9m_annualised": EPS["m9_2026"] * 4 / 3, "bvps_common": common_equity / shares,
             "common_equity": common_equity, "shares": shares, "perp_coupon_2025": 3.0814, "perp_coupon_9m2026": 2.8916,
             "perp_principal": 136.9506, "np_parent_2025": 27.67, "np_common_2025": 27.67 - 3.0814}

# ============================================================ output
def rec(df):
    return json.loads(df.replace({np.nan: None}).to_json(orient="records", force_ascii=False))


res = {
    "annual_ops": [{"y": int(y), **{k2: (None if pd.isna(v) else float(v)) for k2, v in r.items()
                                    if k2 in ("gen", "gen_coal", "gen_gas", "gen_wind", "gen_solar", "ongrid", "tariff", "market",
                                              "cap", "cap_coal", "cap_gas", "cap_wind", "cap_solar", "clean_share")},
                    "coal_unit": COAL_UNIT.get(int(y), (None,))[0], "hours_coal": HOURS["coal"].get(int(y)),
                    "hours_gas": HOURS["gas"].get(int(y)), "hours_wind": HOURS["wind"].get(int(y)), "hours_solar": HOURS["solar"].get(int(y)),
                    "capex": CAPEX.get(int(y)), "funding_cost": FUNDING_COST.get(int(y))} for y, r in fy.iterrows()],
    "latest": {"label": f"{int(latest['year'])} 年前三季度", **{k2: (None if pd.isna(latest[k2]) else float(latest[k2]))
                                                         for k2 in ("gen", "gen_coal", "gen_gas", "gen_wind", "gen_solar", "ongrid", "tariff", "cap",
                                                                    "cap_coal", "cap_gas", "cap_wind", "cap_solar", "clean_share")},
               "prev": {k2: (None if pd.isna(same_ly[k2]) else float(same_ly[k2])) for k2 in ("gen", "gen_coal", "gen_gas", "gen_wind", "gen_solar", "ongrid", "tariff", "cap")}},
    "quarters_gen": rec(quarters),
    "cum_vs_demand": rec(cum),
    "elasticity": elasticity,
    "quarters_profit": rec(qp),
    "plants_fy2025": [{"name": n, "gen": v[0], "ongrid": v[1]} for n, v in sorted(plants_fy25.items(), key=lambda kv: -kv[1][0])],
    "plants_9m2026": [{"name": n, "gen": v[0], "ongrid": v[1]} for n, v in sorted(plants(files[-1]).items(), key=lambda kv: -kv[1][0])],
    "regions_2025": [{"name": n, "rev": r, "gm": g} for n, r, g in REGIONS_2025],
    "subsidiaries_2025": [{"name": n, "biz": b, "rev": r, "np": p} for n, b, r, p in SUBSIDIARIES_2025],
    "fuel_cost": FUEL_COST, "depreciation_power": DEPRECIATION_POWER, "overseas": OVERSEAS, "heat_2025": HEAT_2025, "budget_2026": BUDGET_2026,
    "projects": [{"name": a, "where": b, "type": c, "budget": d, "progress": e, "status": f} for a, b, c, d, e, f in PROJECTS],
    "cip_major_budget": CIP_MAJOR_BUDGET, "capitalised_interest_2025": CAPITALISED_INTEREST_2025,
    "debt": {"labels": debt_labels, "rows": debt_rows},
    "sensitivity": {"rows": sens, "k": k, "parent_share": parent_share, "tax": tax_domestic, "np_parent_2025": np_parent,
                    "dom_coal_gen": dom_coal_gen, "turkey_gen": turkey_gen, "heat_rate": HEAT_RATE, "coal_tce": coal_tce, "coal_cost": coal_cost},
    "coal_monthly": {"dates": coal_m.index.strftime("%Y-%m").tolist(), **{c: [None if pd.isna(v) else round(float(v), 2) for v in coal_m[c]] for c in coal_m.columns}},
    "coal_yearly": {str(y): {c: (None if pd.isna(v) else round(float(v), 1)) for c, v in r.items()} for y, r in coal_year.iterrows()},
    "val_weekly": {"dates": weekly.index.strftime("%Y-%m-%d").tolist(), **{c: [None if pd.isna(v) else round(float(v), 2) for v in weekly[c]] for c in weekly.columns}},
    "per_share": per_share,
}
os.makedirs(OUT, exist_ok=True)
json.dump(res, open(os.path.join(OUT, "power_analysis.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)

pd.set_option("display.width", 220)
print(gen[["year", "period", "gen", "gen_coal", "gen_gas", "gen_wind", "gen_solar", "ongrid", "tariff", "market", "cap", "cap_coal", "cap_gas", "cap_wind", "cap_solar", "clean_share"]].to_string())
print(quarters.tail(12).round(2).to_string())
print(cum.tail(8).round(3).to_string())
print("elasticity", elasticity)
print(qp.round(2).to_string())
print("sensitivity k", round(k, 3), "parent share", round(parent_share, 3), "dom coal gen", round(dom_coal_gen, 1), "turkey", turkey_gen, "coal tce", round(coal_tce, 0), "coal cost", round(coal_cost, 1))
for s in sens:
    print(s["label"], s["change"], round(s["pretax"], 2), round(s["np"], 2), f"{s['share']:.1%}")
for r in debt_rows:
    print(r["date"], round(r["total"], 1), round(r["net"], 1), "perp", round(r["perpetual"], 1), "recv", round(r["receivables"], 1))
print(coal_year.round(1).to_string())
print("per share", {k: round(v, 4) for k, v in per_share.items()})
print("PE weekly last", weekly.tail(3).round(2).to_string())
