"""Inline report_kit CSS/JS and the processed analysis data into report/template.html -> report/sbio_report.html."""
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


keep = ["date", "sb", "sb_idx", "hsi_idx", "sec_idx", "dd_sb", "dd_hsi", "dd_sec", "vol63_sb", "vol63_hsi", "vol63_sec",
        "beta252_hsi", "beta252_sec", "corr63_sec", "corr63_hsi", "garch_sb"]
data = {k: rnd(mkt[k], 4) for k in ["meta", "stats", "sim_hsi_weekly", "sim_sec_weekly", "up_beta_hsi", "down_beta_hsi",
                                     "up_beta_sec", "down_beta_sec", "capm", "two_factor", "two_factor_2025", "by_year",
                                     "peers", "events", "hist", "scatter", "rebased_2025", "car_by_year"]}
data["sim_hsi"] = rnd(mkt["sim_hsi"], 6)
data["sim_sec"] = rnd(mkt["sim_sec"], 6)
data["series"] = {k: rnd(mkt["series"][k], 4) for k in keep}
data["fund"] = rnd(fund, 4)
html = open(P("report", "template.html"), encoding="utf-8").read()
html = html.replace("/*__BASE_CSS__*/", open(os.path.join(KIT, "base.css"), encoding="utf-8").read())
html = html.replace("/*__CHARTS_JS__*/", open(os.path.join(KIT, "charts.js"), encoding="utf-8").read())
html = html.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
open(P("report", "sbio_report.html"), "w", encoding="utf-8").write(html)
print("wrote report", len(html) // 1024, "KB")
