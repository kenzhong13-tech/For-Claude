"""Second fetch for 上海电力: sources the first run missed.

akshare 1.20.4x renamed the CSI index, bond-yield and Shenwan-index functions (the first run logged the new names), the
99qh spot API changed its response, and the 100ppi fallback stopped too early (before May 2016 the thermal-coal futures
code was TC, not ZC). This script fetches:
  idx/csindex_<code>.csv   CSI 300, CSI Dividend and CSI All Share Utilities, price and total return (ak.index_hist_csindex)
  idx/sw_<code>.csv        Shenwan utilities and power indices (ak.index_second_info_sw / index_third_info_sw)
  rates/bond_zh_us_rate.csv  China / US government yields (ak.bond_zh_us_yield_em), same file name as before
  power/100ppi_coal_weekly.csv  thermal-coal spot price from 100ppi's spot-futures table, sampled every Friday
  fin/holders_600021.csv   main shareholders
  filings/announcements_2016_2018.json  announcement titles before 2019, for event dates
"""
import json
import os
import re
import sys
import time

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "report_kit"))
import fetchlib as fl  # noqa: E402

SLUG = os.path.basename(os.path.dirname(HERE))
OUT = os.path.join(SLUG, "data", "raw")
TARGET = "600021"
START, END = "2014-01-01", "2026-11-24"
CSINDEX = ["000300", "H00300", "000922", "H00922", "000995", "H00995"]
SW_PATTERN = r"公用事业|电力|发电|火电|水电|风电|光伏|核电|热力"
for sub in ("idx", "rates", "power", "fin", "filings"):
    os.makedirs(os.path.join(OUT, sub), exist_ok=True)

import akshare as ak  # noqa: E402

s, e = START.replace("-", ""), END.replace("-", "")
for code in CSINDEX:
    fl.tryit(f"csindex {code}", lambda: ak.index_hist_csindex(symbol=code, start_date=s, end_date=e),
             os.path.join(OUT, "idx", f"csindex_{code}.csv"))
fl.tryit("bond yields", lambda: ak.bond_zh_us_yield_em(start_date=s), os.path.join(OUT, "rates", "bond_zh_us_rate.csv"))
fl.tryit("sw 801160 公用事业", lambda: ak.index_hist_sw(symbol="801160", period="day"), os.path.join(OUT, "idx", "sw_801160.csv"))
try:
    for fn_name in ("index_second_info_sw", "index_third_info_sw"):
        info = getattr(ak, fn_name)()
        name_col = next(c for c in info.columns if "名称" in c)
        code_col = next(c for c in info.columns if "代码" in c)
        for code, name in info[[code_col, name_col]].values.tolist():
            if re.search(SW_PATTERN, str(name)):
                c = str(code).split(".")[0]
                fl.tryit(f"sw {c} {name}", lambda: ak.index_hist_sw(symbol=c, period="day"), os.path.join(OUT, "idx", f"sw_{c}.csv"))
except Exception as ex:  # noqa: BLE001
    fl.log("ERR sw", repr(ex)[:200])
fl.tryit("holders", lambda: ak.stock_main_stock_holder(symbol=TARGET), os.path.join(OUT, "fin", f"holders_{TARGET}.csv"))

# thermal-coal spot price: 100ppi's daily spot-futures page, one page per Friday (TC was the futures code before May 2016)
rows, t0, misses = [], time.time(), 0
for d in pd.date_range("2016-01-01", END, freq="W-FRI"):
    if time.time() - t0 > 1200:
        fl.log("100ppi time cap at", d.date())
        break
    try:
        df = ak.futures_spot_price(date=d.strftime("%Y%m%d"), symbols="ZC,TC")
        if df is not None and len(df):
            rows.append(df.assign(sample_date=d.date()))
            misses = 0
        else:
            misses += 1
    except Exception as ex:  # noqa: BLE001
        misses += 1
        if misses <= 3:
            fl.log("100ppi ERR", d.date(), repr(ex)[:150])
    time.sleep(0.3)
if rows:
    fl.save_df(pd.concat(rows), os.path.join(OUT, "power", "100ppi_coal_weekly.csv"))
fl.log("100ppi coal weeks", len(rows))

# announcement titles before 2019 (the first run's list starts in 2019)
try:
    orgs = fl.cninfo_org_ids()
    items = fl.cninfo_list(TARGET, orgs[TARGET], "2016-01-01", "2018-12-31")
    json.dump(items, open(os.path.join(OUT, "filings", "announcements_2016_2018.json"), "w"), ensure_ascii=False, indent=1)
    fl.log("cninfo 2016-2018 items", len(items))
except Exception as ex:  # noqa: BLE001
    fl.log("ERR cninfo 2016-2018", repr(ex)[:300])
fl.log("done")
