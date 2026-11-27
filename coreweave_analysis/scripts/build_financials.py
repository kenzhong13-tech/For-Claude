"""Build quarterly and annual financial tables for CoreWeave from SEC XBRL companyfacts.

Duration facts reported year-to-date in 10-Qs are converted to discrete quarters
(Q4 = FY - 9M). Output: data/processed/financials.json
"""
import json
import os
from collections import defaultdict
from datetime import date

ROOT = os.path.join(os.path.dirname(__file__), "..")
facts = json.load(open(os.path.join(ROOT, "data", "raw", "sec", "companyfacts.json")))["facts"]["us-gaap"]

FLOW = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfServices"],
    "rnd": ["ResearchAndDevelopmentExpense"],
    "sm": ["SellingAndMarketingExpense"],
    "ga": ["GeneralAndAdministrativeExpense"],
    "op_income": ["OperatingIncomeLoss"],
    "interest_exp_debt": ["InterestExpenseDebt"],
    "interest_contractual": ["InterestExpenseDebtExcludingAmortization"],
    "interest_net": ["InterestIncomeExpenseNonoperatingNet", "InterestExpenseNonoperating", "InterestIncomeExpenseNet"],
    "pretax": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "tax": ["IncomeTaxExpenseBenefit"],
    "net_income": ["NetIncomeLoss"],
    "dna": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet"],
    "depreciation": ["Depreciation"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities"],
    "cfi": ["NetCashProvidedByUsedInInvestingActivities"],
    "cff": ["NetCashProvidedByUsedInFinancingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "debt_issued": ["ProceedsFromIssuanceOfLongTermDebt"],
    "debt_repaid": ["RepaymentsOfLongTermDebt"],
    "interest_paid": ["InterestPaidNet"],
    "op_lease_cost": ["OperatingLeaseCost"],
}
STOCK = {
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "cash_restricted_total": ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "assets": ["Assets"], "assets_current": ["AssetsCurrent"],
    "liabilities": ["Liabilities"], "liabilities_current": ["LiabilitiesCurrent"],
    "ppe_net": ["PropertyPlantAndEquipmentNet"],
    "equity": ["StockholdersEquity"],
    "debt_principal": ["DebtInstrumentCarryingAmount"],
    "op_lease_liab": ["OperatingLeaseLiability"],
    "fin_lease_liab": ["FinanceLeaseLiability"],
    "rpo": ["RevenueRemainingPerformanceObligation"],
    "ar": ["AccountsReceivableNetCurrent"],
    "ap": ["AccountsPayableCurrent"],
}


def days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def flow_series(tags):
    """Return {quarter_end: value} of discrete 3-month values plus {fy_end: value}."""
    q3m, ytd, fy = {}, defaultdict(dict), {}
    for tag in tags:
        if tag not in facts:
            continue
        for v in facts[tag]["units"].get("USD", []):
            d = days(v["start"], v["end"])
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
    # derive missing quarters from YTD differences
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
            if d >= 350:  # Q4 = FY - 9M YTD
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
        for v in facts[tag]["units"].get("USD", []):
            out.setdefault(v["end"], v["val"])
        if out:
            break
    return dict(sorted(out.items()))


quarters, annual = defaultdict(dict), defaultdict(dict)
for k, tags in FLOW.items():
    q, fy = flow_series(tags)
    for e, v in q.items():
        quarters[e][k] = v
    for e, v in fy.items():
        annual[e][k] = v
for k, tags in STOCK.items():
    for e, v in stock_series(tags).items():
        quarters[e][k] = v
        if e.endswith("12-31"):
            annual[e][k] = v

qs = {e: v for e, v in sorted(quarters.items()) if e >= "2023-12-31"}
out = {"quarterly": qs, "annual": dict(sorted(annual.items()))}
json.dump(out, open(os.path.join(ROOT, "data", "processed", "financials.json"), "w"), indent=1)

cols = ["revenue", "cost_of_revenue", "op_income", "interest_exp_debt", "net_income", "dna", "sbc", "cfo", "capex",
        "cash", "debt_principal", "equity", "rpo"]
print("quarter     " + " ".join(f"{c[:10]:>11s}" for c in cols))
for e, v in qs.items():
    print(e, " ".join(f"{(v.get(c, float('nan')) / 1e6):11,.0f}" if c in v else f"{'-':>11s}" for c in cols))
print("\nannual")
for e, v in out["annual"].items():
    print(e, " ".join(f"{(v.get(c) or 0) / 1e6:11,.0f}" for c in cols))
