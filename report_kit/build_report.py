"""Build a self-contained report page: inline the kit's CSS/JS and the processed analysis data into the template.

usage (from the repository root):
    python report_kit/build_report.py <slug>_analysis [--out <name>.html] [--kit report_kit] [--digits 5]

Reads  <dir>/report/template.html, <dir>/data/processed/market_analysis.json and, if present, fundamentals.json
Writes <dir>/report/<out> (default <slug>_report.html). DATA in the page = market_analysis plus {"fund": fundamentals}.
Placeholders in the template: /*__BASE_CSS__*/, /*__CHARTS_JS__*/ and __DATA_JSON__.
"""
import argparse
import json
import os
import re


def rnd(v, n):
    if isinstance(v, float):
        return round(v, n)
    if isinstance(v, list):
        return [rnd(x, n) for x in v]
    if isinstance(v, dict):
        return {k: rnd(x, n) for k, x in v.items()}
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--out")
    ap.add_argument("--kit", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--digits", type=int, default=5)
    ap.add_argument("--drop", default="", help="comma-separated top-level keys of market_analysis.json to leave out")
    a = ap.parse_args()
    d = a.dir.rstrip("/")
    slug = os.path.basename(d).replace("_analysis", "")
    proc = os.path.join(d, "data", "processed")
    data = json.load(open(os.path.join(proc, "market_analysis.json"), encoding="utf-8"))
    for k in filter(None, a.drop.split(",")):
        data.pop(k, None)
    fpath = os.path.join(proc, "fundamentals.json")
    if os.path.exists(fpath):
        data["fund"] = json.load(open(fpath, encoding="utf-8"))
    data = rnd(data, a.digits)
    html = open(os.path.join(d, "report", "template.html"), encoding="utf-8").read()
    for ph in ("/*__BASE_CSS__*/", "/*__CHARTS_JS__*/", "__DATA_JSON__"):
        if ph not in html:
            raise SystemExit(f"placeholder {ph} missing from template.html")
    html = html.replace("/*__BASE_CSS__*/", open(os.path.join(a.kit, "base.css"), encoding="utf-8").read())
    html = html.replace("/*__CHARTS_JS__*/", open(os.path.join(a.kit, "charts.js"), encoding="utf-8").read())
    html = html.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    out = os.path.join(d, "report", a.out or f"{slug}_report.html")
    open(out, "w", encoding="utf-8").write(html)
    todo = len(re.findall("【", html))
    print(f"wrote {out}  {len(html) // 1024} KB" + (f"  | {todo} 【…】 placeholders left" if todo else ""))
    if len(html) > 3 * 1024 * 1024:
        print("warning: page over 3 MB; drop unused series keys or lower --digits")


if __name__ == "__main__":
    main()
