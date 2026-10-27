"""Financials, solvency, valuation and peer comparison for <公司>（<代码>） -> data/processed/fundamentals.json.

Template from the stock-analysis-report skill. Copy to <slug>_analysis/scripts/analyze_fundamentals.py and edit.
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
TARGET = "000429"
NAMES = {"000429": "粤高速A", "600377": "宁沪高速", "001965": "招商公路"}   # company first, then peers
YEARS = list(range(2019, 2026))          # complete fiscal years for the annual table
LAST_FY = "2025-12-31"                   # latest full fiscal year (peer comparison)
LAST_BS = "2026-06-30"                   # latest balance sheet date
HALF = ("2026-06-30", "2025-06-30")      # latest interim vs the same period a year earlier; None to skip
INDUSTRY = []                            # [{"label", "value", "url"}] - sourced industry facts
SOURCES = []                             # [{"label", "url"}] - documents the narrative relies on
BROKER_TARGETS = []                      # [{"broker", "rating", "target", "date", "url"}] - third-party, dated
# A-shares
PRIOR_YEAR_AS_REPORTED = {}              # {year: {"revenue": .., "np": .., "np_adj": ..}} when the provider shows restated comparatives
CAPITALISED_INTEREST = {}                # {"2025-12-31": 78.09} from the notes; counted in interest cover when material
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
        cb = company_year(pi, pb_, pf, pind, LAST_BS)
        dps = dps_for(code, int(LAST_FY[:4]))
        row = {"code": code, "name": name, "mcap": float(pv["总市值"]) / M, "price": float(pv["当日收盘价"]),
               "revenue": c1["revenue"], "revenue_yoy": ratio(c1["revenue"], c0["revenue"]), "np": c1["np"], "np_yoy": ratio(c1["np"], c0["np"]),
               "np_adj_yoy": ratio(c1["np_adj"], c0["np_adj"]), "roe": c1["roe"], "gross_margin": c1["gross_margin"],
               "pe_ttm": float(pv["PE(TTM)"]), "pb": float(pv["市净率"]), "dy": dps / float(pv["当日收盘价"]) if dps else 0.0,
               "payout": dps * float(pv["总股本"]) / M / c1["np"] if dps and c1["np"] else None,
               "net_debt": cb["net_debt"], "nd_ebitda": cb["net_debt"] / c1["ebitda"] if c1["ebitda"] else None, "debt_asset": cb["debt_asset"]}
        if HALF:
            h1, h0 = company_year(pi, pb_, pf, pind, HALF[0]), company_year(pi, pb_, pf, pind, HALF[1])
            row.update({"rev_h_yoy": ratio(h1["revenue"], h0["revenue"]), "np_h_yoy": ratio(h1["np"], h0["np"]), "np_adj_h_yoy": ratio(h1["np_adj"], h0["np_adj"])})
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

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "fundamentals.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, ensure_ascii=False, indent=1, default=float)
print(json.dumps({k: res[k] for k in ("solvency", "valuation", "peer_ranks", "peer_medians")}, ensure_ascii=False, indent=1, default=float))
for a in res["annual"]:
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in a.items()})
