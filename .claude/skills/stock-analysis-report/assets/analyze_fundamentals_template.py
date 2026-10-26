"""Financials, solvency, valuation and peer comparison for <公司>（<代码>） -> data/processed/fundamentals.json.

Template from the stock-analysis-report skill. Copy to <slug>_analysis/scripts/analyze_fundamentals.py and edit.
Writes the standard keys the skeleton page reads (see assets/fundamentals.example.json):
  currency, unit_label, annual, balance, solvency, valuation, peers, industry, sources
plus anything company-specific you add (segments, assets, pipeline, debt stack, scenarios, debt path ...).

A-shares: statements, indicators, dividends and valuation for the company AND every peer come from the Eastmoney
files that fetch_data.py saved in data/raw/fin/ (amounts in yuan; converted to RMB million here).
HK / US: there is no equally complete free source for peers. Transcribe the company's figures from its results
announcements / 10-K / 10-Q (data/raw/filings/*.txt) into ANNUAL_MANUAL below, use Yahoo info / statements or the
akshare HK indicator files for peers, and cite the document for every hand-typed number.
"""
import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FIN = os.path.join(ROOT, "data", "raw", "fin")
OUT = os.path.join(ROOT, "data", "processed")
M = 1e6

# ============================================================ CONFIG (edit)
TARGET = "000429"
NAMES = {"000429": "粤高速A", "600377": "宁沪高速", "001965": "招商公路"}   # company first, then peers
YEARS = list(range(2019, 2026))          # complete fiscal years for the annual table
LAST_FY = "2025-12-31"                   # latest full year (peer comparison)
LAST_BS = "2026-06-30"                   # latest balance sheet date
HALF = ("2026-06-30", "2025-06-30")      # latest interim vs same period last year; None to skip
# Overrides for restated comparatives (e.g. common-control acquisitions): {year: {"revenue": .., "np": .., "np_adj": ..}}
PRIOR_YEAR_AS_REPORTED = {}
INDUSTRY = []                            # [{"label", "value", "url"}] - sourced industry facts
SOURCES = []                             # [{"label", "url"}] - documents the narrative relies on
BROKER_TARGETS = []                      # [{"broker", "rating", "target", "date", "url"}] - third-party, dated
CAPITALISED_INTEREST = {}                # {"2025-12-31": 78.09} RMB m from the notes; counted in interest cover when material
EBITDA_ONE_OFFS = {}                     # {"2025-12-31": 310.0} one-off gains inside EBITDA to strip for EV/EBITDA and leverage


# ============================================================ Eastmoney loaders (A-shares)
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


def ratio(a, b):
    return None if b in (0, None) or a is None or np.isnan(a) or np.isnan(b) else a / b - 1


DEBT_COLS = ("SHORT_LOAN", "NONCURRENT_LIAB_1YEAR", "LONG_LOAN", "BOND_PAYABLE", "SHORT_BOND_PAYABLE")
DA_COLS = ("FA_IR_DEPR", "IA_AMORTIZE", "LPE_AMORTIZE", "USERIGHT_ASSET_AMORTIZE")


def company_year(i, b, f, ind, d):
    """Key figures (RMB million) for one report date from Eastmoney statement frames."""
    rev = val(i, d, "TOTAL_OPERATE_INCOME") / M
    debt = sum(nz(val(b, d, c)) for c in DEBT_COLS) / M
    cash = val(b, d, "MONETARYFUNDS") / M
    da = sum(nz(val(f, d, c)) for c in DA_COLS) / M
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


# ============================================================ the company
i, b, f, ind = (load(k, TARGET) for k in ("is", "bs", "cf", "ind"))
annual = []
for y in YEARS:
    cur, prev = company_year(i, b, f, ind, f"{y}-12-31"), company_year(i, b, f, ind, f"{y - 1}-12-31")
    prev.update(PRIOR_YEAR_AS_REPORTED.get(y, {}))
    annual.append({"y": y, **{k: cur[k] for k in ("revenue", "gross_margin", "np", "np_adj", "roe", "ocf", "capex")},
                   "revenue_yoy": ratio(cur["revenue"], prev["revenue"]), "np_yoy": ratio(cur["np"], prev["np"]),
                   "np_adj_yoy": ratio(cur["np_adj"], prev["np_adj"]), "dps": dps_for(TARGET, y) or None})
bal_dates = sorted({d for d in b["d"] if d[5:] in ("12-31", "06-30") and d >= f"{YEARS[0] - 1}-12-31"})
balance = []
for d in bal_dates:
    c = company_year(i, b, f, ind, d)
    balance.append({"p": d[:7] if d[5:] == "06-30" else d[:4], **{k: c[k] for k in ("cash", "debt", "net_debt", "debt_asset", "current_ratio")}})
last = company_year(i, b, f, ind, LAST_BS)
fy = company_year(i, b, f, ind, LAST_FY)
ebitda_rec = fy["ebitda"] - EBITDA_ONE_OFFS.get(LAST_FY, 0.0)
interest_all = fy["interest_exp"] + CAPITALISED_INTEREST.get(LAST_FY, 0.0)
solvency = {"date": LAST_BS, "net_debt": last["net_debt"], "ebitda": fy["ebitda"], "ebitda_recurring": ebitda_rec,
            # reported EBITDA keeps the company on the same basis as the peer table; the recurring version strips one-offs
            "nd_ebitda": last["net_debt"] / fy["ebitda"], "nd_ebitda_recurring": last["net_debt"] / ebitda_rec,
            # EBIT / (expensed + capitalised interest); capitalised interest sits in the notes, not the income statement
            "interest_cover": fy["ebit"] / interest_all if interest_all else None}

# ============================================================ valuation (latest row of stock_value_em)
vv = pd.read_csv(os.path.join(FIN, f"value_{TARGET}.csv"))
v_last = vv.iloc[-1]
price, mcap = float(v_last["当日收盘价"]), float(v_last["总市值"]) / M
pe_hist, pb_hist = pd.to_numeric(vv["PE(TTM)"], errors="coerce").dropna(), pd.to_numeric(vv["市净率"], errors="coerce").dropna()
dps_fy = dps_for(TARGET, int(LAST_FY[:4]))
ev = mcap + last["net_debt"] + last["minority_equity"] + last["perpetual"]  # claims on the consolidated EBITDA
valuation = {"date": str(v_last["数据日期"])[:10], "price": price, "mcap": mcap, "ev": ev,
             "pe_ttm": float(v_last["PE(TTM)"]), "pb": float(v_last["市净率"]),
             "pe_pct": float((pe_hist <= pe_hist.iloc[-1]).mean()), "pb_pct": float((pb_hist <= pb_hist.iloc[-1]).mean()),
             "ev_ebitda": ev / fy["ebitda"], "ev_ebitda_recurring": ev / ebitda_rec, "dy": dps_fy / price if dps_fy else None, "dps": dps_fy or None,
             "broker_targets": BROKER_TARGETS}

# ============================================================ peers (same definitions for every name)
peers = []
for code, name in NAMES.items():
    try:
        pi, pb_, pf, pind = (load(k, code) for k in ("is", "bs", "cf", "ind"))
        pv = pd.read_csv(os.path.join(FIN, f"value_{code}.csv")).iloc[-1]
    except FileNotFoundError as e:
        print("missing data for", code, name, e)
        continue
    c1 = company_year(pi, pb_, pf, pind, LAST_FY)
    c0 = company_year(pi, pb_, pf, pind, f"{int(LAST_FY[:4]) - 1}-12-31")
    cb = company_year(pi, pb_, pf, pind, LAST_BS)
    dps = dps_for(code, int(LAST_FY[:4]))
    shares = float(pv["总股本"])
    row = {"code": code, "name": name, "mcap": float(pv["总市值"]) / M, "price": float(pv["当日收盘价"]),
           "revenue": c1["revenue"], "revenue_yoy": ratio(c1["revenue"], c0["revenue"]), "np": c1["np"], "np_yoy": ratio(c1["np"], c0["np"]),
           "np_adj_yoy": ratio(c1["np_adj"], c0["np_adj"]), "roe": c1["roe"], "gross_margin": c1["gross_margin"],
           "pe_ttm": float(pv["PE(TTM)"]), "pb": float(pv["市净率"]), "dy": dps / float(pv["当日收盘价"]) if dps else 0.0,
           "payout": dps * shares / M / c1["np"] if dps and c1["np"] else None,
           "net_debt": cb["net_debt"], "nd_ebitda": cb["net_debt"] / c1["ebitda"] if c1["ebitda"] else None, "debt_asset": cb["debt_asset"]}
    if HALF:
        h1, h0 = company_year(pi, pb_, pf, pind, HALF[0]), company_year(pi, pb_, pf, pind, HALF[1])
        row.update({"rev_h_yoy": ratio(h1["revenue"], h0["revenue"]), "np_h_yoy": ratio(h1["np"], h0["np"]), "np_adj_h_yoy": ratio(h1["np_adj"], h0["np_adj"])})
    peers.append(row)


def rank(key, code=TARGET, descending=True):
    vals = sorted([(p[key], p["code"]) for p in peers if p.get(key) is not None], reverse=descending)
    return next((k + 1 for k, (_, c) in enumerate(vals) if c == code), None), len(vals)


peer_ranks = {k: dict(zip(("rank", "of"), rank(k))) for k in ("roe", "revenue_yoy", "np_yoy", "np_adj_yoy", "pe_ttm", "pb", "dy", "mcap", "revenue")}
peer_ranks["nd_ebitda_lowest"] = dict(zip(("rank", "of"), rank("nd_ebitda", descending=False)))
medians = {k: float(np.nanmedian([p[k] for p in peers if p.get(k) is not None])) for k in ("pe_ttm", "pb", "dy", "nd_ebitda", "roe", "revenue_yoy")}

res = {"currency": "CNY", "unit_label": "百万元", "annual": annual, "balance": balance, "solvency": solvency, "valuation": valuation,
       "peers": peers, "peer_ranks": peer_ranks, "peer_medians": medians, "peer_mcap_total": sum(p["mcap"] for p in peers),
       "industry": INDUSTRY, "sources": SOURCES}
# ---- add company-specific blocks below (segments, assets, pipeline, debt stack, scenarios, debt path, ...) ----

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "fundamentals.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, ensure_ascii=False, indent=1, default=float)
print(json.dumps({k: res[k] for k in ("solvency", "valuation", "peer_ranks", "peer_medians")}, ensure_ascii=False, indent=1, default=float))
for a in annual:
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in a.items()})
