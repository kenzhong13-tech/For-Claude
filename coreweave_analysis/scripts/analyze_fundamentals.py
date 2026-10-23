"""Fundamental, solvency, sensitivity and valuation calculations for the CoreWeave report.

Inputs: data/kpis.json (press-release KPIs), data/processed/financials.json (XBRL),
data/processed/market_analysis.json (prices/vol). Output: data/processed/fundamentals.json
"""
import json
import math
import os

from scipy.stats import norm

ROOT = os.path.join(os.path.dirname(__file__), "..")
P = lambda *a: os.path.join(ROOT, *a)  # noqa: E731
k = json.load(open(P("data", "kpis.json")))
fin = json.load(open(P("data", "processed", "financials.json")))["quarterly"]
mkt = json.load(open(P("data", "processed", "market_analysis.json")))
qend = {"2024Q1": "2024-03-31", "2024Q2": "2024-06-30", "2024Q3": "2024-09-30", "2024Q4": "2024-12-31",
        "2025Q1": "2025-03-31", "2025Q2": "2025-06-30", "2025Q3": "2025-09-30", "2025Q4": "2025-12-31",
        "2026Q1": "2026-03-31", "2026Q2": "2026-06-30"}
M = 1e6
out = {"quarterly": []}
for i, q in enumerate(k["quarters"]):
    x = fin.get(qend[q], {})
    rev, ebitda, aoi, intr = k["revenue"][i], k["adj_ebitda"][i], k["adj_op_income"][i], k["interest_net"][i]
    debt = x.get("debt_principal")
    cash = x.get("cash")
    row = {
        "q": q, "revenue": rev, "adj_ebitda": ebitda, "adj_op_income": aoi, "interest": intr,
        "net_loss": k["net_loss"][i], "backlog_bn": k["backlog_bn"][i], "active_mw": k["active_mw"][i],
        "contracted_gw": k["contracted_gw"][i],
        "ebitda_margin": ebitda / rev, "aoi_margin": aoi / rev, "net_margin": k["net_loss"][i] / rev,
        "yoy": (rev / k["revenue"][i - 4] - 1) if i >= 4 else None,
        "ebitda_cov": ebitda / intr, "aoi_cov": aoi / intr,
        "dna": x.get("dna", 0) / M if x.get("dna") else None,
        "capex": x.get("capex", 0) / M if x.get("capex") else None,
        "cfo": x.get("cfo", 0) / M if x.get("cfo") is not None else None,
        "debt": debt / M if debt else None, "cash": cash / M if cash else None,
        "equity": x.get("equity") / M if x.get("equity") is not None else None,
        "op_lease": x.get("op_lease_liab") / M if x.get("op_lease_liab") else None,
        "assets_cur": x.get("assets_current") / M if x.get("assets_current") else None,
        "liab_cur": x.get("liabilities_current") / M if x.get("liabilities_current") else None,
        "assets": x.get("assets") / M if x.get("assets") else None,
        "liabilities": x.get("liabilities") / M if x.get("liabilities") else None,
        "ppe": x.get("ppe_net") / M if x.get("ppe_net") else None,
        "rpo_bn": x.get("rpo") / 1e9 if x.get("rpo") else None,
    }
    if row["debt"] and row["cash"] is not None:
        row["net_debt"] = row["debt"] - row["cash"]
        row["net_debt_to_ann_ebitda"] = row["net_debt"] / (ebitda * 4)
        row["debt_to_ann_ebitda"] = row["debt"] / (ebitda * 4)
    if i >= 3:
        ltm = sum(k["adj_ebitda"][i - 3:i + 1])
        row["ltm_ebitda"] = ltm
        if row["debt"]:
            row["debt_to_ltm_ebitda"] = row["debt"] / ltm
    if row["assets_cur"] and row["liab_cur"]:
        row["current_ratio"] = row["assets_cur"] / row["liab_cur"]
    if row["cfo"] is not None and row["capex"] is not None:
        row["fcf"] = row["cfo"] - row["capex"]
    out["quarterly"].append(row)

# ---------- debt stack as of 2026-06-30 (10-Q Note 10) plus post-quarter issuance ----------
out["debt_stack"] = [
    # name, type, maturity, effective rate, principal ($m), recourse
    ["DDTL 1.0", "担保定期贷款", "2028-03", 0.15, 1300, "追索"],
    ["DDTL 2.0", "担保定期贷款", "2030-08", 0.11, 3190, "追索"],
    ["DDTL 2.1", "担保定期贷款", "2031-03", 0.09, 3000, "追索"],
    ["DDTL 3.0", "担保定期贷款", "2030-08", 0.09, 2215, "追索"],
    ["DDTL 5.0", "担保定期贷款", "2031-11", 0.09, 1101, "追索"],
    ["2030年9.25%优先票据", "无担保债券", "2030-06", 0.10, 2000, "追索"],
    ["2031年9.00%优先票据", "无担保债券", "2031-02", 0.10, 1750, "追索"],
    ["2031年9.75%优先票据", "无担保债券", "2031-10", 0.10, 2750, "追索"],
    ["2032年9.625%优先票据", "无担保债券", "2032-07", 0.10, 1250, "追索"],
    ["2032年8.50%欧元票据（€20亿）", "无担保债券", "2032-07", 0.09, 2279, "追索"],
    ["2031年1.75%可转债", "可转债", "2031-12", 0.02, 2588, "追索"],
    ["2032年1.75%可转债", "可转债", "2032-10", 0.02, 4000, "追索"],
    ["OEM及软件许可融资", "设备融资", "2026-12至2030-07", 0.11, 4220, "追索"],
    ["Magnetar贷款", "其他", "2029-01", 0.12, 189, "追索"],
    ["DDTL 4.0（投资级A3/A(low)）", "担保定期贷款", "2032-03", 0.07, 2837, "无追索"],
    ["OEM融资（子公司）", "设备融资", "2026-08至2028-08", 0.09, 882, "无追索"],
]
out["debt_total_jun26"] = sum(r[4] for r in out["debt_stack"])
out["post_quarter"] = [
    ["2033年2.875%可转债（2026年9月）", 4200],
    ["DDTL 5.5额度（2026年8月，SOFR+5.50%，Ba2/BB+）", 2600],
]
out["maturities"] = {"2026H2": 4413, "2027": 6184, "2028": 4416, "2029": 2421, "2030": 3221, "2031+": 14896}
out["leases"] = {"op_lease_liab": 16319, "fin_lease_liab": 221, "not_commenced_undiscounted": 35500,
                 "single_site_cap": 14700}
out["liquidity_jun26"] = {"cash": 5524, "securities": 15, "undrawn": 10014, "total": 15553}
wavg = sum(r[3] * r[4] for r in out["debt_stack"]) / out["debt_total_jun26"]
out["weighted_effective_rate"] = wavg
by_type = {}
for r in out["debt_stack"]:
    by_type[r[1]] = by_type.get(r[1], 0) + r[4]
out["debt_by_type"] = by_type

# ---------- credit-implied default probabilities ----------
def cds_pd(spread_bp, recovery=0.4, years=5):
    lam = spread_bp / 1e4 / (1 - recovery)
    return 1 - math.exp(-lam * years), lam


out["cds"] = {str(s): {"pd5": cds_pd(s)[0], "hazard": cds_pd(s)[1]} for s in (500, 800, 1000, 1082, 1195)}

# Merton / KMV-style distance to default (illustrative)
price = mkt["meta"]["last_close_crwv"]
shares = 551.5  # million, Class A + Class B (Yahoo implied shares outstanding)
E = price * shares  # $m
debt_face = out["debt_total_jun26"] + 4200  # incl. Sept-2026 converts
st_debt = 6235 + 1278  # current recourse + non-recourse debt (10-Q)
dp = st_debt + 0.5 * (debt_face - st_debt)  # KMV default point
sig_e = 1.00  # blend of realised (≈100–108%) and implied (≈90–100%) equity volatility
V = E + debt_face
sig_v = sig_e * E / V
mu = 0.04
merton = {}
for T in (1, 3, 5):
    dd = (math.log(V / dp) + (mu - 0.5 * sig_v ** 2) * T) / (sig_v * math.sqrt(T))
    merton[str(T)] = {"dd": dd, "pd": float(norm.cdf(-dd))}
# with on-balance-sheet lease liabilities treated as debt
debt_l = debt_face + 16540
V2 = E + debt_l
sig_v2 = sig_e * E / V2
dp2 = st_debt + 584 + 0.5 * (debt_l - st_debt - 584)
for T in (1, 5):
    dd = (math.log(V2 / dp2) + (mu - 0.5 * sig_v2 ** 2) * T) / (sig_v2 * math.sqrt(T))
    merton[f"{T}_with_leases"] = {"dd": dd, "pd": float(norm.cdf(-dd))}
out["merton"] = {"E": E, "debt_face": debt_face, "default_point": dp, "V": V, "sigma_v": sig_v,
                 "sigma_v_with_leases": sig_v2, "results": merton}

# ---------- valuation snapshot ----------
net_debt_jun = out["debt_total_jun26"] - 5524 - 15
ev = E + net_debt_jun
q2 = out["quarterly"][-1]
ltm_rev = sum(k["revenue"][-4:])
out["valuation"] = {
    "price": price, "shares_m": shares, "mkt_cap": E, "net_debt_jun26": net_debt_jun, "ev_ex_leases": ev,
    "ev_with_leases": ev + 16540,
    "ev_ltm_rev": ev / ltm_rev, "ev_2026e_rev": ev / 12800, "ev_run_rate_rev": ev / 19000,
    "ev_2027e_rev_consensus": ev / 24800,
    "ev_ltm_ebitda": ev / q2["ltm_ebitda"], "ev_ann_q2_ebitda": ev / (q2["adj_ebitda"] * 4),
    "ps_ltm": E / ltm_rev, "pb": E / (q2["equity"]), "ltm_rev": ltm_rev,
    "analyst": {"mean": 138.34, "median": 142.5, "high": 278, "low": 39, "n": 38},
    "short_pct_float": 0.1924, "insider_pct": 0.186, "inst_pct": 0.769,
}

# ---------- operating & financial leverage (based on Q2'26 run-rate) ----------
rev0, ebitda0, dna0, sbc0, int0 = 2575, 1510, 1393, 165, 640
cash_opex = rev0 - ebitda0
fixed_share = 0.7
lev = []
for chg in (-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3):
    rev = rev0 * (1 + chg)
    opex = cash_opex * fixed_share + cash_opex * (1 - fixed_share) * (1 + chg)
    ebitda = rev - opex
    aoi = ebitda - dna0 + 11  # + amortisation of acquired intangibles added back in adjusted OI
    pretax = ebitda - dna0 - sbc0 - int0 + 125 - 11
    lev.append({"chg": chg, "revenue": rev, "ebitda": ebitda, "ebitda_chg": ebitda / ebitda0 - 1,
                "aoi": aoi, "pretax": pretax, "cov": ebitda / int0})
out["leverage_table"] = lev
out["dol"] = (lev[4]["ebitda_chg"]) / 0.1

# ---------- 2027E illustrative scenarios ----------
scen = {
    "bear": {"label": "悲观：AI资本开支放缓", "revenue": 18000, "margin": 0.52, "rate": 0.095, "debt_ye26": 52000, "capex27": 15000,
             "desc": "新增订单停滞，续约价格下降10–20%，交付延误；信用利差维持高位"},
    "base": {"label": "基准：接近市场一致预期", "revenue": 24000, "margin": 0.58, "rate": 0.085, "debt_ye26": 50000, "capex27": 30000,
             "desc": "积压订单按计划转化，年底年化收入约300亿美元；融资成本小幅改善"},
    "bull": {"label": "乐观：AI需求持续超预期", "revenue": 28000, "margin": 0.62, "rate": 0.075, "debt_ye26": 50000, "capex27": 40000,
             "desc": "算力供不应求、定价坚挺，新增大客户；投资级担保贷款占比上升"},
}
cash_ye26 = 6000
for s in scen.values():
    ebitda = s["revenue"] * s["margin"]
    debt_avg = s["debt_ye26"] + 0.5 * (s["capex27"] * 0.75)
    interest = debt_avg * s["rate"]
    dna = 0.45 * s["revenue"] if s is not scen["bear"] else 0.55 * s["revenue"]
    s.update({
        "ebitda": ebitda, "interest": interest, "cov": ebitda / interest, "dna": dna,
        "ebit": ebitda - dna, "pretax": ebitda - dna - interest,
        "net_debt_ye26": s["debt_ye26"] - cash_ye26,
        "lev": (s["debt_ye26"] - cash_ye26) / ebitda,
        "fcf_pre_fin": ebitda - interest - s["capex27"] - 0.05 * s["revenue"],
    })
    s["equity_by_multiple"] = {}
    for mult in (5, 6, 8, 10, 12):
        eq = mult * ebitda - s["net_debt_ye26"]
        s["equity_by_multiple"][str(mult)] = {"equity": eq, "per_share": eq / 580}
out["scenarios"] = scen
out["scenario_assumptions"] = {"shares_m": 580, "cash_ye26": cash_ye26,
                               "note": "示意性情景，非预测；2026年底债务按6月末355亿美元+9月可转债42亿+下半年担保贷款提款估算。"}

# grid: 2027E revenue x EBITDA margin -> EBITDA / interest coverage at base interest
grid = []
for revenue in (16000, 20000, 24000, 28000, 32000):
    row = []
    for m in (0.50, 0.55, 0.60, 0.65):
        e = revenue * m
        row.append({"ebitda": e, "cov": e / scen["base"]["interest"],
                    "per_share_8x": (8 * e - scen["base"]["net_debt_ye26"]) / 580})
    grid.append({"revenue": revenue, "cells": row})
out["grid"] = grid

# interest-rate sensitivity: refinancing $10bn of unsecured debt at different yields
out["refi_sensitivity"] = [{"yield": y, "annual_interest": 10000 * y, "vs_975": 10000 * (y - 0.0975)}
                           for y in (0.0975, 0.12, 0.145, 0.16)]
json.dump(out, open(P("data", "processed", "fundamentals.json"), "w"), ensure_ascii=False, indent=1)

for r in out["quarterly"]:
    print(r["q"], f"rev {r['revenue']:7.0f} yoy {r['yoy'] if r['yoy'] is None else round(r['yoy']*100)} ebitdaM {r['ebitda_margin']:.0%} aoiM {r['aoi_margin']:.0%} cov {r['ebitda_cov']:.2f}/{r['aoi_cov']:.2f}",
          f"debt {r['debt']} netD/annE {r.get('net_debt_to_ann_ebitda', 0):.2f} D/LTM {r.get('debt_to_ltm_ebitda', 0):.2f} CR {r.get('current_ratio', 0):.2f} FCF {r.get('fcf')}")
print("debt total", out["debt_total_jun26"], "wavg rate", round(wavg, 4), out["debt_by_type"])
print("merton", json.dumps(out["merton"], indent=0)[:600])
print("cds", out["cds"])
print("valuation", {kk: (round(v, 2) if isinstance(v, float) else v) for kk, v in out["valuation"].items()})
print("DOL", out["dol"])
for kk, s in scen.items():
    print(kk, {x: round(v, 2) if isinstance(v, float) else v for x, v in s.items() if x not in ('equity_by_multiple', 'desc')})
    print('   per share', {m: round(v['per_share'], 1) for m, v in s['equity_by_multiple'].items()})
for l in lev:
    print(l)
