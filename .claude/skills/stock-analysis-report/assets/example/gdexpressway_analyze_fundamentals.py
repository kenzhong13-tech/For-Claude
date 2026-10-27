"""Financials, debt and solvency, expansion capex, sensitivities, valuation and peer comparison for 粤高速A (000429.SZ).

Statements, dividends and valuation history come from Eastmoney (data/raw/fin/); road-level traffic and toll revenue,
expansion budgets, toll periods and loan rates are transcribed from the company's annual and interim reports
(data/raw/cninfo/). Writes data/processed/fundamentals.json.
"""
import json
import os

import warnings

import numpy as np
import pandas as pd

warnings.simplefilter("ignore", pd.errors.PerformanceWarning)

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIN = os.path.join(ROOT, "data", "raw", "fin")
OUT = os.path.join(ROOT, "data", "processed")
ME = "000429"
SHARES = 2_090_806_126
NAMES = {"000429": "粤高速A", "600377": "宁沪高速", "001965": "招商公路", "600350": "山东高速", "600548": "深高速",
         "600012": "皖通高速", "601107": "四川成渝", "600269": "赣粤高速", "600033": "福建高速", "000900": "现代投资",
         "600035": "楚天高速", "600020": "中原高速", "000828": "东莞控股", "601518": "吉林高速", "601188": "龙江交通",
         "600368": "五洲交通"}
M = 1e6


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


IS, BS, CF, IND = (load(k, ME) for k in ("is", "bs", "cf", "ind"))
DIV = pd.read_csv(os.path.join(FIN, f"div_{ME}.csv"))
DIV["rp"] = DIV["报告期"].astype(str).str[:10]
dps_by_year = {int(r[:4]): float(v) / 10 for r, v in zip(DIV["rp"], DIV["现金分红-现金分红比例"]) if r.endswith("12-31")}


def debt_parts(df, d):
    parts = {k: nz(val(df, d, c)) / M for k, c in (("short", "SHORT_LOAN"), ("current", "NONCURRENT_LIAB_1YEAR"),
                                                    ("long", "LONG_LOAN"), ("bond", "BOND_PAYABLE"),
                                                    ("short_bond", "SHORT_BOND_PAYABLE"))}
    parts["total"] = sum(parts.values())
    return parts


# ---------- annual ----------
# Eastmoney carries 2019 restated for the 2020 common-control acquisition of 广惠 (consolidated from then on); the 2018
# comparatives below are the restated ones from the 2020 annual report, and 2019 dividends were set on the original
# 2019 profit (1,258.6m)
RESTATED_2018 = {"revenue": 5074.352, "np": 1880.525, "dnp": 1395.441}
AS_REPORTED_NP = {2019: 1258.628}
annual = []
for y in range(2019, 2026):
    d, dp = f"{y}-12-31", f"{y - 1}-12-31"
    rev, rev0 = val(IS, d, "TOTAL_OPERATE_INCOME") / M, val(IS, dp, "TOTAL_OPERATE_INCOME") / M
    npar, npar0 = val(IS, d, "PARENT_NETPROFIT") / M, val(IS, dp, "PARENT_NETPROFIT") / M
    dnp, dnp0 = val(IS, d, "DEDUCT_PARENT_NETPROFIT") / M, val(IS, dp, "DEDUCT_PARENT_NETPROFIT") / M
    if y == 2019:
        rev0, npar0, dnp0 = RESTATED_2018["revenue"], RESTATED_2018["np"], RESTATED_2018["dnp"]
    cost = val(IS, d, "OPERATE_COST") / M
    da = sum(nz(val(CF, d, c)) for c in ("FA_IR_DEPR", "IA_AMORTIZE", "LPE_AMORTIZE", "USERIGHT_ASSET_AMORTIZE")) / M
    tp, ie = val(IS, d, "TOTAL_PROFIT") / M, nz(val(IS, d, "FE_INTEREST_EXPENSE")) / M
    dps = dps_by_year.get(y)
    annual.append({
        "y": y, "revenue": rev, "yoy": rev / rev0 - 1 if rev0 else None, "gm": 1 - cost / rev,
        "np": npar, "np_yoy": npar / npar0 - 1 if npar0 else None, "dnp": dnp, "dnp_yoy": dnp / dnp0 - 1 if dnp0 else None,
        "minority": val(IS, d, "MINORITY_INTEREST") / M, "invest_income": nz(val(IS, d, "INVEST_INCOME")) / M,
        "credit_impair": nz(val(IS, d, "CREDIT_IMPAIRMENT_INCOME")) / M, "interest_exp": ie,
        "interest_inc": nz(val(IS, d, "FE_INTEREST_INCOME")) / M, "da": da, "ebitda": tp + ie + da,
        "ocf": val(CF, d, "NETCASH_OPERATE") / M, "capex": val(CF, d, "CONSTRUCT_LONG_ASSET") / M,
        "eps": val(IS, d, "BASIC_EPS"), "dps": dps, "payout": dps * SHARES / M / AS_REPORTED_NP.get(y, npar) if dps else None,
        "roe": val(IND, d, "ROEJQ") / 100, "roe_ded": val(IND, d, "ROEKCJQ") / 100,
    })
# half years (H2 = full year - H1)
halves = []
for y in (2023, 2024, 2025, 2026):
    for h in ("H1", "H2"):
        if y == 2026 and h == "H2":
            continue
        if h == "H1":
            g = lambda c: val(IS, f"{y}-06-30", c) / M  # noqa: E731
        else:
            g = lambda c: (val(IS, f"{y}-12-31", c) - val(IS, f"{y}-06-30", c)) / M  # noqa: E731
        halves.append({"p": f"{y}{h}", "revenue": g("TOTAL_OPERATE_INCOME"), "np": g("PARENT_NETPROFIT"),
                       "dnp": g("DEDUCT_PARENT_NETPROFIT"), "minority": g("MINORITY_INTEREST"),
                       "credit_impair": g("CREDIT_IMPAIRMENT_INCOME") if not np.isnan(g("CREDIT_IMPAIRMENT_INCOME")) else 0.0,
                       "interest_exp": g("FE_INTEREST_EXPENSE"), "interest_inc": g("FE_INTEREST_INCOME")})
for i, h in enumerate(halves):
    prev = next((x for x in halves if x["p"] == f"{int(h['p'][:4]) - 1}{h['p'][4:]}"), None)
    for k in ("revenue", "np", "dnp"):
        h[f"{k}_yoy"] = h[k] / prev[k] - 1 if prev else None

# ---------- roads: traffic (10k vehicles) and toll revenue (RMB 10k), transcribed from annual / interim reports ----------
ROADS = {  # name: (stake, consolidated, toll period end)
    "佛开高速": (1.00, True, "北段 2036-03 / 南段 2044-06"),
    "京珠高速广珠段": (0.75, True, "2030-05（改扩建后待核定）"),
    "广惠高速": (0.51, True, "改扩建后预计延至 2054-08"),
    "广佛高速": (0.75, True, "2022-03-03 已停止收费"),
    "惠盐高速": (0.3333, False, "深圳段 2047-02"),
    "广肇高速": (0.25, False, "改扩建中"),
    "江中高速": (0.15, False, "改扩建后新收费标准"),
    "康大高速": (0.30, False, "—"),
    "赣康高速": (0.30, False, "—"),
    "广乐高速": (0.09, False, "—"),
}
TOLL = {  # year: {road: (traffic 10k, toll RMB 10k)}
    2019: {"广佛高速": (7596.92, 47134.57), "佛开高速": (7668.46, 127661.44), "京珠高速广珠段": (7330.12, 118742.52),
           "惠盐高速": (4234.94, 24667.08), "广肇高速": (3506.46, 55550.74), "广惠高速": (7033.28, 191770.96),
           "江中高速": (6134.67, 45633.10), "康大高速": (324.21, 25677.24), "赣康高速": (517.41, 18438.04), "广乐高速": (3039.42, 318505.70)},
    2020: {"广佛高速": (7269.75, 32971.09), "佛开高速": (7718.23, 96148.43), "京珠高速广珠段": (6189.52, 78237.88),
           "广惠高速": (7487.22, 159235.27), "惠盐高速": (4349.60, 18593.50), "广肇高速": (2892.08, 43561.59),
           "江中高速": (6095.58, 33867.12), "康大高速": (147.82, 21190.46), "赣康高速": (440.48, 12833.68), "广乐高速": (3467.39, 248409.48)},
    2021: {"广佛高速": (7928.27, 44885.46), "佛开高速": (8574.49, 145437.73), "京珠高速广珠段": (7165.82, 114088.10),
           "广惠高速": (8295.24, 212619.92), "惠盐高速": (5175.24, 24037.38), "广肇高速": (3813.00, 53568.64),
           "江中高速": (6710.69, 47663.06), "康大高速": (145.57, 31287.88), "赣康高速": (460.81, 19905.23), "广乐高速": (3926.49, 335608.32)},
    2022: {"广佛高速": (7799.42, 6560.05), "佛开高速": (7648.24, 129621.28), "京珠高速广珠段": (5673.10, 90273.43),
           "广惠高速": (7550.65, 183121.92), "惠盐高速": (4471.36, 19950.28), "广肇高速": (3391.71, 46380.80),
           "江中高速": (5117.72, 34198.72), "康大高速": (116.22, 27485.46), "赣康高速": (393.98, 18879.86), "广乐高速": (3758.49, 289900.12)},
    2023: {"广佛高速": (9493.71, 0.0), "佛开高速": (8966.25, 152144.86), "京珠高速广珠段": (7328.58, 115682.76),
           "广惠高速": (9001.09, 213241.43), "惠盐高速": (5244.99, 21658.17), "广肇高速": (4179.30, 54603.58),
           "江中高速": (4768.92, 31256.43), "康大高速": (152.45, 29168.29), "赣康高速": (547.89, 24397.74), "广乐高速": (3975.70, 310552.56)},
    2024: {"广佛高速": (9923.53, 0.0), "佛开高速": (9018.41, 149526.79), "京珠高速广珠段": (7788.64, 107975.71),
           "广惠高速": (8671.69, 192480.52), "惠盐高速": (4598.69, 20402.13), "广肇高速": (4205.52, 53629.85),
           "江中高速": (5971.11, 34984.71), "康大高速": (153.57, 30533.45), "赣康高速": (420.09, 21271.61), "广乐高速": (3912.53, 289047.10)},
    2025: {"广佛高速": (10374.41, 0.0), "佛开高速": (8816.05, 142377.62), "京珠高速广珠段": (7380.06, 95553.75),
           "广惠高速": (8941.49, 200330.19), "惠盐高速": (5739.66, 24895.27), "广肇高速": (3885.44, 47550.80),
           "江中高速": (6334.92, 43085.65), "康大高速": (142.94, 29664.07), "赣康高速": (319.56, 19473.98), "广乐高速": (3853.68, 252890.12)},
}
H1_2026 = {"佛开高速": (4620.75, 0.0787, 70860.26, 0.0346), "京珠高速广珠段": (3598.98, -0.0140, 44104.54, -0.0456),
           "广惠高速": (4351.50, 0.0094, 94335.42, 0.0027), "广佛高速": (5197.73, 0.0252, 0.0, None),
           "惠盐高速": (3095.00, 0.1188, 13840.04, 0.1953), "广肇高速": (1693.66, -0.1500, 21156.91, -0.1092),
           "江中高速": (3262.16, 0.0829, 25103.40, 0.5249), "康大高速": (69.58, -0.0482, 14491.32, -0.0278),
           "赣康高速": (159.25, -0.0250, 9190.60, -0.0370), "广乐高速": (1901.74, -0.0024, 128000.28, -0.0141)}
years = sorted(TOLL)
roads = []
for name, (stake, cons, expiry) in ROADS.items():
    t25, t24 = TOLL[2025][name], TOLL[2024][name]
    roads.append({"name": name, "stake": stake, "consolidated": cons, "expiry": expiry,
                  "traffic_2025": t25[0], "traffic_yoy_2025": t25[0] / t24[0] - 1,
                  "toll_2025": t25[1] / 100, "toll_yoy_2025": (t25[1] / t24[1] - 1) if t24[1] else None,
                  "toll_attrib_2025": t25[1] / 100 * stake,
                  "h1_2026_traffic_yoy": H1_2026[name][1], "h1_2026_toll": H1_2026[name][2] / 100, "h1_2026_toll_yoy": H1_2026[name][3],
                  "toll_hist": [TOLL[y][name][1] / 100 for y in years], "traffic_hist": [TOLL[y][name][0] for y in years]})
core = ["佛开高速", "京珠高速广珠段", "广惠高速"]
toll_attrib = sum(r["toll_attrib_2025"] for r in roads if r["name"] in core)

# ---------- balance sheet, liquidity and solvency ----------
liquidity = []
for d in ["2018-12-31", "2019-12-31", "2020-12-31", "2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31", "2025-06-30",
          "2025-12-31", "2026-06-30"]:
    dp = debt_parts(BS, d)
    cash = val(BS, d, "MONETARYFUNDS") / M
    ta, tl = val(BS, d, "TOTAL_ASSETS") / M, val(BS, d, "TOTAL_LIABILITIES") / M
    liquidity.append({"p": d[:7] if d[5:7] == "06" else d[:4], "cash": cash, "debt": dp["total"], "long_loan": dp["long"],
                      "net_debt": dp["total"] - cash, "debt_asset": tl / ta, "cip": nz(val(BS, d, "CIP")) / M,
                      "parent_equity": val(BS, d, "TOTAL_PARENT_EQUITY") / M, "minority_equity": val(BS, d, "MINORITY_EQUITY") / M,
                      "current_ratio": val(BS, d, "TOTAL_CURRENT_ASSETS") / val(BS, d, "TOTAL_CURRENT_LIAB")})
a25 = next(a for a in annual if a["y"] == 2025)
last = liquidity[-1]
solvency = {
    "date": "2026-06-30", "cash": last["cash"], "debt": last["debt"], "net_debt": last["net_debt"],
    "debt_parts": debt_parts(BS, "2026-06-30"), "debt_asset": last["debt_asset"], "current_ratio": last["current_ratio"],
    "ebitda_2025": a25["ebitda"], "net_debt_ebitda": last["net_debt"] / a25["ebitda"],
    # interest charged to profit understates the cost while expansion interest is capitalised (2025: 78.1m on 广珠东 at 2.24%)
    "interest_exp_2025": a25["interest_exp"], "interest_cap_2025": 78.09, "loan_rate_range_2025": [0.021, 0.0294],
    "ebit_2025": a25["ebitda"] - a25["da"],
    "coverage_2025": (a25["ebitda"] - a25["da"]) / (a25["interest_exp"] + 78.09),
    "ocf_2025": a25["ocf"], "capex_2025": a25["capex"],
    "dividends_paid_parent_2025": dps_by_year[2024] * SHARES / M, "dividends_paid_minority_2025": 699.0,
    "ocf_h1_2026": val(CF, "2026-06-30", "NETCASH_OPERATE") / M, "capex_h1_2026": val(CF, "2026-06-30", "CONSTRUCT_LONG_ASSET") / M,
}

# ---------- expansion projects (budgets and progress from the 2025 annual and 2026 interim reports) ----------
projects = [
    {"name": "广惠高速改扩建（济广高速小金口—萝岗段、广惠高速小金口—凌坑段）", "budget": 30520.0, "spent_2026h1": 789.2,
     "stake": 0.51, "consolidated": True, "schedule": "2025 年 1 月核准，2025 年 9 月开工，计划 2030 年完工",
     "irr": None, "note": "折旧年限按经营期延长至 2054 年 8 月"},
    {"name": "广澳高速南沙—珠海段（京珠广珠段）改扩建", "budget": 13736.0, "spent_2026h1": 4658.1, "stake": 0.75,
     "consolidated": True, "schedule": "中山城区—珠海段 2024 年 9 月通车，其余路段计划 2027 年完工", "irr": 0.0575,
     "note": "预算含政府承担部分；公司按 75% 出资资本金约 34.1 亿元"},
    {"name": "广肇高速（G80 横江—马安段）改扩建", "budget": 9220.0, "spent_2026h1": None, "stake": 0.25,
     "consolidated": False, "schedule": "在建", "irr": 0.0523, "note": "公司按 25% 出资资本金约 8.07 亿元"},
    {"name": "惠盐高速深圳段改扩建", "budget": 4351.0, "spent_2026h1": None, "stake": 0.3333, "consolidated": False,
     "schedule": "2025 年建成通车，收费期至 2047 年 2 月", "irr": 0.0588, "note": "公司出资约 4.35 亿元"},
]
remaining_cons = sum(p["budget"] - p["spent_2026h1"] for p in projects if p["consolidated"])


# ---------- illustrative debt path through the expansion cycle ----------
def debt_path(capex_sched, ocf=3600.0, div_parent=0.70 * 1550.0, div_min=700.0, rate=0.025, other_capex=300.0):
    """Net debt from 2026-06-30 onwards; operating cash flow is taken before interest, interest accrues on net debt."""
    nd = last["net_debt"]
    out = []
    for y, (gh, gz, frac) in capex_sched.items():
        inject = 0.35 * (gh * 0.49 + gz * 0.25)  # minority shareholders fund their share of project equity
        interest = nd * rate * frac
        nd = nd + gh + gz + (other_capex - ocf + div_parent + div_min) * frac + interest - inject
        out.append({"y": y, "capex": gh + gz + other_capex * frac, "net_debt": nd, "nd_ebitda": nd / EBITDA_REC})
    return out


EBITDA_REC = a25["ebitda"] - 310.0  # 2025 EBITDA without the one-off bad-debt write-back on 广佛
# project spend by period (RMB m): 广惠 (305.2bn budget, 2025-2030) and 广珠东 (remaining ~9.1bn incl. government-borne
# items, mostly by 2027); an illustrative schedule, not company guidance
SCHED = {"2026H2": (1500.0, 2000.0, 0.5), "2027": (5500.0, 4500.0, 1.0), "2028": (7500.0, 1600.0, 1.0),
         "2029": (8000.0, 0.0, 1.0), "2030": (7300.0, 0.0, 1.0)}
debt_projection = {"base": debt_path(SCHED), "assumptions": {
    "ocf": 3600.0, "div_parent": 0.70 * 1550.0, "div_minority": 700.0, "rate": 0.025, "other_capex": 300.0,
    "equity_share": 0.35, "ebitda_ex_oneoff": EBITDA_REC, "schedule": {k: [v[0], v[1]] for k, v in SCHED.items()}}}

# ---------- sensitivities ----------
# 1% change in the three consolidated roads' tolls, attributable after 25% tax, against 2025 recurring profit
sens_toll_1pct = toll_attrib * 0.01 * 0.75
leverage_table = []
for chg in (-0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10):
    leverage_table.append({"chg": chg, "toll_attrib": toll_attrib * (1 + chg), "dnp": a25["dnp"] + toll_attrib * chg * 0.75,
                           "dnp_chg": toll_attrib * chg * 0.75 / a25["dnp"]})
guangzhu_expiry = {"toll_2025": TOLL[2025]["京珠高速广珠段"][1] / 100, "share_of_revenue": TOLL[2025]["京珠高速广珠段"][1] / 100 / a25["revenue"],
                   "attrib_np_2025": 456.14 * 0.75, "share_of_np": 456.14 * 0.75 / a25["np"]}

# ---------- valuation ----------
v = pd.read_csv(os.path.join(FIN, f"value_{ME}.csv"))
vl = v.iloc[-1]
price = float(vl["当日收盘价"])
mcap = float(vl["总市值"]) / M
eps_26e = 0.755  # mean of the two latest broker forecasts (万联 2026-10-21: 0.76, 太平洋 2026-03-26: 0.75)
valuation = {"date": str(vl["数据日期"]), "price": price, "mcap": mcap, "pe_ttm": float(vl["PE(TTM)"]), "pb": float(vl["市净率"]),
             "ps": float(vl["市销率"]), "dps_2025": dps_by_year[2025], "dy_2025": dps_by_year[2025] / price,
             "eps_26e": eps_26e, "pe_26e": price / eps_26e, "dps_26e": 0.70 * eps_26e, "dy_26e": 0.70 * eps_26e / price,
             "ev": mcap + last["net_debt"] + last["minority_equity"],
             "ev_ebitda": (mcap + last["net_debt"] + last["minority_equity"]) / a25["ebitda"],
             "broker_targets": [{"broker": "中金公司", "rating": "跑赢行业", "target": 15.23, "date": "2026 年一季报点评"},
                                {"broker": "华泰证券", "rating": "增持", "target": 13.52, "date": "2026-03-17"},
                                {"broker": "广发证券", "rating": "增持", "target": 12.81, "date": "2026-03-24"}]}
# implied price at the 10-year yield of 1.64% for a range of dividend-yield spreads
y10 = 1.6414
valuation["yield_gap_grid"] = [{"spread": s, "price_2025dps": dps_by_year[2025] / ((y10 + s) / 100),
                                "price_26e": 0.70 * eps_26e / ((y10 + s) / 100)} for s in (2.0, 2.5, 3.0, 3.5, 4.0)]
valuation["rate_grid"] = [{"y10": y, "price": 0.70 * eps_26e / ((y + 3.0) / 100)} for y in (1.4, 1.6, 1.8, 2.0, 2.2, 2.5)]

# ---------- peers ----------
peers = []
for c, n in NAMES.items():
    i, b, f, ind = (load(k, c) for k in ("is", "bs", "cf", "ind"))
    vv = pd.read_csv(os.path.join(FIN, f"value_{c}.csv")).iloc[-1]
    dv = pd.read_csv(os.path.join(FIN, f"div_{c}.csv"))
    dv["rp"] = dv["报告期"].astype(str).str[:10]
    dps25 = float(dv[dv["rp"].isin(["2025-06-30", "2025-12-31"])]["现金分红-现金分红比例"].sum()) / 10
    g = lambda d, col: val(i, d, col) / M  # noqa: E731
    rev25, rev24, rev22 = g("2025-12-31", "TOTAL_OPERATE_INCOME"), g("2024-12-31", "TOTAL_OPERATE_INCOME"), g("2022-12-31", "TOTAL_OPERATE_INCOME")
    np25, np24 = g("2025-12-31", "PARENT_NETPROFIT"), g("2024-12-31", "PARENT_NETPROFIT")
    dn25, dn24 = g("2025-12-31", "DEDUCT_PARENT_NETPROFIT"), g("2024-12-31", "DEDUCT_PARENT_NETPROFIT")
    h26, h25 = g("2026-06-30", "TOTAL_OPERATE_INCOME"), g("2025-06-30", "TOTAL_OPERATE_INCOME")
    nh26, nh25 = g("2026-06-30", "PARENT_NETPROFIT"), g("2025-06-30", "PARENT_NETPROFIT")
    dh26, dh25 = g("2026-06-30", "DEDUCT_PARENT_NETPROFIT"), g("2025-06-30", "DEDUCT_PARENT_NETPROFIT")
    dp = debt_parts(b, "2026-06-30")
    cash = val(b, "2026-06-30", "MONETARYFUNDS") / M
    da = sum(nz(val(f, "2025-12-31", k)) for k in ("FA_IR_DEPR", "IA_AMORTIZE", "LPE_AMORTIZE", "USERIGHT_ASSET_AMORTIZE")) / M
    ebitda = g("2025-12-31", "TOTAL_PROFIT") + nz(g("2025-12-31", "FE_INTEREST_EXPENSE")) + da
    shares = float(vv["总股本"])
    peers.append({"code": c, "name": n, "rev_2025": rev25, "rev_yoy_2025": rev25 / rev24 - 1, "rev_cagr_22_25": (rev25 / rev22) ** (1 / 3) - 1,
                  "np_2025": np25, "np_yoy_2025": np25 / np24 - 1, "dnp_yoy_2025": dn25 / dn24 - 1,
                  "rev_h1_2026": h26, "rev_h1_yoy": h26 / h25 - 1, "np_h1_2026": nh26, "np_h1_yoy": nh26 / nh25 - 1,
                  "dnp_h1_yoy": dh26 / dh25 - 1, "roe_2025": val(ind, "2025-12-31", "ROEJQ") / 100,
                  "debt_asset": val(b, "2026-06-30", "TOTAL_LIABILITIES") / val(b, "2026-06-30", "TOTAL_ASSETS"),
                  "net_debt": dp["total"] - cash, "nd_ebitda": (dp["total"] - cash) / ebitda,
                  "perpetual": nz(val(b, "2026-06-30", "PERPETUAL_BOND")) / M,
                  "mcap": float(vv["总市值"]) / M, "price": float(vv["当日收盘价"]), "pe_ttm": float(vv["PE(TTM)"]), "pb": float(vv["市净率"]),
                  "dps_2025": dps25, "payout_2025": dps25 * shares / M / np25 if np25 else None, "dy_2025": dps25 / float(vv["当日收盘价"]),
                  "capex_2025": val(f, "2025-12-31", "CONSTRUCT_LONG_ASSET") / M,
                  "ocf_2025": val(f, "2025-12-31", "NETCASH_OPERATE") / M})
industry = {"national_km_2024": 19.07, "national_km_2025": 19.94, "guangdong_km_2025": 1.2, "guangdong_gdp_2024_trn": 14.16,
            "peer_mcap_total": sum(p["mcap"] for p in peers) / 100, "sw_index_constituents": 20, "sw_pe": 14.63,
            "sw_pb": 1.2, "sw_dy": 0.0378}

dividends = [{"y": y, "dps": dps_by_year[y]} for y in range(2013, 2026)]
res = {"annual": annual, "dividends": dividends, "halves": halves, "roads": roads, "toll_years": years, "toll_attrib_core": toll_attrib,
       "liquidity": liquidity, "solvency": solvency, "projects": projects, "remaining_capex_consolidated": remaining_cons,
       "debt_projection": debt_projection, "sens_toll_1pct": sens_toll_1pct, "leverage_table": leverage_table,
       "guangzhu_expiry": guangzhu_expiry, "valuation": valuation, "peers": peers, "industry": industry,
       "guidance_2026": {"revenue": 4513.0, "cost_cap": 1719.0}}
os.makedirs(OUT, exist_ok=True)
json.dump(res, open(os.path.join(OUT, "fundamentals.json"), "w"), ensure_ascii=False, indent=1, default=float)
print(json.dumps({k: res[k] for k in ("solvency", "valuation", "debt_projection", "guangzhu_expiry")}, ensure_ascii=False, indent=1, default=float))
print("toll attributable core", toll_attrib, "1% sens", sens_toll_1pct, "remaining capex", remaining_cons)
for a in annual:
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in a.items()})
for h in halves:
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in h.items()})
