"""Inline report_kit CSS/JS and the processed analysis data into report/template.html -> report/gdexpressway_report.html."""
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
P = lambda *a: os.path.join(ROOT, *a)  # noqa: E731
KIT = os.path.join(ROOT, "..", "report_kit")
mkt = json.load(open(P("data", "processed", "market_analysis.json"), encoding="utf-8"))
fund = json.load(open(P("data", "processed", "fundamentals.json"), encoding="utf-8"))


def rnd(v, n=4):
    if isinstance(v, float):
        return round(v, n)
    if isinstance(v, list):
        return [rnd(x, n) for x in v]
    if isinstance(v, dict):
        return {k: rnd(x, n) for k, x in v.items()}
    return v


keep = ["date", "gd", "gd_idx", "csi_idx", "sec_idx", "div_idx", "y10", "dd_gd", "dd_csi", "dd_sec", "dy_ttm", "spread",
        "vol63_gd", "vol63_csi", "vol63_sec", "beta252_csi", "beta252_sec", "corr126_csi", "corr126_sec", "rate252", "garch_gd"]
data = {k: rnd(mkt[k], 4) for k in ["meta", "stats", "sim_csi_weekly", "sim_sec_weekly", "up_beta_csi", "down_beta_csi", "capm",
                                     "factors", "factors_2016_2020", "factors_2021_2023", "factors_2023", "factors_2024", "garch",
                                     "by_year", "peers", "events", "hist", "rebased_2024", "car_by_year", "ex_dividend",
                                     "ex_dividend_summary", "valuation_now", "resid_sd_daily"]}
for k in ("sim_csi", "sim_sec", "sim_div"):
    data[k] = rnd(mkt[k], 6)
data["series"] = {k: rnd(mkt["series"][k], 4) for k in keep}
data["fund"] = rnd(fund, 4)
html = open(P("report", "template.html"), encoding="utf-8").read()
html = html.replace("/*__BASE_CSS__*/", open(os.path.join(KIT, "base.css"), encoding="utf-8").read())
html = html.replace("/*__CHARTS_JS__*/", open(os.path.join(KIT, "charts.js"), encoding="utf-8").read())
html = html.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
open(P("report", "gdexpressway_report.html"), "w", encoding="utf-8").write(html)
print("wrote report", len(html) // 1024, "KB")
