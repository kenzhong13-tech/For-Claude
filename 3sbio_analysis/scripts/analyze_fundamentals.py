"""Financials, solvency, valuation, 707 scenarios and peer comparison for 3SBio (1530.HK).

Company figures come from HKEX results announcements (data/raw/hkex/); peer figures from Eastmoney financial
indicators and income statements (data/raw/ak/, fetched with akshare) and Yahoo Finance company info
(data/raw/info/). Writes data/processed/fundamentals.json. Amounts in RMB million unless noted.
"""
import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
HKD_PER_USD = 7.80
mkt = json.load(open(os.path.join(OUT, "market_analysis.json"), encoding="utf-8"))
cny_x = pd.read_csv(os.path.join(RAW, "CNY_X.csv"), index_col=0, parse_dates=True)
CNY_PER_USD = float(pd.to_numeric(cny_x["Close"], errors="coerce").dropna().iloc[-1])
CNY_PER_HKD = CNY_PER_USD / HKD_PER_USD


def ak_ind(code, kind):
    d = pd.read_csv(os.path.join(RAW, "ak", f"ind_{int(code):05d}_{kind}.csv"))
    d["REPORT_DATE"] = d["REPORT_DATE"].astype(str).str[:10]
    return d.set_index("REPORT_DATE")


def ak_is(code):
    d = pd.read_csv(os.path.join(RAW, "ak", f"is_{int(code):05d}.csv"))
    d["REPORT_DATE"] = d["REPORT_DATE"].astype(str).str[:10]
    return d.pivot_table(index="REPORT_DATE", columns="STD_ITEM_NAME", values="AMOUNT", aggfunc="first")


def item(df, date, *names):
    for n in names:
        if n in df.columns and date in df.index and pd.notna(df.loc[date, n]):
            return float(df.loc[date, n]) / 1e6
    return None


# ---------- 3SBio annual P&L (Eastmoney indicators + income statement) ----------
ind_y, is_sb = ak_ind("1530", "year"), ak_is("1530")
annual = []
for y in range(2019, 2026):
    d = f"{y}-12-31"
    r = ind_y.loc[d]
    rev = float(r["OPERATE_INCOME"]) / 1e6
    annual.append({"y": str(y), "revenue": rev, "yoy": float(r["OPERATE_INCOME_YOY"]) / 100,
                   "gp": float(r["GROSS_PROFIT"]) / 1e6, "gm": float(r["GROSS_PROFIT_RATIO"]) / 100,
                   "np": float(r["HOLDER_PROFIT"]) / 1e6, "np_yoy": float(r["HOLDER_PROFIT_YOY"]) / 100,
                   "npm": float(r["HOLDER_PROFIT"]) / float(r["OPERATE_INCOME"]),
                   "rd": item(is_sb, d, "研发费用"), "selling": item(is_sb, d, "销售及分销费用"),
                   "op": item(is_sb, d, "经营溢利"), "roe": float(r["ROE_AVG"]) / 100,
                   "debt_asset": float(r["DEBT_ASSET_RATIO"]) / 100})
for a in annual:
    a["rd_ratio"] = a["rd"] / a["revenue"] if a["rd"] else None
    a["sell_ratio"] = a["selling"] / a["revenue"] if a["selling"] else None

# half years (HKEX interim results; H2 = full year minus interim)
ind_p = ak_ind("1530", "period")
halves = []
for d, lab in [("2024-06-30", "2024H1"), ("2025-06-30", "2025H1"), ("2026-06-30", "2026H1")]:
    r = ind_p.loc[d]
    halves.append({"p": lab, "revenue": float(r["OPERATE_INCOME"]) / 1e6, "yoy": float(r["OPERATE_INCOME_YOY"]) / 100,
                   "np": float(r["HOLDER_PROFIT"]) / 1e6, "gm": float(r["GROSS_PROFIT_RATIO"]) / 100,
                   "rd": item(is_sb, d, "研发费用"), "selling": item(is_sb, d, "销售及分销费用")})
fy = {a["y"]: a for a in annual}
for y, h1 in (("2024", halves[0]), ("2025", halves[1])):
    halves.append({"p": f"{y}H2", "revenue": fy[y]["revenue"] - h1["revenue"], "np": fy[y]["np"] - h1["np"],
                   "rd": fy[y]["rd"] - h1["rd"], "selling": fy[y]["selling"] - h1["selling"]})
order = ["2024H1", "2024H2", "2025H1", "2025H2", "2026H1"]
halves = sorted(halves, key=lambda h: order.index(h["p"]))

# revenue mix: product sales / out-license income / CDMO (results announcements)
mix = [
    {"p": "2024", "product": 8927.9, "license": 0.0, "cdmo": 180.1},
    {"p": "2025", "product": 8006.4, "license": 9425.9, "cdmo": 263.5},
    {"p": "2025H1", "product": 4266.9, "license": 0.0, "cdmo": 88.7},
    {"p": "2025H2", "product": 8006.4 - 4266.9, "license": 9425.9, "cdmo": 263.5 - 88.7},
    {"p": "2026H1", "product": 3443.0, "license": 851.6, "cdmo": 231.4},
]
# product-level sales (annual results; FY2025 onwards only the biopharmaceuticals total is disclosed)
products = {
    "years": ["2022", "2023", "2024"],
    "TPIAO 特比澳": [3397.2, 4204.6, 5062.0],
    "EPO 益比奥+赛博尔": [1129.5, 940.3, 1018.5],
    "蔓迪": [893.7, 1124.1, 1336.8],
}
market_share = {"tpiao_value_2025": 0.604, "tpiao_volume_2025": 0.277, "tpiao_value_change_pp": -0.062, "epo_2025": 0.396}

# ---------- liquidity history (results announcements, "Liquidity" sections) ----------
liquidity = [
    {"p": "2020", "cash": 3216.7, "borrow": 413.5, "gearing": 0.032},
    {"p": "2021", "cash": 3052.7, "borrow": 314.3, "gearing": 0.021},
    {"p": "2022", "cash": 2559.9, "borrow": 2265.0, "gearing": 0.147, "current_ratio": 5.4},
    {"p": "2023", "cash": 4900.3, "borrow": 3574.3, "gearing": 0.293, "current_ratio": 2.5},
    {"p": "2024", "cash": 4349.1, "borrow": 2281.4, "gearing": 0.197, "current_ratio": 1.7},
    {"p": "2025H1", "cash": 4368.8, "borrow": 1836.6, "gearing": 0.099, "current_ratio": 2.3},
    {"p": "2025", "cash": 15860.9, "borrow": 2553.9, "gearing": 0.098, "current_ratio": 5.1},
    {"p": "2026H1", "cash": 12469.2, "borrow": 1320.6, "gearing": 0.057, "current_ratio": 6.1},
]
for l in liquidity:
    l["net_cash"] = l["cash"] - l["borrow"]
wmp_2026h1, equity_inv_2026h1 = 5185.2, 889.1
solvency = {
    "cash_2026h1": 12469.2, "wmp_2026h1": wmp_2026h1, "equity_investments_2026h1": equity_inv_2026h1,
    "borrow_2026h1": 1320.6, "borrow_2025": 2553.9, "repaid_2026h1": 1533.9, "new_loans_2026h1": 302.1,
    "net_cash_ex_wmp": 12469.2 - 1320.6, "net_cash_incl_wmp": 12469.2 + wmp_2026h1 - 1320.6,
    "gearing": 0.057, "current_ratio": 6.1, "ocf_2026h1": 899.4, "ocf_2025": 9668.9,
    "finance_cost_2026h1": 30.9, "op_profit_2026h1": item(is_sb, "2026-06-30", "经营溢利"),
    "usd_deposits_musd": 1013.6, "chf_deposits_mchf": 182.4, "capex_3y": [1000, 1200],
    "debt_asset_2025": fy["2025"]["debt_asset"],
}
solvency["interest_cover_2026h1"] = solvency["op_profit_2026h1"] / solvency["finance_cost_2026h1"]

# ---------- valuation ----------
price_hkd = mkt["meta"]["last_raw_close_sb"]
shares_m = 2537.7  # weighted average shares in issue, H1 2026 (interim results)
mcap_hkd = price_hkd * shares_m
mcap_rmb = mcap_hkd * CNY_PER_HKD
ttm = {"revenue": fy["2025"]["revenue"] - halves[2]["revenue"] + halves[4]["revenue"],
       "np": fy["2025"]["np"] - halves[2]["np"] + halves[4]["np"],
       "product": 8006.4 - 4266.9 + 3443.0, "license": 9425.9 + 851.6, "cdmo": 263.5 - 88.7 + 231.4}
# a rough "base business" profit: H1 2026 adjusted profit less the after-tax 707 milestone income
base_np_h1 = 1436.3 - 851.6 * (1 - 0.15)
valuation = {
    "price_hkd": price_hkd, "price_date": mkt["meta"]["last_raw_date_sb"], "shares_m": shares_m,
    "cny_per_hkd": CNY_PER_HKD, "mcap_hkd": mcap_hkd, "mcap_rmb": mcap_rmb, "ttm": ttm,
    "pe_ttm": mcap_rmb / ttm["np"], "ps_product_ttm": mcap_rmb / ttm["product"],
    "ev_rmb_incl_wmp": mcap_rmb - solvency["net_cash_incl_wmp"],
    "net_cash_share_of_mcap": solvency["net_cash_incl_wmp"] / mcap_rmb,
    "base_np_h1_2026": base_np_h1, "base_np_annualised": base_np_h1 * 2,
    "dividend_hkd_2025": 0.25, "div_yield": 0.25 / price_hkd,
    "pb": None,
}
info = json.load(open(os.path.join(RAW, "info", "1530_HK.json")))
valuation["analyst"] = {k: info.get(k) for k in ("targetMeanPrice", "targetMedianPrice", "targetHighPrice", "targetLowPrice",
                                                  "numberOfAnalystOpinions", "forwardPE")}
# what the market price leaves for 707 after net cash and the base business at a range of multiples
sotp = []
for pe in (8, 10, 12, 15):
    base_val = valuation["base_np_annualised"] * pe
    implied_707 = mcap_rmb - solvency["net_cash_incl_wmp"] - base_val
    sotp.append({"pe": pe, "base_value": base_val, "implied_707_rmb": implied_707,
                 "implied_707_hkd_per_share": implied_707 / CNY_PER_HKD / shares_m})
valuation["sotp"] = sotp

# ---------- 707 royalty scenarios (illustrative) ----------
# Pfizer pays tiered double-digit royalties on ex-China net sales; launch 2029, linear 5-year ramp to peak,
# flat to 2038, then -30% a year; 10% discount rate back to 2026; risk-adjusted with a probability of success.
def royalty_npv(peak_usd_bn, rate, pos=0.6, disc=0.10, launch=2029, ramp=5, plateau_end=2038, end=2042):
    v = 0.0
    for yr in range(launch, end + 1):
        if yr < launch + ramp:
            s = peak_usd_bn * (yr - launch + 1) / ramp
        elif yr <= plateau_end:
            s = peak_usd_bn
        else:
            s = peak_usd_bn * 0.7 ** (yr - plateau_end)
        v += s * rate / (1 + disc) ** (yr - 2026)
    return v * pos


grid = []
for peak in (3, 6, 10, 15):
    cells = []
    for rate in (0.10, 0.15, 0.20):
        npv_usd = royalty_npv(peak, rate)
        hkd_ps = npv_usd * 1e9 * HKD_PER_USD / (shares_m * 1e6) * 0.85  # after 15% tax
        cells.append({"rate": rate, "npv_usd_bn": npv_usd, "hkd_per_share": hkd_ps})
    grid.append({"peak_usd_bn": peak, "cells": cells})
milestones_remaining_usd_bn = 4.8 - 851.6 / CNY_PER_USD / 1000
royalty = {"grid": grid, "assumptions": {"launch": 2029, "ramp_years": 5, "plateau_end": 2038, "discount": 0.10, "pos": 0.6, "tax": 0.15},
           "milestones_remaining_usd_bn": milestones_remaining_usd_bn,
           "milestones_remaining_hkd_per_share": milestones_remaining_usd_bn * 1e9 * HKD_PER_USD / (shares_m * 1e6)}

# ---------- operating sensitivity of the base business ----------
# H1 2026 product + CDMO gross profit at constant margin; selling/admin 70% fixed in the short run; R&D fixed
h1 = {"rev": 3443.0 + 231.4, "gm": 0.80, "sell": 1206.7, "admin": 267.8, "rd": 683.8}
lev = []
for chg in (-0.3, -0.2, -0.1, 0, 0.1, 0.2):
    rev = h1["rev"] * (1 + chg)
    gp = rev * h1["gm"]
    sell = h1["sell"] * (0.7 + 0.3 * (1 + chg))
    op = gp - sell - h1["admin"] - h1["rd"]
    lev.append({"chg": chg, "revenue": rev, "gp": gp, "op": op})
base_op = next(x["op"] for x in lev if x["chg"] == 0)
for x in lev:
    x["op_chg"] = x["op"] / base_op - 1 if base_op else None
dol = (next(x["op"] for x in lev if x["chg"] == 0.1) / base_op - 1) / 0.1

# ---------- peers ----------
PEERS = {"1530": "三生制药", "1276": "恒瑞医药", "6160": "百济神州", "1801": "信达生物", "9926": "康方生物",
         "3692": "翰森制药", "1093": "石药集团", "1177": "中国生物制药", "6990": "科伦博泰", "9995": "荣昌生物",
         "2096": "先声药业", "1877": "君实生物"}
peer_mkt = {p["code"]: p for p in mkt["peers"]}
peers = []
for c, name in PEERS.items():
    ip, iy, isd = ak_ind(c, "period"), ak_ind(c, "year"), ak_is(c)
    inf = json.load(open(os.path.join(RAW, "info", f"{int(c):04d}_HK.json")))

    def g(df, d, col):
        return float(df.loc[d, col]) if d in df.index and pd.notna(df.loc[d, col]) else None

    rev25, rev25y = g(iy, "2025-12-31", "OPERATE_INCOME"), g(iy, "2025-12-31", "OPERATE_INCOME_YOY")
    rev24 = g(iy, "2024-12-31", "OPERATE_INCOME")
    h126, h126y = g(ip, "2026-06-30", "OPERATE_INCOME"), g(ip, "2026-06-30", "OPERATE_INCOME_YOY")
    h125 = g(ip, "2025-06-30", "OPERATE_INCOME")
    np25, np_h126 = g(iy, "2025-12-31", "HOLDER_PROFIT"), g(ip, "2026-06-30", "HOLDER_PROFIT")
    np_h126y = g(ip, "2026-06-30", "HOLDER_PROFIT_YOY")
    np_h125 = g(ip, "2025-06-30", "HOLDER_PROFIT")
    rd_h126, rd25 = item(isd, "2026-06-30", "研发费用"), item(isd, "2025-12-31", "研发费用")
    ttm_rev = rev25 + h126 - h125 if None not in (rev25, h126, h125) else None
    ttm_np = np25 + np_h126 - np_h125 if None not in (np25, np_h126, np_h125) else None
    mcap_hkd_c = inf.get("marketCap")
    pm = peer_mkt.get(c, {})
    peers.append({
        "code": c, "name": name,
        "rev_2025": rev25 / 1e6 if rev25 else None, "rev_2025_yoy": rev25y / 100 if rev25y is not None else None,
        "rev_cagr_23_25": ((rev25 / g(iy, "2023-12-31", "OPERATE_INCOME")) ** 0.5 - 1) if rev25 and g(iy, "2023-12-31", "OPERATE_INCOME") else None,
        "rev_h1_2026": h126 / 1e6 if h126 else None, "rev_h1_2026_yoy": h126y / 100 if h126y is not None else None,
        "np_2025": np25 / 1e6 if np25 is not None else None, "np_h1_2026": np_h126 / 1e6 if np_h126 is not None else None,
        "np_h1_2026_yoy": np_h126y / 100 if np_h126y is not None else None,
        "gm_h1_2026": g(ip, "2026-06-30", "GROSS_PROFIT_RATIO") / 100 if g(ip, "2026-06-30", "GROSS_PROFIT_RATIO") is not None else None,
        "rd_h1_2026": rd_h126, "rd_ratio_h1_2026": rd_h126 / (h126 / 1e6) if rd_h126 and h126 else None,
        "rd_2025": rd25, "rd_ratio_2025": rd25 / (rev25 / 1e6) if rd25 and rev25 else None,
        "ttm_rev": ttm_rev / 1e6 if ttm_rev else None, "ttm_np": ttm_np / 1e6 if ttm_np is not None else None,
        "mcap_hkd_bn": mcap_hkd_c / 1e9 if mcap_hkd_c else None,
        "ps_ttm": (mcap_hkd_c * CNY_PER_HKD) / ttm_rev if mcap_hkd_c and ttm_rev else None,
        "pe_ttm": (mcap_hkd_c * CNY_PER_HKD) / ttm_np if mcap_hkd_c and ttm_np and ttm_np > 0 else None,
        "target_mean": inf.get("targetMeanPrice"), "price": inf.get("currentPrice"),
        "upside": inf.get("targetMeanPrice") / inf.get("currentPrice") - 1 if inf.get("targetMeanPrice") and inf.get("currentPrice") else None,
        "vol_1y": pm.get("vol_1y"), "beta_sec": pm.get("beta_sec"), "beta_hsi": pm.get("beta_hsi"), "corr_sec": pm.get("corr_sec"),
        "ret_2025": pm.get("ret_2025"), "ret_2026ytd": pm.get("ret_2026ytd"), "mdd_since2025": pm.get("mdd_since2025"),
        "dd_from_high": pm.get("dd_from_high"), "first": pm.get("first"),
    })
# notes on licence income inside reported revenue (results announcements and press, see the report's sources)
license_note = {"1530": "上半年授权收入 8.5 亿元（占 18.8%）", "1276": "上半年对外许可收入 14.2 亿元（去年同期 19.9 亿元）",
                "1093": "上半年含阿斯利康授权首付款", "6990": "上半年许可及合作收入 3.15 亿元", "9995": "上半年含大额授权收入"}
for p in peers:
    p["license_note"] = license_note.get(p["code"], "")
    if p["code"] == "1530":  # use the company's share count so the table matches the valuation section
        p["mcap_hkd_bn"] = mcap_hkd / 1000
        p["ps_ttm"] = mcap_rmb / p["ttm_rev"]
        p["pe_ttm"] = mcap_rmb / p["ttm_np"]
        p["ps_ex_license"] = mcap_rmb / (ttm["product"] + ttm["cdmo"])
    if p["code"] == "1276" and p["ret_2025"] is None:  # H shares listed in May 2025: use the A shares for 2025
        a_px = pd.read_csv(os.path.join(RAW, "600276_SS.csv"), index_col=0, parse_dates=True)["Adj Close"].dropna()
        p["ret_2025"] = float(a_px[:"2025-12-31"].iloc[-1] / a_px[:"2024-12-31"].iloc[-1] - 1)
        p["ret_2025_note"] = "A股"

# ---------- industry ----------
industry = {
    "bd": [{"y": "2024", "total": 52.0, "upfront": None, "approx": True},
           {"y": "2025", "total": 135.7, "upfront": 7.0, "deals": 157},
           {"y": "2026H1", "total": 99.7, "upfront": 5.0, "deals": 86}],
    "approvals": [{"y": "2024", "n": 48}, {"y": "2025", "n": 76}, {"y": "2026H1", "n": 38}],
    "keytruda_2025_usd_bn": 31.7, "keytruda_loe": 2028,
}

res = {"annual": annual, "halves": halves, "mix": mix, "products": products, "market_share": market_share,
       "liquidity": liquidity, "solvency": solvency, "valuation": valuation, "royalty": royalty,
       "leverage_table": lev, "dol": dol, "peers": peers, "industry": industry,
       "fx": {"cny_per_usd": CNY_PER_USD, "cny_per_hkd": CNY_PER_HKD}}
os.makedirs(OUT, exist_ok=True)
json.dump(res, open(os.path.join(OUT, "fundamentals.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: res[k] for k in ("solvency", "valuation", "dol", "fx")}, indent=1, ensure_ascii=False, default=str))
for a in annual:
    print(a["y"], round(a["revenue"]), f"{a['yoy']:+.1%}", "np", round(a["np"]), f"gm {a['gm']:.1%} rd {a['rd_ratio'] if a['rd_ratio'] is None else round(a['rd_ratio'],3)} sell {a['sell_ratio'] and round(a['sell_ratio'],3)}")
for h in halves:
    print(h)
for p in peers:
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in p.items()})
for g_ in grid:
    print(g_["peak_usd_bn"], [(c["rate"], round(c["npv_usd_bn"], 2), round(c["hkd_per_share"], 2)) for c in g_["cells"]])
print(royalty["milestones_remaining_usd_bn"], royalty["milestones_remaining_hkd_per_share"])
print(lev, dol)
