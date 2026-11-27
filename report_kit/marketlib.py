"""Reusable market-analysis building blocks for single-stock research reports.

Conventions
- Prices are level series (adjusted close for stocks, total-return levels for indices) indexed by date.
- `ret` holds simple daily returns, `logret` daily log returns, `ex` daily excess returns (ret - rf_daily).
- Annualisation uses 252 trading days. Everything returned is plain floats / lists / dicts so it can be
  written to JSON with `dump_json` and read by the report page.

The functions reproduce the calculations used in the CoreWeave, Pop Mart, 3SBio and 粤高速A reports; see
scripts/analyze_market_template.py for how they fit together.
"""
import json
import math

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

TD = 252


# ---------------------------------------------------------------- loading
def read_series(path, date_col, value_col, end=None, start=None):
    """Read one numeric column of a CSV as a date-indexed Series (date part only, duplicates and junk rows dropped)."""
    df = pd.read_csv(path)
    idx = pd.to_datetime(df[date_col].astype(str).str[:10], errors="coerce")
    s = pd.Series(pd.to_numeric(df[value_col], errors="coerce").values, index=idx)
    s = s[s.index.notna()]
    s = s[~s.index.duplicated()].dropna().sort_index()
    if start:
        s = s[s.index >= pd.Timestamp(start)]
    if end:
        s = s[s.index <= pd.Timestamp(end)]
    return s


def yahoo_ticker(code, market):
    """Yahoo symbol for an exchange code: market 'A' (Shanghai .SS / Shenzhen .SZ), 'HK' (4 digits) or 'US'."""
    code = str(code)
    if market == "HK":
        return f"{int(code):04d}.HK"
    if market == "A":
        return f"{code}.{'SS' if code[0] in '69' else 'SZ'}"
    return code


def yahoo_file(ticker):
    """File name used by the fetch scripts for a Yahoo download (e.g. '^HSI' -> 'IDX_HSI.csv', '0013.HK' -> '0013_HK.csv')."""
    return "".join(ch if ch.isalnum() else "_" for ch in ticker.replace("^", "IDX_")) + ".csv"


# ---------------------------------------------------------------- panel construction
def equal_weight_returns(price_df, min_names=1):
    """Equal-weight daily simple return across columns (skipping missing names); NaN where fewer than min_names trade."""
    r = price_df.pct_change(fill_method=None)
    n = r.notna().sum(axis=1)
    return r.mean(axis=1, skipna=True).where(n >= min_names), n, r


def build_panel(prices, calendar=None, extra_returns=None, ffill_limit=5):
    """Align level series on one calendar and derive returns.

    prices: {key: level Series}; extra_returns: {key: daily return Series} for synthetic indices such as an
    equal-weight peer index. Returns (px, ret, logret); px for extra keys is a level starting at 100.
    """
    px = pd.DataFrame(prices)
    if calendar is not None:
        px = px.reindex(calendar)
    px = px.ffill(limit=ffill_limit).dropna()
    ret = px.pct_change().dropna()
    extra_returns = extra_returns or {}
    for k, r in extra_returns.items():
        ret[k] = r.reindex(ret.index)
    ret = ret.dropna()
    px = px.loc[[px.index[0]] + list(ret.index)]
    for k in extra_returns:
        px[k] = (100 * (1 + ret[k]).cumprod()).reindex(px.index)
        px.loc[px.index[0], k] = 100.0
    logret = np.log(px).diff().dropna()
    return px, ret, logret


def daily_rf(rf_annual, index):
    """Daily risk-free return from an annual rate (decimal, Series or float), aligned to index."""
    if isinstance(rf_annual, (int, float)):
        rf_annual = pd.Series(float(rf_annual), index=index)
    rf = rf_annual.reindex(index).ffill().bfill()
    return (1 + rf) ** (1 / TD) - 1


# ---------------------------------------------------------------- descriptive risk statistics
def max_drawdown(levels):
    """(max drawdown, peak date, trough date, drawdown series) for a level series."""
    peak = levels.cummax()
    dd = levels / peak - 1
    trough = dd.idxmin()
    return float(dd.min()), str(levels.loc[:trough].idxmax().date()), str(trough.date()), dd


def risk_stats(r, lr, levels, rf_d):
    """Return, volatility, tail and drawdown statistics. r simple, lr log returns, levels price/index levels."""
    q95, q99 = np.percentile(r, 5), np.percentile(r, 1)
    mdd, pk, tr, _ = max_drawdown(levels)
    excess = r - rf_d.reindex(r.index) if isinstance(rf_d, pd.Series) else r - rf_d
    down = np.sqrt((np.minimum(r, 0) ** 2).mean())
    return {
        "total_return": float(levels.iloc[-1] / levels.iloc[0] - 1),
        "ann_return_geo": float((levels.iloc[-1] / levels.iloc[0]) ** (TD / len(r)) - 1),
        "ann_vol": float(lr.std() * np.sqrt(TD)),
        "downside_dev_ann": float(down * np.sqrt(TD)),
        "skew": float(stats.skew(r)), "excess_kurtosis": float(stats.kurtosis(r)),
        "var95_hist": float(-q95), "var99_hist": float(-q99),
        "cvar95_hist": float(-r[r <= q95].mean()), "cvar99_hist": float(-r[r <= q99].mean()),
        "max_up_day": float(r.max()), "max_up_date": str(r.idxmax().date()),
        "max_down_day": float(r.min()), "max_down_date": str(r.idxmin().date()),
        "days_abs_gt_3pct": int((r.abs() > 0.03).sum()), "days_abs_gt_5pct": int((r.abs() > 0.05).sum()),
        "max_drawdown": mdd, "mdd_peak": pk, "mdd_trough": tr,
        "current_drawdown": float(levels.iloc[-1] / levels.cummax().iloc[-1] - 1),
        "sharpe": float(excess.mean() / r.std() * np.sqrt(TD)),
        "sortino": float(excess.mean() * TD / (down * np.sqrt(TD))),
    }


def top_days_variance_share(r, n=10):
    """Share of total squared deviation contributed by the n largest days (how concentrated the risk is)."""
    sq = (r - r.mean()) ** 2
    return float(sq.sort_values(ascending=False).iloc[:n].sum() / sq.sum())


def return_histogram(ret, cols, width=0.10, step=0.01):
    """Counts of daily returns per bin of `step`, clipped to +/-width (use width 0.2, step 0.02 for very volatile names)."""
    bins = np.arange(-width, width + step / 10, step)
    out = {"bins": [float(round(b, 6)) for b in bins]}
    for k in cols:
        out[k] = np.histogram(ret[k].clip(-width + 1e-4, width - 1e-4), bins=bins)[0].tolist()
    return out


# ---------------------------------------------------------------- regressions
def ols(y, x):
    return sm.OLS(y, sm.add_constant(x)).fit()


def ols_hac(y, x, lags=5):
    return sm.OLS(y, sm.add_constant(x)).fit(cov_type="HAC", cov_kwds={"maxlags": lags})


def sim(y, x, scale=TD, hac_lags=5):
    """Single-index model of excess returns y on x: beta (OLS and HAC s.e.), alpha, R², variance split."""
    m = ols(y, x)
    mh = ols_hac(y, x, hac_lags)
    beta = m.params.iloc[1]
    resid_var = m.resid.var(ddof=2)
    out = {"alpha_ann": float(m.params.iloc[0] * scale), "alpha_t": float(m.tvalues.iloc[0]),
           "beta": float(beta), "beta_se": float(m.bse.iloc[1]), "beta_se_hac": float(mh.bse.iloc[1]),
           "beta_t": float(m.tvalues.iloc[1]),
           "beta_ci95": [float(beta - 1.96 * m.bse.iloc[1]), float(beta + 1.96 * m.bse.iloc[1])],
           "r2": float(m.rsquared), "corr": float(np.corrcoef(y, x)[0, 1]),
           "total_var_ann": float(y.var() * scale), "systematic_var_ann": float(beta ** 2 * x.var() * scale),
           "resid_var_ann": float(resid_var * scale), "resid_vol_ann": float(np.sqrt(resid_var * scale)),
           "blume_beta": float(0.67 * beta + 0.33), "n": int(len(y)), "alpha_daily": float(m.params.iloc[0])}
    out["systematic_share"] = out["systematic_var_ann"] / out["total_var_ann"]
    return out


def resampled_sim(px, y, x, rf_annual=0.0, rule="W-FRI"):
    """Weekly ('W-FRI') or monthly ('ME') single-index model, a check against non-synchronous trading."""
    per = px[[y, x]].resample(rule).last().pct_change().dropna()
    n = 52 if rule.startswith("W") else 12
    if isinstance(rf_annual, pd.Series):
        rf = rf_annual.resample(rule).last().reindex(per.index).ffill().bfill() / n
    else:
        rf = float(rf_annual) / n
    return sim(per[y] - rf, per[x] - rf, scale=n)


def up_down_beta(y, x):
    up, dn = x > 0, x < 0
    return float(ols(y[up], x[up]).params.iloc[1]), float(ols(y[dn], x[dn]).params.iloc[1])


def dimson_beta(y, x):
    """Dimson (1979) beta: sum of coefficients on lagged, same-day and leading market returns (thinly traded stocks)."""
    d = pd.concat([y, x.shift(1), x, x.shift(-1)], axis=1).dropna()
    return float(ols(d.iloc[:, 0], d.iloc[:, 1:]).params.iloc[1:].sum())


def capture_and_active(r, m):
    """Up/down capture ratios, tracking error and information ratio of simple returns r against m."""
    active = r - m
    te = float(active.std() * np.sqrt(TD))
    return {"up_capture": float(r[m > 0].mean() / m[m > 0].mean()), "down_capture": float(r[m < 0].mean() / m[m < 0].mean()),
            "tracking_error": te, "information_ratio": float(active.mean() * TD / te)}


def factor_model(ex, y, mkt, sec=None, dy=None, since=None, until=None, rate_unit=0.10, hac_lags=5):
    """Market + orthogonalised sector (+ rate) model on excess returns.

    sec: column of a sector return; it enters as its residual on the market so its beta measures the
    industry-specific co-movement. dy: daily change of a yield in percentage points; rate betas are reported
    per +rate_unit (0.10 = 10bp). Returns (model used for abnormal returns, summary dict).
    """
    cols = [y, mkt] + ([sec] if sec else [])
    d = ex[cols].copy()
    if dy is not None:
        d["dy"] = dy.reindex(d.index)
    if since:
        d = d[d.index >= pd.Timestamp(since)]
    if until:
        d = d[d.index <= pd.Timestamp(until)]
    d = d.dropna()
    m1 = ols(d[y], d[[mkt]])
    out = {"since": str(d.index[0].date()), "until": str(d.index[-1].date()), "n": int(len(d)),
           "r2_mkt": float(m1.rsquared), "beta_mkt": float(m1.params[mkt])}
    model = m1
    if sec:
        d["sec_o"] = ols(d[sec], d[mkt]).resid
        m2 = ols(d[y], d[[mkt, "sec_o"]])
        out.update({"r2_two": float(m2.rsquared), "beta_mkt": float(m2.params[mkt]),
                    "beta_sec_o": float(m2.params["sec_o"]), "t_sec_o": float(m2.tvalues["sec_o"])})
        model = m2
    if dy is not None:
        m_rate = ols_hac(d[y], d[[mkt, "dy"]], hac_lags)
        out.update({"rate_beta_10bp": float(m_rate.params["dy"] * rate_unit), "rate_t": float(m_rate.tvalues["dy"])})
        if sec:
            m3 = ols_hac(d[y], d[[mkt, "sec_o", "dy"]], hac_lags)
            m_sec = ols_hac(d[sec], d[[mkt, "dy"]], hac_lags)
            out.update({"r2_three": float(m3.rsquared), "rate_beta_10bp_3f": float(m3.params["dy"] * rate_unit),
                        "rate_t_3f": float(m3.tvalues["dy"]),
                        "rate_beta_10bp_sector": float(m_sec.params["dy"] * rate_unit), "rate_t_sector": float(m_sec.tvalues["dy"])})
    return model, out


def monthly_rate_link(levels, y10, rate_unit=0.10):
    """Monthly log price change regressed on the monthly change of the yield level: (beta per +10bp, correlation)."""
    mo = pd.concat([np.log(levels.resample("ME").last()).diff().rename("p"), y10.resample("ME").last().diff().rename("dy")], axis=1).dropna()
    return float(ols(mo["p"], mo["dy"]).params.iloc[1] * rate_unit), float(mo.corr().iloc[0, 1])


# ---------------------------------------------------------------- volatility dynamics
def garch_t(logret_series):
    """GARCH(1,1) with Student-t errors on daily log returns. Returns (fit, summary)."""
    from arch import arch_model
    fit = arch_model(logret_series * 100, vol="GARCH", p=1, q=1, dist="t", mean="Constant").fit(disp="off")
    a, b, om = float(fit.params["alpha[1]"]), float(fit.params["beta[1]"]), float(fit.params["omega"])
    pers = a + b
    return fit, {"alpha": a, "beta": b, "persistence": pers,
                 "half_life_days": float(np.log(0.5) / np.log(pers)) if pers < 1 else None,
                 "long_run_vol_ann": float(np.sqrt(om / (1 - pers) * TD) / 100) if pers < 1 else None,
                 "current_cond_vol_ann": float(fit.conditional_volatility.iloc[-1] * np.sqrt(TD) / 100),
                 "nu": float(fit.params.get("nu", np.nan))}


def rolling_metrics(logret, ex, y, mkt, sec=None, dy=None, vol_win=63, beta_win=252, corr_win=126, rate_unit=0.10):
    """Rolling volatility of every column, rolling beta / correlation of y on mkt (and sec), rolling rate beta."""
    roll = pd.DataFrame(index=logret.index)
    for k in logret.columns:
        roll[f"vol{vol_win}_{k}"] = logret[k].rolling(vol_win).std() * np.sqrt(TD)
    for b in [mkt] + ([sec] if sec else []):
        roll[f"beta{beta_win}_{b}"] = ex[y].rolling(beta_win).cov(ex[b]) / ex[b].rolling(beta_win).var()
        roll[f"corr{corr_win}_{b}"] = ex[y].rolling(corr_win).corr(ex[b])
    if dy is not None:
        d = dy.reindex(ex.index)
        roll[f"rate{beta_win}"] = ex[y].rolling(beta_win).cov(d) / d.rolling(beta_win).var() * rate_unit
    return roll


def by_year(px, ret, logret, ex, y, mkt, sec=None, others=(), y10=None):
    """Calendar-year returns (from the previous year-end), volatility, betas, drawdown and the yield change."""
    cols = [y, mkt] + ([sec] if sec else []) + list(others)
    rows = []
    for yr in sorted(set(ret.index.year)):
        sel = ret.index.year == yr
        p_y = px[px.index.year == yr]
        prev = px[px.index.year < yr]
        base = prev.iloc[-1] if len(prev) else p_y.iloc[0]
        e_y = ex[sel]
        row = {"year": int(yr), "n": int(sel.sum()), **{f"ret_{k}": float(p_y[k].iloc[-1] / base[k] - 1) for k in cols},
               **{f"vol_{k}": float(logret[k][logret.index.year == yr].std() * np.sqrt(TD)) for k in cols}}
        s_m = sim(e_y[y], e_y[mkt])
        row.update({"beta_mkt": s_m["beta"], "r2_mkt": s_m["r2"], "mdd": max_drawdown(p_y[y])[0]})
        if sec:
            s_s = sim(e_y[y], e_y[sec])
            row.update({"beta_sec": s_s["beta"], "r2_sec": s_s["r2"]})
        if y10 is not None:
            yy = y10[y10.index.year == yr]
            before = y10[y10.index.year < yr]
            row.update({"y10_end": float(yy.iloc[-1]), "y10_chg": float(yy.iloc[-1] - (before.iloc[-1] if len(before) else yy.iloc[0]))})
        rows.append(row)
    return rows


# ---------------------------------------------------------------- peers
def period_return(levels, a, b):
    """Return from the last level on/before date a to the last level on/before date b (None if unavailable)."""
    s = levels.dropna()
    s0, s1 = s[s.index <= pd.Timestamp(a)], s[s.index <= pd.Timestamp(b)]
    if not len(s0) or not len(s1):
        return None
    return float(s1.iloc[-1] / s0.iloc[-1] - 1)


def peer_risk_table(all_px, peer_ret, mkt_ret, names, since, end, periods, dy=None, min_names=1, mdd_since=None, rate_unit=0.10):
    """Risk and return of the target and every peer inside the sector.

    all_px: adjusted levels of target + peers (one column per code); peer_ret: daily returns of the peers that
    make up the sector index; mkt_ret: market simple returns. Each name's sector beta is measured against the
    sector index *without that name* (leave-one-out), so a peer is not regressed on itself.
    periods: [(key, start, end)], e.g. [("ret_2025", "2024-12-31", "2025-12-31")].
    """
    rows = []
    for c in all_px.columns:
        p = all_px[c].dropna()
        if len(p) < 30:
            continue
        r_c = p.pct_change().dropna()
        loo = peer_ret.drop(columns=[c], errors="ignore")
        sec_loo = loo.mean(axis=1).where(loo.notna().sum(axis=1) >= min_names)
        parts = [r_c.rename("y"), mkt_ret.rename("mkt"), sec_loo.rename("sec")] + ([dy.rename("dy")] if dy is not None else [])
        j = pd.concat(parts, axis=1, sort=True).dropna()
        js = j[j.index >= pd.Timestamp(since)]
        j1y = j.iloc[-TD:]
        row = {"code": c, "name": names.get(c, c), "first": str(p.index[0].date()),
               "vol_1y": float(np.log(1 + j1y["y"]).std() * np.sqrt(TD)),
               "vol_since": float(np.log(1 + js["y"]).std() * np.sqrt(TD)),
               "beta_mkt": float(ols(js["y"], js["mkt"]).params.iloc[1]),
               "beta_sec": float(ols(js["y"], js["sec"]).params.iloc[1]),
               "corr_sec": float(js[["y", "sec"]].corr().iloc[0, 1]),
               "dd_from_high": float(p.iloc[-1] / p.max() - 1), "high_date": str(p.idxmax().date())}
        if dy is not None:
            row["rate_10bp"] = float(ols(js["y"], js[["mkt", "dy"]]).params["dy"] * rate_unit)
        for key, a, b in periods:
            row[key] = period_return(p, a, b)
        row["ret_3y"] = period_return(p, str((pd.Timestamp(end) - pd.DateOffset(years=3)).date()), end)
        if mdd_since:
            row["mdd_since"] = max_drawdown(p[p.index >= pd.Timestamp(mdd_since)])[0]
        rows.append(row)
    return rows


def rank_of(rows, key, code, descending=True):
    """1-based rank of `code` among rows by `key` (None values excluded) and the number ranked."""
    vals = [(r[key], r["code"]) for r in rows if r.get(key) is not None]
    vals.sort(key=lambda t: t[0], reverse=descending)
    for i, (_, c) in enumerate(vals, 1):
        if c == code:
            return i, len(vals)
    return None, len(vals)


# ---------------------------------------------------------------- event study
def abnormal_returns(ex, y, mkt, sec=None):
    """Full-sample market (+ orthogonalised sector) model; returns (abnormal returns, residual s.d., model)."""
    if sec:
        f_sec = ols(ex[sec], ex[mkt]).resid
        m = ols(ex[y], pd.concat([ex[mkt], f_sec.rename("sec_o")], axis=1))
        pred = m.params["const"] + m.params[mkt] * ex[mkt] + m.params["sec_o"] * f_sec
        sd = float(m.resid.std(ddof=3))
    else:
        m = ols(ex[y], ex[[mkt]])
        pred = m.params["const"] + m.params[mkt] * ex[mkt]
        sd = float(m.resid.std(ddof=2))
    return ex[y] - pred, sd, m


def event_table(events, abn, resid_sd, ret, cols, dy=None, raw_close=None, post=5, pre=5):
    """Day-0 reaction and abnormal returns for each event.

    events: dicts with at least 'date' (YYYY-MM-DD). Day 0 is the first trading day on/after that date, so put
    the date of the first session in which the market could react (next day for after-close announcements).
    cols: {output name: ret column}, e.g. {"ret_tgt": "tgt", "ret_mkt": "mkt", "ret_sec": "sec"}.
    """
    dates = ret.index
    last = len(dates) - 1
    out = []
    for ev in events:
        pos = dates.searchsorted(pd.Timestamp(ev["date"]))
        if pos > last:
            continue
        row = {**ev, "day0": str(dates[pos].date()), **{k: float(ret[c].iloc[pos]) for k, c in cols.items()},
               "ar": float(abn.iloc[pos]), "ar_t": float(abn.iloc[pos] / resid_sd),
               f"car_0_p{post}": float(abn.iloc[pos:min(pos + post, last) + 1].sum()),
               f"car_m{pre}_p{post}": float(abn.iloc[max(pos - pre, 0):min(pos + post, last) + 1].sum())}
        if dy is not None:
            row["dy10_bp"] = float(dy.reindex(dates).iloc[pos] * 100)
        if raw_close is not None:
            row["price_day0"] = float(raw_close.reindex([dates[pos]]).iloc[0])
        out.append(row)
    return out


def top_days(series, n, fields):
    """Largest absolute values of `series` with the matching values of other series: fields = {name: Series}."""
    top = series.abs().sort_values(ascending=False).iloc[:n]
    return [{"date": str(d.date()), **{k: float(s[d]) for k, s in fields.items()}} for d in top.index]


def earnings_move(ret_y, earnings_day0s):
    """Average absolute return on earnings reaction days vs all other days."""
    mask = ret_y.index.strftime("%Y-%m-%d").isin(list(earnings_day0s))
    return (float(ret_y[mask].abs().mean()) if mask.any() else None), float(ret_y[~mask].abs().mean())


def car_by_year(abn):
    return {str(y): float(abn[abn.index.year == y].sum()) for y in sorted(set(abn.index.year))}


def ex_dividend_table(dividends, ret, abn, raw_close, y, sec=None, post=5):
    """Record-day and ex-day returns around each cash dividend. dividends: [(ex_date, dps)] in the stock's currency.

    With dividend-adjusted prices the ex-day return already adds the dividend back, so a negative ex-day return
    means the price fell by more than the dividend.
    """
    dates = ret.index
    last = len(dates) - 1
    rows = []
    for ex_s, dps in dividends:
        ex_day = pd.Timestamp(ex_s)
        if ex_day < dates[1] or ex_day > dates[-1]:
            continue
        pos = dates.searchsorted(ex_day)
        prev_close = float(raw_close.reindex([dates[pos - 1]]).iloc[0])
        row = {"ex_date": str(dates[pos].date()), "record_date": str(dates[pos - 1].date()), "dps": float(dps),
               "dps_yield": float(dps) / prev_close, "ret_record": float(ret[y].iloc[pos - 1]), "ar_record": float(abn.iloc[pos - 1]),
               "ret_ex": float(ret[y].iloc[pos]), "ar_ex": float(abn.iloc[pos]),
               "car_ex_p5": float(abn.iloc[pos:min(pos + post, last) + 1].sum())}
        if sec:
            row["ret_sec_ex"] = float(ret[sec].iloc[pos])
        rows.append(row)
    summary = {"n": len(rows), "n_neg": int(sum(r["ret_ex"] < 0 for r in rows)),
               "avg_ret_ex": float(np.mean([r["ret_ex"] for r in rows])) if rows else None,
               "avg_ar_ex": float(np.mean([r["ar_ex"] for r in rows])) if rows else None,
               "avg_ret_record": float(np.mean([r["ret_record"] for r in rows])) if rows else None}
    return rows, summary


# ---------------------------------------------------------------- valuation helpers
def dividend_yield_spread(dps_by_announcement, raw_close, y10_pct):
    """Trailing dividend yield on the latest *announced* annual DPS and its spread over a bond yield (in pp).

    dps_by_announcement: Series of annual DPS indexed by the date the market learned it (plan announcement).
    """
    dps = dps_by_announcement.sort_index()
    dps_t = dps.reindex(dps.index.union(raw_close.index)).ffill().reindex(raw_close.index)
    dy = dps_t / raw_close
    return dy, dy * 100 - y10_pct.reindex(raw_close.index).ffill()


def percentile_rank(series):
    """Share of history at or below the latest value (e.g. P/E percentile since the series began)."""
    s = series.dropna()
    return float((s <= s.iloc[-1]).mean())


def atm_iv_term(options, spot, band=0.06, min_oi=50):
    """Median at-the-money implied volatility per expiry from a Yahoo option-chain dump (columns: expiry, strike,
    impliedVolatility, openInterest)."""
    term = []
    for ex_, g in options.groupby("expiry"):
        g = g[(g.impliedVolatility > 0.05) & (g.openInterest.fillna(0) > min_oi)]
        atm = g[(g.strike - spot).abs() <= spot * band]
        if len(atm):
            term.append({"expiry": ex_, "atm_iv": float(atm.impliedVolatility.median()), "n": int(len(atm))})
    return term


def cds_default_prob(spread_bp, recovery=0.4, years=5):
    """Risk-neutral cumulative default probability implied by a CDS spread (constant hazard)."""
    lam = spread_bp / 1e4 / (1 - recovery)
    return float(1 - math.exp(-lam * years))


def merton_pd(E, sigma_E, D, r, T=1.0, iters=200):
    """Merton model: solve asset value and volatility from equity value/volatility; return (distance to default, PD)."""
    from scipy.stats import norm
    V, sV = E + D, sigma_E * E / (E + D)
    for _ in range(iters):
        d1 = (math.log(V / D) + (r + 0.5 * sV ** 2) * T) / (sV * math.sqrt(T))
        d2 = d1 - sV * math.sqrt(T)
        V_new = (E + D * math.exp(-r * T) * norm.cdf(d2)) / norm.cdf(d1)
        sV = sigma_E * E / (norm.cdf(d1) * V_new)
        if abs(V_new - V) < 1e-6 * V:
            V = V_new
            break
        V = V_new
    d2 = (math.log(V / D) + (r - 0.5 * sV ** 2) * T) / (sV * math.sqrt(T))
    return float(d2), float(norm.cdf(-d2))


# ---------------------------------------------------------------- output
def series_payload(df, digits=5):
    """{"date": [...], col: [...]} with NaN as None, for chart series."""
    out = {"date": df.index.strftime("%Y-%m-%d").tolist()}
    for c in df.columns:
        out[c] = [None if pd.isna(v) else round(float(v), digits) for v in df[c]]
    return out


def clean(obj):
    """Convert numpy scalars / NaN / Timestamps recursively into JSON-safe values."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj.date())
    return obj


def dump_json(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean(obj), f, ensure_ascii=False, indent=1)
