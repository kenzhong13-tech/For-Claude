"""Is there room for volatility arbitrage in 百胜中国? Writes data/processed/volarb.json.

Volatility arbitrage means trading options (or variance) against a forecast of realised volatility, delta-hedged,
to earn the gap between implied and realised volatility. It needs (1) a liquid options market, (2) a gap between
implied and forecast realised volatility that is stable or predictable, (3) a gap larger than the trading costs,
and (4) a way to carry the tail risk (earnings gaps). This script measures each one:
- market structure: listed options exist on the NYSE line (YUMC); whether HKEX lists options on 9987
- realised volatility: close-to-close, Parkinson, Garman-Klass, Rogers-Satchell, Yang-Zhang; a volatility cone
- forecasts: GARCH(1,1)-t, GJR-GARCH-t and HAR-RV, with an out-of-sample test against a random walk (QLIKE, MSE,
  Diebold-Mariano, Mincer-Zarnowitz)
- implied volatility: the YUMC option-chain snapshot (CBOE delayed quotes, Yahoo as a fallback): ATM term
  structure, 25-delta skew, liquidity and bid-ask spreads in volatility points, the earnings move priced in
- implied-volatility history when one of the fetch routes returned it: the variance risk premium and a short
  variance-swap back-test
- earnings: historical reaction-day moves against the implied move
- the cross-listing: HK price in USD against the NYSE close (premium, ADF, half-life), lead-lag between the two
  sessions (does one market's close predict the other's open-to-close return?), volatility of the two lines
"""
import glob
import json
import math
import os
import re
import sys
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.tsa.stattools import adfuller, kpss

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
sys.path.insert(0, os.path.join(ROOT, "..", "report_kit"))
import marketlib as ml  # noqa: E402

warnings.simplefilter("ignore")
TD = 252
OPT = os.path.join(RAW, "options")
US_START, HK_START = "2016-11-01", "2020-09-10"


def rnd(x, d=4):
    try:
        return None if x is None or not math.isfinite(float(x)) else round(float(x), d)
    except (TypeError, ValueError):
        return None


def ohlc(ticker):
    path = os.path.join(RAW, "yahoo", ml.yahoo_file(ticker))
    d = pd.read_csv(path)
    d.index = pd.to_datetime(d["Date"].astype(str).str[:10])
    d = d[~d.index.duplicated()].sort_index()
    for c in ("Open", "High", "Low", "Close", "Adj Close", "Volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["Close"])
    f = d["Adj Close"] / d["Close"]  # dividend adjustment applied to every price field
    for c in ("Open", "High", "Low", "Close"):
        d[c + "_a"] = d[c] * f
    return d


def series(ticker, col="Adj Close"):
    path = os.path.join(RAW, "yahoo", ml.yahoo_file(ticker))
    return ml.read_series(path, "Date", col) if os.path.exists(path) and os.path.getsize(path) > 0 else None


# ---------------------------------------------------------------- realised-volatility estimators (daily variances)
def daily_components(d):
    o = np.log(d["Open_a"] / d["Close_a"].shift(1))          # overnight
    c = np.log(d["Close_a"] / d["Open_a"])                   # open to close
    cc = np.log(d["Close_a"] / d["Close_a"].shift(1))        # close to close
    hl = np.log(d["High_a"] / d["Low_a"])
    hc, ho = np.log(d["High_a"] / d["Close_a"]), np.log(d["High_a"] / d["Open_a"])
    lc, lo = np.log(d["Low_a"] / d["Close_a"]), np.log(d["Low_a"] / d["Open_a"])
    park = hl ** 2 / (4 * math.log(2))
    gk = 0.5 * hl ** 2 - (2 * math.log(2) - 1) * c ** 2
    rs = hc * ho + lc * lo
    ok = (d["High_a"] >= d["Low_a"]) & (d["Open_a"] > 0)
    return pd.DataFrame({"o": o, "c": c, "cc": cc, "park": park, "gk": gk, "rs": rs}).where(ok).dropna()


def yang_zhang(comp, n):
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    so = comp["o"].rolling(n).var()
    sc = comp["c"].rolling(n).var()
    srs = comp["rs"].rolling(n).mean()
    return np.sqrt((so + k * sc + (1 - k) * srs) * TD)


def estimators_now(comp, n=21):
    tail = comp.iloc[-n:]
    return {"close_to_close": rnd(tail["cc"].std() * math.sqrt(TD)), "parkinson": rnd(math.sqrt(tail["park"].mean() * TD)),
            "garman_klass": rnd(math.sqrt(tail["gk"].mean() * TD)), "rogers_satchell": rnd(math.sqrt(max(tail["rs"].mean(), 0) * TD)),
            "yang_zhang": rnd(yang_zhang(comp, n).iloc[-1]), "overnight_share": rnd((tail["o"] ** 2).sum() / (tail["cc"] ** 2).sum(), 3)}


def vol_cone(cc, windows=(10, 21, 42, 63, 126, 252)):
    rows = []
    for w in windows:
        v = cc.rolling(w).std().dropna() * math.sqrt(TD)
        rows.append({"window": w, "min": rnd(v.min()), "p10": rnd(v.quantile(0.10)), "p25": rnd(v.quantile(0.25)),
                     "p50": rnd(v.median()), "p75": rnd(v.quantile(0.75)), "p90": rnd(v.quantile(0.90)), "max": rnd(v.max()),
                     "now": rnd(v.iloc[-1]), "pct_now": rnd((v <= v.iloc[-1]).mean(), 3)})
    return rows


# ---------------------------------------------------------------- forecasting models
def garch_forecast(lr, h, kind="GARCH"):
    from arch import arch_model
    o = 1 if kind == "GJR" else 0
    fit = arch_model(lr * 100, vol="GARCH", p=1, o=o, q=1, dist="t", mean="Constant").fit(disp="off")
    f = fit.forecast(horizon=h, reindex=False).variance.values[-1]
    return float(math.sqrt(f.mean() * TD) / 100), fit


def har_design(rv):
    return pd.DataFrame({"d": rv, "w": rv.rolling(5).mean(), "m": rv.rolling(22).mean()})


def har_fit(rv, h=21):
    X = har_design(rv)
    y = rv[::-1].rolling(h).mean()[::-1].shift(-1)  # mean of the next h days
    j = pd.concat([y.rename("y"), X], axis=1).dropna()
    m = sm.OLS(j["y"], sm.add_constant(j[["d", "w", "m"]])).fit(cov_type="HAC", cov_kwds={"maxlags": h})
    return m


def har_forecast(rv, h=21):
    m = har_fit(rv, h)
    x = har_design(rv).iloc[-1]
    f = float(m.params["const"] + m.params["d"] * x["d"] + m.params["w"] * x["w"] + m.params["m"] * x["m"])
    return math.sqrt(max(f, 1e-8) * TD), m


def oos_evaluation(lr, rv, h=21, start="2019-01-01", step=21):
    """Expanding-window forecasts of the next h-day realised variance every `step` days (non-overlapping targets)."""
    from arch import arch_model
    idx = lr.index
    pos0 = idx.searchsorted(pd.Timestamp(start))
    rows = []
    for pos in range(pos0, len(idx) - h, step):
        train = lr.iloc[:pos]
        target = float((lr.iloc[pos:pos + h] ** 2).mean())  # realised variance, daily units
        rw = float((train.iloc[-h:] ** 2).mean())
        try:
            fit = arch_model(train * 100, vol="GARCH", p=1, q=1, dist="t", mean="Constant").fit(disp="off")
            g = float(fit.forecast(horizon=h, reindex=False).variance.values[-1].mean() / 1e4)
        except Exception:  # noqa: BLE001
            g = np.nan
        rv_tr = rv[rv.index < idx[pos]]
        try:
            m = har_fit(rv_tr, h)
            x = har_design(rv_tr).iloc[-1]
            hf = float(m.params["const"] + m.params["d"] * x["d"] + m.params["w"] * x["w"] + m.params["m"] * x["m"])
        except Exception:  # noqa: BLE001
            hf = np.nan
        rows.append({"date": idx[pos], "target": target, "rw": rw, "garch": g, "har": max(hf, 1e-8) if np.isfinite(hf) else np.nan})
    df = pd.DataFrame(rows).set_index("date").dropna()

    def qlike(f, y):
        return y / f - np.log(y / f) - 1

    out = {"n": int(len(df)), "h": h, "start": str(df.index[0].date()), "end": str(df.index[-1].date()), "models": {}}
    for k in ("rw", "garch", "har"):
        e_vol = np.sqrt(df[k] * TD) - np.sqrt(df["target"] * TD)
        mz = sm.OLS(df["target"], sm.add_constant(df[k])).fit(cov_type="HC1")
        out["models"][k] = {"rmse_vol": rnd(np.sqrt((e_vol ** 2).mean())), "mae_vol": rnd(e_vol.abs().mean()), "bias_vol": rnd(e_vol.mean()),
                            "qlike": rnd(qlike(df[k], df["target"]).mean()), "mz_a": rnd(mz.params.iloc[0] * TD), "mz_b": rnd(mz.params.iloc[1], 3),
                            "mz_r2": rnd(mz.rsquared, 3)}
    for k in ("garch", "har"):  # Diebold-Mariano on the QLIKE loss differential (non-overlapping, so plain s.e.)
        dlt = qlike(df[k], df["target"]) - qlike(df["rw"], df["target"])
        t = dlt.mean() / (dlt.std(ddof=1) / math.sqrt(len(dlt)))
        out["models"][k]["dm_vs_rw_t"] = rnd(t, 3)
        out["models"][k]["dm_vs_rw_p"] = rnd(2 * stats.norm.sf(abs(t)))
    out["series"] = {"date": [str(d.date()) for d in df.index], **{k: [rnd(math.sqrt(v * TD)) for v in df[k]] for k in ("target", "rw", "garch", "har")}}
    return out


# ---------------------------------------------------------------- option chain
def parse_osi(sym):
    m = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", sym.strip())
    if not m:
        return None
    root, ymd, cp, k = m.groups()
    return root, pd.Timestamp(f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:]}"), "call" if cp == "C" else "put", int(k) / 1000


def load_chain():
    """Option chain as a DataFrame: expiry, type, strike, bid, ask, iv, oi, volume, delta, vega; plus spot and time."""
    path = os.path.join(OPT, "cboe_options_YUMC.json")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        js = json.load(open(path))
        data = js.get("data", js)
        rows = []
        for o in data.get("options", []):
            p = parse_osi(o.get("option", ""))
            if not p:
                continue
            rows.append({"expiry": p[1], "type": p[2], "strike": p[3], "bid": o.get("bid"), "ask": o.get("ask"), "iv": o.get("iv"),
                         "oi": o.get("open_interest"), "volume": o.get("volume"), "delta": o.get("delta"), "vega": o.get("vega"),
                         "last": o.get("last_trade_price")})
        df = pd.DataFrame(rows)
        spot = data.get("current_price") or data.get("close")
        ts = js.get("timestamp") or data.get("last_trade_time")
        return df, float(spot), str(ts), "CBOE", {k: data.get(k) for k in ("iv30", "iv30_change", "close", "prev_day_close", "current_price") if k in data}
    path = os.path.join(OPT, "yumc_options_yahoo.csv")
    y = pd.read_csv(path)
    df = pd.DataFrame({"expiry": pd.to_datetime(y["expiry"]), "type": y["type"], "strike": y["strike"], "bid": y["bid"], "ask": y["ask"],
                       "iv": y["impliedVolatility"], "oi": y["openInterest"], "volume": y["volume"], "delta": np.nan, "vega": np.nan,
                       "last": y["lastPrice"]})
    spot = float(series("YUMC", "Close").iloc[-1])
    return df, spot, str(y["snapshot_utc"].iloc[0]), "Yahoo", {}


def bs_delta_vega(S, K, T, sigma, r, q, kind):
    if not (S > 0 and K > 0 and T > 0 and sigma > 0):
        return np.nan, np.nan
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    nd1 = stats.norm.pdf(d1)
    delta = math.exp(-q * T) * (stats.norm.cdf(d1) if kind == "call" else stats.norm.cdf(d1) - 1)
    vega = S * math.exp(-q * T) * nd1 * math.sqrt(T) / 100  # per 1 vol point
    return delta, vega


def bs_price(S, K, T, r, q, sig, kind):
    d1 = (math.log(S / K) + (r - q + 0.5 * sig ** 2) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    if kind == "call":
        return S * math.exp(-q * T) * stats.norm.cdf(d1) - K * math.exp(-r * T) * stats.norm.cdf(d2)
    return K * math.exp(-r * T) * stats.norm.cdf(-d2) - S * math.exp(-q * T) * stats.norm.cdf(-d1)


def implied_vol(price, S, K, T, r, q, kind):
    """Black-Scholes implied volatility (continuous dividend yield); None when the price is outside no-arbitrage bounds."""
    from scipy.optimize import brentq
    lo, hi = 0.01, 4.0
    try:
        if not (bs_price(S, K, T, r, q, lo, kind) < price < bs_price(S, K, T, r, q, hi, kind)):
            return None
        return brentq(lambda v: bs_price(S, K, T, r, q, v, kind) - price, lo, hi, xtol=1e-6)
    except (ValueError, ZeroDivisionError):
        return None


def chain_summary(df, spot, asof, r=0.04, q=0.02):
    """Per expiry: ATM implied vol from mid quotes of the out-of-the-money put and call next to the forward (IVs are
    recomputed with Black-Scholes, because Yahoo's IV field mixes stale last prices), the bid-ask band in vol points,
    25-delta put and call IVs, open interest and volume."""
    df = df.copy()
    for c in ("bid", "ask", "oi", "volume", "strike"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["T"] = (df["expiry"] - asof).dt.days / 365.0
    df = df[df["T"] > 2 / 365].copy()
    df["mid"] = (df["bid"] + df["ask"]) / 2
    term = []
    for ex_, g in df.groupby("expiry"):
        T = float(g["T"].iloc[0])
        F = spot * math.exp((r - q) * T)
        g = g[(g["bid"] > 0) & (g["ask"] > g["bid"])].copy()
        g = g[((g["type"] == "put") & (g["strike"] < F)) | ((g["type"] == "call") & (g["strike"] >= F))]  # OTM only
        if g.empty:
            continue
        g["iv_mid"] = [implied_vol(m, spot, k, T, r, q, ty) for m, k, ty in zip(g["mid"], g["strike"], g["type"])]
        g["iv_bid"] = [implied_vol(m, spot, k, T, r, q, ty) for m, k, ty in zip(g["bid"], g["strike"], g["type"])]
        g["iv_ask"] = [implied_vol(m, spot, k, T, r, q, ty) for m, k, ty in zip(g["ask"], g["strike"], g["type"])]
        g = g[g["iv_mid"].notna()]
        if g.empty:
            continue
        g["delta"] = [bs_delta_vega(spot, k, T, v, r, q, ty)[0] for k, v, ty in zip(g["strike"], g["iv_mid"], g["type"])]
        g["vega"] = [bs_delta_vega(spot, k, T, v, r, q, ty)[1] for k, v, ty in zip(g["strike"], g["iv_mid"], g["type"])]
        put = g[g["type"] == "put"].sort_values("strike").tail(1)
        call = g[g["type"] == "call"].sort_values("strike").head(1)
        pts = pd.concat([put, call])
        if len(pts) == 2:
            k1, k2 = float(put["strike"].iloc[0]), float(call["strike"].iloc[0])
            w = (F - k1) / (k2 - k1)
            atm = float(put["iv_mid"].iloc[0] * (1 - w) + call["iv_mid"].iloc[0] * w)
        else:
            atm = float(pts["iv_mid"].iloc[0])
        band = pts.dropna(subset=["iv_bid", "iv_ask"])
        volpts = float((band["iv_ask"] - band["iv_bid"]).mean()) if len(band) else None
        puts, calls = g[g["type"] == "put"].sort_values("delta"), g[g["type"] == "call"].sort_values("delta")
        iv25p = float(np.interp(-0.25, puts["delta"], puts["iv_mid"])) if len(puts) >= 2 and puts["delta"].min() <= -0.25 <= puts["delta"].max() else None
        iv25c = float(np.interp(0.25, calls["delta"], calls["iv_mid"])) if len(calls) >= 2 and calls["delta"].min() <= 0.25 <= calls["delta"].max() else None
        allx = df[df["expiry"] == ex_]
        term.append({"expiry": str(ex_.date()), "days": int(round(T * 365)), "forward": rnd(F, 2), "atm_iv": rnd(atm),
                     "atm_strikes": [rnd(v, 2) for v in pts["strike"]], "iv25_put": rnd(iv25p), "iv25_call": rnd(iv25c),
                     "rr25": rnd(iv25c - iv25p) if iv25p is not None and iv25c is not None else None,
                     "oi": int(allx["oi"].fillna(0).sum()), "volume": int(allx["volume"].fillna(0).sum()), "n_quoted": int(len(g)),
                     "atm_rel_spread": rnd(float(((pts["ask"] - pts["bid"]) / pts["mid"]).mean())), "atm_spread_volpts": rnd(volpts),
                     "smile": [{"k": rnd(k, 2), "type": ty, "iv": rnd(v)} for k, ty, v in zip(g["strike"], g["type"], g["iv_mid"])]})
    tot = {"oi": int(df["oi"].fillna(0).sum()), "volume": int(df["volume"].fillna(0).sum()), "n_contracts": int(len(df)),
           "n_expiries": int(df["expiry"].nunique()),
           "oi_call": int(df.loc[df["type"] == "call", "oi"].fillna(0).sum()), "oi_put": int(df.loc[df["type"] == "put", "oi"].fillna(0).sum()),
           "n_two_sided": int(((df["bid"] > 0) & (df["ask"] > df["bid"])).sum())}
    return term, tot


def event_variance(term, earn_day):
    """Earnings move priced in: total variance to the first expiry after the event minus diffusive variance
    (taken from the last expiry before it)."""
    e = pd.Timestamp(earn_day)
    before = [t for t in term if pd.Timestamp(t["expiry"]) < e and t["atm_iv"]]
    after = [t for t in term if pd.Timestamp(t["expiry"]) >= e and t["atm_iv"]]
    if not before or not after:
        return None
    t1, t2 = before[-1], after[0]
    s1, s2, T2 = t1["atm_iv"], t2["atm_iv"], t2["days"] / 365
    v = (s2 ** 2 - s1 ** 2) * T2
    sd = math.sqrt(v) if v > 0 else 0.0
    return {"before": t1["expiry"], "after": t2["expiry"], "iv_before": s1, "iv_after": s2, "event_sd": rnd(sd),
            "event_abs_move": rnd(sd * math.sqrt(2 / math.pi)), "earn_day": earn_day}


# ---------------------------------------------------------------- implied-volatility history (if a fetch route worked)
MANUAL_IV = os.path.join(RAW, "manual", "yumc_iv30.csv")  # user-supplied history: columns date,iv30 (decimal or percent)


def iv_history():
    """Daily 30-day implied volatility: a user-supplied file first, then alphaquery or Barchart dumps; None if none has a year of data."""
    cands = []
    if os.path.exists(MANUAL_IV):
        m = pd.read_csv(MANUAL_IV, parse_dates=["date"]).set_index("date")["iv30"].dropna().astype(float).sort_index()
        if m.median() > 3:  # percent units
            m = m / 100
        if len(m) > 250:
            cands.append((MANUAL_IV, m))
    for path in sorted(glob.glob(os.path.join(OPT, "alphaquery_iv-mean.json")) + glob.glob(os.path.join(OPT, "barchart_hist_iv.json"))):
        try:
            js = json.load(open(path))
        except Exception:  # noqa: BLE001
            continue
        rows = js if isinstance(js, list) else js.get("data") or js.get("results") or []
        pts = []
        for r in rows if isinstance(rows, list) else []:
            if not isinstance(r, dict):
                continue
            r = r.get("raw", r)
            d = r.get("date") or r.get("tradeTime") or r.get("x")
            v = r.get("value") or r.get("impliedVolatility") or r.get("y")
            if d is not None and v is not None:
                pts.append((pd.to_datetime(str(d)[:10], errors="coerce"), float(v)))
        s = pd.Series({d: v for d, v in pts if d is not pd.NaT}).sort_index()
        if len(s) > 250:
            if s.median() > 3:  # percent units
                s = s / 100
            cands.append((path, s))
    return cands[0] if cands else (None, None)


# ================================================================ run
res = {}
us, hk = ohlc("YUMC"), ohlc("9987.HK")
us = us[us.index >= US_START]
hk = hk[hk.index >= HK_START]
fx = series("HKD=X", "Close")  # HKD per USD
comp_us, comp_hk = daily_components(us), daily_components(hk)
res["sample"] = {"us": [str(us.index[0].date()), str(us.index[-1].date()), int(len(us))], "hk": [str(hk.index[0].date()), str(hk.index[-1].date()), int(len(hk))]}

# ---- 1. realised volatility now, cones
res["rv_now"] = {"us": estimators_now(comp_us), "hk": estimators_now(comp_hk), "window": 21}
res["cone_us"] = vol_cone(comp_us["cc"])
res["cone_hk"] = vol_cone(comp_hk["cc"])
yz_us = yang_zhang(comp_us, 21)
cc21_us = comp_us["cc"].rolling(21).std() * math.sqrt(TD)

# ---- 2. forecasts (US line, horizons to match option expiries)
lr_us = comp_us["cc"]
rv_us = comp_us["o"] ** 2 + comp_us["gk"].clip(lower=0)  # daily variance proxy: overnight + Garman-Klass intraday
fc = {}
for h in (5, 21, 42, 63, 126):
    g, gfit = garch_forecast(lr_us, h)
    gj, _ = garch_forecast(lr_us, h, "GJR")
    hv, hm = har_forecast(rv_us, h)
    fc[str(h)] = {"garch": rnd(g), "gjr": rnd(gj), "har": rnd(hv)}
res["forecast"] = fc
res["garch_us"] = {k: rnd(v, 4) for k, v in gfit.params.items()}
res["garch_us"]["persistence"] = rnd(gfit.params["alpha[1]"] + gfit.params["beta[1]"], 4)
hm21 = har_fit(rv_us, 21)
res["har_us"] = {"params": {k: rnd(v, 4) for k, v in hm21.params.items()}, "t": {k: rnd(v, 2) for k, v in hm21.tvalues.items()}, "r2": rnd(hm21.rsquared, 3)}
res["oos"] = oos_evaluation(lr_us, rv_us, h=21)

# ---- 3. options snapshot
try:
    chain, spot, ts, src, quote = load_chain()
    asof = pd.Timestamp(str(us.index[-1].date()))  # quotes are from the last US close
    r_now = float(series("^IRX", "Close").dropna().iloc[-1]) / 100
    dv = pd.read_csv(os.path.join(RAW, "yahoo", "YUMC_dividends.csv"))
    q_now = float(dv.iloc[-4:, 1].sum()) / spot  # trailing four quarterly dividends
    term, tot = chain_summary(chain, spot, asof, r_now, q_now)
    res["options"] = {"source": src, "snapshot": ts, "asof_close": str(asof.date()), "spot": rnd(spot, 2), "r": rnd(r_now), "q": rnd(q_now),
                      "term": term, "totals": tot,
                      "quote": {k: rnd(v) if isinstance(v, (int, float)) else v for k, v in quote.items()}}
    adv = float((us["Volume"].iloc[-63:]).mean())
    res["options"]["stock_adv_shares_3m"] = rnd(adv, 0)
    res["options"]["oi_in_shares_vs_adv"] = rnd(tot["oi"] * 100 / adv, 2)
except Exception as e:  # noqa: BLE001
    res["options"] = {"error": repr(e)[:300]}
# HKEX: is there a stock-option class on 9987?
hk_cls = os.path.join(OPT, "hkex_stock_option_classes.html")
hits = {}
if os.path.exists(hk_cls):
    txt = open(hk_cls, encoding="utf-8", errors="ignore").read()
    hits["class_page_bytes"] = len(txt)
    hits["class_page_yum"] = len(re.findall(r"Yum China|YUM CHINA|9987", txt))
for p in glob.glob(os.path.join(OPT, "hkex_dqe*.htm.gz")):
    import gzip
    t = gzip.open(p).read().decode("latin-1")
    hits["dqe_file"] = os.path.basename(p)
    hits["dqe_bytes"] = len(t)
    hits["dqe_yum"] = len(re.findall(r"YUM", t))
    # the report opens with an index of every option class (HKATS codes); the class summary gives code, name, stock code
    hits["dqe_n_classes"] = len(set(re.findall(r'<A HREF="#([A-Z0-9]{3})">', t)) - {"SUMMARY"})
    hits["dqe_has_9987"] = bool(re.search(r"\(09987\)", t))
res["hkex_options"] = hits

# ---- 4. implied-volatility history: variance risk premium and a short variance-swap back-test
src_iv, iv = iv_history()
if iv is not None:
    iv = iv[iv.index >= US_START]
    rv_fwd = (lr_us[::-1].rolling(21).apply(lambda x: math.sqrt((x ** 2).mean() * TD), raw=True)[::-1]).shift(-1)
    j = pd.concat([iv.rename("iv"), rv_fwd.rename("rv_fwd"), cc21_us.rename("rv_past")], axis=1).dropna()
    gap = j["iv"] - j["rv_fwd"]
    nw = sm.OLS(gap, np.ones(len(gap))).fit(cov_type="HAC", cov_kwds={"maxlags": 21})
    monthly = j.resample("ME").first()  # one short variance swap per month, struck at that day's IV
    pnl = (monthly["iv"] ** 2 - monthly["rv_fwd"] ** 2) / (2 * monthly["iv"])  # vega-notional P&L in vol points
    res["vrp"] = {"source": os.path.basename(src_iv), "n_days": int(len(j)), "start": str(j.index[0].date()), "end": str(j.index[-1].date()),
                  "mean_iv": rnd(j["iv"].mean()), "mean_rv_fwd": rnd(j["rv_fwd"].mean()), "mean_gap": rnd(gap.mean()), "t_nw": rnd(nw.tvalues.iloc[0], 3),
                  "p_nw": rnd(nw.pvalues.iloc[0]), "share_positive": rnd((gap > 0).mean(), 3),
                  "corr_iv_rvfwd": rnd(j[["iv", "rv_fwd"]].corr().iloc[0, 1], 3), "corr_rvpast_rvfwd": rnd(j[["rv_past", "rv_fwd"]].corr().iloc[0, 1], 3),
                  "swap": {"n": int(pnl.notna().sum()), "mean": rnd(pnl.mean()), "sd": rnd(pnl.std()), "sharpe_ann": rnd(pnl.mean() / pnl.std() * math.sqrt(12), 3),
                           "worst": rnd(pnl.min()), "worst_month": str(pnl.idxmin().date())[:7] if pnl.notna().any() else None,
                           "share_positive": rnd((pnl > 0).mean(), 3)},
                  "series": {"date": [str(d.date()) for d in j.index[::5]], "iv": [rnd(v) for v in j["iv"][::5]], "rv_fwd": [rnd(v) for v in j["rv_fwd"][::5]]}}
else:
    res["vrp"] = None

# ---- 4b. the last three months of 30-day implied volatility (alphaquery's free chart data covers only ~3 months)
aq = os.path.join(OPT, "alphaquery_iv-mean.json")
if os.path.exists(aq):
    pts = [(pd.Timestamp(d["x"][:10]), d["value"]) for d in json.load(open(aq)) if d.get("value") is not None]
    iv30 = pd.Series({d: v for d, v in pts}).sort_index()
    rv21 = cc21_us.reindex(iv30.index)
    pre = iv30[iv30.index < "2026-11-03"]
    post = iv30[iv30.index >= "2026-11-03"]
    res["iv30_recent"] = {"source": "alphaquery（30 天平均隐含波动率）", "start": str(iv30.index[0].date()), "end": str(iv30.index[-1].date()),
                          "n": int(len(iv30)), "last": rnd(iv30.iloc[-1]), "mean": rnd(iv30.mean()), "min": rnd(iv30.min()), "max": rnd(iv30.max()),
                          "max_date": str(iv30.idxmax().date()), "pre_earnings_last": rnd(pre.iloc[-1]) if len(pre) else None,
                          "pre_earnings_date": str(pre.index[-1].date()) if len(pre) else None,
                          "post_earnings_first": rnd(post.iloc[0]) if len(post) else None, "post_earnings_date": str(post.index[0].date()) if len(post) else None,
                          "mean_iv_minus_rv21": rnd((iv30 - rv21).mean()),
                          "series": {"date": [str(d.date()) for d in iv30.index], "iv30": [rnd(v) for v in iv30], "rv21": [rnd(v) for v in rv21]}}

# ---- 5. earnings: reaction-day moves (needs earnings_days.json from analyze_ops.py)
EARN = os.path.join(OUT, "earnings_days.json")
if os.path.exists(EARN):
    ed = json.load(open(EARN))
    rows = []
    for e in ed:
        r = {"period": e["period"], "release": e.get("release")}
        for key, comp in (("us", comp_us), ("hk", comp_hk)):
            d0 = e.get(f"day0_{key}")
            if d0 and pd.Timestamp(d0) in comp.index:
                r[f"ret_{key}"] = rnd(math.exp(comp.loc[pd.Timestamp(d0), "cc"]) - 1, 5)
                r[f"gap_{key}"] = rnd(math.exp(comp.loc[pd.Timestamp(d0), "o"]) - 1, 5)
        rows.append(r)
    res["earnings"] = {"rows": rows}
    for key in ("us", "hk"):
        a = np.array([abs(r[f"ret_{key}"]) for r in rows if r.get(f"ret_{key}") is not None])
        if len(a):
            boot = [RNG_mean for RNG_mean in (np.random.default_rng(7).choice(a, (5000, len(a))).mean(axis=1),)][0]
            normal = np.abs(np.exp((comp_us if key == "us" else comp_hk)["cc"]) - 1)
            res["earnings"][key] = {"n": int(len(a)), "mean_abs": rnd(a.mean()), "median_abs": rnd(np.median(a)), "max_abs": rnd(a.max()),
                                    "ci95": [rnd(np.percentile(boot, 2.5)), rnd(np.percentile(boot, 97.5))], "normal_mean_abs": rnd(normal.mean()),
                                    "ratio_to_normal": rnd(a.mean() / normal.mean(), 2)}
    nxt = [e for e in ed if e.get("next")]
    if nxt and "options" in res and "term" in res["options"]:
        ev = event_variance(res["options"]["term"], nxt[0]["day0_us"])
        if ev:
            a = np.array([abs(r["ret_us"]) for r in rows if r.get("ret_us") is not None])
            ev["share_hist_above"] = rnd((a > ev["event_abs_move"]).mean(), 3) if len(a) and ev["event_abs_move"] else None
            ev["hist_mean_abs"] = rnd(a.mean()) if len(a) else None
        res["earnings"]["implied_next"] = ev

# ---- 6. current implied vs forecast realised (the trade a vol arbitrageur would put on today)
if "options" in res and res["options"].get("term"):
    cmp_rows = []
    for t in res["options"]["term"]:
        h = max(1, int(round(t["days"] * TD / 365)))
        g, _ = garch_forecast(lr_us, h)
        hv, _ = har_forecast(rv_us, h)
        cone = next((c for c in res["cone_us"] if c["window"] >= h), res["cone_us"][-1])
        cmp_rows.append({"expiry": t["expiry"], "days": t["days"], "atm_iv": t["atm_iv"], "garch": rnd(g), "har": rnd(hv),
                         "iv_minus_garch": rnd(t["atm_iv"] - g) if t["atm_iv"] else None, "iv_minus_har": rnd(t["atm_iv"] - hv) if t["atm_iv"] else None,
                         "cone_window": cone["window"], "cone_p50": cone["p50"], "cone_p90": cone["p90"], "spread_volpts": t["atm_spread_volpts"]})
    res["iv_vs_forecast"] = cmp_rows

# ---- 7. cross-listing: HK price in USD against the NYSE line
hk_usd = (hk["Close"] / fx.reindex(hk.index).ffill(limit=5)).dropna()
us_c = us["Close"]
prev_us = us_c.reindex(us_c.index.union(hk_usd.index)).ffill().shift(1).reindex(hk_usd.index)  # last US close before the HK close
next_us = us_c.reindex(us_c.index.union(hk_usd.index)).bfill().reindex(hk_usd.index)  # first US close on/after the HK date
prem = pd.DataFrame({"prev": np.log(hk_usd / prev_us), "next": np.log(hk_usd / next_us)}).dropna()
prem = prem[prem.index >= "2020-09-11"]
out = {}
for k in ("prev", "next"):
    s = prem[k]
    adf = adfuller(s, regression="c", autolag="AIC")
    kp = kpss(s, regression="c", nlags="auto")
    phi = float(sm.OLS(s.iloc[1:].values, sm.add_constant(s.shift(1).iloc[1:].values)).fit().params[1])
    out[k] = {"mean_bp": rnd(s.mean() * 1e4, 1), "sd_bp": rnd(s.std() * 1e4, 1), "p05_bp": rnd(s.quantile(0.05) * 1e4, 1),
              "p95_bp": rnd(s.quantile(0.95) * 1e4, 1), "share_abs_gt_50bp": rnd((s.abs() > 0.005).mean(), 3),
              "share_abs_gt_100bp": rnd((s.abs() > 0.01).mean(), 3), "share_abs_gt_200bp": rnd((s.abs() > 0.02).mean(), 3),
              "adf": rnd(adf[0], 2), "adf_p": rnd(adf[1]), "kpss": rnd(kp[0], 3), "kpss_p": rnd(kp[1]), "ar1": rnd(phi, 3),
              "half_life_days": rnd(math.log(0.5) / math.log(phi), 2) if 0 < phi < 1 else None, "n": int(len(s))}
out["series"] = {"date": [str(d.date()) for d in prem.index[::3]], "prev_bp": [rnd(v * 1e4, 1) for v in prem["prev"][::3]]}
res["premium"] = out

# lead-lag between the sessions (HAC t-statistics); returns in USD for the HK line
hk_r = pd.DataFrame({"cc": np.log(hk_usd).diff(), "gap": np.log(hk["Open"] / hk["Close"].shift(1)), "oc": np.log(hk["Close"] / hk["Open"])})
us_r = pd.DataFrame({"cc": np.log(us_c).diff(), "gap": np.log(us["Open"] / us["Close"].shift(1)), "oc": np.log(us["Close"] / us["Open"])})


def lag_reg(y, x, label):
    j = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    m = sm.OLS(j["y"], sm.add_constant(j["x"])).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    return {"label": label, "beta": rnd(m.params["x"], 3), "t": rnd(m.tvalues["x"], 2), "p": rnd(m.pvalues["x"]), "r2": rnd(m.rsquared, 3), "n": int(len(j))}


# the last US session that closed before each HK session, and the US session that follows each HK session
us_last = pd.Series(us_r["cc"].values, index=us_r.index)
prev_map = pd.Series(us_last.index, index=us_last.index).reindex(us_last.index.union(hk_r.index)).ffill().shift(1).reindex(hk_r.index)
us_prev_for_hk = pd.Series([us_last.get(d) if pd.notna(d) else np.nan for d in prev_map], index=hk_r.index)
hk_last = pd.Series(hk_r["cc"].values, index=hk_r.index)
hk_map = pd.Series(hk_last.index, index=hk_last.index).reindex(hk_last.index.union(us_r.index)).ffill().reindex(us_r.index)
hk_for_us = pd.Series([hk_last.get(d) if pd.notna(d) else np.nan for d in hk_map], index=us_r.index)
sub = lambda s: s[s.index >= "2020-09-14"]  # noqa: E731
res["lead_lag"] = [
    lag_reg(sub(hk_r["cc"]), sub(us_prev_for_hk), "港股收盘到收盘 ← 前一个美股交易日"),
    lag_reg(sub(hk_r["gap"]), sub(us_prev_for_hk), "港股开盘跳空 ← 前一个美股交易日"),
    lag_reg(sub(hk_r["oc"]), sub(us_prev_for_hk), "港股开盘到收盘 ← 前一个美股交易日"),
    lag_reg(sub(us_r["cc"]), sub(hk_for_us), "美股收盘到收盘 ← 当日港股"),
    lag_reg(sub(us_r["gap"]), sub(hk_for_us), "美股开盘跳空 ← 当日港股"),
    lag_reg(sub(us_r["oc"]), sub(hk_for_us), "美股开盘到收盘 ← 当日港股"),
]
# is the HK intraday drift after a US move tradable? (1) control for the market: add the prior S&P 500 return and the
# same-day HSI (Tracker Fund) intraday return; (2) a simple rule: at the HK open, go long 9987 after a YUMC close-to-close
# rise of more than x, short after a fall of more than x, exit at the HK close; costs 0.25% per round trip (stamp duty
# 0.1% each side plus commission and half-spread); estimate on 2020-09 to 2023, test on 2024 onward.
spx = series("^GSPC", "Close")
spx_r = np.log(spx).diff()
spx_last = pd.Series(spx_r.values, index=spx_r.index)
spx_map = pd.Series(spx_last.index, index=spx_last.index).reindex(spx_last.index.union(hk_r.index)).ffill().shift(1).reindex(hk_r.index)
spx_prev_for_hk = pd.Series([spx_last.get(d) if pd.notna(d) else np.nan for d in spx_map], index=hk_r.index)
tf = ohlc("2800.HK")
tf_oc = np.log(tf["Close"] / tf["Open"])
X = pd.concat([sub(hk_r["oc"]).rename("y"), sub(us_prev_for_hk).rename("yumc_prev"), sub(spx_prev_for_hk).rename("spx_prev"), tf_oc.rename("hsi_oc")], axis=1).dropna()
mctrl = sm.OLS(X["y"], sm.add_constant(X[["yumc_prev", "spx_prev", "hsi_oc"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
res["lead_lag_controls"] = {"n": int(len(X)), **{f"beta_{k}": rnd(mctrl.params[k], 3) for k in ("yumc_prev", "spx_prev", "hsi_oc")},
                            **{f"t_{k}": rnd(mctrl.tvalues[k], 2) for k in ("yumc_prev", "spx_prev", "hsi_oc")}, "r2": rnd(mctrl.rsquared, 3)}
COST = 0.0025
rule = []
for x in (0.0, 0.01, 0.02, 0.03):
    for lab, a, b in (("2020-09 至 2023", "2020-09-14", "2023-12-31"), ("2024 年以来", "2024-01-01", None)):
        d = X[(X.index >= a) & ((X.index <= b) if b else True)]
        sig = np.sign(d["yumc_prev"]).where(d["yumc_prev"].abs() > x, 0.0)
        trades = (sig * d["y"])[sig != 0]
        net = trades - COST
        rule.append({"threshold": x, "period": lab, "n": int(len(trades)), "gross_mean": rnd(trades.mean(), 5), "net_mean": rnd(net.mean(), 5),
                     "t_net": rnd(net.mean() / (net.std(ddof=1) / math.sqrt(len(net))), 2) if len(net) > 2 else None,
                     "hit": rnd((trades > 0).mean(), 3) if len(trades) else None, "net_total": rnd(net.sum(), 3)})
res["intraday_rule"] = {"cost_round_trip": COST, "rows": rule}

# volatility of the two lines over the common period, daily and weekly (USD terms)
c0 = "2020-09-14"
hk_d, us_d = hk_r["cc"][hk_r.index >= c0].dropna(), us_r["cc"][us_r.index >= c0].dropna()
hk_w = np.log(hk_usd.resample("W-FRI").last()).diff().dropna()
us_w = np.log(us_c.resample("W-FRI").last()).diff().dropna()
hk_w, us_w = hk_w[hk_w.index >= c0], us_w[us_w.index >= c0]
lev = stats.levene(hk_d, us_d, center="median")
levw = stats.levene(hk_w, us_w, center="median")
jw = pd.concat([hk_w.rename("hk"), us_w.rename("us")], axis=1).dropna()
res["two_lines"] = {"vol_daily": {"hk": rnd(hk_d.std() * math.sqrt(TD)), "us": rnd(us_d.std() * math.sqrt(TD))},
                    "vol_weekly": {"hk": rnd(hk_w.std() * math.sqrt(52)), "us": rnd(us_w.std() * math.sqrt(52))},
                    "levene_daily_p": rnd(lev.pvalue), "levene_weekly_p": rnd(levw.pvalue),
                    "corr_daily_same_date": rnd(pd.concat([hk_d, us_d], axis=1).dropna().corr().iloc[0, 1], 3),
                    "corr_weekly": rnd(jw.corr().iloc[0, 1], 3), "n_weekly": int(len(jw))}
# where the trading happens: share of dollar volume in Hong Kong, by year
hk_dv = (hk["Close"] * hk["Volume"] / fx.reindex(hk.index).ffill()).resample("YE").sum()
us_dv = (us["Close"] * us["Volume"]).resample("YE").sum()
vs = pd.concat([hk_dv.rename("hk"), us_dv.rename("us")], axis=1).dropna()
vs = vs[vs.index >= "2021-01-01"]
res["volume_share_hk"] = [{"y": int(d.year), "hk_share": rnd(r.hk / (r.hk + r.us), 3), "hk_usd_bn": rnd(r.hk / 1e9, 1), "us_usd_bn": rnd(r.us / 1e9, 1)}
                          for d, r in vs.iterrows()]

# the NYSE line over its full history, against the S&P 500 total return
spx_tr = series("^SP500TR")
u = us["Close_a"]
j = pd.concat([u.rename("u"), spx_tr.rename("m")], axis=1).dropna()
lr_u, lr_m = np.log(j["u"]).diff().dropna(), np.log(j["m"]).diff().dropna()
bm = sm.OLS(j["u"].pct_change().dropna(), sm.add_constant(j["m"].pct_change().dropna())).fit()
res["us_line_stats"] = {"start": str(j.index[0].date()), "end": str(j.index[-1].date()), "total_return": rnd(j["u"].iloc[-1] / j["u"].iloc[0] - 1),
                        "ann_return": rnd((j["u"].iloc[-1] / j["u"].iloc[0]) ** (TD / len(lr_u)) - 1), "ann_vol": rnd(lr_u.std() * math.sqrt(TD)),
                        "spx_total_return": rnd(j["m"].iloc[-1] / j["m"].iloc[0] - 1), "spx_ann_vol": rnd(lr_m.std() * math.sqrt(TD)),
                        "beta_spx": rnd(bm.params.iloc[1], 3), "r2_spx": rnd(bm.rsquared, 3)}

# chart series: realised vol (21-day close-to-close and Yang-Zhang), weekly sampling
ch = pd.DataFrame({"cc21": cc21_us, "yz21": yz_us}).dropna().iloc[::5]
res["rv_series"] = {"date": [str(d.date()) for d in ch.index], "cc21": [rnd(v) for v in ch["cc21"]], "yz21": [rnd(v) for v in ch["yz21"]]}

os.makedirs(OUT, exist_ok=True)
ml.dump_json(res, os.path.join(OUT, "volarb.json"))
skip = ("rv_series", "premium", "oos", "cone_us", "cone_hk")
print(json.dumps(ml.clean({k: v for k, v in res.items() if k not in skip}), indent=1, ensure_ascii=False)[:9000])
print("premium", {k: v for k, v in res["premium"].items() if k != "series"})
print("oos", {k: v for k, v in res["oos"].items() if k != "series"})
print("cone_us", res["cone_us"])
