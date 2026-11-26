"""Operating KPIs from Yum China's quarterly press releases (SEC 8-K exhibit 99.1), the release times that decide
which session could first react in New York and in Hong Kong, and quarterly growth of national catering revenue.
Writes data/processed/ops_kpis.json, earnings_days.json and catering_quarterly.json.

- Quarters: Yum China moved to calendar quarters in 2018 (with 2017 recast). Releases about 2017 and earlier use the
  old calendar (Q1 Jan-Feb, Q2 Mar-May, Q3 Jun-Aug, Q4 Sep-Dec) and are flagged calendar="old".
- Release time: SEC acceptanceDateTime of the 8-K (UTC). It matches Yahoo's release times: 05:00 ET releases since late
  2024 have 8-Ks accepted at about 10:00-11:00 UTC, and the after-the-close releases before that at about 20:45 UTC
  (16:45 ET). day0_us is the first NYSE session that opens after it, day0_hk the first HKEX session (09:30 HKT).
- Catering revenue: NBS monthly releases when the fetch got them, otherwise total retail sales (Eastmoney); quarterly
  growth = sum of monthly values / sum of the implied prior-year values (value / (1 + YoY)) - 1.
"""
import glob
import json
import os
import re
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
sys.path.insert(0, os.path.join(ROOT, "..", "report_kit"))
import marketlib as ml  # noqa: E402

ET, HKT = ZoneInfo("America/New_York"), ZoneInfo("Asia/Hong_Kong")
QN = {"First": 1, "Second": 2, "Third": 3, "Fourth": 4}
NEXT_EARNINGS = "2027-02-04"  # Yahoo's date for the Q4 2026 release (08:00 ET, an estimate until the company confirms it)


def num_row(txt, label):
    """First value of a key-results table row such as 'Same-Store Sales Growth (2) (%) | (3 | ) | 1 | ...'."""
    m = re.search(rf"^{label}[^|\n]*\|(.*)$", txt, re.M)
    if not m:
        return None
    toks = [t.strip() for t in m.group(1).split("|")]
    for i, t in enumerate(toks):
        t2 = t.replace(",", "")
        if re.fullmatch(r"\(?[-+]?\d+(\.\d+)?\)?", t2):
            neg = t2.startswith("(") and (t2.endswith(")") or (i + 1 < len(toks) and toks[i + 1].startswith(")")))
            return -float(t2.strip("()")) if neg else float(t2.strip("()"))
    return None


def first(pattern, txt, cast=float, flags=re.I | re.S):
    m = re.search(pattern, txt, flags)
    return cast(m.group(1).replace(",", "")) if m else None


def parse_release(path):
    raw = open(path, encoding="utf-8", errors="ignore").read()
    head = raw[:3000]
    m = re.search(r"Yum China Reports (First|Second|Third|Fourth) Quarter(?: and (?:Full|Fiscal) Year)?\s*(\d{4})?", head)
    if not m:
        return None
    fdate = os.path.basename(path)[:10]
    q = QN[m.group(1)]
    year = int(m.group(2)) if m.group(2) else (int(fdate[:4]) - 1 if q == 4 else int(fdate[:4]))
    old = year <= 2017
    end = {1: "02-28" if old else "03-31", 2: "05-31" if old else "06-30", 3: "08-31" if old else "09-30", 4: "12-31"}[q]
    t = re.sub(r"[ \t]+", " ", raw)
    flat = re.sub(r"\s+", " ", raw)
    rec = {"p": f"{year}-{end}", "label": f"{year}Q{q}", "calendar": "old" if old else "calendar", "file": os.path.basename(path),
           "filing_date": fdate}
    rec["sys_growth"] = num_row(t, r"System Sales Growth")
    rec["sssg"] = num_row(t, r"Same-Store Sales Growth")
    lead = flat[:20000]
    if rec["sssg"] is None:  # older releases state it in the highlights: "grew 4%", "declined 15%", "reached 97% of the prior year's level"
        for verb, n in re.findall(r"Same-store sales (?:index )?(grew|increased|declined|decreased|were flat|was flat|reached)\s*(?:to |by )?(?:approximately )?(\d+)?%?", lead):
            if "flat" in verb:
                rec["sssg"] = 0.0
                break
            if n:
                v = float(n)
                rec["sssg"] = v - 100 if verb == "reached" else (v if verb in ("grew", "increased") else -v)
                break
    if rec["sys_growth"] is None:
        for verb, n in re.findall(r"(?:Total )?[Ss]ystem sales (grew|increased|declined|decreased|were flat|was flat)\s*(?:by )?(\d+)?%", lead):
            if "flat" in verb or n:
                rec["sys_growth"] = 0.0 if "flat" in verb else (float(n) if verb in ("grew", "increased") else -float(n))
                break
    rec["opm_pr"] = num_row(t, r"OP Margin")
    rec["op_mn"] = num_row(t, r"Operating Profit \(\$mn\)") or num_row(t, r"Operating Profit")
    rec["adj_op_mn"] = num_row(t, r"Adjusted Operating Profit")  # excludes special items (e.g. re-measurement gains on KFC JV stakes)
    rec["rm"] = first(r"Restaurant margin (?:was|of|reached) ([\d.]+)%", flat)
    # the company-wide count comes first in the highlights; brand counts and targets come later, so take the earliest exact
    # count, and fall back to a rounded "exceeded 12,000" only when no exact one is given
    def store_cands(pats):
        return [(m.start(), int(m.group(1).replace(",", ""))) for pat in pats for m in re.finditer(pat, flat[:20000], re.I)]
    cands = store_cands((r"total store count (?:reached|to|of) ([\d,]{5,7})", r"Total stores reached ([\d,]{5,7})",
                         r"reached ([\d,]{5,7}) stores")) or store_cands((r"Total stores exceeded ([\d,]{5,7})",))
    rec["stores"] = min(cands)[1] if cands else None
    rec["net_new"] = first(r"([\d,]+) net new stores", flat, int)
    rec["sst"] = None
    m2 = re.search(r"Same-store transactions (grew|increased|declined|decreased|were flat)\s*(?:by )?(\d+)?%?", flat, re.I)
    if m2:
        rec["sst"] = 0.0 if "flat" in m2.group(1) else (float(m2.group(2)) * (1 if m2.group(1) in ("grew", "increased") else -1) if m2.group(2) else None)
    rec["delivery_pct"] = first(r"[Dd]elivery (?:sales )?contributed (?:approximately |about )?(\d+)%", flat)
    rec["digital_pct"] = first(r"[Dd]igital (?:ordering|sales|orders)[^.]{0,60}?(?:approximately |about )?(\d+)%", flat)
    rec["members_mn"] = first(r"(?:[Mm]embers|[Mm]embership)[^.]{0,90}?(?:exceeded|reached|over|surpassed) ([\d.]+) million", flat)
    rec["franchise_share_new"] = first(r"with (\d+)% opened by franchisees", flat)
    for k in ("sys_growth", "sssg", "opm_pr", "rm", "sst", "delivery_pct", "digital_pct", "franchise_share_new"):
        if rec.get(k) is not None:
            rec[k] = rec[k] / 100
    return rec


# ---------------------------------------------------------------- releases and their timing
files = sorted(glob.glob(os.path.join(RAW, "sec", "*_8-K_ex99_*.txt")))
recs = [r for r in (parse_release(f) for f in files) if r]
recs = sorted({r["label"]: r for r in recs}.values(), key=lambda r: r["p"])
subs = []
for f in ("submissions.json", "submissions-001.json"):
    path = os.path.join(RAW, "sec", f)
    if os.path.exists(path):
        js = json.load(open(path))
        rec = js["filings"]["recent"] if "filings" in js else js
        subs += [dict(zip(rec.keys(), vals)) for vals in zip(*rec.values())]
acc = {}
for s in subs:
    if s.get("form") == "8-K" and s.get("acceptanceDateTime"):
        t = datetime.fromisoformat(s["acceptanceDateTime"].replace("Z", "+00:00")).astimezone(ET)
        acc.setdefault(s["filingDate"], []).append(t)
us_cal = ml.read_series(os.path.join(RAW, "yahoo", "YUMC.csv"), "Date", "Close").index
hk_cal = ml.read_series(os.path.join(RAW, "yahoo", "9987_HK.csv"), "Date", "Close").index


def first_session(cal, t_local, open_t):
    """First session in calendar `cal` whose open (open_t local) is after local time t_local."""
    d = pd.Timestamp(t_local.date())
    if t_local.time() >= open_t:
        d = d + pd.Timedelta(days=1)
    pos = cal.searchsorted(d)
    return str(cal[pos].date()) if pos < len(cal) else None


days = []
for r in recs:
    ts = sorted(acc.get(r["filing_date"], []))
    if not ts:
        continue
    t_et = ts[0]
    t_hk = t_et.astimezone(HKT)
    r["release_et"] = t_et.strftime("%Y-%m-%d %H:%M")
    r["release_hkt"] = t_hk.strftime("%Y-%m-%d %H:%M")
    r["day0_us"] = first_session(us_cal, t_et, time(9, 30))
    r["day0_hk"] = first_session(hk_cal, t_hk, time(9, 30)) if t_hk.date() >= hk_cal[0].date() else None
    days.append({"period": r["p"], "label": r["label"], "release": r["release_et"], "release_hkt": r["release_hkt"],
                 "day0_us": r["day0_us"], "day0_hk": r["day0_hk"], "file": r["file"]})
days.append({"period": "2026-12-31", "label": "2026Q4", "release": NEXT_EARNINGS + " 08:00", "day0_us": NEXT_EARNINGS,
             "day0_hk": "2027-02-05", "next": True})

# ---------------------------------------------------------------- national consumption by quarter
# (1) total retail sales, monthly since 2008 (Eastmoney): the long series for the cycle tests
d = pd.read_csv(os.path.join(RAW, "macro", "retail_sales.csv"))
d["y"] = d["月份"].str[:4].astype(int)
d["m"] = d["月份"].str[5:7].astype(int)
rs = pd.DataFrame({"y": d["y"], "m": d["m"], "v": pd.to_numeric(d["当月"], errors="coerce"),
                   "yoy": pd.to_numeric(d["同比增长"], errors="coerce") / 100}).dropna()
rs["q"] = (rs["m"] - 1) // 3 + 1
retail = {}
for (y, q), g in rs.groupby(["y", "q"]):
    if len(g) >= 2 or q == 1:  # January and February are released together
        retail[f"{y}-{['03-31', '06-30', '09-30', '12-31'][q - 1]}"] = float(g["v"].sum() / (g["v"] / (1 + g["yoy"])).sum() - 1)
# (2) catering revenue (餐饮收入) from the NBS releases. A release titled "N月份" reports month N; one titled "1—N月份",
#     "一季度", "上半年", "前三季度" or the full year reports the year to date. Months are rebuilt from both kinds
#     (month N = YTD(N) - YTD(N-1), prior-year base likewise), and a quarter is kept only when all its months are known.
catering = {}
nbs = os.path.join(RAW, "macro", "nbs_retail_releases.json")
if os.path.exists(nbs):
    month, ytd = {}, {}
    for r in json.load(open(nbs)):
        t = r.get("title", "")
        if "catering" not in r:
            continue
        v, g = r["catering"], r["catering_yoy"] / 100
        m = re.match(r"(\d{4})年(.*?)社会消费品零售总额", t)
        if not m:
            continue
        y, part = int(m.group(1)), m.group(2)
        if re.fullmatch(r"1—(\d{1,2})月份?", part):
            ytd[(y, int(re.fullmatch(r"1—(\d{1,2})月份?", part).group(1)))] = (v, g)
        elif part in ("一季度", "上半年", "前三季度", ""):
            ytd[(y, {"一季度": 3, "上半年": 6, "前三季度": 9, "": 12}[part])] = (v, g)
        elif re.fullmatch(r"(\d{1,2})月份?", part):
            month[(y, int(re.fullmatch(r"(\d{1,2})月份?", part).group(1)))] = (v, v / (1 + g))
    # rebuild the year-to-date sums month by month: a reported YTD figure resets the sum, a monthly figure adds to it
    full = {}
    for y in sorted({k[0] for k in list(ytd) + list(month)}):
        cv = cb = None
        for n in range(2, 13):
            if (y, n) in ytd:
                v, g = ytd[(y, n)]
                cv, cb = v, v / (1 + g)
            elif cv is not None and (y, n) in month:
                cv, cb = cv + month[(y, n)][0], cb + month[(y, n)][1]
            else:
                cv = cb = None
            if cv is not None:
                full[(y, n)] = (cv, cb)
    for (y, n), (v, b_) in full.items():
        key = f"{y}-{['03-31', '06-30', '09-30', '12-31'][n // 3 - 1]}" if n % 3 == 0 else None
        if key and n == 3:
            catering[key] = float(v / b_ - 1)
        elif key and (y, n - 3) in full:
            v0, b0 = full[(y, n - 3)]
            catering[key] = float((v - v0) / (b_ - b0) - 1)

cat = {"retail": dict(sorted(retail.items())), "catering": dict(sorted(catering.items())),
       "source_retail": "社会消费品零售总额（东方财富，国家统计局口径）", "source_catering": "国家统计局月度新闻稿中的 1—N 月餐饮收入"}
src = f"retail {len(retail)} quarters, catering {len(catering)} quarters"

os.makedirs(OUT, exist_ok=True)
ml.dump_json({"source": "Yum China quarterly press releases (SEC 8-K exhibit 99.1)", "quarters": recs}, os.path.join(OUT, "ops_kpis.json"))
ml.dump_json(days, os.path.join(OUT, "earnings_days.json"))
ml.dump_json(cat, os.path.join(OUT, "catering_quarterly.json"))
print("consumption series:", src)
cols = ["label", "sys_growth", "sssg", "sst", "rm", "opm_pr", "op_mn", "stores", "net_new", "delivery_pct", "members_mn", "release_et", "day0_us", "day0_hk"]
print(pd.DataFrame(recs)[[c for c in cols if c in pd.DataFrame(recs).columns]].to_string())
