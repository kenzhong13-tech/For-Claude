"""Fundamentals helpers for US and Hong Kong companies and their peers.

A-shares need none of this: analyze_fundamentals_template.py reads Eastmoney statements for the company and every
peer directly. For the other markets:
- sec_periods(): discrete quarters and fiscal years from SEC XBRL companyfacts (10-Q values are year-to-date, so
  quarters are differenced and Q4 = FY - 9M), then sec_annual_rows() / sec_balance_rows() map them to the standard
  `annual` / `balance` keys of fundamentals.json (USD million).
- hk_indicators(): Eastmoney HK financial indicators (ak.stock_financial_hk_analysis_indicator_em, "报告期"), which
  hold annual and interim rows; hk_annual_rows() maps the annual ones; hk_peer_row() builds one peer-table row.
- yahoo_peer_row(): one peer-table row from Yahoo `info` (US peers).

Currency notes (checked on the 3SBio peer set, Oct 2026):
- Eastmoney HK amounts (revenue, profit, BPS) are in RMB for every company, even when CURRENCY says 美元: BeOne's,
  HUTCHMED's and Zai Lab's revenue there is about 7x Yahoo's USD figure. So convert prices and market caps with CNY
  per HKD for every HK name.
- Yahoo's trailingPE for these names differed from P/E on TTM attributable profit by 5-17% (e.g. 3SBio 3.7 vs 3.5),
  so hk_peer_row() computes P/E and P/B itself. Yahoo's revenueGrowth / earningsGrowth are the latest quarter's
  year-on-year change, not the fiscal year's. dividendYield is in percent in current yfinance versions;
  trailingAnnualDividendYield is a fraction.
"""
import json
import os
from collections import defaultdict
from datetime import date

import pandas as pd

M = 1e6

# ---------------------------------------------------------------- SEC XBRL (US filers)
FLOW = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfServices"],
    "rnd": ["ResearchAndDevelopmentExpense"],
    "sm": ["SellingAndMarketingExpense"],
    "ga": ["GeneralAndAdministrativeExpense"],
    "op_income": ["OperatingIncomeLoss"],
    "interest_exp_debt": ["InterestExpenseDebt", "InterestExpense"],
    "interest_net": ["InterestIncomeExpenseNonoperatingNet", "InterestExpenseNonoperating", "InterestIncomeExpenseNet"],
    "pretax": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "tax": ["IncomeTaxExpenseBenefit"],
    "net_income": ["NetIncomeLoss"],
    "dna": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities"],
    "cfi": ["NetCashProvidedByUsedInInvestingActivities"],
    "cff": ["NetCashProvidedByUsedInFinancingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "dividends_paid": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
}
STOCK = {
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "short_investments": ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "assets": ["Assets"], "assets_current": ["AssetsCurrent"],
    "liabilities": ["Liabilities"], "liabilities_current": ["LiabilitiesCurrent"],
    "equity": ["StockholdersEquity"],
    "lt_debt": ["LongTermDebt"],
    "lt_debt_noncurrent": ["LongTermDebtNoncurrent"],
    "lt_debt_current": ["LongTermDebtCurrent"],
    "short_borrowings": ["ShortTermBorrowings", "CommercialPaper"],
    "debt_principal": ["DebtInstrumentCarryingAmount"],
    "op_lease_liab": ["OperatingLeaseLiability"],
    "fin_lease_liab": ["FinanceLeaseLiability"],
    "rpo": ["RevenueRemainingPerformanceObligation"],
    "ar": ["AccountsReceivableNetCurrent"],
    "ap": ["AccountsPayableCurrent"],
    "ppe_net": ["PropertyPlantAndEquipmentNet"],
}


def _days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def sec_periods(companyfacts_path, flow=None, stock=None, unit="USD"):
    """({quarter_end: {key: value}}, {fiscal_year_end: {key: value}}) in units of `unit` from companyfacts.json.

    For each key the first tag (in list order) that has data is used. Duration facts of about 3 months are taken as
    quarters; 6- and 9-month year-to-date values and fiscal years fill in missing quarters by differencing.
    """
    facts_all = json.load(open(companyfacts_path))["facts"]
    facts = facts_all.get("us-gaap") or facts_all.get("ifrs-full") or {}
    flow, stock = flow or FLOW, stock or STOCK

    def flow_series(tags):
        q3m, ytd, fy = {}, defaultdict(dict), {}
        for tag in tags:
            if tag not in facts:
                continue
            for v in facts[tag]["units"].get(unit, []):
                if "start" not in v:
                    continue
                d = _days(v["start"], v["end"])
                key = v["end"]
                if 80 <= d <= 100:
                    q3m.setdefault(key, v["val"])
                elif 170 <= d <= 190 or 260 <= d <= 280:
                    ytd[key][d] = v["val"]
                elif 350 <= d <= 380:
                    fy.setdefault(key, v["val"])
                    ytd[key][d] = v["val"]
            if q3m or fy:
                break
        ends = sorted(set(list(ytd.keys()) + list(q3m.keys())))
        for e in ends:
            if e in q3m:
                continue
            for d, val in ytd[e].items():
                prev_end = sorted(k for k in ends if k < e)
                if not prev_end:
                    continue
                p = prev_end[-1]
                prior = None
                if d >= 350:
                    prior = next((x for dd, x in ytd[p].items() if 260 <= dd <= 280), None)
                elif 260 <= d <= 280:
                    prior = next((x for dd, x in ytd[p].items() if 170 <= dd <= 190), None)
                elif 170 <= d <= 190:
                    prior = q3m.get(p)
                if prior is not None:
                    q3m[e] = val - prior
                    break
        return dict(sorted(q3m.items())), dict(sorted(fy.items()))

    def stock_series(tags):
        out = {}
        for tag in tags:
            if tag not in facts:
                continue
            for v in facts[tag]["units"].get(unit, []):
                out.setdefault(v["end"], v["val"])
            if out:
                break
        return dict(sorted(out.items()))

    quarters, annual = defaultdict(dict), defaultdict(dict)
    for k, tags in flow.items():
        q, fy = flow_series(tags)
        for e, v in q.items():
            quarters[e][k] = v
        for e, v in fy.items():
            annual[e][k] = v
    # balance-sheet values at fiscal year ends (same month-day as the fiscal years found, e.g. 12-31 or 06-30),
    # including the opening balance of the first year so averages (ROE) work
    md = pd.Series([e[5:] for e in annual]).mode()
    fy_md = md.iloc[0] if len(md) else "12-31"
    for k, tags in stock.items():
        for e, v in stock_series(tags).items():
            quarters[e][k] = v
            if e[5:] == fy_md:
                annual[e][k] = v
    return dict(sorted(quarters.items())), dict(sorted(annual.items()))


def _debt(v):
    """Total financial debt from the balance-sheet keys, in order of preference (check against the debt note)."""
    short = v.get("short_borrowings") or 0
    if v.get("lt_debt") is not None:
        return v["lt_debt"] + short
    if v.get("lt_debt_noncurrent") is not None or v.get("lt_debt_current") is not None:
        return (v.get("lt_debt_noncurrent") or 0) + (v.get("lt_debt_current") or 0) + short
    return v.get("debt_principal")


def sec_annual_rows(annual, since=None):
    """Standard `annual` rows (USD million) from sec_periods() fiscal years."""
    rows, prev = [], None
    for e, v in annual.items():
        if since and e < since:
            prev = v
            continue
        rev, ni = v.get("revenue"), v.get("net_income")
        eq0, eq1 = (prev or {}).get("equity"), v.get("equity")
        row = {"y": int(e[:4]), "fy_end": e, "revenue": rev / M if rev is not None else None,
               "revenue_yoy": rev / prev["revenue"] - 1 if prev and prev.get("revenue") and rev is not None else None,
               "gross_margin": 1 - v["cost_of_revenue"] / rev if rev and v.get("cost_of_revenue") is not None else None,
               "op_income": v.get("op_income") / M if v.get("op_income") is not None else None,
               "np": ni / M if ni is not None else None,
               "np_yoy": ni / prev["net_income"] - 1 if prev and prev.get("net_income") and ni is not None and prev["net_income"] > 0 else None,
               "np_adj": None, "np_adj_yoy": None,
               "roe": ni / ((eq0 + eq1) / 2) if ni is not None and eq0 and eq1 else None,
               "ocf": v.get("cfo") / M if v.get("cfo") is not None else None,
               "capex": v.get("capex") / M if v.get("capex") is not None else None, "dps": None}
        rows.append(row)
        prev = v
    return rows


def sec_balance_rows(quarters, since=None):
    """Standard `balance` rows (USD million) at each quarter end from sec_periods()."""
    rows = []
    for e, v in quarters.items():
        if (since and e < since) or v.get("assets") is None:
            continue
        debt = _debt(v)
        cash = (v.get("cash") or 0) + (v.get("short_investments") or 0)
        rows.append({"p": e[:7], "cash": cash / M, "debt": debt / M if debt is not None else None,
                     "net_debt": (debt - cash) / M if debt is not None else None,
                     "debt_asset": v["liabilities"] / v["assets"] if v.get("liabilities") else None,
                     "current_ratio": v["assets_current"] / v["liabilities_current"] if v.get("assets_current") and v.get("liabilities_current") else None})
    return rows


# ---------------------------------------------------------------- Hong Kong (Eastmoney HK indicators)
def hk_indicators(path):
    """Tidy frame of an Eastmoney HK indicator file, indexed by report date (YYYY-MM-DD); 'annual' marks full years."""
    d = pd.read_csv(path)
    d["d"] = d["REPORT_DATE"].astype(str).str[:10]
    d["annual"] = pd.to_numeric(d["DATE_TYPE_CODE"], errors="coerce") == 1
    return d.drop_duplicates("d").set_index("d").sort_index()


def _g(df, d, col, scale=1.0):
    if d in df.index and col in df.columns and pd.notna(df.loc[d, col]):
        return float(df.loc[d, col]) * scale
    return None


def hk_annual_rows(ind, since_year=None):
    """Standard `annual` rows (reporting currency, million) from hk_indicators(); cash-flow and debt columns that the
    indicator file lacks stay None (fill them from the results announcement)."""
    rows = []
    for d in [x for x in ind.index if ind.loc[x, "annual"]]:
        if since_year and int(d[:4]) < since_year:
            continue
        rev = _g(ind, d, "OPERATE_INCOME", 1 / M)
        rows.append({"y": int(d[:4]), "fy_end": d, "revenue": rev, "revenue_yoy": _g(ind, d, "OPERATE_INCOME_YOY", 0.01),
                     "gross_margin": _g(ind, d, "GROSS_PROFIT_RATIO", 0.01), "np": _g(ind, d, "HOLDER_PROFIT", 1 / M),
                     "np_yoy": _g(ind, d, "HOLDER_PROFIT_YOY", 0.01), "np_adj": None, "np_adj_yoy": None,
                     "roe": _g(ind, d, "ROE_AVG", 0.01),
                     "ocf": rev * _g(ind, d, "OCF_SALES", 0.01) if rev is not None and _g(ind, d, "OCF_SALES") is not None else None,
                     "capex": None, "dps": None})
    return rows


def hk_ttm(ind, col, last_fy, half=None):
    """Trailing-twelve-month value: last full year + latest interim - same interim a year earlier."""
    fy = _g(ind, last_fy, col)
    if not half:
        return fy
    h1, h0 = _g(ind, half[0], col), _g(ind, half[1], col)
    return fy + h1 - h0 if None not in (fy, h1, h0) else fy


def hk_peer_row(code, name, ind, info, last_fy, half=None, fx_report_per_trade=1.0):
    """One peer row for an HK-listed company. ind: hk_indicators(); info: Yahoo info dict.

    fx_report_per_trade converts the trading currency into the currency of the Eastmoney figures: CNY per HKD
    (Eastmoney reports HK companies in RMB whatever their reporting currency). Market cap is reported in the trading
    currency (million); P/E and P/B are market cap (converted) / TTM attributable profit and price (converted) / BPS.
    """
    mcap = info.get("marketCap")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    ttm_np = hk_ttm(ind, "HOLDER_PROFIT", last_fy, half)
    bps = _g(ind, half[0] if half else last_fy, "BPS") or _g(ind, last_fy, "BPS")
    prev_fy = f"{int(last_fy[:4]) - 1}{last_fy[4:]}"
    row = {"code": code, "name": name, "mcap": mcap / M if mcap else None, "price": price,
           "revenue": _g(ind, last_fy, "OPERATE_INCOME", 1 / M), "revenue_yoy": _g(ind, last_fy, "OPERATE_INCOME_YOY", 0.01),
           "np": _g(ind, last_fy, "HOLDER_PROFIT", 1 / M), "np_yoy": _g(ind, last_fy, "HOLDER_PROFIT_YOY", 0.01),
           "roe": _g(ind, last_fy, "ROE_AVG", 0.01), "gross_margin": _g(ind, last_fy, "GROSS_PROFIT_RATIO", 0.01),
           "pe_ttm": (mcap * fx_report_per_trade) / ttm_np if mcap and ttm_np and ttm_np > 0 else None,
           "pb": (price * fx_report_per_trade) / bps if price and bps else None,
           "dy": info.get("trailingAnnualDividendYield") or 0.0,
           "nd_ebitda": (info["totalDebt"] - info["totalCash"]) / info["ebitda"] if info.get("ebitda") and info.get("totalDebt") is not None and info.get("totalCash") is not None else None,
           "debt_asset": _g(ind, half[0] if half else last_fy, "DEBT_ASSET_RATIO", 0.01),
           "target_mean": info.get("targetMeanPrice"), "n_analysts": info.get("numberOfAnalystOpinions"),
           "rev_prev": _g(ind, prev_fy, "OPERATE_INCOME", 1 / M)}
    if half:
        row.update({"rev_h_yoy": _g(ind, half[0], "OPERATE_INCOME_YOY", 0.01), "np_h_yoy": _g(ind, half[0], "HOLDER_PROFIT_YOY", 0.01)})
    return row


# ---------------------------------------------------------------- Yahoo info (US peers)
def load_info(path):
    return json.load(open(path)) if os.path.exists(path) else {}


def yahoo_peer_row(code, name, info):
    """One peer row from Yahoo info. Growth fields are the latest quarter year-on-year (label them so)."""
    g = info.get
    debt, cash, ebitda = g("totalDebt"), g("totalCash"), g("ebitda")
    return {"code": code, "name": name, "mcap": g("marketCap") / M if g("marketCap") else None, "price": g("currentPrice"),
            "revenue": g("totalRevenue") / M if g("totalRevenue") else None, "revenue_yoy": g("revenueGrowth"),
            "np": g("netIncomeToCommon") / M if g("netIncomeToCommon") else None, "np_yoy": g("earningsGrowth"),
            "roe": g("returnOnEquity"), "gross_margin": g("grossMargins"), "pe_ttm": g("trailingPE"), "pe_fwd": g("forwardPE"),
            "pb": g("priceToBook"), "dy": g("trailingAnnualDividendYield") or 0.0,
            "nd_ebitda": (debt - cash) / ebitda if ebitda and debt is not None and cash is not None else None,
            "target_mean": g("targetMeanPrice"), "n_analysts": g("numberOfAnalystOpinions"), "growth_basis": "latest quarter YoY"}
