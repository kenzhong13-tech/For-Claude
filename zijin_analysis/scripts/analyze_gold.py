"""紫金矿业与金价、铜价：走势比较、敏感性与联动 -> data/processed/gold_analysis.json.

Run from the repository root after analyze_market.py (it reuses that script's sample end date):
    python zijin_analysis/scripts/analyze_gold.py
Series (data/raw/, saved by scripts/fetch_data.py):
- 紫金矿业 A 股: Yahoo 601899.SS Adj Close (dividends reinvested) and Close; H 股 2899.HK; 紫金黄金国际 2259.HK.
- Gold: SGE Au99.99 spot close (RMB per gram; trades on the A-share calendar) and COMEX GC=F (USD per ounce).
- Copper: SHFE main contract CU0 (RMB per tonne, Sina's continuous series, spliced at each roll) and COMEX HG=F.
- CSI 300 total return; equal-weight indices of the A-share gold peers and copper peers (lists in analyze_market.py).
Models: daily (and weekly) excess returns regressed on the market plus the gold and copper price changes, OLS with
HAC t-values; the R² that each factor adds; the same model for the gold-peer and copper-peer indices as yardsticks.
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
warnings.simplefilter("ignore", pd.errors.PerformanceWarning)  # wide Eastmoney statement files

START = "2016-01-04"
MIN_PEERS_GOLD, MIN_PEERS_COPPER = 4, 3
SUBPERIODS = [("2016–2019", None, "2019-12-31"), ("2020–2022", "2020-01-01", "2022-12-31"),
              ("2023–2024", "2023-01-01", "2024-12-31"), ("2025 年以来", "2025-01-01", None)]
GOLD_PEERS = {"600547": "山东黄金", "600489": "中金黄金", "000975": "山金国际", "002155": "湖南黄金", "601069": "西部黄金",
              "002237": "恒邦股份", "001337": "四川黄金"}
COPPER_PEERS = {"600362": "江西铜业", "000630": "铜陵有色", "603993": "洛阳钼业", "601168": "西部矿业", "000878": "云南铜业",
                "603979": "金诚信"}
GLOBAL = {"GDX": "VanEck 金矿股 ETF", "NEM": "纽蒙特", "AEM": "伊格尔矿业", "B": "巴里克", "FCX": "自由港", "SCCO": "南方铜业"}
OZ = 31.1035  # grams per troy ounce
mkt_meta = json.load(open(os.path.join(OUT, "market_analysis.json"), encoding="utf-8"))["meta"]
END = mkt_meta["end"]


# ============================================================ loading
def have(rel):
    p = os.path.join(RAW, rel)
    return os.path.exists(p) and os.path.getsize(p) > 0


def yahoo(t, col="Adj Close"):
    return ml.read_series(os.path.join(RAW, "yahoo", ml.yahoo_file(t)), "Date", col)


def csindex(code, col="收盘"):
    return ml.read_series(os.path.join(RAW, "idx", f"csindex_{code}.csv"), "日期", col)


def commod(name, date_col=None, col=None):
    path = os.path.join(RAW, "commod", f"{name}.csv")
    cols = pd.read_csv(path, nrows=0).columns
    return ml.read_series(path, date_col or cols[0], col or next(c for c in cols if c.lower() in ("close", "收盘价", "收盘")))


def gold_cny():
    """SGE Au99.99 spot close (starts 2016-12-19 here); earlier days use the SHFE gold main contract scaled to spot."""
    spot, fut = commod("sge_Au99.99"), commod("main_AU0")
    d0 = spot.index[0]
    early = fut[fut.index < d0] * spot.iloc[0] / fut[fut.index <= d0].iloc[-1]
    return pd.concat([early, spot]).sort_index(), f"上海黄金交易所 Au99.99 现货收盘价（元/克；{d0.date()} 之前用上期所黄金主力合约衔接）"


def copper_cny():
    if have("commod/main_CU0.csv"):
        return commod("main_CU0"), "上期所沪铜主力连续合约收盘价（元/吨）"
    hg, cny = yahoo("HG=F", "Close"), yahoo("CNY=X", "Close")
    return (hg * 2204.62 * cny.reindex(hg.index).ffill()).dropna(), "COMEX 铜 × 美元兑人民币（元/吨）"


vol = csindex("000300", "成交量")
cal = vol.index[(vol > 0) & (vol.index >= pd.Timestamp(START)) & (vol.index <= pd.Timestamp(END))]
zj, zj_raw = yahoo("601899.SS"), yahoo("601899.SS", "Close")
gold, gold_src = gold_cny()
cu, cu_src = copper_cny()
mkt = csindex("H00300")
gold_usd, cu_usd, usdcny = yahoo("GC=F", "Close"), yahoo("HG=F", "Close"), yahoo("CNY=X", "Close")
bond = pd.read_csv(os.path.join(RAW, "rates", "bond_zh_us_rate.csv"))
bond.index = pd.to_datetime(bond["日期"])
rf_annual = pd.to_numeric(bond.sort_index()["中国国债收益率2年"], errors="coerce") / 100

px = pd.DataFrame({"zj": zj, "mkt": mkt, "gold": gold, "cu": cu}).reindex(cal).ffill(limit=5)
px = px.dropna()
ret = px.pct_change().dropna()
for key, peers, mn in (("gp", GOLD_PEERS, MIN_PEERS_GOLD), ("cp", COPPER_PEERS, MIN_PEERS_COPPER)):
    lv = pd.DataFrame({c: yahoo(ml.yahoo_ticker(c, "A")) for c in peers}).reindex(cal)
    ret[key] = ml.equal_weight_returns(lv, mn)[0].reindex(ret.index)
ret = ret.dropna()
px = px.loc[[px.index[0]] + list(ret.index)]
for key in ("gp", "cp"):
    px[key] = (100 * (1 + ret[key]).cumprod()).reindex(px.index)
    px.loc[px.index[0], key] = 100.0
rf_d = ml.daily_rf(rf_annual, ret.index)
ex = ret.copy()
for k in ("zj", "mkt", "gp", "cp"):  # equities in excess of the risk-free rate; metal price changes enter as they are
    ex[k] = ret[k] - rf_d
NAMES = {"zj": "紫金矿业", "mkt": "沪深 300 全收益", "gold": "金价（人民币）", "cu": "铜价（人民币）", "gp": "黄金同业", "cp": "铜同业",
         "gold_usd": "COMEX 黄金（美元）", "cu_usd": "COMEX 铜（美元）", "gdx": "GDX 金矿股 ETF（美元）"}
res = {"meta": {"start": str(px.index[0].date()), "end": END, "n_days": int(len(ret)), "names": NAMES,
                "gold_source": gold_src, "copper_source": cu_src,
                "gold_peers": list(GOLD_PEERS.values()), "copper_peers": list(COPPER_PEERS.values()),
                "gold_last": float(px["gold"].iloc[-1]), "cu_last": float(px["cu"].iloc[-1]),
                "gold_usd_last": float(gold_usd[gold_usd.index <= pd.Timestamp(END)].iloc[-1]),
                "usdcny_last": float(usdcny[usdcny.index <= pd.Timestamp(END)].iloc[-1])}}


def last_on(s, d):
    s = s.dropna()
    s = s[s.index <= pd.Timestamp(d)]
    return float(s.iloc[-1]) if len(s) else None


def window_ret(s, a, b):
    x0, x1 = last_on(s, a), last_on(s, b)
    return None if x0 is None or x1 is None else x1 / x0 - 1


# ============================================================ performance over windows
g = px["gold"]
gold_peak = g[g.index >= "2025-06-01"].idxmax()
low22 = g[(g.index >= "2022-07-01") & (g.index <= "2022-12-31")].idxmin()
zj_peak = px["zj"].idxmax()
gdx = yahoo("GDX")
LEVELS = {"zj": px["zj"], "gold": px["gold"], "gold_usd": gold_usd, "cu": px["cu"], "cu_usd": cu_usd, "mkt": px["mkt"],
          "gp": px["gp"], "cp": px["cp"], "gdx": gdx}
y_end = lambda y: str(px.index[px.index.year == y][-1].date())  # noqa: E731
first = str(px.index[0].date())
WINDOWS = [(f"{first[:4]} 年初以来", first, END), ("2019 年以来", y_end(2018), END),
           (f"本轮金价上涨以来（{low22.date()} 起）", str(low22.date()), END),
           ("2023 年", y_end(2022), y_end(2023)), ("2024 年", y_end(2023), y_end(2024)), ("2025 年", y_end(2024), y_end(2025)),
           ("2026 年以来", y_end(2025), END), (f"金价高点（{gold_peak.date()}）以来", str(gold_peak.date()), END)]
res["windows"] = [{"label": lab, "start": a, "end": b, **{k: window_ret(s, a, b) for k, s in LEVELS.items()}} for lab, a, b in WINDOWS]
res["gold_peak"] = {"date": str(gold_peak.date()), "gold": float(g[gold_peak]), "dd_now": float(g.iloc[-1] / g[gold_peak] - 1),
                    "zj_at_gold_peak": float(px["zj"][gold_peak]), "zj_peak_date": str(zj_peak.date()),
                    "zj_dd_now": float(px["zj"].iloc[-1] / px["zj"].max() - 1)}
res["gold_low_2022"] = {"date": str(low22.date()), "gold": float(g[low22])}

# ============================================================ chart series
wk = px.resample("W-FRI").last().dropna()
res["long"] = ml.series_payload((wk[["zj", "gold", "cu", "mkt", "gp", "cp"]] / wk.iloc[0] * 100).round(2), 2)
rs = pd.DataFrame({"zj_gold": wk["zj"] / wk["gold"], "zj_cu": wk["zj"] / wk["cu"], "gp_gold": wk["gp"] / wk["gold"],
                   "zj_basket": wk["zj"] / np.sqrt(wk["gold"] * wk["cu"])})
res["rel_strength"] = ml.series_payload((rs / rs.iloc[0] * 100).round(2), 2)
recent = px[px.index >= pd.Timestamp(y_end(2024))]
res["recent"] = ml.series_payload((recent[["zj", "gold", "cu", "mkt", "gp", "cp"]] / recent.iloc[0] * 100).round(2), 2)

# ============================================================ rolling betas and correlations
roll = pd.DataFrame(index=ret.index)
for f in ("gold", "cu"):
    roll[f"beta_{f}"] = ex["zj"].rolling(252).cov(ret[f]) / ret[f].rolling(252).var()
    roll[f"corr_{f}"] = ex["zj"].rolling(126).corr(ret[f])
    roll[f"gp_beta_{f}"] = ex["gp"].rolling(252).cov(ret[f]) / ret[f].rolling(252).var()
roll["corr_mkt"] = ex["zj"].rolling(126).corr(ex["mkt"])
roll["gold_cu_corr"] = ret["gold"].rolling(126).corr(ret["cu"])
res["rolling"] = ml.series_payload(roll.iloc[::5].dropna(how="all").round(3), 3)
res["rolling_last"] = {k: float(roll[k].dropna().iloc[-1]) for k in roll.columns}


# ============================================================ factor models
def fm(y, frame, factors, since=None, until=None):
    d = frame[[y] + factors].dropna()
    if since:
        d = d[d.index >= pd.Timestamp(since)]
    if until:
        d = d[d.index <= pd.Timestamp(until)]
    m = ml.ols_hac(d[y], d[factors])
    return {"n": int(len(d)), "r2": float(m.rsquared), **{f"b_{f}": float(m.params[f]) for f in factors},
            **{f"t_{f}": float(m.tvalues[f]) for f in factors}, "alpha_ann": float(m.params["const"] * 252)}


def model_set(frame, y, since=None, until=None):
    m1 = fm(y, frame, ["mkt"], since, until)
    m2 = fm(y, frame, ["mkt", "gold"], since, until)
    m3 = fm(y, frame, ["mkt", "gold", "cu"], since, until)
    g1 = fm(y, frame, ["gold"], since, until)
    c1 = fm(y, frame, ["cu"], since, until)
    return {"since": str(frame.index[frame.index >= pd.Timestamp(since or START)][0].date()), "r2_mkt": m1["r2"], "r2_mkt_gold": m2["r2"],
            "r2_all": m3["r2"], "r2_gold_only": g1["r2"], "r2_cu_only": c1["r2"], "b_gold_only": g1["b_gold"], "b_cu_only": c1["b_cu"],
            **{k: m3[k] for k in m3 if k.startswith(("b_", "t_"))}, "n": m3["n"]}


wex = pd.DataFrame({k: px[k] for k in ("zj", "mkt", "gold", "cu", "gp", "cp")}).resample("W-FRI").last().pct_change().dropna()
rf_w = rf_annual.resample("W-FRI").last().reindex(wex.index).ffill().bfill() / 52
for k in ("zj", "mkt", "gp", "cp"):
    wex[k] = wex[k] - rf_w
res["models"] = {}
for y in ("zj", "gp", "cp"):
    res["models"][y] = {"daily": [{"label": "全样本", **model_set(ex, y)}] + [{"label": lab, **model_set(ex, y, a, b)} for lab, a, b in SUBPERIODS],
                        "weekly": [{"label": "全样本", **model_set(wex, y)}] + [{"label": lab, **model_set(wex, y, a, b)} for lab, a, b in SUBPERIODS]}

# ============================================================ monthly link, capture, lead-lag
mo = pd.DataFrame({k: px[k] for k in ("zj", "gold", "cu", "mkt", "gp")}).resample("ME").last().pct_change().dropna()
up, dn = mo["gold"] > 0, mo["gold"] < 0
mreg = ml.ols(mo["zj"], mo[["gold"]])
res["monthly"] = {"n": int(len(mo)), "beta": float(mreg.params["gold"]), "r2": float(mreg.rsquared), "corr": float(mo["zj"].corr(mo["gold"])),
                  "corr_cu": float(mo["zj"].corr(mo["cu"])), "n_up": int(up.sum()), "n_down": int(dn.sum()),
                  "avg_zj_gold_up": float(mo["zj"][up].mean()), "avg_zj_gold_down": float(mo["zj"][dn].mean()),
                  "avg_gold_up": float(mo["gold"][up].mean()), "avg_gold_down": float(mo["gold"][dn].mean()),
                  "hit_up": float((mo["zj"][up] > 0).mean()), "hit_down": float((mo["zj"][dn] < 0).mean()),
                  "up_capture": float(mo["zj"][up].mean() / mo["gold"][up].mean()), "down_capture": float(mo["zj"][dn].mean() / mo["gold"][dn].mean()),
                  "scatter": {"x": [round(float(v), 4) for v in mo["gold"]], "y": [round(float(v), 4) for v in mo["zj"]],
                              "dates": mo.index.strftime("%Y-%m").tolist(), "a": float(mreg.params["const"]), "b": float(mreg.params["gold"])}}
wr = pd.DataFrame({k: px[k] for k in ("zj", "gold", "cu")}).resample("W-FRI").last().pct_change().dropna()
res["leadlag"] = [{"lag": k, "corr_gold": float(wr["zj"].corr(wr["gold"].shift(k))), "corr_cu": float(wr["zj"].corr(wr["cu"].shift(k)))}
                  for k in range(-4, 5)]  # lag k > 0: gold k weeks earlier vs the stock now

# ============================================================ big gold days and gold drawdowns
big = ret["gold"].sort_values()
pick = lambda idx: [{"date": str(d.date()), "gold": float(ret["gold"][d]), "zj": float(ret["zj"][d]), "mkt": float(ret["mkt"][d]),  # noqa: E731
                     "gp": float(ret["gp"][d]), "cp": float(ret["cp"][d]), "cu": float(ret["cu"][d])} for d in idx]
res["big_gold_days"] = {"down": pick(big.index[:12]), "up": pick(big.index[::-1][:12])}
top20_up, top20_dn = big.index[::-1][:20], big.index[:20]
res["big_gold_days"]["summary"] = {"avg_zj_on_up": float(ret["zj"][top20_up].mean()), "avg_gold_on_up": float(ret["gold"][top20_up].mean()),
                                   "avg_zj_on_down": float(ret["zj"][top20_dn].mean()), "avg_gold_on_down": float(ret["gold"][top20_dn].mean()),
                                   "avg_gp_on_up": float(ret["gp"][top20_up].mean()), "avg_gp_on_down": float(ret["gp"][top20_dn].mean())}


def drawdown_episodes(levels, threshold=-0.08):
    peak = levels.cummax()
    dd = levels / peak - 1
    eps, i, n = [], 0, len(dd)
    while i < n:
        if dd.iloc[i] < 0:
            j = i
            while j < n and dd.iloc[j] < 0:
                j += 1
            seg = dd.iloc[i:j]
            if seg.min() <= threshold:
                tr = seg.idxmin()
                pk = levels.loc[:tr].idxmax()
                eps.append((pk, tr, j >= n))
            i = j
        else:
            i += 1
    return eps


res["gold_drawdowns"] = [{"peak": str(pk.date()), "trough": str(tr.date()), "ongoing": bool(on),
                          **{k: window_ret(LEVELS[k], pk, tr) for k in ("gold", "zj", "mkt", "gp", "cp", "cu")}}
                         for pk, tr, on in drawdown_episodes(px["gold"])]

# ============================================================ profits against metal prices (quarterly)
isd = pd.read_csv(os.path.join(RAW, "fin", "is_601899.csv"))
isd["d"] = pd.to_datetime(isd["REPORT_DATE"].astype(str).str[:10])
isd = isd.sort_values("d")
cum = pd.Series(pd.to_numeric(isd["PARENT_NETPROFIT"], errors="coerce").values, index=isd["d"]) / 1e8
q = cum[cum.index.month.isin([3, 6, 9, 12])]
q = q[~q.index.duplicated()]
single = q - q.groupby(q.index.year).shift(1).fillna(0)
single = single[single.index >= "2016-01-01"]
qa = pd.DataFrame({"gold": gold, "cu": cu}).resample("QE").mean()
qdf = pd.DataFrame({"np": single}).join(qa, how="left")
res["quarterly"] = {"q": [f"{d.year}Q{(d.month - 1) // 3 + 1}" for d in qdf.index], "np": [round(float(v), 2) for v in qdf["np"]],
                    "gold": [round(float(v), 1) for v in qdf["gold"]], "cu": [round(float(v), 0) for v in qdf["cu"]]}
lq = np.log(qdf[qdf["np"] > 0]).dropna()
lreg = ml.ols(lq["np"], pd.DataFrame({"gold": lq["gold"], "cu": lq["cu"], "t": np.arange(len(lq)) / 4}, index=lq.index))
res["quarterly"]["loglevel_fit"] = {"b_gold": float(lreg.params["gold"]), "b_cu": float(lreg.params["cu"]), "trend": float(lreg.params["t"]),
                                    "r2": float(lreg.rsquared), "n": int(len(lq)), "t_gold": float(lreg.tvalues["gold"]), "t_cu": float(lreg.tvalues["cu"])}

# ============================================================ valuation context: P/E history, A/H premium, Zijin Gold International
vv = pd.read_csv(os.path.join(RAW, "fin", "value_601899.csv"))
vv.index = pd.to_datetime(vv["数据日期"].astype(str).str[:10])
pe = pd.to_numeric(vv["PE(TTM)"], errors="coerce").sort_index()
pe_w = pe.resample("W-FRI").last()
gold_w = gold.resample("W-FRI").last().reindex(pe_w.index)
res["pe_gold"] = ml.series_payload(pd.DataFrame({"pe": pe_w, "gold": gold_w}).dropna().round(2), 2)
h, hk = yahoo("2899.HK", "Close"), yahoo("HKDCNY=X", "Close")
ah = (zj_raw / (h * hk.reindex(h.index).ffill()).reindex(zj_raw.index).ffill() - 1).dropna()
ah = ah[(ah.index >= pd.Timestamp(START)) & (ah.index <= pd.Timestamp(END))]
res["ah_premium"] = {**ml.series_payload(ah.resample("W-FRI").last().dropna().rename("prem").to_frame().round(4), 4),
                     "last": float(ah.iloc[-1]), "avg_since_2016": float(ah.mean()), "min": float(ah.min()), "max": float(ah.max())}


def info(t):
    p = os.path.join(RAW, "yahoo", ml.yahoo_file(t)[:-4] + "_info.json")
    return json.load(open(p)) if os.path.exists(p) else {}


zgi = info("2259.HK")
zgi_px = last_on(yahoo("2259.HK", "Close"), END)
hkd = last_on(hk, END)
res["zgi"] = {"price_hkd": zgi_px, "shares": zgi.get("sharesOutstanding"), "mcap_hkd": zgi.get("marketCap"), "hkdcny": hkd,
              "ret_since_ipo": (zgi_px / 71.59 - 1) if zgi_px else None}

# ============================================================ global gold and copper miners (USD, US calendar)
spx = yahoo("^GSPC", "Close")
glob = []
for t, name in GLOBAL.items():
    if t == "B" and not have(os.path.join("yahoo", ml.yahoo_file(t))):
        t = "GOLD"  # Barrick traded as GOLD until May 2025
    if not have(os.path.join("yahoo", ml.yahoo_file(t))):
        continue
    lv = yahoo(t)
    d = pd.DataFrame({"y": lv, "m": spx, "g": gold_usd, "c": cu_usd}).dropna().pct_change().dropna()
    d = d[(d.index >= "2024-01-01") & (d.index <= pd.Timestamp(END))]
    m3 = ml.ols_hac(d["y"], d[["m", "g", "c"]])
    i = info(t)
    glob.append({"ticker": t, "name": name, "b_mkt": float(m3.params["m"]), "b_gold": float(m3.params["g"]), "b_cu": float(m3.params["c"]),
                 "t_gold": float(m3.tvalues["g"]), "t_cu": float(m3.tvalues["c"]), "r2": float(m3.rsquared),
                 "vol": float(np.log(1 + d["y"]).std() * np.sqrt(252)),
                 "ret_2025": window_ret(lv, "2024-12-31", "2025-12-31"), "ret_ytd": window_ret(lv, "2025-12-31", END),
                 "ret_since_gold_peak": window_ret(lv, gold_peak, END),
                 "pe": i.get("trailingPE"), "pe_fwd": i.get("forwardPE"), "pb": i.get("priceToBook"), "mcap_usd": i.get("marketCap")})
res["global"] = glob
res["global_basis"] = "2024-01-01 起美股日收益，对标普 500、COMEX 黄金、COMEX 铜三因子回归（HAC）"

os.makedirs(OUT, exist_ok=True)
ml.dump_json(res, os.path.join(OUT, "gold_analysis.json"))
show = {k: v for k, v in res.items() if k not in ("long", "rel_strength", "recent", "rolling", "pe_gold", "ah_premium", "quarterly")}
show["monthly"] = {k: v for k, v in res["monthly"].items() if k != "scatter"}
print(json.dumps(ml.clean(show), ensure_ascii=False, indent=1)[:20000])
