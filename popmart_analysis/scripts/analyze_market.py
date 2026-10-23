"""Volatility, Single-Index-Model and event-study analysis of Pop Mart (9992.HK) against the Hang Seng Index.

Reads popmart_analysis/data/raw/*.csv (Yahoo daily) and writes data/processed/market_analysis.json.
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
END_DATE = "2026-10-20"  # 2026-10-21 row from Yahoo is incomplete


def load_yahoo(name, col="Adj Close"):
    df = pd.read_csv(os.path.join(RAW, f"{name}.csv"), index_col=0, parse_dates=True)
    df = df[pd.to_numeric(df["Close"], errors="coerce").notna()]
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    return s[~s.index.duplicated()]


pm, hsi = load_yahoo("9992_HK"), load_yahoo("IDX_HSI")
px = pd.DataFrame({"pm": pm, "hsi": hsi}).dropna()
px = px[px.index <= END_DATE]
ret = px.pct_change().dropna()
logret = np.log(px).diff().dropna()
irx = load_yahoo("IDX_IRX", "Close").reindex(ret.index).ffill().bfill() / 100.0
rf_annual = irx
rf_daily = (1 + rf_annual) ** (1 / TD) - 1
ex = ret.sub(rf_daily, axis=0)
res = {"meta": {"start": str(px.index[0].date()), "end": str(px.index[-1].date()), "n_days": int(len(ret)),
                "rf_source": "13-week US T-bill (^IRX), HKD is pegged to USD", "rf_avg": float(rf_annual.mean()),
                "last_close_pm": float(px["pm"].iloc[-1]), "last_close_hsi": float(px["hsi"].iloc[-1]),
                "last_date": str(px.index[-1].date())}}


def max_drawdown(series):
    peak = series.cummax()
    dd = series / peak - 1
    trough = dd.idxmin()
    return float(dd.min()), str(series.loc[:trough].idxmax().date()), str(trough.date()), dd


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


res["stats"] = {"pm": risk_stats(ret["pm"], logret["pm"], px["pm"], rf_daily),
                "hsi": risk_stats(ret["hsi"], logret["hsi"], px["hsi"], rf_daily)}
res["stats"]["vol_ratio"] = res["stats"]["pm"]["ann_vol"] / res["stats"]["hsi"]["ann_vol"]


def sim(y, x, scale=TD):
    X = sm.add_constant(x)
    m = sm.OLS(y, X).fit()
    mh = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
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


res["sim_daily"] = sim(ex["pm"], ex["hsi"])
wk = px.resample("W-FRI").last().pct_change().dropna()
rfw = rf_annual.resample("W-FRI").last().reindex(wk.index).ffill() / 52
res["sim_weekly"] = sim(wk["pm"] - rfw, wk["hsi"] - rfw, scale=52)
mo = px.resample("ME").last().pct_change().dropna()
rfm = rf_annual.resample("ME").last().reindex(mo.index).ffill() / 12
res["sim_monthly"] = sim(mo["pm"] - rfm, mo["hsi"] - rfm, scale=12)
dim = pd.concat([ex["pm"], ex["hsi"].shift(1), ex["hsi"], ex["hsi"].shift(-1)], axis=1).dropna()
res["dimson_beta"] = float(sm.OLS(dim.iloc[:, 0], sm.add_constant(dim.iloc[:, 1:])).fit().params.iloc[1:].sum())
up, dn = ex["hsi"] > 0, ex["hsi"] < 0
res["up_beta"] = float(sm.OLS(ex["pm"][up], sm.add_constant(ex["hsi"][up])).fit().params.iloc[1])
res["down_beta"] = float(sm.OLS(ex["pm"][dn], sm.add_constant(ex["hsi"][dn])).fit().params.iloc[1])
res["up_capture"] = float(ret["pm"][ret["hsi"] > 0].mean() / ret["hsi"][ret["hsi"] > 0].mean())
res["down_capture"] = float(ret["pm"][ret["hsi"] < 0].mean() / ret["hsi"][ret["hsi"] < 0].mean())
active = ret["pm"] - ret["hsi"]
res["tracking_error"] = float(active.std() * np.sqrt(TD))
res["information_ratio"] = float(active.mean() * TD / res["tracking_error"])
res["treynor"] = float(ex["pm"].mean() * TD / res["sim_daily"]["beta"])
res["capm"] = {"rf_latest": float(rf_annual.iloc[-1]),
               "required_return_6pct_erp": float(rf_annual.iloc[-1] + res["sim_daily"]["beta"] * 0.06)}

# calendar-year breakdown
years = []
for y in sorted(set(ret.index.year)):
    r_y, lr_y, ex_y = ret[ret.index.year == y], logret[logret.index.year == y], ex[ex.index.year == y]
    p_y = px[px.index.year == y]
    prev = px[px.index.year < y]
    base = prev.iloc[-1] if len(prev) else p_y.iloc[0]
    s_y = sim(ex_y["pm"], ex_y["hsi"])
    years.append({"year": int(y), "n": int(len(r_y)),
                  "ret_pm": float(p_y["pm"].iloc[-1] / base["pm"] - 1), "ret_hsi": float(p_y["hsi"].iloc[-1] / base["hsi"] - 1),
                  "vol_pm": float(lr_y["pm"].std() * np.sqrt(TD)), "vol_hsi": float(lr_y["hsi"].std() * np.sqrt(TD)),
                  "beta": s_y["beta"], "r2": s_y["r2"], "corr": s_y["corr"],
                  "mdd_pm": max_drawdown(p_y["pm"])[0]})
res["by_year"] = years

# rolling statistics
W = 63
roll = pd.DataFrame(index=logret.index)
for k in ("pm", "hsi"):
    roll[f"vol21_{k}"] = logret[k].rolling(21).std() * np.sqrt(TD)
    roll[f"vol63_{k}"] = logret[k].rolling(W).std() * np.sqrt(TD)
roll["beta63"] = ex["pm"].rolling(W).cov(ex["hsi"]) / ex["hsi"].rolling(W).var()
roll["beta252"] = ex["pm"].rolling(252).cov(ex["hsi"]) / ex["hsi"].rolling(252).var()
roll["corr63"] = ex["pm"].rolling(W).corr(ex["hsi"])

# GARCH(1,1)-t
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


g_pm, res_g_pm = garch(logret["pm"])
_, res_g_hsi = garch(logret["hsi"])
res["garch"] = {"pm": res_g_pm, "hsi": res_g_hsi}
roll["garch_pm"] = g_pm.conditional_volatility / 100 * np.sqrt(TD)

sq = (ret["pm"] - ret["pm"].mean()) ** 2
res["top10_days_var_share"] = float(sq.sort_values(ascending=False).iloc[:10].sum() / sq.sum())

# factor sensitivity (HK-listed factors on the same calendar; US names use weekly data)
idx = {}
for k, f in [("hsce", "IDX_HSCE"), ("miniso", "9896_HK"), ("laopu", "6181_HK"),
             ("mixue", "2097_HK"), ("anta", "2020_HK")]:
    try:
        idx[k] = load_yahoo(f)
    except Exception:  # noqa: BLE001
        pass
idx_ret = pd.DataFrame(idx).reindex(px.index).pct_change().reindex(ret.index)
fac = {}
for k in idx_ret.columns:
    xk = idx_ret[k].dropna()
    xk = xk[xk.index >= "2023-01-01"]
    yk = ret["pm"].reindex(xk.index)
    if len(xk) < 60:
        continue
    mk = sm.OLS(yk, sm.add_constant(xk)).fit()
    fac[k] = {"beta": float(mk.params.iloc[1]), "r2": float(mk.rsquared), "corr": float(np.corrcoef(yk, xk)[0, 1]),
              "n": int(len(xk)), "since": str(xk.index[0].date())}
weekly_us = {}
for k, f in [("spx", "IDX_GSPC"), ("bandai", "7832_T"), ("hasbro", "HAS"), ("mattel", "MAT"), ("mchi", "MCHI")]:
    try:
        s = load_yahoo(f).resample("W-FRI").last().pct_change().dropna()
        j = pd.concat([wk["pm"], s], axis=1).dropna()
        j = j[j.index >= "2023-01-01"]
        mk = sm.OLS(j.iloc[:, 0], sm.add_constant(j.iloc[:, 1])).fit()
        weekly_us[k] = {"beta": float(mk.params.iloc[1]), "r2": float(mk.rsquared), "corr": float(j.corr().iloc[0, 1])}
    except Exception as e:  # noqa: BLE001
        weekly_us[k] = {"error": str(e)}
res["factor_betas"] = fac
res["weekly_betas_since_2023"] = weekly_us
# multi-factor since Laopu Gold's listing: HSI + Miniso (orthogonal) + Laopu Gold (orthogonal) as "new consumption"
mf = pd.concat([ex["pm"], ex["hsi"], idx_ret["miniso"], idx_ret["laopu"]], axis=1).dropna()
mf.columns = ["pm", "hsi", "miniso", "laopu"]
mf = mf[mf.index >= "2024-07-02"]
f_min = sm.OLS(mf["miniso"], sm.add_constant(mf["hsi"])).fit().resid.rename("f_min")
f_lao = sm.OLS(mf["laopu"], sm.add_constant(pd.concat([mf["hsi"], f_min], axis=1))).fit().resid.rename("f_lao")
X3 = pd.concat([mf["hsi"], f_min, f_lao], axis=1)
m1 = sm.OLS(mf["pm"], sm.add_constant(mf[["hsi"]])).fit()
m2 = sm.OLS(mf["pm"], sm.add_constant(X3[["hsi", "f_min"]])).fit()
m3 = sm.OLS(mf["pm"], sm.add_constant(X3)).fit()
res["multi_factor"] = {"since": str(mf.index[0].date()), "n": int(len(mf)),
                       "r2_sim": float(m1.rsquared), "beta_sim": float(m1.params["hsi"]),
                       "r2_two": float(m2.rsquared), "beta_min": float(m2.params["f_min"]), "t_min": float(m2.tvalues["f_min"]),
                       "r2_three": float(m3.rsquared), "beta_lao": float(m3.params["f_lao"]), "t_lao": float(m3.tvalues["f_lao"])}

# event study
EVENTS = json.load(open(os.path.join(ROOT, "data", "events.json"))) if os.path.exists(os.path.join(ROOT, "data", "events.json")) else []
sd = res["sim_daily"]
resid_sd = float(np.sqrt(sd["resid_var_ann"] / TD))
abn = ex["pm"] - (sd["alpha_daily"] + sd["beta"] * ex["hsi"])
dates = ret.index
ev_out = []
for ev in EVENTS:
    pos = dates.searchsorted(pd.Timestamp(ev["date"]))
    if pos >= len(dates):
        continue
    row = {**ev, "day0": str(dates[pos].date()), "ret_pm": float(ret["pm"].iloc[pos]), "ret_hsi": float(ret["hsi"].iloc[pos]),
           "ar": float(abn.iloc[pos]), "ar_t": float(abn.iloc[pos] / resid_sd)}
    lo, hi = max(pos - 1, 0), min(pos + 1, len(dates) - 1)
    row["car_m1_p1"] = float(abn.iloc[lo:hi + 1].sum())
    hi5 = min(pos + 5, len(dates) - 1)
    row["car_0_p5"] = float(abn.iloc[pos:hi5 + 1].sum())
    # ret drops px's first row, so the px row for dates[pos] is pos + 1
    row["price_before"] = float(px["pm"].iloc[pos])
    row["price_day0"] = float(px["pm"].iloc[pos + 1])
    for k in ("hsce", "miniso", "laopu"):
        if k in idx_ret.columns:
            v = idx_ret[k].iloc[pos]
            row[f"ret_{k}"] = None if pd.isna(v) else float(v)
    ev_out.append(row)
res["events"] = ev_out
res["resid_sd_daily"] = resid_sd
top = abn.abs().sort_values(ascending=False).iloc[:40]
res["top_abnormal_days"] = [{"date": str(d.date()), "ret_pm": float(ret["pm"][d]), "ret_hsi": float(ret["hsi"][d]),
                             "ar": float(abn[d]), "ar_t": float(abn[d] / resid_sd),
                             "ret_laopu": None if "laopu" not in idx_ret or pd.isna(idx_ret["laopu"][d]) else float(idx_ret["laopu"][d]),
                             "ret_miniso": None if "miniso" not in idx_ret or pd.isna(idx_ret["miniso"][d]) else float(idx_ret["miniso"][d])}
                            for d in top.index]
earn = [e["day0"] for e in ev_out if e.get("category") in ("earnings", "update")]
mask = ret.index.strftime("%Y-%m-%d").isin(earn)
res["earnings_abs_move_avg"] = float(ret["pm"][mask].abs().mean()) if mask.any() else None
res["normal_abs_move_avg"] = float(ret["pm"][~mask].abs().mean())

bins = np.arange(-0.24, 0.2401, 0.02)
res["hist"] = {"bins": [float(b) for b in bins],
               "pm": np.histogram(ret["pm"].clip(-0.239, 0.239), bins=bins)[0].tolist(),
               "hsi": np.histogram(ret["hsi"].clip(-0.239, 0.239), bins=bins)[0].tolist()}
_, _, _, dd_p = max_drawdown(px["pm"])
_, _, _, dd_h = max_drawdown(px["hsi"])
series = pd.DataFrame({"pm": px["pm"], "hsi": px["hsi"], "pm_idx": px["pm"] / px["pm"].iloc[0] * 100,
                       "hsi_idx": px["hsi"] / px["hsi"].iloc[0] * 100, "dd_pm": dd_p, "dd_hsi": dd_h}).join(roll)
series.index = series.index.strftime("%Y-%m-%d")
res["series"] = {"date": series.index.tolist(),
                 **{c: [None if pd.isna(v) else round(float(v), 5) for v in series[c]] for c in series.columns}}
res["scatter"] = {"x": [round(float(v), 5) for v in ex["hsi"]], "y": [round(float(v), 5) for v in ex["pm"]],
                  "dates": ex.index.strftime("%Y-%m-%d").tolist()}
os.makedirs(OUT, exist_ok=True)
json.dump(res, open(os.path.join(OUT, "market_analysis.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in res.items() if k not in ("series", "scatter", "hist", "events", "top_abnormal_days")}, indent=1, ensure_ascii=False))
if "--events" in sys.argv:
    for e in ev_out:
        print(e["day0"], e["category"], f"{e['ret_pm']:+.1%} hsi {e['ret_hsi']:+.1%} AR {e['ar']:+.1%} t={e['ar_t']:.1f}", e["title"])
    print("--- top abnormal days")
    for t in res["top_abnormal_days"]:
        print(t["date"], f"{t['ret_pm']:+.1%} hsi {t['ret_hsi']:+.1%} AR {t['ar']:+.1%} t={t['ar_t']:.1f} laopu {t['ret_laopu']} miniso {t['ret_miniso']}")
