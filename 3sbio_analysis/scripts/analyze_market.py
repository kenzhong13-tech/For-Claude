"""Volatility, market/sector betas, peer comparison and event study for 3SBio (1530.HK).

Benchmarks: the Hang Seng Index (market) and an innovative-drug sector index. Reads data/raw/ and writes
data/processed/market_analysis.json.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm
from arch import arch_model
from scipy import stats

ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
TD = 252
START = "2019-01-02"
# HK innovative-drug peers used for the equal-weight sector index and the comparison tables
PEERS = {"1276": "恒瑞医药", "6160": "百济神州", "1801": "信达生物", "9926": "康方生物", "3692": "翰森制药",
         "1093": "石药集团", "1177": "中国生物制药", "6990": "科伦博泰", "1877": "君实生物", "9995": "荣昌生物",
         "2096": "先声药业", "0013": "和黄医药", "9688": "再鼎医药", "9606": "映恩生物", "2162": "康诺亚"}
COMPARE = ["1530", "1276", "6160", "1801", "9926", "3692", "1093", "1177", "6990"]
NAMES = {"1530": "三生制药", **PEERS}


def load_yahoo(name, col="Adj Close"):
    df = pd.read_csv(os.path.join(RAW, f"{name}.csv"), index_col=0, parse_dates=True)
    df = df[pd.to_numeric(df["Close"], errors="coerce").notna()]
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    return s[~s.index.duplicated()].dropna()


def yname(code):
    return f"{int(code):04d}_HK"


def max_drawdown(series):
    peak = series.cummax()
    dd = series / peak - 1
    trough = dd.idxmin()
    return float(dd.min()), str(series.loc[:trough].idxmax().date()), str(trough.date()), dd


def ols(y, x):
    return sm.OLS(y, sm.add_constant(x)).fit()


def sim(y, x, scale=TD):
    m = ols(y, x)
    mh = sm.OLS(y, sm.add_constant(x)).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    beta = m.params.iloc[1]
    resid_var = m.resid.var(ddof=2)
    out = {"alpha_ann": float(m.params.iloc[0] * scale), "alpha_t": float(m.tvalues.iloc[0]),
           "beta": float(beta), "beta_se": float(m.bse.iloc[1]), "beta_se_hac": float(mh.bse.iloc[1]),
           "beta_ci95": [float(beta - 1.96 * m.bse.iloc[1]), float(beta + 1.96 * m.bse.iloc[1])],
           "r2": float(m.rsquared), "corr": float(np.corrcoef(y, x)[0, 1]),
           "total_var_ann": float(y.var() * scale), "systematic_var_ann": float(beta ** 2 * x.var() * scale),
           "resid_var_ann": float(resid_var * scale), "resid_vol_ann": float(np.sqrt(resid_var * scale)),
           "blume_beta": float(0.67 * beta + 0.33), "n": int(len(y)), "alpha_daily": float(m.params.iloc[0])}
    out["systematic_share"] = out["systematic_var_ann"] / out["total_var_ann"]
    return out


def risk_stats(r, lr, prices, rf_d):
    q95, q99 = np.percentile(r, 5), np.percentile(r, 1)
    mdd, pk, tr, _ = max_drawdown(prices)
    excess = r - rf_d
    return {
        "total_return": float(prices.iloc[-1] / prices.iloc[0] - 1),
        "ann_return_geo": float((prices.iloc[-1] / prices.iloc[0]) ** (TD / len(r)) - 1),
        "ann_vol": float(lr.std() * np.sqrt(TD)),
        "downside_dev_ann": float(np.sqrt((np.minimum(r, 0) ** 2).mean()) * np.sqrt(TD)),
        "skew": float(stats.skew(r)), "excess_kurtosis": float(stats.kurtosis(r)),
        "var95_hist": float(-q95), "var99_hist": float(-q99),
        "cvar95_hist": float(-r[r <= q95].mean()), "cvar99_hist": float(-r[r <= q99].mean()),
        "max_up_day": float(r.max()), "max_up_date": str(r.idxmax().date()),
        "max_down_day": float(r.min()), "max_down_date": str(r.idxmin().date()),
        "days_abs_gt_5pct": int((r.abs() > 0.05).sum()), "days_abs_gt_10pct": int((r.abs() > 0.10).sum()),
        "max_drawdown": mdd, "mdd_peak": pk, "mdd_trough": tr,
        "current_drawdown": float(prices.iloc[-1] / prices.cummax().iloc[-1] - 1),
        "sharpe": float(excess.mean() / r.std() * np.sqrt(TD)),
        "sortino": float(excess.mean() * TD / (np.sqrt((np.minimum(r, 0) ** 2).mean()) * np.sqrt(TD))),
    }


def garch(series):
    fit = arch_model(series * 100, vol="GARCH", p=1, q=1, dist="t", mean="Constant").fit(disp="off")
    a, b, om = float(fit.params["alpha[1]"]), float(fit.params["beta[1]"]), float(fit.params["omega"])
    pers = a + b
    fc = fit.forecast(horizon=21, reindex=False).variance.values[-1]
    return fit, {"alpha": a, "beta": b, "persistence": pers,
                 "half_life_days": float(np.log(0.5) / np.log(pers)) if pers < 1 else None,
                 "long_run_vol_ann": float(np.sqrt(om / (1 - pers) * TD) / 100) if pers < 1 else None,
                 "current_cond_vol_ann": float(fit.conditional_volatility.iloc[-1] * np.sqrt(TD) / 100),
                 "forecast_21d_vol_ann": float(np.sqrt(fc.mean() * TD) / 100), "nu": float(fit.params.get("nu", np.nan))}


# ---------- data ----------
hsi_all = load_yahoo("IDX_HSI")
END_DATE = str(hsi_all.index[-1].date())  # last day with a complete index close
cal = hsi_all.index[(hsi_all.index >= START) & (hsi_all.index <= END_DATE)]
sb = load_yahoo("1530_HK")
peer_px = pd.DataFrame({c: load_yahoo(yname(c)) for c in PEERS}).reindex(cal)
peer_ret = peer_px.pct_change(fill_method=None)
n_avail = peer_ret.notna().sum(axis=1)
sec_ret = peer_ret.mean(axis=1, skipna=True).where(n_avail >= 4)
px = pd.DataFrame({"sb": sb.reindex(cal), "hsi": hsi_all.reindex(cal)}).dropna()
ret = px.pct_change().dropna()
ret["sec"] = sec_ret.reindex(ret.index)
ret = ret.dropna()
px = px.loc[[px.index[0]] + list(ret.index)]
px["sec"] = 100 * (1 + ret["sec"]).cumprod().reindex(px.index).fillna(1.0)
px.loc[px.index[0], "sec"] = 100.0
logret = np.log(px).diff().dropna()
etf = load_yahoo("3069_HK").reindex(ret.index).pct_change(fill_method=None)
irx = load_yahoo("IDX_IRX", "Close").reindex(ret.index).ffill().bfill() / 100.0
rf_daily = (1 + irx) ** (1 / TD) - 1
ex = ret.sub(rf_daily, axis=0)
res = {"meta": {"start": str(px.index[0].date()), "end": str(px.index[-1].date()), "n_days": int(len(ret)),
                "rf_avg": float(irx.mean()), "last_close_sb": float(px["sb"].iloc[-1]),
                "last_raw_close_sb": float(load_yahoo("1530_HK", "Close").iloc[-1]),
                "last_raw_date_sb": str(load_yahoo("1530_HK", "Close").index[-1].date()),
                "last_close_hsi": float(px["hsi"].iloc[-1]), "sector_names": [PEERS[c] for c in PEERS],
                "sector_min_names": 4}}

res["stats"] = {k: risk_stats(ret[k], logret[k], px[k], rf_daily) for k in ("sb", "hsi", "sec")}

# ---------- single-index models ----------
res["sim_hsi"] = sim(ex["sb"], ex["hsi"])
res["sim_sec"] = sim(ex["sb"], ex["sec"])
res["sec_on_hsi"] = sim(ex["sec"], ex["hsi"])
wk = px.resample("W-FRI").last().pct_change().dropna()
rfw = irx.resample("W-FRI").last().reindex(wk.index).ffill() / 52
res["sim_hsi_weekly"] = sim(wk["sb"] - rfw, wk["hsi"] - rfw, scale=52)
res["sim_sec_weekly"] = sim(wk["sb"] - rfw, wk["sec"] - rfw, scale=52)
mo = px.resample("ME").last().pct_change().dropna()
rfm = irx.resample("ME").last().reindex(mo.index).ffill() / 12
res["sim_hsi_monthly"] = sim(mo["sb"] - rfm, mo["hsi"] - rfm, scale=12)
dim = pd.concat([ex["sb"], ex["hsi"].shift(1), ex["hsi"], ex["hsi"].shift(-1)], axis=1).dropna()
res["dimson_beta_hsi"] = float(ols(dim.iloc[:, 0], dim.iloc[:, 1:]).params.iloc[1:].sum())
up, dn = ex["hsi"] > 0, ex["hsi"] < 0
res["up_beta_hsi"] = float(ols(ex["sb"][up], ex["hsi"][up]).params.iloc[1])
res["down_beta_hsi"] = float(ols(ex["sb"][dn], ex["hsi"][dn]).params.iloc[1])
ups, dns = ex["sec"] > 0, ex["sec"] < 0
res["up_beta_sec"] = float(ols(ex["sb"][ups], ex["sec"][ups]).params.iloc[1])
res["down_beta_sec"] = float(ols(ex["sb"][dns], ex["sec"][dns]).params.iloc[1])
res["capm"] = {"rf_latest": float(irx.iloc[-1]), "required_return_6pct_erp": float(irx.iloc[-1] + res["sim_hsi"]["beta"] * 0.06)}


# ---------- two-factor model: market + sector (orthogonalised) ----------
def two_factor(e, since=None):
    d = e if since is None else e[e.index >= since]
    f_sec = ols(d["sec"], d["hsi"]).resid.rename("sec_o")
    X = pd.concat([d["hsi"], f_sec], axis=1)
    m1 = ols(d["sb"], d[["hsi"]])
    m2 = ols(d["sb"], X)
    return m2, {"since": str(d.index[0].date()), "n": int(len(d)), "r2_hsi": float(m1.rsquared),
                "r2_two": float(m2.rsquared), "beta_hsi": float(m2.params["hsi"]), "beta_sec_o": float(m2.params["sec_o"]),
                "t_sec_o": float(m2.tvalues["sec_o"]), "r2_sec_only": float(ols(d["sb"], d[["sec"]]).rsquared)}


m_two, res["two_factor"] = two_factor(ex)
res["two_factor_2025"] = two_factor(ex, "2025-01-01")[1]
res["two_factor_2023"] = two_factor(ex, "2023-01-01")[1]
etf_j = pd.concat([ret["sb"], etf.rename("etf"), ret["sec"]], axis=1).dropna()
res["etf_check"] = {"name": "3069.HK", "since": str(etf_j.index[0].date()), "corr_sec": float(etf_j[["etf", "sec"]].corr().iloc[0, 1]),
                    "beta_sb_on_etf": float(ols(etf_j["sb"], etf_j["etf"]).params.iloc[1]),
                    "r2_sb_on_etf": float(ols(etf_j["sb"], etf_j["etf"]).rsquared)}

# ---------- calendar years ----------
years = []
for y in sorted(set(ret.index.year)):
    sel = ret.index.year == y
    p_y = px[px.index.year == y]
    prev = px[px.index.year < y]
    base = prev.iloc[-1] if len(prev) else p_y.iloc[0]
    e_y = ex[sel]
    s_h, s_s = sim(e_y["sb"], e_y["hsi"]), sim(e_y["sb"], e_y["sec"])
    years.append({"year": int(y), "n": int(sel.sum()),
                  **{f"ret_{k}": float(p_y[k].iloc[-1] / base[k] - 1) for k in ("sb", "hsi", "sec")},
                  **{f"vol_{k}": float(logret[k][logret.index.year == y].std() * np.sqrt(TD)) for k in ("sb", "hsi", "sec")},
                  "beta_hsi": s_h["beta"], "r2_hsi": s_h["r2"], "beta_sec": s_s["beta"], "r2_sec": s_s["r2"],
                  "mdd_sb": max_drawdown(p_y["sb"])[0]})
res["by_year"] = years

# ---------- rolling ----------
roll = pd.DataFrame(index=logret.index)
for k in ("sb", "hsi", "sec"):
    roll[f"vol63_{k}"] = logret[k].rolling(63).std() * np.sqrt(TD)
roll["beta252_hsi"] = ex["sb"].rolling(252).cov(ex["hsi"]) / ex["hsi"].rolling(252).var()
roll["beta252_sec"] = ex["sb"].rolling(252).cov(ex["sec"]) / ex["sec"].rolling(252).var()
roll["beta63_sec"] = ex["sb"].rolling(63).cov(ex["sec"]) / ex["sec"].rolling(63).var()
roll["corr63_sec"] = ex["sb"].rolling(63).corr(ex["sec"])
roll["corr63_hsi"] = ex["sb"].rolling(63).corr(ex["hsi"])
g_sb, res_g_sb = garch(logret["sb"])
res["garch"] = {"sb": res_g_sb, "sec": garch(logret["sec"])[1], "hsi": garch(logret["hsi"])[1]}
roll["garch_sb"] = g_sb.conditional_volatility / 100 * np.sqrt(TD)
sq = (ret["sb"] - ret["sb"].mean()) ** 2
res["top10_days_var_share"] = float(sq.sort_values(ascending=False).iloc[:10].sum() / sq.sum())

# ---------- peers: volatility and returns inside the innovative-drug sector ----------
def period_ret(p, a, b):
    s = p.dropna()
    s0, s1 = s[s.index <= a], s[s.index <= b]
    if not len(s0) or not len(s1) or s0.index[-1] < s.index[0]:
        return None
    return float(s1.iloc[-1] / s0.iloc[-1] - 1)


peers_out = []
all_px = peer_px.copy()
all_px["1530"] = sb.reindex(cal)
for c in ["1530"] + list(PEERS):
    p = all_px[c].dropna()
    r_c = p.pct_change().dropna()
    loo = peer_ret.drop(columns=[c], errors="ignore")
    sec_loo = loo.mean(axis=1).where(loo.notna().sum(axis=1) >= 5)
    j = pd.concat([r_c.rename("y"), ret["hsi"].rename("hsi"), sec_loo.rename("sec")], axis=1).dropna()
    j23 = j[j.index >= "2023-01-01"]
    j1y = j.iloc[-252:]
    first = str(p.index[0].date())
    row = {"code": c, "name": NAMES[c], "first": first,
           "vol_1y": float(np.log(1 + j1y["y"]).std() * np.sqrt(TD)),
           "vol_since2023": float(np.log(1 + j23["y"]).std() * np.sqrt(TD)) if len(j23) > 60 else None,
           "beta_hsi": float(ols(j23["y"], j23["hsi"]).params.iloc[1]) if len(j23) > 60 else None,
           "beta_sec": float(ols(j23["y"], j23["sec"]).params.iloc[1]) if len(j23) > 60 else None,
           "corr_sec": float(j23[["y", "sec"]].corr().iloc[0, 1]) if len(j23) > 60 else None,
           "r2_sec": float(ols(j23["y"], j23["sec"]).rsquared) if len(j23) > 60 else None,
           "beta_sec_1y": float(ols(j1y["y"], j1y["sec"]).params.iloc[1]),
           "ret_2025": period_ret(p, "2024-12-31", "2025-12-31") if p.index[0] <= pd.Timestamp("2025-01-02") else None,
           "ret_2026ytd": period_ret(p, "2025-12-31", END_DATE),
           "mdd_since2025": max_drawdown(p[p.index >= "2025-01-01"])[0],
           "dd_from_high": float(p.iloc[-1] / p[p.index >= "2025-01-01"].max() - 1),
           "high_date": str(p[p.index >= "2025-01-01"].idxmax().date()),
           "last": float(p.iloc[-1])}
    peers_out.append(row)
res["peers"] = peers_out
res["sector_index_note"] = {"n_names_last": int(n_avail.iloc[-1]), "n_names_start": int(n_avail.iloc[1])}

# ---------- event study (market model with HSI and the orthogonalised sector factor) ----------
EV_PATH = os.path.join(ROOT, "data", "events.json")
EVENTS = json.load(open(EV_PATH, encoding="utf-8")) if os.path.exists(EV_PATH) else []
f_sec_full = ols(ex["sec"], ex["hsi"]).resid
fit_hat = m_two.params["const"] + m_two.params["hsi"] * ex["hsi"] + m_two.params["sec_o"] * f_sec_full
abn = ex["sb"] - fit_hat
resid_sd = float(m_two.resid.std(ddof=3))
abn_hsi = ex["sb"] - (res["sim_hsi"]["alpha_daily"] + res["sim_hsi"]["beta"] * ex["hsi"])
dates = ret.index
ev_out = []
for ev in EVENTS:
    pos = dates.searchsorted(pd.Timestamp(ev["date"]))
    if pos >= len(dates):
        continue
    row = {**ev, "day0": str(dates[pos].date()), "ret_sb": float(ret["sb"].iloc[pos]), "ret_hsi": float(ret["hsi"].iloc[pos]),
           "ret_sec": float(ret["sec"].iloc[pos]), "ar": float(abn.iloc[pos]), "ar_t": float(abn.iloc[pos] / resid_sd),
           "ar_hsi_only": float(abn_hsi.iloc[pos])}
    lo, hi = max(pos - 1, 0), min(pos + 1, len(dates) - 1)
    row["car_m1_p1"] = float(abn.iloc[lo:hi + 1].sum())
    row["car_0_p5"] = float(abn.iloc[pos:min(pos + 5, len(dates) - 1) + 1].sum())
    row["price_day0"] = float(px["sb"].loc[dates[pos]])
    ev_out.append(row)
res["events"] = ev_out
res["resid_sd_daily"] = resid_sd
top = abn.abs().sort_values(ascending=False).iloc[:40]
res["top_abnormal_days"] = [{"date": str(d.date()), "ret_sb": float(ret["sb"][d]), "ret_hsi": float(ret["hsi"][d]),
                             "ret_sec": float(ret["sec"][d]), "ar": float(abn[d]), "ar_t": float(abn[d] / resid_sd)}
                            for d in top.index]
top_sec = ret["sec"].abs().sort_values(ascending=False).iloc[:15]
res["top_sector_days"] = [{"date": str(d.date()), "ret_sec": float(ret["sec"][d]), "ret_sb": float(ret["sb"][d]),
                           "ret_hsi": float(ret["hsi"][d])} for d in top_sec.index]
earn = [e["day0"] for e in ev_out if e.get("category") in ("earnings",)]
mask = ret.index.strftime("%Y-%m-%d").isin(earn)
res["earnings_abs_move_avg"] = float(ret["sb"][mask].abs().mean()) if mask.any() else None
res["normal_abs_move_avg"] = float(ret["sb"][~mask].abs().mean())
# cumulative abnormal return by calendar year and over key windows (two-factor model)
res["car_by_year"] = {str(y): float(abn[abn.index.year == y].sum()) for y in sorted(set(abn.index.year))}
def window(a, b):
    w = ret.loc[a:b]
    return {"from": a, "to": b, "ret_sb": float((1 + w["sb"]).prod() - 1), "ret_sec": float((1 + w["sec"]).prod() - 1),
            "ret_hsi": float((1 + w["hsi"]).prod() - 1), "car": float(abn.loc[a:b].sum())}
res["windows"] = {"deal_runup": window("2025-05-16", "2025-05-21"), "peak_to_now": window("2025-09-10", END_DATE),
                  "ytd_2026": window("2026-01-02", END_DATE), "y2025": window("2025-01-02", "2025-12-31")}

bins = np.arange(-0.30, 0.3001, 0.02)
res["hist"] = {"bins": [float(b) for b in bins],
               **{k: np.histogram(ret[k].clip(-0.299, 0.299), bins=bins)[0].tolist() for k in ("sb", "sec", "hsi")}}
dd = {k: max_drawdown(px[k])[3] for k in ("sb", "hsi", "sec")}
series = pd.DataFrame({"sb": px["sb"], "sb_idx": px["sb"] / px["sb"].iloc[0] * 100, "hsi_idx": px["hsi"] / px["hsi"].iloc[0] * 100,
                       "sec_idx": px["sec"] / px["sec"].iloc[0] * 100, "dd_sb": dd["sb"], "dd_hsi": dd["hsi"], "dd_sec": dd["sec"]}).join(roll)
series.index = series.index.strftime("%Y-%m-%d")
res["series"] = {"date": series.index.tolist(),
                 **{c: [None if pd.isna(v) else round(float(v), 5) for v in series[c]] for c in series.columns}}
res["scatter"] = {"x": [round(float(v), 5) for v in ex["sec"]], "y": [round(float(v), 5) for v in ex["sb"]],
                  "dates": ex.index.strftime("%Y-%m-%d").tolist()}
# rebased performance since the end of 2024 for the peer chart
base_day = all_px.index[all_px.index <= "2024-12-31"][-1]
reb = {}
for c in COMPARE:
    p = all_px[c].dropna()
    p = p[p.index >= base_day]
    if len(p):
        reb[c] = (p / p.iloc[0] * 100).round(2)
sec_lvl = px["sec"][px.index >= base_day]
reb["sec"] = (sec_lvl / sec_lvl.iloc[0] * 100).round(2)
h_lvl = px["hsi"][px.index >= base_day]
reb["hsi"] = (h_lvl / h_lvl.iloc[0] * 100).round(2)
rb = pd.DataFrame(reb)
rb.index = rb.index.strftime("%Y-%m-%d")
res["rebased_2025"] = {"date": rb.index.tolist(), **{c: [None if pd.isna(v) else float(v) for v in rb[c]] for c in rb.columns}}

os.makedirs(OUT, exist_ok=True)
json.dump(res, open(os.path.join(OUT, "market_analysis.json"), "w"), ensure_ascii=False, indent=1)
skip = ("series", "scatter", "hist", "events", "top_abnormal_days", "peers", "rebased_2025", "by_year", "top_sector_days")
print(json.dumps({k: v for k, v in res.items() if k not in skip}, indent=1, ensure_ascii=False))
if "--events" in sys.argv:
    for e in ev_out:
        print(e["day0"], e["category"], f"{e['ret_sb']:+.1%} hsi {e['ret_hsi']:+.1%} sec {e['ret_sec']:+.1%} AR {e['ar']:+.1%} t={e['ar_t']:.1f}", e["title"])
    print("--- top abnormal days")
    for t in res["top_abnormal_days"]:
        print(t["date"], f"{t['ret_sb']:+.1%} hsi {t['ret_hsi']:+.1%} sec {t['ret_sec']:+.1%} AR {t['ar']:+.1%} t={t['ar_t']:.1f}")
    print("--- top sector days")
    for t in res["top_sector_days"]:
        print(t["date"], f"sec {t['ret_sec']:+.1%} sb {t['ret_sb']:+.1%} hsi {t['ret_hsi']:+.1%}")
    for p in res["peers"]:
        print(p)
    for y in res["by_year"]:
        print(y)
