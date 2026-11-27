"""Inject processed analysis data into report/template.html -> report/coreweave_report.html."""
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
P = lambda *a: os.path.join(ROOT, *a)  # noqa: E731
mkt = json.load(open(P("data", "processed", "market_analysis.json")))
fund = json.load(open(P("data", "processed", "fundamentals.json")))


def rnd(v, n=4):
    if isinstance(v, float):
        return round(v, n)
    if isinstance(v, list):
        return [rnd(x, n) for x in v]
    if isinstance(v, dict):
        return {k: rnd(x, n) for k, x in v.items()}
    return v


keep = ["date", "crwv", "spx", "crwv_idx", "spx_idx", "dd_crwv", "dd_spx", "vol21_crwv", "vol21_spx",
        "vol63_crwv", "vol63_spx", "garch_crwv", "beta63", "corr63", "corr63_nbis", "r_crwv", "r_spx"]
data = {
    "meta": mkt["meta"],
    "series": {k: rnd(mkt["series"][k], 4) for k in keep},
    "scatter": mkt["scatter"],
    "hist": mkt["hist"],
    "events": rnd(mkt["events"], 4),
    "iv": rnd(mkt.get("implied_vol", {}), 4),
    "quarterly": rnd(fund["quarterly"], 4),
    "maturities": [[k, v] for k, v in fund["maturities"].items()],
    "debt_stack": fund["debt_stack"],
    "factor_betas": rnd(mkt["factor_betas"], 3),
    "scenarios": rnd(fund["scenarios"], 4),
    "grid": rnd(fund["grid"], 4),
    "leverage_table": rnd(fund["leverage_table"], 4),
    "refi": rnd(fund["refi_sensitivity"], 4),
}
html = open(P("report", "template.html"), encoding="utf-8").read()
html = html.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
open(P("report", "coreweave_report.html"), "w", encoding="utf-8").write(html)
print("wrote report", len(html) // 1024, "KB")
