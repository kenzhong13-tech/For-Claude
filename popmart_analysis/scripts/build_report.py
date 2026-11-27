"""Inline report_kit CSS/JS and the processed analysis data into report/template.html -> report/popmart_report.html."""
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


keep = ["date", "pm", "hsi", "pm_idx", "hsi_idx", "dd_pm", "dd_hsi", "vol63_pm", "vol63_hsi",
        "garch_pm", "beta63", "beta252", "corr63"]
data = {
    "meta": mkt["meta"],
    "series": {k: rnd(mkt["series"][k], 4) for k in keep},
    "scatter": mkt["scatter"],
    "hist": rnd(mkt["hist"], 4),
    "events": rnd(mkt["events"], 4),
    "by_year": rnd(mkt["by_year"], 4),
    "factor_betas": rnd(mkt["factor_betas"], 4),
    "sim_daily": rnd(mkt["sim_daily"], 6),
    "multi": rnd(mkt["multi_factor"], 4),
    "fund": rnd(fund, 4),
}
html = open(P("report", "template.html"), encoding="utf-8").read()
html = html.replace("/*__BASE_CSS__*/", open(os.path.join(KIT, "base.css"), encoding="utf-8").read())
html = html.replace("/*__CHARTS_JS__*/", open(os.path.join(KIT, "charts.js"), encoding="utf-8").read())
html = html.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
open(P("report", "popmart_report.html"), "w", encoding="utf-8").write(html)
print("wrote report", len(html) // 1024, "KB")
