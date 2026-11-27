"""Volatility, market/sector/rate betas, peer comparison and event study for 粤高速A (000429.SZ).

Benchmarks: the CSI 300 total-return index (market), an equal-weight index of 15 A-share expressway peers (sector,
checked against the Shenwan expressway index), the CSI Dividend total-return index (style) and the 10-year China
government bond yield (rates). Stock returns use Yahoo Finance adjusted closes, which reinvest cash dividends
multiplicatively; Eastmoney's back-adjusted series adds dividends back as fixed amounts and understates percentage
returns, so it is only used for the raw price check. Reads data/raw/ and writes data/processed/market_analysis.json.
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
START = "2016-01-04"
PEERS = {"600377": "宁沪高速", "001965": "招商公路", "600350": "山东高速", "600548": "深高速", "600012": "皖通高速",
         "601107": "四川成渝", "600269": "赣粤高速", "600033": "福建高速", "000900": "现代投资", "600035": "楚天高速",
         "600020": "中原高速", "000828": "东莞控股", "601518": "吉林高速", "601188": "龙江交通", "600368": "五洲交通"}
ME = "000429"
NAMES = {ME: "粤高速A", **PEERS}
COMPARE = [ME, "600377", "001965", "600350", "600548", "600012", "601107"]


def load_csv(path, date_col, col):
    df = pd.read_csv(os.path.join(RAW, path))
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = pd.to_datetime(df[date_col]).dt.tz_localize(None).dt.normalize()
    return s[~s.index.duplicated()].dropna().sort_index()


def load_yahoo(code, col="Adj Close"):
    t = f"{code}_{'SS' if code.startswith('6') else 'SZ'}"
    return load_csv(os.path.join("yahoo", f"{t}.csv"), "Date", col)


def load_csi(code):
    return load_csv(os.path.join("idx", f"csindex_{code}.csv"), "日期", "收盘")


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
           "n": int(len(y)), "alpha_daily": float(m.params.iloc[0])}
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
        "days_abs_gt_3pct": int((r.abs() > 0.03).sum()), "days_abs_gt_5pct": int((r.abs() > 0.05).sum()),
        "max_drawdown": mdd, "mdd_peak": pk, "mdd_trough": tr,
        "current_drawdown": float(prices.iloc[-1] / prices.cummax().iloc[-1] - 1),
        "sharpe": float(excess.mean() / r.std() * np.sqrt(TD)),
        "sortino": float(excess.mean() * TD / (np.sqrt((np.minimum(r, 0) ** 2).mean()) * np.sqrt(TD))),
    }


def garch(series):
    fit = arch_model(series * 100, vol="GARCH", p=1, q=1, dist="t", mean="Constant").fit(disp="off")
    a, b, om = float(fit.params["alpha[1]"]), float(fit.params["beta[1]"]), float(fit.params["omega"])
    pers = a + b
    return fit, {"alpha": a, "beta": b, "persistence": pers,
                 "half_life_days": float(np.log(0.5) / np.log(pers)) if pers < 1 else None,
                 "long_run_vol_ann": float(np.sqrt(om / (1 - pers) * TD) / 100) if pers < 1 else None,
                 "current_cond_vol_ann": float(fit.conditional_volatility.iloc[-1] * np.sqrt(TD) / 100),
                 "nu": float(fit.params.get("nu", np.nan))}


# ---------- data ----------
csi = load_csi("H00300")  # CSI 300 total return
END_DATE = str(csi.index[-1].date())  # last complete session in every source
csi_vol = load_csv(os.path.join("idx", "csindex_000300.csv"), "日期", "成交量")
cal = csi_vol.index[(csi_vol > 0) & (csi_vol.index >= START) & (csi_vol.index <= END_DATE)]
gd_adj, gd_raw = load_yahoo(ME), load_yahoo(ME, "Close")
gd_adj, gd_raw = gd_adj[gd_adj.index <= END_DATE], gd_raw[gd_raw.index <= END_DATE]
peer_px = pd.DataFrame({c: load_yahoo(c) for c in PEERS}).reindex(cal)
peer_ret = peer_px.pct_change(fill_method=None)
n_avail = peer_ret.notna().sum(axis=1)
sec_ret = peer_ret.mean(axis=1, skipna=True).where(n_avail >= 8)
divi = load_csi("H00922")  # CSI Dividend total return
sw = load_csv(os.path.join("em", "sw_851731.csv"), "日期", "收盘")  # Shenwan expressway index (price)
px = pd.DataFrame({"gd": gd_adj.reindex(cal), "csi": csi.reindex(cal), "div": divi.reindex(cal)}).ffill(limit=5).dropna()
ret = px.pct_change().dropna()
ret["sec"] = sec_ret.reindex(ret.index)
ret = ret.dropna()
px = px.loc[[px.index[0]] + list(ret.index)]
px["sec"] = 100 * (1 + ret["sec"]).cumprod().reindex(px.index)
px.loc[px.index[0], "sec"] = 100.0
logret = np.log(px).diff().dropna()
# a suspended day carries the previous close; count the stock's own zero-volume days so they can be reported
bond = pd.read_csv(os.path.join(RAW, "em", "bond_zh_us_rate.csv"))
bond.index = pd.to_datetime(bond["日期"])
bond = bond.sort_index()
y10 = pd.to_numeric(bond["中国国债收益率10年"], errors="coerce").reindex(ret.index).ffill()
y2 = pd.to_numeric(bond["中国国债收益率2年"], errors="coerce").reindex(ret.index).ffill().bfill() / 100
rf_daily = (1 + y2) ** (1 / TD) - 1
dy10 = y10.diff().fillna(0)  # percentage points per day
ex = ret.sub(rf_daily, axis=0)
sw_ret = sw.reindex(px.index).pct_change().reindex(ret.index)
res = {"meta": {"start": str(px.index[0].date()), "end": END_DATE, "n_days": int(len(ret)), "rf_avg": float(y2.mean()),
                "last_raw_close": float(gd_raw.iloc[-1]), "last_raw_date": str(gd_raw.index[-1].date()),
                "last_csi": float(csi.iloc[-1]), "y10_last": float(y10.iloc[-1]), "y2_last": float(y2.iloc[-1]),
                "sector_names": [PEERS[c] for c in PEERS], "sector_min_names": 8,
                "sw_check": {"corr_daily": float(pd.concat([ret["sec"], sw_ret], axis=1).dropna().corr().iloc[0, 1])}}}
res["stats"] = {k: risk_stats(ret[k], logret[k], px[k], rf_daily) for k in ("gd", "csi", "sec", "div")}

# ---------- single-index models ----------
res["sim_csi"] = sim(ex["gd"], ex["csi"])
res["sim_sec"] = sim(ex["gd"], ex["sec"])
res["sim_div"] = sim(ex["gd"], ex["div"])
res["sec_on_csi"] = sim(ex["sec"], ex["csi"])
wk = px.resample("W-FRI").last().pct_change().dropna()
res["sim_csi_weekly"] = sim(wk["gd"], wk["csi"], scale=52)
res["sim_sec_weekly"] = sim(wk["gd"], wk["sec"], scale=52)
up, dn = ex["csi"] > 0, ex["csi"] < 0
res["up_beta_csi"] = float(ols(ex["gd"][up], ex["csi"][up]).params.iloc[1])
res["down_beta_csi"] = float(ols(ex["gd"][dn], ex["csi"][dn]).params.iloc[1])
res["capm"] = {"rf_latest": float(y2.iloc[-1]), "y10_latest": float(y10.iloc[-1]) / 100,
               "required_return_6pct_erp": float(y10.iloc[-1] / 100 + res["sim_csi"]["beta"] * 0.06)}


# ---------- multi-factor: market, sector (orthogonalised) and rates ----------
def factors(e, since=None, until=None):
    d = e.copy()
    d["dy"] = dy10.reindex(d.index)
    if since:
        d = d[d.index >= since]
    if until:
        d = d[d.index <= until]
    d["sec_o"] = ols(d["sec"], d["csi"]).resid
    m1 = ols(d["gd"], d[["csi"]])
    m2 = ols(d["gd"], d[["csi", "sec_o"]])
    m3 = sm.OLS(d["gd"], sm.add_constant(d[["csi", "sec_o", "dy"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    m_rate = sm.OLS(d["gd"], sm.add_constant(d[["csi", "dy"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    m_sec_rate = sm.OLS(d["sec"], sm.add_constant(d[["csi", "dy"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    return m2, {"since": str(d.index[0].date()), "until": str(d.index[-1].date()), "n": int(len(d)),
                "r2_csi": float(m1.rsquared), "r2_two": float(m2.rsquared), "r2_three": float(m3.rsquared),
                "beta_csi": float(m2.params["csi"]), "beta_sec_o": float(m2.params["sec_o"]), "t_sec_o": float(m2.tvalues["sec_o"]),
                # return per +10bp move in the 10-year yield, holding the market fixed
                "rate_beta_10bp": float(m_rate.params["dy"] * 0.10), "rate_t": float(m_rate.tvalues["dy"]),
                "rate_beta_10bp_sector": float(m_sec_rate.params["dy"] * 0.10), "rate_t_sector": float(m_sec_rate.tvalues["dy"]),
                "rate_beta_10bp_3f": float(m3.params["dy"] * 0.10), "rate_t_3f": float(m3.tvalues["dy"])}


m_two, res["factors"] = factors(ex)
res["factors_2023"] = factors(ex, "2023-01-01")[1]
res["factors_2016_2020"] = factors(ex, None, "2020-12-31")[1]
res["factors_2021_2023"] = factors(ex, "2021-01-01", "2023-12-31")[1]
res["factors_2024"] = factors(ex, "2024-01-01")[1]
# monthly view of the bond-proxy link: stock vs 10-year yield level
mo_px = px["gd"].resample("ME").last()
mo_y = y10.resample("ME").last()
mo = pd.concat([np.log(mo_px).diff().rename("gd"), mo_y.diff().rename("dy")], axis=1).dropna()
res["monthly_rate_beta_10bp"] = float(ols(mo["gd"], mo["dy"]).params.iloc[1] * 0.10)
res["monthly_rate_corr"] = float(mo.corr().iloc[0, 1])

# ---------- calendar years ----------
years = []
for y in sorted(set(ret.index.year)):
    sel = ret.index.year == y
    p_y = px[px.index.year == y]
    prev = px[px.index.year < y]
    base = prev.iloc[-1] if len(prev) else p_y.iloc[0]
    e_y = ex[sel]
    s_c, s_s = sim(e_y["gd"], e_y["csi"]), sim(e_y["gd"], e_y["sec"])
    yy = y10[y10.index.year == y]
    years.append({"year": int(y), "n": int(sel.sum()),
                  **{f"ret_{k}": float(p_y[k].iloc[-1] / base[k] - 1) for k in ("gd", "csi", "sec", "div")},
                  **{f"vol_{k}": float(logret[k][logret.index.year == y].std() * np.sqrt(TD)) for k in ("gd", "csi", "sec")},
                  "beta_csi": s_c["beta"], "r2_csi": s_c["r2"], "beta_sec": s_s["beta"], "r2_sec": s_s["r2"],
                  "mdd_gd": max_drawdown(p_y["gd"])[0], "y10_end": float(yy.iloc[-1]), "y10_chg": float(yy.iloc[-1] - (y10[y10.index.year < y].iloc[-1] if (y10.index.year < y).any() else yy.iloc[0]))})
res["by_year"] = years

# ---------- rolling ----------
roll = pd.DataFrame(index=logret.index)
for k in ("gd", "csi", "sec"):
    roll[f"vol63_{k}"] = logret[k].rolling(63).std() * np.sqrt(TD)
roll["beta252_csi"] = ex["gd"].rolling(252).cov(ex["csi"]) / ex["csi"].rolling(252).var()
roll["beta252_sec"] = ex["gd"].rolling(252).cov(ex["sec"]) / ex["sec"].rolling(252).var()
roll["corr126_csi"] = ex["gd"].rolling(126).corr(ex["csi"])
roll["corr126_sec"] = ex["gd"].rolling(126).corr(ex["sec"])
# rolling rate sensitivity: daily return on yield change, 252-day window, per +10bp
dyy = dy10.reindex(ex.index)
roll["rate252"] = ex["gd"].rolling(252).cov(dyy) / dyy.rolling(252).var() * 0.10
g_fit, res_g = garch(logret["gd"])
res["garch"] = {"gd": res_g, "sec": garch(logret["sec"])[1], "csi": garch(logret["csi"])[1]}
roll["garch_gd"] = g_fit.conditional_volatility / 100 * np.sqrt(TD)
sq = (ret["gd"] - ret["gd"].mean()) ** 2
res["top10_days_var_share"] = float(sq.sort_values(ascending=False).iloc[:10].sum() / sq.sum())


# ---------- peers: risk and returns inside the expressway sector ----------
def period_ret(p, a, b):
    s = p.dropna()
    s0, s1 = s[s.index <= a], s[s.index <= b]
    if not len(s0) or not len(s1):
        return None
    return float(s1.iloc[-1] / s0.iloc[-1] - 1)


peers_out = []
all_px = peer_px.copy()
all_px[ME] = gd_adj.reindex(cal)
for c in [ME] + list(PEERS):
    p = all_px[c].dropna()
    r_c = p.pct_change().dropna()
    loo = peer_ret.drop(columns=[c], errors="ignore")
    sec_loo = loo.mean(axis=1).where(loo.notna().sum(axis=1) >= 8)
    j = pd.concat([r_c.rename("y"), ret["csi"].rename("csi"), sec_loo.rename("sec"), dy10.rename("dy")], axis=1, sort=True).dropna()
    j23 = j[j.index >= "2023-01-01"]
    j1y = j.iloc[-252:]
    row = {"code": c, "name": NAMES[c], "first": str(p.index[0].date()),
           "vol_1y": float(np.log(1 + j1y["y"]).std() * np.sqrt(TD)),
           "vol_since2023": float(np.log(1 + j23["y"]).std() * np.sqrt(TD)),
           "beta_csi": float(ols(j23["y"], j23["csi"]).params.iloc[1]),
           "beta_sec": float(ols(j23["y"], j23["sec"]).params.iloc[1]),
           "corr_sec": float(j23[["y", "sec"]].corr().iloc[0, 1]),
           "rate_10bp": float(ols(j23["y"], j23[["csi", "dy"]]).params["dy"] * 0.10),
           "ret_2024": period_ret(p, "2023-12-31", "2024-12-31"),
           "ret_2025": period_ret(p, "2024-12-31", "2025-12-31"),
           "ret_2026ytd": period_ret(p, "2025-12-31", END_DATE),
           "ret_3y": period_ret(p, str((pd.Timestamp(END_DATE) - pd.DateOffset(years=3)).date()), END_DATE),
           "mdd_since2024": max_drawdown(p[p.index >= "2024-01-01"])[0],
           "dd_from_high": float(p.iloc[-1] / p.max() - 1), "high_date": str(p.idxmax().date())}
    peers_out.append(row)
res["peers"] = peers_out
res["sector_index_note"] = {"n_names_last": int(n_avail.iloc[-1]), "n_names_start": int(n_avail.loc[ret.index[0]])}

# ---------- event study (market model with CSI 300 and the orthogonalised sector factor) ----------
EV_PATH = os.path.join(ROOT, "data", "events.json")
EVENTS = json.load(open(EV_PATH, encoding="utf-8")) if os.path.exists(EV_PATH) else []
f_sec_full = ols(ex["sec"], ex["csi"]).resid
abn = ex["gd"] - (m_two.params["const"] + m_two.params["csi"] * ex["csi"] + m_two.params["sec_o"] * f_sec_full)
resid_sd = float(m_two.resid.std(ddof=3))
dates = ret.index
ev_out = []
for ev in EVENTS:
    pos = dates.searchsorted(pd.Timestamp(ev["date"]))
    if pos >= len(dates):
        continue
    row = {**ev, "day0": str(dates[pos].date()), "ret_gd": float(ret["gd"].iloc[pos]), "ret_csi": float(ret["csi"].iloc[pos]),
           "ret_sec": float(ret["sec"].iloc[pos]), "dy10_bp": float(dy10.iloc[pos] * 100),
           "ar": float(abn.iloc[pos]), "ar_t": float(abn.iloc[pos] / resid_sd)}
    row["car_0_p5"] = float(abn.iloc[pos:min(pos + 5, len(dates) - 1) + 1].sum())
    row["car_m5_p5"] = float(abn.iloc[max(pos - 5, 0):min(pos + 5, len(dates) - 1) + 1].sum())
    row["price_day0"] = float(gd_raw.reindex([dates[pos]]).iloc[0])
    ev_out.append(row)
res["events"] = ev_out
res["resid_sd_daily"] = resid_sd
top = abn.abs().sort_values(ascending=False).iloc[:40]
res["top_abnormal_days"] = [{"date": str(d.date()), "ret_gd": float(ret["gd"][d]), "ret_csi": float(ret["csi"][d]),
                             "ret_sec": float(ret["sec"][d]), "ar": float(abn[d]), "ar_t": float(abn[d] / resid_sd)} for d in top.index]
top_sec = ret["sec"].abs().sort_values(ascending=False).iloc[:15]
res["top_sector_days"] = [{"date": str(d.date()), "ret_sec": float(ret["sec"][d]), "ret_gd": float(ret["gd"][d]),
                           "ret_csi": float(ret["csi"][d])} for d in top_sec.index]
earn = [e["day0"] for e in ev_out if e.get("category") == "earnings"]
mask = ret.index.strftime("%Y-%m-%d").isin(earn)
res["earnings_abs_move_avg"] = float(ret["gd"][mask].abs().mean()) if mask.any() else None
res["normal_abs_move_avg"] = float(ret["gd"][~mask].abs().mean())
res["car_by_year"] = {str(y): float(abn[abn.index.year == y].sum()) for y in sorted(set(abn.index.year))}

# dividend yield on the latest declared annual dividend (known to the market from the plan announcement in March)
# against the 10-year government bond yield
dv = pd.read_csv(os.path.join(RAW, "fin", f"div_{ME}.csv"))
dv = dv[dv["报告期"].astype(str).str[5:10] == "12-31"]
ann = pd.to_datetime(dv["预案公告日"].fillna(dv["业绩披露日期"]))
dps = pd.Series(dv["现金分红-现金分红比例"].values / 10, index=ann.values).sort_index()
raw_c = gd_raw.reindex(px.index).ffill()
dps_ttm = dps.reindex(dps.index.union(px.index)).ffill().reindex(px.index)
dy_ttm = dps_ttm / raw_c
val = pd.read_csv(os.path.join(RAW, "fin", f"value_{ME}.csv"))
val.index = pd.to_datetime(val["数据日期"])
pe_ttm = pd.to_numeric(val["PE(TTM)"], errors="coerce").reindex(px.index)
pb = pd.to_numeric(val["市净率"], errors="coerce").reindex(px.index)
y10_px = y10.reindex(px.index).ffill()
spread = dy_ttm * 100 - y10_px
res["valuation_now"] = {"date": END_DATE, "price": float(raw_c.iloc[-1]), "dps_ttm": float(dps_ttm.iloc[-1]), "dy_ttm": float(dy_ttm.iloc[-1]),
                        "y10": float(y10_px.iloc[-1]), "spread_pp": float(spread.iloc[-1]),
                        "pe_ttm": float(pe_ttm.dropna().iloc[-1]), "pb": float(pb.dropna().iloc[-1]),
                        "spread_avg_2018_2023": float(spread[(spread.index >= "2018-01-01") & (spread.index <= "2023-12-31")].mean()),
                        "spread_min_since2018": float(spread[spread.index >= "2018-01-01"].min()),
                        "spread_min_date": str(spread[spread.index >= "2018-01-01"].idxmin().date()),
                        "dy_avg_2018_2023": float(dy_ttm[(dy_ttm.index >= "2018-01-01") & (dy_ttm.index <= "2023-12-31")].mean()),
                        "y10_avg_2018_2023": float(y10_px[(y10_px.index >= "2018-01-01") & (y10_px.index <= "2023-12-31")].mean()),
                        "pe_pct_rank": float((pe_ttm.dropna() <= pe_ttm.dropna().iloc[-1]).mean()),
                        "pb_pct_rank": float((pb.dropna() <= pb.dropna().iloc[-1]).mean()), "val_since": str(pe_ttm.dropna().index[0].date())}
# how the yield gap moved with the price: regress monthly log price change on monthly change in the gap
mg = pd.concat([np.log(raw_c).resample("ME").last().diff().rename("p"), spread.resample("ME").last().diff().rename("s"),
                y10_px.resample("ME").last().diff().rename("y")], axis=1, sort=True).dropna()
mg = mg[mg.index >= "2018-01-01"]
res["yield_gap_monthly_corr_y10"] = float(mg[["p", "y"]].corr().iloc[0, 1])
# year-end snapshots of the yield gap for the table
res["yield_gap_by_year"] = [{"date": str(d.date()), "dy": float(dy_ttm[d]), "y10": float(y10_px[d]), "spread": float(spread[d]),
                             "pe": None if pd.isna(pe_ttm[d]) else float(pe_ttm[d]), "pb": None if pd.isna(pb[d]) else float(pb[d])}
                            for d in [px.index[px.index.year == y][-1] for y in sorted(set(px.index.year))]]

# ex-dividend days: total return (dividend added back) on the record day and the ex-day, abnormal returns from the model
exd = []
for ex_s, cash10, rec_s in zip(dv["除权除息日"], dv["现金分红-现金分红比例"], dv["股权登记日"]):
    if pd.isna(ex_s):
        continue
    ex_day = pd.Timestamp(ex_s)
    if ex_day < pd.Timestamp(START) or ex_day > pd.Timestamp(END_DATE):
        continue
    pos = dates.searchsorted(ex_day)
    exd.append({"ex_date": str(dates[pos].date()), "record_date": str(dates[pos - 1].date()), "dps": float(cash10) / 10,
                "dps_yield": float(cash10) / 10 / float(gd_raw.reindex([dates[pos - 1]]).iloc[0]),
                "ret_record": float(ret["gd"].iloc[pos - 1]), "ar_record": float(abn.iloc[pos - 1]),
                "ret_ex": float(ret["gd"].iloc[pos]), "ar_ex": float(abn.iloc[pos]), "ret_sec_ex": float(ret["sec"].iloc[pos]),
                "car_ex_p5": float(abn.iloc[pos:min(pos + 5, len(dates) - 1) + 1].sum())})
res["ex_dividend"] = exd
res["ex_dividend_summary"] = {"n": len(exd), "n_neg": int(sum(e["ret_ex"] < 0 for e in exd)),
                              "avg_ret_ex": float(np.mean([e["ret_ex"] for e in exd])), "avg_ar_ex": float(np.mean([e["ar_ex"] for e in exd])),
                              "avg_ret_record": float(np.mean([e["ret_record"] for e in exd]))}

bins = np.arange(-0.10, 0.1001, 0.01)
res["hist"] = {"bins": [float(b) for b in bins],
               **{k: np.histogram(ret[k].clip(-0.0999, 0.0999), bins=bins)[0].tolist() for k in ("gd", "sec", "csi")}}
dd = {k: max_drawdown(px[k])[3] for k in ("gd", "csi", "sec", "div")}
series = pd.DataFrame({"gd": gd_raw.reindex(px.index), "gd_idx": px["gd"] / px["gd"].iloc[0] * 100,
                       "csi_idx": px["csi"] / px["csi"].iloc[0] * 100, "sec_idx": px["sec"] / px["sec"].iloc[0] * 100,
                       "div_idx": px["div"] / px["div"].iloc[0] * 100, "y10": y10.reindex(px.index).ffill(),
                       "dd_gd": dd["gd"], "dd_csi": dd["csi"], "dd_sec": dd["sec"], "dy_ttm": dy_ttm, "spread": spread,
                       "pe_ttm": pe_ttm, "pb": pb}).join(roll)
series.index = series.index.strftime("%Y-%m-%d")
res["series"] = {"date": series.index.tolist(),
                 **{c: [None if pd.isna(v) else round(float(v), 5) for v in series[c]] for c in series.columns}}
res["scatter"] = {"x": [round(float(v), 5) for v in ex["csi"]], "y": [round(float(v), 5) for v in ex["gd"]],
                  "dates": ex.index.strftime("%Y-%m-%d").tolist()}
base_day = all_px.index[all_px.index <= "2023-12-31"][-1]
reb = {}
for c in COMPARE:
    p = all_px[c].dropna()
    p = p[p.index >= base_day]
    reb[c] = (p / p.iloc[0] * 100).round(2)
for k in ("sec", "csi", "div"):
    lv = px[k][px.index >= base_day]
    reb[k] = (lv / lv.iloc[0] * 100).round(2)
rb = pd.DataFrame(reb)
rb.index = rb.index.strftime("%Y-%m-%d")
res["rebased_2024"] = {"date": rb.index.tolist(), **{c: [None if pd.isna(v) else float(v) for v in rb[c]] for c in rb.columns}}

os.makedirs(OUT, exist_ok=True)
json.dump(res, open(os.path.join(OUT, "market_analysis.json"), "w"), ensure_ascii=False, indent=1)
skip = ("series", "scatter", "hist", "events", "top_abnormal_days", "peers", "rebased_2024", "by_year", "top_sector_days")
print(json.dumps({k: v for k, v in res.items() if k not in skip}, indent=1, ensure_ascii=False))
if "--events" in sys.argv:
    for e in ev_out:
        print(e["day0"], e["category"], f"{e['ret_gd']:+.1%} csi {e['ret_csi']:+.1%} sec {e['ret_sec']:+.1%} dy {e['dy10_bp']:+.1f}bp AR {e['ar']:+.1%} t={e['ar_t']:.1f}", e["title"])
    print("--- top abnormal days")
    for t in res["top_abnormal_days"]:
        print(t["date"], f"{t['ret_gd']:+.1%} csi {t['ret_csi']:+.1%} sec {t['ret_sec']:+.1%} AR {t['ar']:+.1%} t={t['ar_t']:.1f}")
    print("--- top sector days")
    for t in res["top_sector_days"]:
        print(t["date"], f"sec {t['ret_sec']:+.1%} gd {t['ret_gd']:+.1%} csi {t['ret_csi']:+.1%}")
    for p in res["peers"]:
        print(p)
    for y in res["by_year"]:
        print(y)
