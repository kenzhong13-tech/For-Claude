"""Cycle and seasonality tests for 百胜中国: are there calendar or cyclical patterns in the share price, and how
seasonal is the business? Writes data/processed/cycles.json.

Samples
- returns: the NYSE line (YUMC) since the spin-off (first full month 2016-12) for the longest history, and the HKEX
  line (9987) since its listing (2020-09-10). They are the same shares, so the two samples are not independent.
- business: quarterly revenue and operating margin from SEC XBRL for calendar quarters since 2017 (Yum China reported
  Jan-Feb, Mar-May, Jun-Aug and Sep-Dec quarters until 2017 and recast 2017 when it moved to calendar quarters in 2018);
  same-store sales growth and restaurant margin from the quarterly press releases since 2018 (ops_kpis.json); national
  consumption from total retail sales (since 2018) and NBS catering revenue (quarters available since 2022).

Tests (each reported with its statistic, p-value and sample size)
- month of year: OLS F-test of 12 month dummies, Alexander-Govern (unequal variances), Kruskal-Wallis, a
  permutation test of the F statistic, and per-month Welch t-tests with Benjamini-Hochberg q-values; raw and
  market-adjusted returns; the smallest monthly effect the sample could detect (80% power)
- day of week, turn of month, Chinese New Year and Golden Week windows, pre- and post-earnings drift
- serial dependence: Ljung-Box (returns and squared returns), ARCH-LM, Lo-MacKinlay variance ratios (robust),
  runs test
- spectral: periodogram with Fisher's g-test for one dominant cycle, Bartlett's cumulative-periodogram test
- price cycles: peaks and troughs by the 20% rule, phase durations and how regular they are
- business: trend + quarter-dummy regression of log revenue (F-test), Friedman test of operating margin by quarter,
  same-store sales against national catering revenue (correlation, Granger), earnings-day reaction against
  same-store sales
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import signal, stats
from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
from statsmodels.stats.multitest import multipletests

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
sys.path.insert(0, os.path.join(ROOT, "..", "report_kit"))
import finlib as fl  # noqa: E402
import marketlib as ml  # noqa: E402

RNG = np.random.default_rng(20261126)
N_PERM = 20000
MONTHS = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五"]
# Chinese New Year's Day (first day of the lunar year)
CNY = ["2017-01-28", "2018-02-16", "2019-02-05", "2020-01-25", "2021-02-12", "2022-02-01", "2023-01-22", "2024-02-10",
       "2025-01-29", "2026-02-17"]
LINES = {
    "us": {"ticker": "YUMC", "mkt": "^SP500TR", "mkt_fallback": "^GSPC", "start": "2016-11-01", "label": "美股 YUMC",
           "mkt_label": "标普 500 全收益"},
    "hk": {"ticker": "9987.HK", "mkt": "2800.HK", "mkt_fallback": "^HSI", "start": "2020-09-10", "label": "港股 9987",
           "mkt_label": "恒指（盈富基金，含息）"},
}


def yahoo(ticker, col="Adj Close"):
    path = os.path.join(RAW, "yahoo", ml.yahoo_file(ticker))
    return ml.read_series(path, "Date", col) if os.path.exists(path) and os.path.getsize(path) > 0 else None


def rnd(x, d=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), d)


# ---------------------------------------------------------------- generic tests
def group_tests(values, labels, n_perm=N_PERM):
    """Equal-means tests across groups: OLS F (dummies), Alexander-Govern, Kruskal-Wallis, permutation of F."""
    df = pd.DataFrame({"y": np.asarray(values, float), "g": np.asarray(labels)}).dropna()
    groups = [g["y"].values for _, g in df.groupby("g")]

    def f_stat(y, g):
        mu = y.mean()
        cats = pd.unique(g)
        ssb = sum(len(y[g == c]) * (y[g == c].mean() - mu) ** 2 for c in cats)
        ssw = sum(((y[g == c] - y[g == c].mean()) ** 2).sum() for c in cats)
        k, n = len(cats), len(y)
        return (ssb / (k - 1)) / (ssw / (n - k))

    y, g = df["y"].values, df["g"].values
    f_obs = f_stat(y, g)
    k, n = len(groups), len(y)
    p_f = float(stats.f.sf(f_obs, k - 1, n - k))
    perm = np.empty(n_perm)
    for i in range(n_perm):
        perm[i] = f_stat(y, RNG.permutation(g))
    p_perm = float((1 + (perm >= f_obs).sum()) / (n_perm + 1))
    ag = stats.alexandergovern(*groups)
    kw = stats.kruskal(*groups)
    return {"n": int(n), "k": int(k), "f": rnd(f_obs), "p_f": rnd(p_f), "p_perm": rnd(p_perm),
            "ag": rnd(ag.statistic), "p_ag": rnd(ag.pvalue), "kw": rnd(kw.statistic), "p_kw": rnd(kw.pvalue)}


def per_group(values, labels, names):
    """Mean, s.d., n, hit rate per group, and a Welch t-test of each group against all the others."""
    df = pd.DataFrame({"y": values, "g": labels}).dropna()
    rows = []
    for i, nm in enumerate(names):
        a, b = df.loc[df.g == i, "y"], df.loc[df.g != i, "y"]
        if len(a) < 2:
            continue
        t = stats.ttest_ind(a, b, equal_var=False)
        rows.append({"label": nm, "n": int(len(a)), "mean": rnd(a.mean(), 5), "sd": rnd(a.std(), 5),
                     "median": rnd(a.median(), 5), "hit": rnd((a > 0).mean(), 3), "t": rnd(t.statistic, 3), "p": rnd(t.pvalue)})
    if rows:
        q = multipletests([r["p"] for r in rows], method="fdr_bh")[1]
        for r, qq in zip(rows, q):
            r["q_bh"] = rnd(qq)
    return rows


def mde(sd, n1, n2, alpha=0.05, power=0.80):
    """Smallest difference in means a two-sample test would detect with the given power."""
    return float((stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)) * sd * math.sqrt(1 / n1 + 1 / n2))


def fisher_g(x):
    """Fisher's g-test for one dominant periodic component in a de-meaned series (exact p-value)."""
    x = np.asarray(x, float) - np.mean(x)
    n = len(x)
    f, p = signal.periodogram(x, detrend=False, scaling="spectrum")
    f, p = f[1:], p[1:]
    if n % 2 == 0:  # drop the Nyquist frequency
        f, p = f[:-1], p[:-1]
    m = len(p)
    g = p.max() / p.sum()
    kmax = int(math.floor(1 / g))
    pval = sum((-1) ** (j - 1) * math.comb(m, j) * (1 - j * g) ** (m - 1) for j in range(1, kmax + 1))
    # Bartlett's cumulative periodogram test against white noise (Kolmogorov-Smirnov form)
    cum = np.cumsum(p) / p.sum()
    d = np.max(np.abs(cum - np.arange(1, m + 1) / m))
    p_bartlett = float(stats.kstwobign.sf(d * math.sqrt(m)))
    k = int(np.argmax(p))
    order = np.argsort(p)[::-1][:5]
    return {"n": n, "m": m, "g": rnd(g), "p_g": rnd(min(max(pval, 0.0), 1.0)), "peak_period": rnd(1 / f[k], 2),
            "peak_share": rnd(p[k] / p.sum()), "bartlett_d": rnd(d), "p_bartlett": rnd(p_bartlett),
            "top_periods": [rnd(1 / f[i], 2) for i in order],
            "spectrum": {"period": [rnd(1 / v, 3) for v in f], "power_share": [rnd(v / p.sum(), 5) for v in p]}}


def variance_ratios(logp, lags):
    from arch.unitroot import VarianceRatio
    out = []
    for q in lags:
        vr = VarianceRatio(logp, lags=q, robust=True, debiased=True, overlap=True)
        out.append({"q": q, "vr": rnd(vr.vr), "z": rnd(vr.stat, 3), "p": rnd(vr.pvalue)})
    if out:
        zmax = max(abs(o["z"]) for o in out)
        out_p = min(1.0, len(out) * 2 * stats.norm.sf(zmax))  # Chow-Denning style joint test (Bonferroni bound)
        return out, {"max_abs_z": rnd(zmax, 3), "p_joint_bonferroni": rnd(out_p)}
    return out, {}


def runs_test(r):
    s = np.sign(r[r != 0])
    n1, n2 = int((s > 0).sum()), int((s < 0).sum())
    runs = 1 + int((s[1:] != s[:-1]).sum())
    mu = 2 * n1 * n2 / (n1 + n2) + 1
    var = 2 * n1 * n2 * (2 * n1 * n2 - n1 - n2) / ((n1 + n2) ** 2 * (n1 + n2 - 1))
    z = (runs - mu) / math.sqrt(var)
    return {"runs": runs, "expected": rnd(mu, 1), "z": rnd(z, 3), "p": rnd(2 * stats.norm.sf(abs(z)))}


def ljung_box(x, lags):
    lb = acorr_ljungbox(x, lags=lags, return_df=True)
    return [{"lag": int(l), "q": rnd(lb.loc[l, "lb_stat"], 2), "p": rnd(lb.loc[l, "lb_pvalue"])} for l in lags]


def turning_points(levels, thr=0.20):
    """Peaks and troughs by the 20% rule: a bear phase starts once the price is 20% below its running peak, a bull
    phase once it is 20% above its running trough. Returns the phases with dates, length and size."""
    s = levels.dropna()
    pts, mode = [], None
    hi, hi_d, lo, lo_d = s.iloc[0], s.index[0], s.iloc[0], s.index[0]
    for d, v in s.items():
        if v > hi:
            hi, hi_d = v, d
        if v < lo:
            lo, lo_d = v, d
        if mode in (None, "up") and v <= hi * (1 - thr):
            pts.append(("peak", hi_d, hi))
            mode, lo, lo_d = "down", v, d
        elif mode in (None, "down") and v >= lo * (1 + thr):
            pts.append(("trough", lo_d, lo))
            mode, hi, hi_d = "up", v, d
    phases = []
    for (t0, d0, v0), (t1, d1, v1) in zip(pts, pts[1:]):
        phases.append({"type": "bear" if t0 == "peak" else "bull", "start": str(d0.date()), "end": str(d1.date()),
                       "months": rnd((d1 - d0).days / 30.44, 1), "change": rnd(v1 / v0 - 1)})
    last_t, last_d, last_v = pts[-1] if pts else (None, s.index[0], s.iloc[0])
    ongoing = {"type": "bear" if last_t == "peak" else "bull", "start": str(last_d.date()), "end": str(s.index[-1].date()),
               "months": rnd((s.index[-1] - last_d).days / 30.44, 1), "change": rnd(s.iloc[-1] / last_v - 1), "ongoing": True}
    return [{"type": t, "date": str(d.date()), "level": rnd(v, 3)} for t, d, v in pts], phases, ongoing


def window_car(ex, day0, a, b):
    """Sum of excess returns over trading days [day0+a, day0+b] (day0 = first session on or after the date)."""
    idx = ex.index
    pos = idx.searchsorted(pd.Timestamp(day0))
    if pos + a < 0 or pos + b >= len(idx):
        return None
    return float(ex.iloc[pos + a: pos + b + 1].sum())


def one_sample(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 3:
        return {"n": len(xs)}
    t = stats.ttest_1samp(xs, 0.0)
    w = stats.wilcoxon(xs) if len(xs) >= 6 else None
    pos = sum(x > 0 for x in xs)
    sign_p = stats.binomtest(pos, len(xs), 0.5).pvalue
    return {"n": len(xs), "mean": rnd(np.mean(xs), 5), "median": rnd(np.median(xs), 5), "pos": int(pos), "t": rnd(t.statistic, 3),
            "p_t": rnd(t.pvalue), "p_wilcoxon": rnd(w.pvalue) if w is not None else None, "p_sign": rnd(sign_p)}


# ---------------------------------------------------------------- returns: load both lines
res = {"meta": {"n_perm": N_PERM, "seed": 20261126}}
lines = {}
for key, cfg in LINES.items():
    px = yahoo(cfg["ticker"])
    mkt = yahoo(cfg["mkt"]) if yahoo(cfg["mkt"]) is not None else yahoo(cfg["mkt_fallback"])
    px = px[px.index >= pd.Timestamp(cfg["start"])]
    end = min(px.index[-1], mkt.index[-1])
    px, mkt = px[px.index <= end], mkt[mkt.index <= end]
    lr = np.log(px).diff().dropna()
    mkt_al = mkt.reindex(px.index).ffill(limit=5)
    ex = (px.pct_change() - mkt_al.pct_change()).dropna()
    # complete calendar months only: the first month must start before the first close, the last must be finished
    me_px = px.resample("ME").last()
    me_mkt = mkt.resample("ME").last()
    mret = me_px.pct_change()
    mex = mret - me_mkt.pct_change().reindex(mret.index)
    first_full = (px.index[0] + pd.offsets.MonthEnd(0))  # month of the first close is partial
    last_full = end if end == end + pd.offsets.MonthEnd(0) else end - pd.offsets.MonthEnd(1)
    keep = (mret.index > first_full) & (mret.index <= last_full)
    mret, mex = mret[keep].dropna(), mex[keep].dropna()
    lines[key] = {"px": px, "mkt": mkt, "lr": lr, "ex": ex, "mret": mret, "mex": mex}
    res.setdefault("samples", {})[key] = {"label": cfg["label"], "mkt_label": cfg["mkt_label"], "start": str(px.index[0].date()),
                                          "end": str(end.date()), "n_days": int(len(lr)), "n_months": int(len(mret)),
                                          "first_month": str(mret.index[0].date())[:7], "last_month": str(mret.index[-1].date())[:7]}

# ---------------------------------------------------------------- 1. month of year
res["month"] = {}
for key, L in lines.items():
    out = {}
    for kind, s in (("raw", L["mret"]), ("excess", L["mex"])):
        lab = s.index.month - 1
        out[kind] = {"tests": group_tests(s.values, lab), "by_month": per_group(s.values, lab, MONTHS)}
        sd = float(s.std())
        n_m = len(s) / 12
        out[kind]["mde_one_month"] = rnd(mde(sd, n_m, len(s) - n_m))
        out[kind]["monthly_sd"] = rnd(sd)
    # Sell in May (Nov-Apr vs May-Oct), raw and excess
    for kind, s in (("raw", L["mret"]), ("excess", L["mex"])):
        winter = s[s.index.month.isin([11, 12, 1, 2, 3, 4])]
        summer = s[s.index.month.isin([5, 6, 7, 8, 9, 10])]
        t = stats.ttest_ind(winter, summer, equal_var=False)
        out[kind]["halloween"] = {"winter_mean": rnd(winter.mean(), 5), "summer_mean": rnd(summer.mean(), 5),
                                  "t": rnd(t.statistic, 3), "p": rnd(t.pvalue), "n": [int(len(winter)), int(len(summer))]}
    out["series"] = {"month": [str(d.date())[:7] for d in L["mret"].index], "raw": [rnd(v, 5) for v in L["mret"]],
                     "excess": [rnd(L["mex"].get(d), 5) for d in L["mret"].index]}
    res["month"][key] = out

# ---------------------------------------------------------------- 2. day of week, turn of month
res["weekday"], res["tom"] = {}, {}
for key, L in lines.items():
    r = L["lr"]
    wd = r.index.weekday
    ok = wd < 5
    res["weekday"][key] = {"raw": {"tests": group_tests(r[ok].values, wd[ok], n_perm=5000), "by_day": per_group(r[ok].values, wd[ok], WEEKDAYS)},
                           "excess": {"tests": group_tests(L["ex"].values, L["ex"].index.weekday, n_perm=5000),
                                      "by_day": per_group(L["ex"].values, L["ex"].index.weekday, WEEKDAYS)}}
    # turn of month: last trading day of a month and the first three of the next
    d = pd.Series(r.index, index=r.index)
    month_id = r.index.to_period("M")
    pos_in_m = d.groupby(month_id).cumcount()
    rev_pos = d.groupby(month_id).cumcount(ascending=False)
    tom = (pos_in_m < 3) | (rev_pos == 0)
    out = {}
    for kind, s in (("raw", r), ("excess", L["ex"])):
        tm = tom.reindex(s.index).fillna(False).astype(bool)
        t = stats.ttest_ind(s[tm], s[~tm], equal_var=False)
        out[kind] = {"tom_mean": rnd(s[tm].mean(), 6), "other_mean": rnd(s[~tm].mean(), 6), "t": rnd(t.statistic, 3),
                     "p": rnd(t.pvalue), "n_tom": int(tm.sum()), "n_other": int((~tm).sum())}
    res["tom"][key] = out

# ---------------------------------------------------------------- 3. holiday windows (excess returns)
res["holidays"] = {}
for key, L in lines.items():
    ex = L["ex"]
    cny = [d for d in CNY if pd.Timestamp(d) > ex.index[0] + pd.Timedelta(days=20) and pd.Timestamp(d) < ex.index[-1] - pd.Timedelta(days=20)]
    gw = [f"{y}-10-01" for y in range(2017, 2026) if pd.Timestamp(f"{y}-10-01") > ex.index[0] + pd.Timedelta(days=20)]
    out = {}
    for nm, dates in (("cny", cny), ("golden_week", gw)):
        pre = [window_car(ex, d, -10, -1) for d in dates]
        post = [window_car(ex, d, 0, 9) for d in dates]
        out[nm] = {"dates": dates, "pre": one_sample(pre), "post": one_sample(post),
                   "rows": [{"date": d, "pre": rnd(a, 5), "post": rnd(b, 5)} for d, a, b in zip(dates, pre, post)]}
    res["holidays"][key] = out

# ---------------------------------------------------------------- 4. serial dependence
res["dependence"] = {}
for key, L in lines.items():
    r = L["lr"]
    wk = np.log(L["px"].resample("W-FRI").last()).diff().dropna()
    mo = np.log(1 + L["mret"])
    acf = sm.tsa.acf(r, nlags=20, fft=True)
    arch = het_arch(r - r.mean(), nlags=5)
    vr_d, vr_d_joint = variance_ratios(np.log(L["px"]).values, [2, 5, 10, 20])
    vr_w, vr_w_joint = variance_ratios(np.log(L["px"].resample("W-FRI").last()).dropna().values, [2, 4, 8, 13])
    res["dependence"][key] = {
        "lb_daily": ljung_box(r, [5, 10, 20]), "lb_weekly": ljung_box(wk, [4, 8, 13]), "lb_monthly": ljung_box(mo, [6, 12]),
        "lb_sq_daily": ljung_box((r - r.mean()) ** 2, [5, 10, 20]),
        "arch_lm": {"lm": rnd(arch[0], 2), "p": rnd(arch[1]), "lags": 5},
        "acf": [rnd(v, 4) for v in acf[1:]], "acf_band": rnd(1.96 / math.sqrt(len(r)), 4),
        "acf_abs": [rnd(v, 4) for v in sm.tsa.acf(r.abs(), nlags=20, fft=True)[1:]],
        "vr_daily": vr_d, "vr_daily_joint": vr_d_joint, "vr_weekly": vr_w, "vr_weekly_joint": vr_w_joint,
        "runs": runs_test(r.values), "n_daily": int(len(r)), "n_weekly": int(len(wk)), "n_monthly": int(len(mo))}

# ---------------------------------------------------------------- 5. spectral tests
res["spectral"] = {}
for key, L in lines.items():
    wk = np.log(L["px"].resample("W-FRI").last()).diff().dropna()
    res["spectral"][key] = {"monthly": fisher_g(np.log(1 + L["mret"]).values), "monthly_excess": fisher_g(L["mex"].values),
                            "weekly": fisher_g(wk.values)}

# ---------------------------------------------------------------- 6. price cycles (20% rule), longest sample only
pts, phases, ongoing = turning_points(lines["us"]["px"])
peaks = [pd.Timestamp(p["date"]) for p in pts if p["type"] == "peak"]
p2p = [(b - a).days / 30.44 for a, b in zip(peaks, peaks[1:])]
res["price_cycles"] = {"line": "us", "threshold": 0.20, "points": pts, "phases": phases, "ongoing": ongoing,
                       "bull_months": [p["months"] for p in phases if p["type"] == "bull"],
                       "bear_months": [p["months"] for p in phases if p["type"] == "bear"],
                       "peak_to_peak_months": [rnd(v, 1) for v in p2p],
                       "p2p_mean": rnd(np.mean(p2p), 1) if p2p else None,
                       "p2p_cv": rnd(np.std(p2p, ddof=1) / np.mean(p2p), 3) if len(p2p) > 1 else None}
for t in ("bull", "bear"):
    xs = [p for p in phases if p["type"] == t]
    res["price_cycles"][f"{t}_summary"] = {"n": len(xs), "mean_months": rnd(np.mean([p["months"] for p in xs]), 1) if xs else None,
                                           "cv_months": rnd(np.std([p["months"] for p in xs], ddof=1) / np.mean([p["months"] for p in xs]), 3) if len(xs) > 1 else None,
                                           "mean_change": rnd(np.mean([p["change"] for p in xs])) if xs else None}

# is the timing of the 20% swings more regular than chance? Stationary block bootstrap of the daily log returns
# (mean block 20 days keeps volatility clustering), same start price, same rule; compare the number of phases and the
# coefficient of variation of peak-to-peak lengths with the simulated distribution.
lr_us = lines["us"]["lr"]
sims_n, sims_cv = [], []
rng = np.random.default_rng(7)
for _ in range(2000):
    idx, n = [], len(lr_us)
    while len(idx) < n:
        start, ln = rng.integers(0, n), rng.geometric(1 / 20)
        idx.extend(((start + np.arange(ln)) % n).tolist())
    path = pd.Series(np.exp(np.cumsum(lr_us.values[np.array(idx[:n])])) * lines["us"]["px"].iloc[0], index=lr_us.index)
    p_, ph_, _ = turning_points(path)
    pk = [pd.Timestamp(x["date"]) for x in p_ if x["type"] == "peak"]
    d_ = [(b - a).days / 30.44 for a, b in zip(pk, pk[1:])]
    sims_n.append(len(ph_))
    if len(d_) > 1:
        sims_cv.append(np.std(d_, ddof=1) / np.mean(d_))
obs_cv = res["price_cycles"]["p2p_cv"]
res["price_cycles"]["bootstrap"] = {"n_sims": 2000, "mean_block_days": 20,
                                    "phases_obs": len(phases), "phases_sim_p10_p50_p90": [rnd(np.percentile(sims_n, q_), 1) for q_ in (10, 50, 90)],
                                    "cv_obs": obs_cv, "cv_sim_p10_p50_p90": [rnd(np.percentile(sims_cv, q_), 3) for q_ in (10, 50, 90)],
                                    "p_more_regular": rnd(float(np.mean(np.array(sims_cv) <= obs_cv)), 3)}

# robustness of the one significant serial-correlation result (HK daily Ljung-Box): by sub-period and without the
# 20 largest days
r_hk = lines["hk"]["lr"]
rob = []
for a, b in (("2020-09-11", "2022-12-31"), ("2023-01-01", None)):
    x = r_hk[a:b] if b else r_hk[a:]
    rob.append({"period": f"{a[:7]} 至 {(b or str(x.index[-1].date()))[:7]}", "n": int(len(x)), "ac1": rnd(sm.tsa.acf(x, nlags=2)[1], 3),
                "ac2": rnd(sm.tsa.acf(x, nlags=2)[2], 3), "p_lb10": rnd(acorr_ljungbox(x, lags=[10], return_df=True)["lb_pvalue"].iloc[0])})
x2 = r_hk.drop(r_hk.abs().sort_values().index[-20:])
rob.append({"period": "全样本，剔除最大 20 天", "n": int(len(x2)), "ac1": rnd(sm.tsa.acf(x2, nlags=2)[1], 3), "ac2": rnd(sm.tsa.acf(x2, nlags=2)[2], 3),
            "p_lb10": rnd(acorr_ljungbox(x2, lags=[10], return_df=True)["lb_pvalue"].iloc[0])})
res["dependence"]["hk"]["robustness"] = rob

# ---------------------------------------------------------------- 7. earnings drift (US line; reaction day from the 8-K time)
EARN_PATH = os.path.join(OUT, "earnings_days.json")  # written by analyze_ops.py
if os.path.exists(EARN_PATH):
    ed = json.load(open(EARN_PATH))
    out = {}
    for key, L in lines.items():
        ex = L["ex"]
        rows = []
        for e in ed:
            d0 = e.get(f"day0_{key}")
            if not d0 or pd.Timestamp(d0) < ex.index[0] + pd.Timedelta(days=30):
                continue
            rows.append({"period": e["period"], "day0": d0, "pre": window_car(ex, d0, -10, -1), "d0": window_car(ex, d0, 0, 0),
                         "post": window_car(ex, d0, 1, 10)})
        rows = [r for r in rows if None not in (r["pre"], r["d0"], r["post"])]
        if len(rows) >= 8:
            d0v = np.array([r["d0"] for r in rows])
            post = np.array([r["post"] for r in rows])
            m = sm.OLS(post, sm.add_constant(d0v)).fit()
            out[key] = {"n": len(rows), "pre": one_sample([r["pre"] for r in rows]), "day0_abs_mean": rnd(np.abs(d0v).mean(), 5),
                        "post": one_sample(list(post)),
                        "post_on_day0": {"slope": rnd(m.params[1], 3), "t": rnd(m.tvalues[1], 3), "p": rnd(m.pvalues[1]), "r2": rnd(m.rsquared, 3)},
                        "rows": [{k: (rnd(v, 5) if isinstance(v, float) else v) for k, v in r.items()} for r in rows]}
    res["earnings_drift"] = out

# ---------------------------------------------------------------- 8. business seasonality
q, _ = fl.sec_periods(os.path.join(RAW, "sec", "companyfacts.json"))
qr = pd.DataFrame(q).T
qr.index = pd.to_datetime(qr.index)
qr = qr[(qr.index >= "2017-01-01") & qr["revenue"].notna()][["revenue", "op_income", "net_income"]].astype(float)
qr = qr[qr.index.is_quarter_end]
qr["opm"] = qr["op_income"] / qr["revenue"]
qr["q"] = qr.index.quarter
qr["t"] = np.arange(len(qr))
covid = qr.index.isin(pd.to_datetime(["2020-03-31", "2020-06-30", "2022-06-30", "2022-12-31"]))
X = pd.get_dummies(qr["q"], prefix="q", drop_first=True).astype(float)
X["t"] = qr["t"]
X["covid"] = covid.astype(float)
m = sm.OLS(np.log(qr["revenue"]), sm.add_constant(X)).fit()
ftest = m.f_test("q_2 = 0, q_3 = 0, q_4 = 0")
seas = {f"Q{k}": rnd(math.exp(m.params.get(f"q_{k}", 0.0)) - 1, 4) for k in (1, 2, 3, 4)}
full_years = [y for y in sorted(set(qr.index.year)) if (qr.index.year == y).sum() == 4]
tab = qr[qr.index.year.isin(full_years)].pivot_table(index=qr.index.year[qr.index.year.isin(full_years)], columns="q", values="opm")
fr = stats.friedmanchisquare(*[tab[c].values for c in tab.columns])
kendall_w = fr.statistic / (len(tab) * (tab.shape[1] - 1))
res["business"] = {
    "quarters": [{"p": str(d.date()), "q": int(r.q), "revenue": rnd(r.revenue / 1e6, 1), "op_income": rnd(r.op_income / 1e6, 1),
                  "opm": rnd(r.opm, 4)} for d, r in qr.iterrows()],
    "revenue_seasonal": {"f": rnd(float(np.squeeze(ftest.fvalue)), 3), "p": rnd(float(ftest.pvalue)), "df": [int(ftest.df_num), int(ftest.df_denom)],
                         "factor_vs_q1": seas, "trend_q": rnd(m.params["t"], 5), "r2": rnd(m.rsquared, 3), "n": int(len(qr))},
    "opm_by_quarter": {"years": [int(y) for y in tab.index], "table": {f"Q{c}": [rnd(v, 4) for v in tab[c]] for c in tab.columns},
                       "mean": {f"Q{c}": rnd(tab[c].mean(), 4) for c in tab.columns},
                       "friedman": rnd(fr.statistic, 3), "p": rnd(fr.pvalue), "kendall_w": rnd(kendall_w, 3),
                       "rank_q_best": {f"Q{c}": int((tab.rank(axis=1, ascending=False)[c] == 1).sum()) for c in tab.columns}},
}

# same-store sales against national catering revenue; earnings reaction against same-store sales
OPS_PATH = os.path.join(OUT, "ops_kpis.json")
CAT_PATH = os.path.join(OUT, "catering_quarterly.json")  # written by analyze_ops.py from NBS / Eastmoney data
if os.path.exists(OPS_PATH):
    ops = pd.DataFrame(json.load(open(OPS_PATH))["quarters"])
    ops["p"] = pd.to_datetime(ops["p"])
    ops = ops.set_index("p").sort_index()
    if "adj_op_mn" in ops:  # adjusted operating margin (special items such as JV re-measurement gains removed)
        adj = (ops["adj_op_mn"] / (qr["revenue"].reindex(ops.index) / 1e6)).dropna()
        adj = adj[adj.index >= "2018-01-01"]
        at = pd.DataFrame({"y": adj.index.year, "q": adj.index.quarter, "v": adj.values})
        at = at[at.groupby("y")["q"].transform("count") == 4].pivot(index="y", columns="q", values="v")
        if len(at) >= 3:
            f3 = stats.friedmanchisquare(*[at[c].values for c in at.columns])
            res["business"]["adj_opm_by_quarter"] = {"years": [int(y) for y in at.index], "table": {f"Q{c}": [rnd(v, 4) for v in at[c]] for c in at.columns},
                                                     "mean": {f"Q{c}": rnd(at[c].mean(), 4) for c in at.columns},
                                                     "friedman": rnd(f3.statistic, 3), "p": rnd(f3.pvalue),
                                                     "kendall_w": rnd(f3.statistic / (len(at) * (at.shape[1] - 1)), 3),
                                                     "rank_q_best": {f"Q{c}": int((at.rank(axis=1, ascending=False)[c] == 1).sum()) for c in at.columns},
                                                     "rank_q_worst": {f"Q{c}": int((at.rank(axis=1, ascending=True)[c] == 1).sum()) for c in at.columns}}
    if "rm" in ops:  # restaurant margin by quarter (Friedman), calendar quarters only
        rm = ops.loc[ops.index >= "2018-01-01", "rm"].dropna()
        rmt = pd.DataFrame({"y": rm.index.year, "q": rm.index.quarter, "v": rm.values})
        rmt = rmt[rmt.groupby("y")["q"].transform("count") == 4].pivot(index="y", columns="q", values="v")
        if len(rmt) >= 3:
            f2 = stats.friedmanchisquare(*[rmt[c].values for c in rmt.columns])
            res["business"]["rm_by_quarter"] = {"years": [int(y) for y in rmt.index], "table": {f"Q{c}": [rnd(v, 4) for v in rmt[c]] for c in rmt.columns},
                                                "mean": {f"Q{c}": rnd(rmt[c].mean(), 4) for c in rmt.columns},
                                                "friedman": rnd(f2.statistic, 3), "p": rnd(f2.pvalue),
                                                "kendall_w": rnd(f2.statistic / (len(rmt) * (rmt.shape[1] - 1)), 3)}
    if os.path.exists(CAT_PATH) and "sssg" in ops:
        cq = json.load(open(CAT_PATH))
        out = {}
        for nm in ("retail", "catering"):
            cat = pd.Series(cq.get(nm, {}), dtype=float)
            cat.index = pd.to_datetime(cat.index)
            j = pd.concat([ops["sssg"].rename("sssg"), cat.rename("cat")], axis=1).dropna()
            j = j[j.index >= "2018-01-01"]
            if len(j) < 8:
                continue
            pr, sp = stats.pearsonr(j["sssg"], j["cat"]), stats.spearmanr(j["sssg"], j["cat"])
            ex_covid = j[~j.index.year.isin([2020, 2021, 2022, 2023])]
            pr2 = stats.pearsonr(ex_covid["sssg"], ex_covid["cat"]) if len(ex_covid) >= 6 else None
            gr = {}
            if nm == "retail" and len(j) >= 20:
                from statsmodels.tsa.stattools import grangercausalitytests
                for lag in (1, 2):
                    g1 = grangercausalitytests(j[["sssg", "cat"]].values, maxlag=[lag])[lag][0]["ssr_ftest"]
                    g2 = grangercausalitytests(j[["cat", "sssg"]].values, maxlag=[lag])[lag][0]["ssr_ftest"]
                    gr[f"lag{lag}"] = {"cat_to_sssg_p": rnd(g1[1]), "sssg_to_cat_p": rnd(g2[1])}
            beta = sm.OLS(j["sssg"], sm.add_constant(j["cat"])).fit(cov_type="HC1")
            out[nm] = {"n": int(len(j)), "first": str(j.index[0].date()), "last": str(j.index[-1].date()),
                       "pearson": rnd(pr.statistic, 3), "p_pearson": rnd(pr.pvalue), "spearman": rnd(sp.statistic, 3), "p_spearman": rnd(sp.pvalue),
                       "slope": rnd(beta.params.iloc[1], 3), "slope_t": rnd(beta.tvalues.iloc[1], 2),
                       "pearson_ex_2020_2023": rnd(pr2.statistic, 3) if pr2 else None, "p_ex_2020_2023": rnd(pr2.pvalue) if pr2 else None,
                       "n_ex": int(len(ex_covid)), "granger": gr,
                       "series": {"p": [str(d.date()) for d in j.index], "sssg": [rnd(v, 4) for v in j["sssg"]], "cat": [rnd(v, 4) for v in j["cat"]]}}
        res["business"]["sssg_vs_consumption"] = out
        # persistence of same-store sales growth (is there a cycle in the company's own comps?)
        ss = ops.loc[ops.index >= "2018-01-01", "sssg"].dropna()
        lb = acorr_ljungbox(ss, lags=[4], return_df=True)
        res["business"]["sssg_persistence"] = {"n": int(len(ss)), "ac1": rnd(ss.autocorr(1), 3), "ac4": rnd(ss.autocorr(4), 3),
                                               "lb4": rnd(lb["lb_stat"].iloc[0], 2), "p_lb4": rnd(lb["lb_pvalue"].iloc[0])}
    if "earnings_drift" in res and "us" in res["earnings_drift"] and "sssg" in ops:
        rows = pd.DataFrame(res["earnings_drift"]["us"]["rows"])
        ed = {e["period"]: e for e in json.load(open(EARN_PATH))}
        rows["sssg"] = [ops["sssg"].get(pd.Timestamp(p)) for p in rows["period"]]
        rows["d_sssg"] = [ops["sssg"].get(pd.Timestamp(p)) - ops["sssg"].shift(1).get(pd.Timestamp(p))
                          if pd.Timestamp(p) in ops.index and not pd.isna(ops["sssg"].shift(1).get(pd.Timestamp(p))) else None for p in rows["period"]]
        out = {}
        for col in ("sssg", "d_sssg"):
            jj = rows[["d0", col]].dropna()
            if len(jj) >= 10:
                mm = sm.OLS(jj["d0"].astype(float), sm.add_constant(jj[col].astype(float))).fit(cov_type="HC1")
                out[col] = {"n": int(len(jj)), "slope": rnd(mm.params.iloc[1], 4), "t": rnd(mm.tvalues.iloc[1], 3), "p": rnd(mm.pvalues.iloc[1]),
                            "r2": rnd(mm.rsquared, 3)}
        res["business"]["reaction_vs_sssg"] = out

# ---------------------------------------------------------------- 9. multiple testing across the return-pattern tests
fam = []
for key in lines:
    for kind in ("raw", "excess"):
        fam.append((f"{key} 月份效应（{kind}，置换 F）", res["month"][key][kind]["tests"]["p_perm"]))
        fam.append((f"{key} 星期效应（{kind}，Kruskal-Wallis）", res["weekday"][key][kind]["tests"]["p_kw"]))
        fam.append((f"{key} 月末月初效应（{kind}）", res["tom"][key][kind]["p"]))
        fam.append((f"{key} 冬半年/夏半年（{kind}）", res["month"][key][kind]["halloween"]["p"]))
    for nm in ("cny", "golden_week"):
        for w in ("pre", "post"):
            p = res["holidays"][key][nm][w].get("p_t")
            if p is not None:
                fam.append((f"{key} {nm} {w}", p))
    dep = res["dependence"][key]
    fam.append((f"{key} Ljung-Box 日度 Q(10)", dep["lb_daily"][1]["p"]))
    fam.append((f"{key} Ljung-Box 月度 Q(12)", dep["lb_monthly"][1]["p"]))
    fam.append((f"{key} 方差比（日度，联合）", dep["vr_daily_joint"].get("p_joint_bonferroni")))
    fam.append((f"{key} 方差比（周度，联合）", dep["vr_weekly_joint"].get("p_joint_bonferroni")))
    fam.append((f"{key} 游程检验", dep["runs"]["p"]))
    fam.append((f"{key} Fisher g（月度）", res["spectral"][key]["monthly"]["p_g"]))
    fam.append((f"{key} Fisher g（周度）", res["spectral"][key]["weekly"]["p_g"]))
for key, v in (res.get("earnings_drift") or {}).items():
    fam.append((f"{key} 财报前漂移", v["pre"].get("p_t")))
    fam.append((f"{key} 财报后漂移", v["post"].get("p_t")))
fam.append(("us 20% 涨跌波段的规律性（自助法）", res["price_cycles"]["bootstrap"]["p_more_regular"]))
fam = [(n, p) for n, p in fam if p is not None]
rej, qv, _, _ = multipletests([p for _, p in fam], alpha=0.10, method="fdr_bh")
res["fdr"] = {"alpha": 0.10, "n_tests": len(fam), "n_raw_p_below_005": int(sum(p < 0.05 for _, p in fam)),
              "tests": [{"name": n, "p": rnd(p), "q": rnd(q_), "reject": bool(r)} for (n, p), q_, r in zip(fam, qv, rej)]}

os.makedirs(OUT, exist_ok=True)
ml.dump_json(res, os.path.join(OUT, "cycles.json"))
show = {k: res[k] for k in ("samples", "fdr")}
print(json.dumps(ml.clean(show), indent=1, ensure_ascii=False)[:6000])
for key in lines:
    for kind in ("raw", "excess"):
        print(key, kind, "month tests", res["month"][key][kind]["tests"], "MDE", res["month"][key][kind]["mde_one_month"])
    print(key, "weekday", res["weekday"][key]["raw"]["tests"])
    print(key, "dependence", {k: res["dependence"][key][k] for k in ("lb_daily", "lb_monthly", "arch_lm", "vr_daily", "vr_weekly", "runs")})
    print(key, "spectral monthly", {k: res["spectral"][key]["monthly"][k] for k in ("g", "p_g", "peak_period", "p_bartlett")})
print("business", json.dumps(ml.clean({k: v for k, v in res["business"].items() if k != "quarters"}), ensure_ascii=False)[:3000])
print("price cycles", res["price_cycles"]["phases"], res["price_cycles"]["ongoing"])
