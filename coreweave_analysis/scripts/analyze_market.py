"""Volatility, Single-Index-Model and event-study analysis of CRWV against the S&P 500.

Reads coreweave_analysis/data/raw/{CRWV,IDX_GSPC}.csv (Yahoo daily) and writes
coreweave_analysis/data/processed/market_analysis.json for the report page.
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
END_DATE = "2026-10-19"  # last complete session before the report date


def load_yahoo(name):
    df = pd.read_csv(os.path.join(RAW, f"{name}.csv"), index_col=0, parse_dates=True)
    df = df[pd.to_numeric(df["Close"], errors="coerce").notna()].astype(float)
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df


def load_rf(index):
    """Daily risk-free rate from the 13-week T-bill yield (Yahoo ^IRX, percent p.a.); falls back to a flat 4%."""
    try:
        r = load_yahoo("IDX_IRX")["Close"]
        r = r.reindex(index).ffill().bfill()
        return r / 100.0, "13-week US T-bill (^IRX)"
    except Exception:  # noqa: BLE001
        return pd.Series(0.04, index=index), "flat 4.0%"


crwv = load_yahoo("CRWV")
spx = load_yahoo("IDX_GSPC")
px = pd.DataFrame({"crwv": crwv["Adj Close"], "spx": spx["Adj Close"]}).dropna()
px = px[(px.index >= "2025-03-28") & (px.index <= END_DATE)]
ret = px.pct_change().dropna()
peers = pd.DataFrame({p: load_yahoo(f)["Adj Close"] for p, f in [("nbis", "NBIS"), ("nvda", "NVDA"), ("orcl", "ORCL"), ("smh", "SMH")]})
peer_ret = peers.pct_change().reindex(ret.index)
logret = np.log(px).diff().dropna()
rf_annual, rf_source = load_rf(ret.index)
rf_daily = (1 + rf_annual) ** (1 / TD) - 1
ex = ret.sub(rf_daily, axis=0)

res = {"meta": {
    "start": str(px.index[0].date()), "end": str(px.index[-1].date()),
    "n_days": int(len(ret)), "rf_source": rf_source,
    "rf_avg": float(rf_annual.mean()),
    "last_close_crwv": float(px["crwv"].iloc[-1]), "last_close_spx": float(px["spx"].iloc[-1]),
}}


# ---------- descriptive & risk statistics ----------
def max_drawdown(series):
    peak = series.cummax()
    dd = series / peak - 1
    trough = dd.idxmin()
    peak_date = series.loc[:trough].idxmax()
    return float(dd.min()), str(peak_date.date()), str(trough.date()), dd


def risk_stats(r, lr, prices, rf_d):
    ann_vol = float(lr.std() * np.sqrt(TD))
    downside = r[r < 0]
    q95, q99 = np.percentile(r, 5), np.percentile(r, 1)
    mdd, pk, tr, _ = max_drawdown(prices)
    excess = r - rf_d
    sharpe = float(excess.mean() / r.std() * np.sqrt(TD))
    sortino = float(excess.mean() * TD / (np.sqrt((np.minimum(r, 0) ** 2).mean()) * np.sqrt(TD)))
    return {
        "total_return": float(prices.iloc[-1] / prices.iloc[0] - 1),
        "ann_return_geo": float((prices.iloc[-1] / prices.iloc[0]) ** (TD / len(r)) - 1),
        "ann_vol": ann_vol,
        "daily_vol": float(r.std()),
        "downside_dev_ann": float(np.sqrt((np.minimum(r, 0) ** 2).mean()) * np.sqrt(TD)),
        "skew": float(stats.skew(r)),
        "excess_kurtosis": float(stats.kurtosis(r)),
        "jarque_bera_p": float(stats.jarque_bera(r).pvalue),
        "var95_hist": float(-q95), "var99_hist": float(-q99),
        "cvar95_hist": float(-r[r <= q95].mean()), "cvar99_hist": float(-r[r <= q99].mean()),
        "var95_param": float(-(r.mean() - 1.645 * r.std())),
        "max_up_day": float(r.max()), "max_up_date": str(r.idxmax().date()),
        "max_down_day": float(r.min()), "max_down_date": str(r.idxmin().date()),
        "days_abs_gt_5pct": int((r.abs() > 0.05).sum()),
        "days_abs_gt_10pct": int((r.abs() > 0.10).sum()),
        "pct_up_days": float((r > 0).mean()),
        "max_drawdown": mdd, "mdd_peak": pk, "mdd_trough": tr,
        "current_drawdown": float(prices.iloc[-1] / prices.cummax().iloc[-1] - 1),
        "sharpe": sharpe, "sortino": sortino,
        "n_down_days": int(len(downside)),
    }


res["stats"] = {
    "crwv": risk_stats(ret["crwv"], logret["crwv"], px["crwv"], rf_daily),
    "spx": risk_stats(ret["spx"], logret["spx"], px["spx"], rf_daily),
}
res["stats"]["vol_ratio"] = res["stats"]["crwv"]["ann_vol"] / res["stats"]["spx"]["ann_vol"]

# volatility by period
periods = {}
for label, (a, b) in {
    "2025 (IPO-Dec)": ("2025-03-28", "2025-12-31"),
    "2026 YTD": ("2026-01-01", "2026-12-31"),
    "Last 63 days": (str(logret.index[-63].date()), "2100-01-01"),
    "Last 21 days": (str(logret.index[-21].date()), "2100-01-01"),
}.items():
    sl = logret.loc[a:b]
    periods[label] = {
        "crwv": float(sl["crwv"].std() * np.sqrt(TD)),
        "spx": float(sl["spx"].std() * np.sqrt(TD)),
        "corr": float(sl.corr().iloc[0, 1]),
        "n": int(len(sl)),
    }
res["vol_by_period"] = periods


# ---------- Single Index Model (OLS) ----------
def sim(y, x):
    X = sm.add_constant(x)
    m = sm.OLS(y, X).fit()
    mh = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    beta, alpha = m.params.iloc[1], m.params.iloc[0]
    resid_var = m.resid.var(ddof=2)
    return {
        "alpha_daily": float(alpha), "alpha_ann": float(alpha * TD),
        "beta": float(beta), "beta_se": float(m.bse.iloc[1]), "beta_se_hac": float(mh.bse.iloc[1]),
        "beta_ci95": [float(beta - 1.96 * m.bse.iloc[1]), float(beta + 1.96 * m.bse.iloc[1])],
        "alpha_t": float(m.tvalues.iloc[0]), "beta_t": float(m.tvalues.iloc[1]),
        "r2": float(m.rsquared), "corr": float(np.corrcoef(y, x)[0, 1]),
        "total_var_ann": float(y.var() * TD),
        "systematic_var_ann": float(beta ** 2 * x.var() * TD),
        "resid_var_ann": float(resid_var * TD),
        "resid_vol_ann": float(np.sqrt(resid_var * TD)),
        "blume_beta": float(0.67 * beta + 0.33),
        "n": int(len(y)),
    }, m


sim_daily, sim_model = sim(ex["crwv"], ex["spx"])
sim_daily["systematic_share"] = sim_daily["systematic_var_ann"] / sim_daily["total_var_ann"]
res["sim_daily"] = sim_daily

# weekly (Friday) returns as a robustness check against non-synchronous trading noise
wk = px.resample("W-FRI").last().pct_change().dropna()
rf_w = rf_annual.resample("W-FRI").last().reindex(wk.index).ffill() / 52
sim_weekly, _ = sim(wk["crwv"] - rf_w, wk["spx"] - rf_w)
sim_weekly["systematic_share"] = sim_weekly["systematic_var_ann"] / sim_weekly["total_var_ann"]
for k in ("total_var_ann", "systematic_var_ann", "resid_var_ann"):
    sim_weekly[k] = sim_weekly[k] / TD * 52
sim_weekly["resid_vol_ann"] = float(np.sqrt(sim_weekly["resid_var_ann"]))
sim_weekly["alpha_ann"] = sim_weekly["alpha_daily"] * 52
res["sim_weekly"] = sim_weekly

# Dimson (1979) beta: sum of coefficients on lead, contemporaneous and lagged market returns
dim = pd.concat([ex["crwv"], ex["spx"].shift(1), ex["spx"], ex["spx"].shift(-1)], axis=1).dropna()
dm = sm.OLS(dim.iloc[:, 0], sm.add_constant(dim.iloc[:, 1:])).fit()
res["dimson_beta"] = float(dm.params.iloc[1:].sum())

# up / down market betas and capture ratios
up, dn = ex["spx"] > 0, ex["spx"] < 0
res["up_beta"] = float(sm.OLS(ex["crwv"][up], sm.add_constant(ex["spx"][up])).fit().params.iloc[1])
res["down_beta"] = float(sm.OLS(ex["crwv"][dn], sm.add_constant(ex["spx"][dn])).fit().params.iloc[1])
res["up_capture"] = float(ret["crwv"][ret["spx"] > 0].mean() / ret["spx"][ret["spx"] > 0].mean())
res["down_capture"] = float(ret["crwv"][ret["spx"] < 0].mean() / ret["spx"][ret["spx"] < 0].mean())
res["treynor"] = float(ex["crwv"].mean() * TD / sim_daily["beta"])
active = ret["crwv"] - ret["spx"]
res["tracking_error"] = float(active.std() * np.sqrt(TD))
res["information_ratio"] = float(active.mean() * TD / res["tracking_error"])
res["jensen_alpha_ann"] = sim_daily["alpha_ann"]
# CAPM required return given realised market premium
mkt_prem = float(ex["spx"].mean() * TD)
res["capm"] = {"market_premium_realised": mkt_prem,
               "required_return_realised": float(rf_annual.mean() + sim_daily["beta"] * mkt_prem),
               "required_return_5pct_erp": float(rf_annual.iloc[-1] + sim_daily["beta"] * 0.05),
               "rf_latest": float(rf_annual.iloc[-1])}

# ---------- rolling statistics ----------
W = 63
roll = pd.DataFrame(index=logret.index)
roll["vol21_crwv"] = logret["crwv"].rolling(21).std() * np.sqrt(TD)
roll["vol21_spx"] = logret["spx"].rolling(21).std() * np.sqrt(TD)
roll["vol63_crwv"] = logret["crwv"].rolling(W).std() * np.sqrt(TD)
roll["vol63_spx"] = logret["spx"].rolling(W).std() * np.sqrt(TD)
cov = ex["crwv"].rolling(W).cov(ex["spx"])
roll["beta63"] = cov / ex["spx"].rolling(W).var()
roll["corr63"] = ex["crwv"].rolling(W).corr(ex["spx"])
roll["ratio63"] = roll["vol63_crwv"] / roll["vol63_spx"]

# ---------- GARCH(1,1), Student-t ----------
g = arch_model(logret["crwv"] * 100, vol="GARCH", p=1, q=1, dist="t", mean="Constant").fit(disp="off")
gs = arch_model(logret["spx"] * 100, vol="GARCH", p=1, q=1, dist="t", mean="Constant").fit(disp="off")


def garch_summary(fit):
    a, b = float(fit.params["alpha[1]"]), float(fit.params["beta[1]"])
    omega = float(fit.params["omega"])
    pers = a + b
    lr_var = omega / (1 - pers) if pers < 1 else float("nan")
    fc = fit.forecast(horizon=21, reindex=False).variance.values[-1]
    return {"omega": omega, "alpha": a, "beta": b, "persistence": pers,
            "half_life_days": float(np.log(0.5) / np.log(pers)) if pers < 1 else None,
            "long_run_vol_ann": float(np.sqrt(lr_var * TD) / 100) if pers < 1 else None,
            "current_cond_vol_ann": float(fit.conditional_volatility.iloc[-1] * np.sqrt(TD) / 100),
            "forecast_21d_vol_ann": float(np.sqrt(fc.mean() * TD) / 100),
            "nu": float(fit.params.get("nu", np.nan))}


res["garch"] = {"crwv": garch_summary(g), "spx": garch_summary(gs)}
roll["garch_crwv"] = g.conditional_volatility / 100 * np.sqrt(TD)
roll["garch_spx"] = gs.conditional_volatility / 100 * np.sqrt(TD)

# ---------- concentration of variance in a few days ----------
sq = (ret["crwv"] - ret["crwv"].mean()) ** 2
res["top10_days_var_share"] = float(sq.sort_values(ascending=False).iloc[:10].sum() / sq.sum())

# ---------- event study (market model) ----------
EVENTS = json.load(open(os.path.join(ROOT, "data", "events.json")))
resid_sd = float(np.sqrt(sim_daily["resid_var_ann"] / TD))
a_d, b_d = sim_daily["alpha_daily"], sim_daily["beta"]
abn = ex["crwv"] - (a_d + b_d * ex["spx"])
dates = ret.index
ev_out = []
for ev in EVENTS:
    d0 = pd.Timestamp(ev["date"])
    pos = dates.searchsorted(d0)
    if pos >= len(dates):
        continue
    row = {**ev, "day0": str(dates[pos].date())}
    row["ret_crwv"] = float(ret["crwv"].iloc[pos])
    row["ret_spx"] = float(ret["spx"].iloc[pos])
    row["ar"] = float(abn.iloc[pos])
    row["ar_t"] = float(abn.iloc[pos] / resid_sd)
    lo, hi = max(pos - 1, 0), min(pos + 1, len(dates) - 1)
    row["car_m1_p1"] = float(abn.iloc[lo:hi + 1].sum())
    row["car_t_m1_p1"] = float(row["car_m1_p1"] / (resid_sd * np.sqrt(hi - lo + 1)))
    hi5 = min(pos + 5, len(dates) - 1)
    row["car_0_p5"] = float(abn.iloc[pos:hi5 + 1].sum())
    row["ret_0_p5"] = float((1 + ret["crwv"].iloc[pos:hi5 + 1]).prod() - 1)
    row["price_before"] = float(px["crwv"].iloc[pos - 1]) if pos > 0 else None
    row["price_day0"] = float(px["crwv"].iloc[pos])
    for p in peer_ret.columns:
        row[f"ret_{p}"] = float(peer_ret[p].iloc[pos])
    ev_out.append(row)
res["events"] = ev_out
res["resid_sd_daily"] = resid_sd

# largest absolute abnormal-return days (for cross-checking the event list)
top = abn.abs().sort_values(ascending=False).iloc[:25]
res["top_abnormal_days"] = [
    {"date": str(d.date()), "ret_crwv": float(ret["crwv"][d]), "ret_spx": float(ret["spx"][d]),
     "ar": float(abn[d]), "ar_t": float(abn[d] / resid_sd),
     "ret_nbis": float(peer_ret["nbis"][d]), "ret_nvda": float(peer_ret["nvda"][d])} for d in top.index]

# earnings-day vs normal-day absolute moves
earn_days = [e["day0"] for e in ev_out if e.get("category") == "earnings"]
mask = ret.index.strftime("%Y-%m-%d").isin(earn_days)
res["earnings_abs_move_avg"] = float(ret["crwv"][mask].abs().mean()) if mask.any() else None
res["normal_abs_move_avg"] = float(ret["crwv"][~mask].abs().mean())

# ---------- histogram data ----------
bins = np.arange(-0.30, 0.3001, 0.02)
res["hist"] = {
    "bins": [float(b) for b in bins],
    "crwv": np.histogram(ret["crwv"].clip(-0.299, 0.299), bins=bins)[0].tolist(),
    "spx": np.histogram(ret["spx"].clip(-0.299, 0.299), bins=bins)[0].tolist(),
}

# ---------- series for charts ----------
_, _, _, dd_c = max_drawdown(px["crwv"])
_, _, _, dd_s = max_drawdown(px["spx"])
series = pd.DataFrame({
    "crwv": px["crwv"], "spx": px["spx"],
    "crwv_idx": px["crwv"] / px["crwv"].iloc[0] * 100, "spx_idx": px["spx"] / px["spx"].iloc[0] * 100,
    "dd_crwv": dd_c, "dd_spx": dd_s,
}).join(ret.add_prefix("r_")).join(roll)
series.index = series.index.strftime("%Y-%m-%d")
res["series"] = {"date": series.index.tolist(),
                 **{c: [None if pd.isna(v) else round(float(v), 6) for v in series[c]] for c in series.columns}}
res["scatter"] = {"x": [round(float(v), 5) for v in ex["spx"]], "y": [round(float(v), 5) for v in ex["crwv"]]}

# ---------- sensitivity to the AI trade (multi-index betas, two-factor model) ----------
idx = pd.DataFrame({k: load_yahoo(f)["Adj Close"] for k, f in
                    [("qqq", "QQQ"), ("smh", "SMH"), ("nvda", "NVDA"), ("nbis", "NBIS"), ("orcl", "ORCL"), ("msft", "MSFT")]})
idx_ret = idx.pct_change().reindex(ret.index)
fac = {}
for k in idx_ret.columns:
    xk = idx_ret[k].dropna()
    yk = ret["crwv"].reindex(xk.index)
    mk = sm.OLS(yk, sm.add_constant(xk)).fit()
    fac[k] = {"beta": float(mk.params.iloc[1]), "r2": float(mk.rsquared), "corr": float(np.corrcoef(yk, xk)[0, 1])}
# AI factor = semiconductor ETF return orthogonalised to the S&P 500
xs = pd.concat([ret["spx"], idx_ret["smh"]], axis=1).dropna()
ai = sm.OLS(xs["smh"], sm.add_constant(xs["spx"])).fit().resid.rename("ai_factor")
X2 = pd.concat([xs["spx"], ai], axis=1)
m2 = sm.OLS(ret["crwv"].reindex(X2.index), sm.add_constant(X2)).fit()
res["two_factor"] = {"beta_spx": float(m2.params["spx"]), "beta_ai": float(m2.params["ai_factor"]),
                     "t_spx": float(m2.tvalues["spx"]), "t_ai": float(m2.tvalues["ai_factor"]),
                     "r2": float(m2.rsquared), "r2_sim": sim_daily["r2"]}
# add a neocloud peer factor (Nebius orthogonalised to SPX and AI factor)
xn = pd.concat([X2, idx_ret["nbis"]], axis=1).dropna()
nb = sm.OLS(xn["nbis"], sm.add_constant(xn[["spx", "ai_factor"]])).fit().resid.rename("neocloud")
X3 = pd.concat([xn[["spx", "ai_factor"]], nb], axis=1)
m3 = sm.OLS(ret["crwv"].reindex(X3.index), sm.add_constant(X3)).fit()
res["three_factor"] = {"beta_spx": float(m3.params["spx"]), "beta_ai": float(m3.params["ai_factor"]),
                       "beta_neo": float(m3.params["neocloud"]), "r2": float(m3.rsquared)}
res["factor_betas"] = fac
big = idx_ret["smh"].abs() > 0.03
res["smh_big_days"] = {"n": int(big.sum()),
                       "avg_abs_crwv": float(ret["crwv"][big].abs().mean()),
                       "avg_abs_smh": float(idx_ret["smh"][big].abs().mean()),
                       "same_sign_share": float((np.sign(ret["crwv"][big]) == np.sign(idx_ret["smh"][big])).mean())}
roll["corr63_nbis"] = ret["crwv"].rolling(W).corr(idx_ret["nbis"])
series_extra = roll[["corr63_nbis"]].copy()
series_extra.index = series_extra.index.strftime("%Y-%m-%d")
res["series"]["corr63_nbis"] = [None if pd.isna(v) else round(float(v), 4) for v in series_extra["corr63_nbis"].reindex(res["series"]["date"])]

# ---------- implied volatility (Yahoo option chain snapshot, 2026-10-20 intraday) ----------
try:
    o = pd.read_csv(os.path.join(RAW, "crwv_options.csv"))
    spot = float(crwv["Close"].iloc[-1])
    iv = []
    for ex_, g in o.groupby("expiry"):
        g = g[(g.impliedVolatility > 0.05) & (g.openInterest.fillna(0) > 50)]
        atm = g[(g.strike - spot).abs() <= spot * 0.06]
        if len(atm):
            iv.append({"expiry": ex_, "atm_iv": float(atm.impliedVolatility.median()), "n": int(len(atm))})
    res["implied_vol"] = {"spot": spot, "term": iv}
except Exception as e:  # noqa: BLE001
    res["implied_vol"] = {"error": str(e)}

os.makedirs(OUT, exist_ok=True)
json.dump(res, open(os.path.join(OUT, "market_analysis.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in res.items() if k not in ("series", "scatter", "hist", "events", "top_abnormal_days")},
                 indent=1, ensure_ascii=False))
if "--events" in sys.argv:
    for e in res["events"]:
        print(e["day0"], e["category"], f"{e['ret_crwv']:+.1%} spx {e['ret_spx']:+.1%} AR {e['ar']:+.1%} t={e['ar_t']:.1f}", e["title"])
    print("--- top abnormal days")
    for t in res["top_abnormal_days"]:
        print(t["date"], f"{t['ret_crwv']:+.1%} spx {t['ret_spx']:+.1%} AR {t['ar']:+.1%} t={t['ar_t']:.1f}")
