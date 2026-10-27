"""Fundamental, solvency, valuation and scenario calculations for the Pop Mart report.

Figures (RMB million) are transcribed from HKEX results announcements in data/raw/hkex/ and
Yahoo Finance statements; derived halves are annual minus interim. Output: data/processed/fundamentals.json
"""
import json
import os

import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
P = lambda *a: os.path.join(ROOT, *a)  # noqa: E731
HKD_PER_USD = 7.80  # HKD peg (7.75-7.85 band)

# ---------- reported results (RMB m): revenue, gross profit, operating profit, attributable NP, adjusted NP ----------
annual = {
    "2020": [2513.5, 1594.1, 718.8, 523.5, 590.5],
    "2021": [4490.7, 2758.6, 1149.8, 854.3, 1001.6],
    "2022": [4617.3, 2654.5, 583.4, 475.7, 573.5],
    "2023": [6301.0, 3864.1, 1230.6, 1082.3, 1190.5],
    "2024": [13037.7, 8707.8, 4154.3, 3125.5, 3403.2],
    "2025": [37120.1, 26764.9, 16890.5, 12775.7, 13083.6],
}
interim = {
    "2021": [1772.6, 1117.1, 486.7, 358.7, 435.2],
    "2022": [2358.8, 1370.4, 446.1, 332.8, 376.3],
    "2023": [2813.8, 1698.4, 537.8, 476.6, 535.4],
    "2024": [4557.8, 2919.1, 1126.4, 921.3, 1017.6],
    "2025": [13876.3, 9761.1, 6043.7, 4574.4, 4709.6],
    "2026": [17172.9, 11965.7, 6724.7, 5038.4, 5155.8],
}
halves = []
for y in range(2021, 2027):
    h1 = interim[str(y)]
    halves.append({"p": f"{y}H1", "revenue": h1[0], "gp": h1[1], "op": h1[2], "np": h1[3], "adj": h1[4]})
    if str(y) in annual and y <= 2025:
        a = annual[str(y)]
        halves.append({"p": f"{y}H2", "revenue": a[0] - h1[0], "gp": a[1] - h1[1], "op": a[2] - h1[2],
                       "np": a[3] - h1[3], "adj": a[4] - h1[4]})
for i, h in enumerate(halves):
    h["gm"], h["opm"], h["npm"] = h["gp"] / h["revenue"], h["op"] / h["revenue"], h["np"] / h["revenue"]
    prev = next((x for x in halves if x["p"] == f"{int(h['p'][:4]) - 1}{h['p'][4:]}"), None)
    h["yoy"] = h["revenue"] / prev["revenue"] - 1 if prev else None
    h["np_yoy"] = h["np"] / prev["np"] - 1 if prev else None
ann_rows = []
for y, a in annual.items():
    prev = annual.get(str(int(y) - 1))
    ann_rows.append({"y": y, "revenue": a[0], "gp": a[1], "op": a[2], "np": a[3], "adj": a[4],
                     "gm": a[1] / a[0], "opm": a[2] / a[0], "npm": a[3] / a[0],
                     "yoy": a[0] / prev[0] - 1 if prev else None, "np_yoy": a[3] / prev[3] - 1 if prev else None})

# quarterly business updates: YoY revenue growth range (unaudited)
quarterly_growth = [["21Q3", 0.75, 0.80], ["22Q1", 0.65, 0.70], ["22Q3", -0.10, -0.05], ["23Q1", 0.00, 0.05],
                    ["23Q3", 0.35, 0.40], ["24Q1", 0.40, 0.45], ["24Q3", 1.20, 1.25], ["25Q1", 1.65, 1.70],
                    ["25Q3", 2.45, 2.50], ["26Q1", 0.75, 0.80]]

# revenue by region (RMB m)
regions = {
    "FY2024": {"中国内地": 8886.5, "亚太": 3109.7, "美洲": 802.2, "欧洲及其他": 239.3},
    "H1 2025": {"中国内地": 8282.8, "亚太": 2850.9, "美洲": 2264.9, "欧洲及其他": 477.7},
    "FY2025": {"中国内地": 20851.7, "亚太": 8011.0, "美洲": 6806.2, "欧洲及其他": 1451.1},
    "H1 2026": {"中国内地": 12200.5, "亚太": 2575.0, "美洲": 1891.6, "欧洲及其他": 505.7},
}
# revenue by IP (RMB m)
ips = {
    "FY2024": {"THE MONSTERS": 3040.7, "MOLLY": 2093.2, "SKULLPANDA": 1308.3, "CRYBABY": 1164.9, "DIMOO": 909.6,
               "HIRONO": 726.5, "星星人": 120.8},
    "FY2025": {"THE MONSTERS": 14161.1, "SKULLPANDA": 3539.5, "CRYBABY": 2929.0, "MOLLY": 2897.1, "DIMOO": 2776.7,
               "星星人": 2055.6, "HIRONO": 1735.2},
    "H1 2025": {"THE MONSTERS": 4814.0, "星星人": 389.4, "CRYBABY": 1218.2, "DIMOO": 1105.1, "SKULLPANDA": 1220.5,
                "HIRONO": 728.4, "MOLLY": 1357.2},
    "H1 2026": {"THE MONSTERS": 4454.4, "星星人": 2650.0, "CRYBABY": 1632.6, "DIMOO": 1619.2, "SKULLPANDA": 1551.2,
                "HIRONO": 1008.9, "MOLLY": 900.6},
}

# balance sheet snapshots (RMB m)
bs = [
    {"p": "2021-12", "cash_dep": 5285.2, "lease": 621.5, "debt": 0, "inventory": 788.8, "assets": 8323.6, "liab": 1503.6, "equity": 6818.2, "ca": 6757.3, "cl": 1092.7},
    {"p": "2022-12", "cash_dep": 5054.3, "lease": 741.1, "debt": 0, "inventory": 867.0, "assets": 8580.1, "liab": 1614.7, "equity": 6963.3, "ca": 6615.5, "cl": 1130.7},
    {"p": "2023-12", "cash_dep": 5971.7, "lease": 777.8, "debt": 15.1, "inventory": 904.7, "assets": 9968.9, "liab": 2188.5, "equity": 7769.9, "ca": 7683.5, "cl": 1733.3},
    {"p": "2024-12", "cash_dep": 9620.2, "lease": 964.6, "debt": 0, "inventory": 1524.5, "assets": 14870.7, "liab": 3986.0, "equity": 10683.5, "ca": 12236.1, "cl": 3370.0},
    {"p": "2025-06", "cash_dep": 13777.1, "lease": 1411.2, "debt": 0, "inventory": 2273.7, "assets": 21356.7, "liab": 6927.1, "equity": 14184.0, "ca": 17850.6, "cl": 5923.2},
    {"p": "2025-12", "cash_dep": 17225.0, "lease": 2861.6, "debt": 0, "inventory": 5472.8, "assets": 32101.4, "liab": 9449.0, "equity": 22277.7, "ca": 24914.6, "cl": 7168.2},
    {"p": "2026-06", "cash_dep": 14164.0, "lease": 3727.6, "debt": 0, "inventory": 6101.5, "assets": 31028.1, "liab": 7739.7, "equity": 23059.0, "ca": 22092.3, "cl": 4672.6},
]
for b in bs:
    b["net_cash"] = b["cash_dep"] - b["lease"] - b["debt"]
    b["current_ratio"] = b["ca"] / b["cl"]
    b["gearing"] = b["liab"] / b["assets"]
inventory_days = {"2024": 102, "2025": 123, "2026H1": 201}

cash_flow = [  # RMB m: operating cash flow, capex, dividends paid, buybacks
    {"p": "2021", "cfo": 779.1, "capex": 333.7, "div": 208.8, "buyback": 0},
    {"p": "2022", "cfo": 891.0, "capex": 347.6, "div": 220.1, "buyback": 634.3},
    {"p": "2023", "cfo": 1990.6, "capex": 392.5, "div": 121.6, "buyback": 333.7},
    {"p": "2024", "cfo": 4954.2, "capex": 516.7, "div": 378.0, "buyback": 78.0},
    {"p": "2026H1", "cfo": 3637.3, "capex": 724.1, "div": None, "buyback": 1545.7},
]
for c in cash_flow:
    c["fcf"] = c["cfo"] - c["capex"]

# ---------- market data, P/E history ----------
px = pd.read_csv(P("data", "raw", "9992_HK.csv"), index_col=0, parse_dates=True)["Close"].dropna()
px = px[px.index <= "2026-10-20"]
fx = pd.read_csv(P("data", "raw", "CNY_X.csv"), index_col=0, parse_dates=True)["Close"].dropna()
cny_per_hkd = (fx / HKD_PER_USD).reindex(px.index, method="ffill").bfill()
ttm_eps = pd.Series({  # RMB, known from the announcement date onward
    "2021-03-26": 0.44, "2021-08-27": 0.5776, "2022-03-28": 0.62, "2022-08-25": 0.6014, "2023-03-29": 0.35,
    "2023-08-22": 0.4628, "2024-03-20": 0.81, "2024-08-20": 1.1503, "2025-03-26": 2.36, "2025-08-19": 5.1068,
    "2026-03-25": 9.61, "2026-08-20": 9.9683})
ttm_eps.index = pd.to_datetime(ttm_eps.index)
eps_d = ttm_eps.reindex(px.index.union(ttm_eps.index)).ffill().reindex(px.index)
pe = (px * cny_per_hkd / eps_d).dropna()
pe_m = pe.resample("W-FRI").last().dropna()
peak = px.idxmax()
last = px.index[-1]
eps_hkd_peak = eps_d[peak] / cny_per_hkd[peak]
eps_hkd_last = eps_d[last] / cny_per_hkd[last]
decomp = {"peak_date": str(peak.date()), "peak_price": float(px[peak]), "last_price": float(px[last]),
          "pe_peak": float(pe[peak]), "pe_last": float(pe[last]),
          "eps_hkd_peak": float(eps_hkd_peak), "eps_hkd_last": float(eps_hkd_last),
          "price_chg": float(px[last] / px[peak] - 1), "eps_chg": float(eps_hkd_last / eps_hkd_peak - 1),
          "pe_chg": float(pe[last] / pe[peak] - 1)}

# ---------- valuation snapshot ----------
shares = 1322.1  # million, after cancellations (Yahoo)
price = float(px[last])
rate = float(cny_per_hkd[last])
mcap_hkd = price * shares
ttm_rev = annual["2025"][0] - interim["2025"][0] + interim["2026"][0]
ttm_np = annual["2025"][3] - interim["2025"][3] + interim["2026"][3]
ttm_adj = annual["2025"][4] - interim["2025"][4] + interim["2026"][4]
ttm_op = annual["2025"][2] - interim["2025"][2] + interim["2026"][2]
net_cash = bs[-1]["net_cash"]
mcap_rmb = mcap_hkd * rate
ev_rmb = mcap_rmb - net_cash
valuation = {"price": price, "shares_m": shares, "cny_per_hkd": rate, "mcap_hkd": mcap_hkd, "mcap_rmb": mcap_rmb,
             "net_cash_rmb": net_cash, "ev_rmb": ev_rmb, "ttm_rev": ttm_rev, "ttm_np": ttm_np, "ttm_adj": ttm_adj, "ttm_op": ttm_op,
             "pe_ttm": mcap_rmb / ttm_np, "pe_adj_ttm": mcap_rmb / ttm_adj, "ev_sales": ev_rmb / ttm_rev, "ev_op": ev_rmb / ttm_op,
             "pb": mcap_rmb / bs[-1]["equity"], "div_yield": 2.38 / rate / price,
             "analyst": {"mean": 170.3, "median": 175.0, "high": 213.5, "low": 115.8, "n": 22},
             "earnings_yield": ttm_np / mcap_rmb}
# Altman Z (original manufacturing form; indicative only)
wc = bs[-1]["ca"] - bs[-1]["cl"]
ta = bs[-1]["assets"]
re_ = 24189.7
z = 1.2 * wc / ta + 1.4 * re_ / ta + 3.3 * ttm_op / ta + 0.6 * mcap_rmb / bs[-1]["liab"] + 1.0 * ttm_rev / ta
solvency = {"altman_z": z, "net_cash": net_cash, "cash_dep": bs[-1]["cash_dep"], "lease": bs[-1]["lease"],
            "current_ratio": bs[-1]["current_ratio"], "gearing": bs[-1]["gearing"],
            "lease_interest_est": 0.045 * bs[-1]["lease"], "op_to_lease_interest": ttm_op / (0.045 * bs[-1]["lease"]),
            "buyback_max_vs_cash": 5000 / bs[-1]["cash_dep"]}

# ---------- operating leverage (H1 2026 base, excluding FX loss) ----------
rev0, gp0, op0, fx_loss = 17172.9, 11965.7, 6724.7, 688.8
opex0 = gp0 - op0 - fx_loss
var_cost_ratio = 1 - gp0 / rev0
lev = []
for chg in (-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3):
    rev = rev0 * (1 + chg)
    gp = rev * (1 - var_cost_ratio)
    opex = opex0 * 0.6 + opex0 * 0.4 * (1 + chg)
    op = gp - opex
    lev.append({"chg": chg, "revenue": rev, "gp": gp, "op": op, "op_chg": op / (op0 + fx_loss) - 1, "opm": op / rev})
dol = lev[4]["op_chg"] / 0.1

# ---------- 2027E scenarios (illustrative) ----------
scen = {
    "bear": {"label": "悲观：IP热度继续退潮", "revenue": 30000, "npm": 0.27, "pe": 10,
             "desc": "LABUBU与海外继续下滑，新IP接力不足，库存去化压低毛利"},
    "base": {"label": "基准：调整后恢复温和增长", "revenue": 38000, "npm": 0.32, "pe": 15,
             "desc": "国内多IP支撑，海外企稳，收入温和增长、利润率小幅回落"},
    "bull": {"label": "乐观：新IP与海外再加速", "revenue": 46000, "npm": 0.35, "pe": 20,
             "desc": "星星人等新IP持续放量，内容/乐园带动，海外重回增长"},
}
for s in scen.values():
    s["np"] = s["revenue"] * s["npm"]
    s["eps_hkd"] = s["np"] / rate / shares
    s["by_pe"] = {str(m): s["eps_hkd"] * m for m in (8, 10, 12, 15, 20, 25)}
    s["price"] = s["eps_hkd"] * s["pe"]
grid = []
for revenue in (28000, 32000, 36000, 40000, 44000, 48000):
    grid.append({"revenue": revenue, "cells": [{"npm": m, "price_15x": revenue * m / rate / shares * 15} for m in (0.27, 0.30, 0.33, 0.36)]})

out = {"annual": ann_rows, "halves": halves, "quarterly_growth": quarterly_growth, "regions": regions, "ips": ips,
       "balance": bs, "inventory_days": inventory_days, "cash_flow": cash_flow,
       "pe_weekly": {"date": [d.strftime("%Y-%m-%d") for d in pe_m.index], "pe": [round(float(v), 2) for v in pe_m]},
       "decomp": decomp, "valuation": valuation, "solvency": solvency, "leverage_table": lev, "dol": dol,
       "scenarios": scen, "grid": grid}
json.dump(out, open(P("data", "processed", "fundamentals.json"), "w"), ensure_ascii=False, indent=1)
for h in halves:
    print(h["p"], f"rev {h['revenue']:8.1f} yoy {h['yoy'] if h['yoy'] is None else round(h['yoy']*100,1)} gm {h['gm']:.1%} opm {h['opm']:.1%} npm {h['npm']:.1%} np_yoy {h['np_yoy'] if h['np_yoy'] is None else round(h['np_yoy']*100,1)}")
print("decomp", decomp)
print("valuation", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in valuation.items()})
print("solvency", {k: round(v, 3) for k, v in solvency.items()})
print("dol", dol, [(round(l['chg'],1), round(l['op']), round(l['op_chg'],3)) for l in lev])
for k, s in scen.items():
    print(k, round(s["np"]), round(s["eps_hkd"], 2), {m: round(v, 1) for m, v in s["by_pe"].items()})
print("pe range", pe.min(), pe.idxmin(), pe.max(), pe.idxmax())
