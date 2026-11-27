"""Market analysis for <公司>（<代码>）: volatility, betas (market / sector / style / rates), peers and event study.

Template from the stock-analysis-report skill. Copy to <slug>_analysis/scripts/analyze_market.py, edit the CONFIG and
LOAD blocks, then run from the repository root:
    python <slug>_analysis/scripts/analyze_market.py            # writes data/processed/market_analysis.json
    python <slug>_analysis/scripts/analyze_market.py --events   # also prints events, top abnormal days and peers
Generic keys: tgt = the stock, mkt = market benchmark, sec = equal-weight peer index, sty = optional style index.
The skeleton report page (report/template.html) reads exactly these keys.
"""
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
sys.path.insert(0, os.path.join(ROOT, "..", "report_kit"))
import marketlib as ml  # noqa: E402

warnings.simplefilter("ignore", pd.errors.PerformanceWarning)

# ============================================================ CONFIG (edit)
TARGET = "000429"                     # exchange code of the stock
MARKET = "A"                          # "A" (Shanghai/Shenzhen), "HK" or "US"
NAMES = {"tgt": "粤高速", "mkt": "沪深 300 全收益", "sec": "公路同业", "sty": "中证红利全收益"}  # chart / table labels
PEERS = {"600377": "宁沪高速", "001965": "招商公路", "600350": "山东高速"}  # sector peers, target excluded; {} = no sector factor
MIN_PEERS = 2                         # minimum names with a return for the sector index to count a day (about half)
START, END = "2016-01-04", None       # END None = last date common to the stock and the market index
USE_RATE_FACTOR = True                # add the 10-year yield change as a factor (banks, utilities, REITs, dividend stocks)
PEER_SINCE = "2023-01-01"             # window for peer betas / correlations / since-volatility
MDD_SINCE = "2024-01-01"
PERIODS = [("ret_2024", "2023-12-31", "2024-12-31"), ("ret_2025", "2024-12-31", "2025-12-31")]  # + YTD and 3Y added below
SUBPERIODS = [("2016–2020", None, "2020-12-31"), ("2021–2023", "2021-01-01", "2023-12-31"), ("2024 年以来", "2024-01-01", None)]
REBASE_AT = "2023-12-31"              # rebased comparison chart starts at the last close on/before this date
COMPARE = []                          # peer codes to show in the rebased chart besides the target (3-5 large names)
HIST_WIDTH, HIST_STEP = 0.10, 0.01    # daily-return histogram range; use 0.20 / 0.02 for very volatile stocks
ERP = 0.06                            # equity risk premium for the CAPM required return


# ============================================================ LOAD (edit to match data/raw)
def yahoo(ticker, col="Adj Close"):
    return ml.read_series(os.path.join(RAW, "yahoo", ml.yahoo_file(ticker)), "Date", col)


def csindex(code, col="收盘"):
    return ml.read_series(os.path.join(RAW, "idx", f"csindex_{code}.csv"), "日期", col)


def fred(series_id):
    path = os.path.join(RAW, "rates", f"fred_{series_id}.csv")
    date_col = pd.read_csv(path, nrows=0).columns[0]
    return ml.read_series(path, date_col, series_id)


tkr = lambda c: ml.yahoo_ticker(c, MARKET)  # noqa: E731
have = lambda f: os.path.exists(os.path.join(RAW, f)) and os.path.getsize(os.path.join(RAW, f)) > 0  # noqa: E731
tgt_adj, tgt_raw = yahoo(tkr(TARGET)), yahoo(tkr(TARGET), "Close")
y10 = None
if MARKET == "A":
    mkt = csindex("H00300")                       # CSI 300 total return
    sty = csindex("H00922") if have("idx/csindex_H00922.csv") else None  # CSI Dividend TR as the style benchmark
    vol = csindex("000300", "成交量")
    calendar = vol.index[vol > 0]                 # exchange trading days
    bond = pd.read_csv(os.path.join(RAW, "rates", "bond_zh_us_rate.csv"))
    bond.index = pd.to_datetime(bond["日期"])
    bond = bond.sort_index()
    y10 = pd.to_numeric(bond["中国国债收益率10年"], errors="coerce")
    rf_annual = pd.to_numeric(bond["中国国债收益率2年"], errors="coerce") / 100
elif MARKET == "HK":
    mkt = yahoo("^HSI")                           # Hang Seng (price index; Yahoo has no HSI total-return series)
    sty = None
    calendar = mkt.index
    rf_annual = yahoo("^IRX", "Close") / 100      # 13-week US T-bill, a proxy under the HKD peg
else:
    mkt = yahoo("^SP500TR") if have(os.path.join("yahoo", ml.yahoo_file("^SP500TR"))) else yahoo("^GSPC")
    sty = None                                    # e.g. a sector ETF such as yahoo("SMH")
    calendar = mkt.index
    # FRED when the fetch got it, otherwise Yahoo's ^IRX (13-week bill) and ^TNX (10-year yield, in percent)
    rf_annual = (fred("DGS3MO") if have("rates/fred_DGS3MO.csv") else yahoo("^IRX", "Close")) / 100
    y10 = (fred("DGS10") if have("rates/fred_DGS10.csv") else yahoo("^TNX", "Close")) if USE_RATE_FACTOR else None
peer_px = pd.DataFrame({c: yahoo(tkr(c)) for c in PEERS}) if PEERS else pd.DataFrame()
# cash dividends [(ex_date, dps)] for the ex-dividend study; [] to skip
DIVIDENDS = []
# annual DPS indexed by the date the plan was announced, for the dividend-yield spread; None to skip
DPS_ANNOUNCED = None

# ============================================================ panel
END = END or str(min(tgt_adj.index[-1], mkt.index[-1]).date())
cal = calendar[(calendar >= pd.Timestamp(START)) & (calendar <= pd.Timestamp(END))]
prices = {"tgt": tgt_adj.reindex(cal), "mkt": mkt.reindex(cal)}
if sty is not None:
    prices["sty"] = sty.reindex(cal)
extra, n_avail, peer_ret = {}, None, None
if PEERS:
    sec_ret, n_avail, peer_ret = ml.equal_weight_returns(peer_px.reindex(cal), MIN_PEERS)
    extra["sec"] = sec_ret
px, ret, logret = ml.build_panel(prices, extra_returns=extra)
SEC = "sec" if PEERS else None
STY = "sty" if sty is not None else None
rf_d = ml.daily_rf(rf_annual, ret.index)
ex = ret.sub(rf_d, axis=0)
dy = None
if y10 is not None and USE_RATE_FACTOR:
    y10 = y10.reindex(ret.index).ffill()
    dy = y10.diff().fillna(0)                      # percentage points per day
raw_close = tgt_raw.reindex(px.index).ffill()

res = {"meta": {"target_code": TARGET, "market": MARKET, "names": NAMES, "start": str(px.index[0].date()), "end": END,
                "n_days": int(len(ret)), "rf_avg": float(rf_annual.reindex(ret.index).ffill().mean()) if isinstance(rf_annual, pd.Series) else float(rf_annual),
                "last_raw_close": float(raw_close.iloc[-1]), "y10_last": float(y10.iloc[-1]) if y10 is not None else None,
                "has_sec": bool(SEC), "has_sty": bool(STY), "has_rate": dy is not None,
                "sector": {"names": list(PEERS.values()), "min_names": MIN_PEERS,
                           "n_last": int(n_avail.iloc[-1]) if n_avail is not None else 0,
                           "n_start": int(n_avail.reindex(ret.index).iloc[0]) if n_avail is not None else 0}}}
cols = [k for k in ("tgt", "mkt", "sec", "sty") if k in px.columns]
res["stats"] = {k: ml.risk_stats(ret[k], logret[k], px[k], rf_d) for k in cols}

# ============================================================ single-index and factor models
res["sim_mkt"] = ml.sim(ex["tgt"], ex["mkt"])
if SEC:
    res["sim_sec"] = ml.sim(ex["tgt"], ex["sec"])
    res["sec_on_mkt"] = ml.sim(ex["sec"], ex["mkt"])
if STY:
    res["sim_sty"] = ml.sim(ex["tgt"], ex["sty"])
res["sim_mkt_weekly"] = ml.resampled_sim(px, "tgt", "mkt", rf_annual, "W-FRI")
res["sim_mkt_monthly"] = ml.resampled_sim(px, "tgt", "mkt", rf_annual, "ME")
if SEC:
    res["sim_sec_weekly"] = ml.resampled_sim(px, "tgt", "sec", rf_annual, "W-FRI")
res["up_beta_mkt"], res["down_beta_mkt"] = ml.up_down_beta(ex["tgt"], ex["mkt"])
res["dimson_beta_mkt"] = ml.dimson_beta(ex["tgt"], ex["mkt"])
res["active"] = ml.capture_and_active(ret["tgt"], ret["mkt"])
rf_last = float(rf_annual.dropna().iloc[-1]) if isinstance(rf_annual, pd.Series) else float(rf_annual)
res["capm"] = {"rf_latest": rf_last, "erp": ERP, "required_return": rf_last + res["sim_mkt"]["beta"] * ERP}
model_full, res["factors"] = ml.factor_model(ex, "tgt", "mkt", SEC, dy)
res["factors_periods"] = []
for lab, a, b in SUBPERIODS:  # sub-periods with less than about 3 months of data inside the sample are skipped
    span = ex[(ex.index >= pd.Timestamp(a or START)) & (ex.index <= pd.Timestamp(b or END))]
    if len(span) >= 60:
        res["factors_periods"].append({"label": lab, **ml.factor_model(ex, "tgt", "mkt", SEC, dy, a, b)[1]})
if dy is not None:
    b10, c10 = ml.monthly_rate_link(px["tgt"], y10)
    res["monthly_rate"] = {"beta_10bp": b10, "corr": c10}
res["by_year"] = ml.by_year(px, ret, logret, ex, "tgt", "mkt", SEC, [STY] if STY else [], y10)

# ============================================================ volatility dynamics
roll = ml.rolling_metrics(logret, ex, "tgt", "mkt", SEC, dy)
g_fit, res_g = ml.garch_t(logret["tgt"])
res["garch"] = {"tgt": res_g, "mkt": ml.garch_t(logret["mkt"])[1]}
if SEC:
    res["garch"]["sec"] = ml.garch_t(logret["sec"])[1]
roll["garch_tgt"] = g_fit.conditional_volatility / 100 * np.sqrt(ml.TD)
res["top10_days_var_share"] = ml.top_days_variance_share(ret["tgt"])
res["hist"] = ml.return_histogram(ret, [k for k in ("tgt", "sec", "mkt") if k in ret.columns], HIST_WIDTH, HIST_STEP)

# ============================================================ peers inside the sector
if PEERS:
    all_px = peer_px.reindex(cal).copy()
    all_px.insert(0, TARGET, tgt_adj.reindex(cal))
    periods = PERIODS + [("ret_ytd", f"{int(END[:4]) - 1}-12-31", END)]
    res["peers"] = ml.peer_risk_table(all_px, peer_ret, ret["mkt"], {TARGET: NAMES["tgt"], **PEERS}, PEER_SINCE, END, periods,
                                      dy, MIN_PEERS, MDD_SINCE)
    res["peer_ranks"] = {k: dict(zip(("rank", "of"), ml.rank_of(res["peers"], k, TARGET)))
                         for k in ("vol_1y", "beta_sec", "ret_ytd", "ret_3y") + tuple(p[0] for p in PERIODS)}

# ============================================================ event study
EV_PATH = os.path.join(ROOT, "data", "events.json")
EVENTS = json.load(open(EV_PATH, encoding="utf-8")) if os.path.exists(EV_PATH) else []
abn, resid_sd, _ = ml.abnormal_returns(ex, "tgt", "mkt", SEC)
ev_cols = {"ret_tgt": "tgt", "ret_mkt": "mkt", **({"ret_sec": "sec"} if SEC else {})}
res["events"] = ml.event_table(EVENTS, abn, resid_sd, ret, ev_cols, dy, raw_close)
res["resid_sd_daily"] = resid_sd
fields = {"ret_tgt": ret["tgt"], "ret_mkt": ret["mkt"], **({"ret_sec": ret["sec"]} if SEC else {}), "ar": abn, "ar_t": abn / resid_sd}
res["top_abnormal_days"] = ml.top_days(abn, 40, fields)
if SEC:
    res["top_sector_days"] = ml.top_days(ret["sec"], 15, {"ret_sec": ret["sec"], "ret_tgt": ret["tgt"], "ret_mkt": ret["mkt"]})
res["earnings_abs_move_avg"], res["normal_abs_move_avg"] = ml.earnings_move(ret["tgt"], [e["day0"] for e in res["events"] if e.get("category") == "earnings"])
res["car_by_year"] = ml.car_by_year(abn)
if DIVIDENDS:
    res["ex_dividend"], res["ex_dividend_summary"] = ml.ex_dividend_table(DIVIDENDS, ret, abn, raw_close, "tgt", SEC)

# ============================================================ valuation context
dy_ttm = spread = None
if DPS_ANNOUNCED is not None and y10 is not None:
    dy_ttm, spread = ml.dividend_yield_spread(DPS_ANNOUNCED, raw_close, y10.reindex(px.index).ffill())
    res["dividend_yield_now"] = {"dps": float(DPS_ANNOUNCED.sort_index().iloc[-1]), "dy": float(dy_ttm.iloc[-1]),
                                 "y10": float(y10.iloc[-1]), "spread_pp": float(spread.iloc[-1])}

# ============================================================ chart series
dd = {k: ml.max_drawdown(px[k])[3] for k in cols}
series = pd.DataFrame({"tgt_px": raw_close, **{f"{k}_idx": px[k] / px[k].iloc[0] * 100 for k in cols},
                       **{f"dd_{k}": dd[k] for k in cols}}).join(roll)
if y10 is not None:
    series["y10"] = y10.reindex(px.index).ffill()
if dy_ttm is not None:
    series["dy_ttm"], series["spread"] = dy_ttm, spread
res["series"] = ml.series_payload(series, 5)
res["scatter"] = {"x": [round(float(v), 5) for v in ex["mkt"]], "y": [round(float(v), 5) for v in ex["tgt"]],
                  "dates": ex.index.strftime("%Y-%m-%d").tolist(), "a": float(res["sim_mkt"]["alpha_daily"]), "b": float(res["sim_mkt"]["beta"])}
base_day = px.index[px.index <= pd.Timestamp(REBASE_AT)][-1] if (px.index <= pd.Timestamp(REBASE_AT)).any() else px.index[0]
reb = {}
for c in [TARGET] + [c for c in COMPARE if c in PEERS]:
    p = (tgt_adj if c == TARGET else peer_px[c]).reindex(cal).dropna()
    p = p[p.index >= base_day]
    reb[c] = (p / p.iloc[0] * 100).round(2)
for k in cols[1:]:
    lv = px[k][px.index >= base_day]
    reb[k] = (lv / lv.iloc[0] * 100).round(2)
res["rebased"] = {"base_date": str(base_day.date()), **ml.series_payload(pd.DataFrame(reb), 2)}

os.makedirs(OUT, exist_ok=True)
ml.dump_json(res, os.path.join(OUT, "market_analysis.json"))
skip = ("series", "scatter", "hist", "events", "top_abnormal_days", "top_sector_days", "peers", "rebased", "by_year", "ex_dividend")
print(json.dumps(ml.clean({k: v for k, v in res.items() if k not in skip}), indent=1, ensure_ascii=False))
print(f"\nsample {res['meta']['start']} – {END}, {len(ret)} days. Check that {END} is a complete session in every source.")
if "--events" in sys.argv:
    for e in res["events"]:
        print(e["day0"], e.get("category"), f"{e['ret_tgt']:+.1%} mkt {e['ret_mkt']:+.1%}" + (f" sec {e['ret_sec']:+.1%}" if SEC else ""),
              f"AR {e['ar']:+.1%} t={e['ar_t']:.1f}", e.get("title", ""))
    print("--- top abnormal days (look these up: unexplained big days are often missing events)")
    for t in res["top_abnormal_days"][:20]:
        print(t["date"], f"{t['ret_tgt']:+.1%} mkt {t['ret_mkt']:+.1%} AR {t['ar']:+.1%} t={t['ar_t']:.1f}")
    for p in res.get("peers", []):
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in p.items()})
