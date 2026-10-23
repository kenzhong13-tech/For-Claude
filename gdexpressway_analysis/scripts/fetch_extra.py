"""Second pass for 粤高速A: index histories that Eastmoney's quote server refused to serve to the runner.

Tries CSI's own site (price and total-return versions), then Sina and Tencent. Outputs land in
gdexpressway_analysis/data/raw/idx/.
"""
import os
import time

import akshare as ak

OUT = "gdexpressway_analysis/data/raw/idx"
os.makedirs(OUT, exist_ok=True)


def log(*a):
    print(*a, flush=True)


def save(df, name):
    df.to_csv(os.path.join(OUT, name), index=False)
    log("saved", name, len(df), df.iloc[0].tolist()[:3], df.iloc[-1].tolist()[:3])


# CSI 300, CSI Dividend and CSI Dividend Low Volatility, plus total-return versions (H00xxx), from csindex.com.cn
for code in ("000300", "H00300", "000922", "H00922", "H30269"):
    try:
        save(ak.stock_zh_index_hist_csindex(symbol=code, start_date="20140101", end_date="20261023"), f"csindex_{code}.csv")
    except Exception as e:  # noqa: BLE001
        log("ERR csindex", code, repr(e)[:300])
    time.sleep(1)
for sym in ("sh000300", "sh000922", "sh000001"):
    try:
        save(ak.stock_zh_index_daily(symbol=sym), f"sina_{sym}.csv")
    except Exception as e:  # noqa: BLE001
        log("ERR sina", sym, repr(e)[:300])
    time.sleep(1)
    try:
        save(ak.stock_zh_index_daily_tx(symbol=sym), f"tx_{sym}.csv")
    except Exception as e:  # noqa: BLE001
        log("ERR tx", sym, repr(e)[:300])
    time.sleep(1)
log("done")
