# Data: access, sources, pitfalls

## 1. Access and the GitHub Actions route

Cloud sessions reach PyPI, npm and Google Fonts but usually not finance hosts. Probe once (8 s timeout):

```bash
for u in https://query1.finance.yahoo.com/v8/finance/chart/AAPL https://datacenter-web.eastmoney.com/api/data/v1/get \
         https://www1.hkexnews.hk/ https://data.sec.gov/ https://www.csindex.com.cn/; do
  printf "%-60s " "$u"; curl -s -o /dev/null -m 8 -w "%{http_code}\n" "$u" || echo blocked; done
```

If reachable, run `fetch_data.py` locally. If blocked (the usual case), use `.github/workflows/fetch-market-data.yml`:
it runs on pushes to `claude/**` that change a `*_analysis/scripts/fetch*.py`, executes only the changed scripts,
and commits `*_analysis/data/` back as "Refresh raw data", rebasing onto anything pushed meanwhile. Dispatch only
works once the workflow is on the default branch, so on a fresh branch the push is the trigger.

1. Commit and push the fetch script. While the run is in progress, push code only.
2. Wait in the background (`run_in_background`, timeout ~70 min), and research meanwhile:
   ```bash
   B=$(git rev-parse --abbrev-ref HEAD)
   until git fetch -q origin "$B" && git log -1 --format=%s "origin/$B" | grep -q '^Refresh raw data'; do sleep 30; done
   ```
3. `git pull`, read the run log (`actions_list`, `get_job_logs`) for `ERR` and `empty` lines, then fill gaps with
   `fetch_extra.py`. Two or three rounds are normal; a run takes 5–25 minutes.

WebSearch and WebFetch work even when the sandbox is blocked: use them for articles and filings pages, not for
price series.

## 2. Sources by market

| | US | Hong Kong | A-shares |
|---|---|---|---|
| Prices | Yahoo Adj Close | Yahoo `NNNN.HK` (4 digits) | Yahoo `6xxxxx.SS` / `0xxxxx.SZ` |
| Market index | `^SP500TR` (fallback `^GSPC`) | `^HSI` is price only: use 2800.HK Adj Close as HSI with dividends | `ak.index_hist_csindex`: `H00300` CSI 300 TR, `000300` price (volume gives the calendar) |
| Style / sector | sector ETFs; equal-weight peer index | equal-weight peer index | `H00922` CSI Dividend TR; Shenwan `ak.index_hist_sw` |
| Rates | `^IRX` (3M), `^TNX` (10Y); FRED when reachable | `^IRX` (HKD peg) | `ak.bond_zh_us_yield_em()`: 2Y (rf), 10Y (rate factor) |
| Statements | SEC XBRL companyfacts; 8-K ex-99 releases for KPIs | `ak.stock_financial_hk_analysis_indicator_em(symbol, indicator="报告期")`; `stock_financial_hk_report_em` (see pitfalls) | `ak.stock_profit_sheet_by_report_em(symbol="SZ000429")` etc.; `stock_financial_analysis_indicator_em` |
| Dividends | Yahoo `dividends` | results announcements; `ak.stock_hk_dividend_payout_em` | `ak.stock_fhps_detail_em` (ex-date, record date, cash per 10 shares) |
| Valuation history | price × shares | `ak.stock_hk_valuation_baidu` | `ak.stock_value_em` |
| Filings | EDGAR submissions JSON → 10-K/10-Q, 8-K ex-99 (User-Agent with contact) | HKEXnews `titleSearchServlet.do` (≤1000 rows per range) | cninfo `hisAnnouncement/query`; PDFs at `static.cninfo.com.cn` |
| Options | Yahoo chain; alphaquery (≈3 months of IV30); CBOE/Barchart refuse runners | HKEX stock-option classes page and daily report `dqeYYMMDD.htm` | — |
| Consensus | Yahoo info (targets, forward P/E) | `ak.stock_hk_profit_forecast_et`; Yahoo info | `ak.stock_research_report_em` |

`report_kit/fetchlib.py` wraps these and `assets/fetch_template.py` calls them per market; `report_kit/finlib.py`
turns them into the standard fundamentals keys. Convert filings with `pdftotext -layout` on the runner, grep them
locally, and transcribe figures into `analyze_fundamentals.py` with a comment naming the document and section.

## 3. Web research

- Prefer primary sources (filings, IR pages, exchanges, regulators, statistics bureaus); media is fine for broker
  targets and channel checks, labelled third-party.
- Keep the URL and date of every fact in `events.json` (`source`) or `fundamentals.json` (`sources`,
  `industry[].url`, `broker_targets[].url`).
- Events: start from the filings list (results, M&A, financing, dividends, buy-backs, guidance), add policy and
  macro shocks, then look up the large unexplained days that `--events` prints.

## 4. Pitfalls (each cost time before)

- **Eastmoney quote endpoints refuse runners** (`stock_zh_a_hist`, `index_zh_a_hist`); the datacenter endpoints
  work. **Yahoo A-share indices are unreliable**; use the CSI site, then Sina or Tencent.
- **Eastmoney hfq prices add dividends back as amounts**, understating returns; use Yahoo Adj Close.
- **Partial last session**: set `END` to the last complete session every source has.
- **Restated comparatives and one-offs**: growth in a deal year uses as-reported figures; separate 归母/扣非 or
  GAAP/adjusted; for XBRL annual facts take the latest filing's value (Yum China 2017 revenue moved from 7,144 to
  7,769 under the new revenue standard).
- **Currencies**: Eastmoney HK figures are in RMB for every company, whatever the `CURRENCY` column says; convert
  HKD prices and market caps with CNY per HKD. Yahoo's HK P/E differs 5–17% from P/E on TTM attributable profit:
  compute P/E and P/B yourself. Yahoo's HK dividend yield mixes currencies and specials (9987.HK showed 0.28%):
  compute it from dividends or leave it out.
- **Yahoo fields**: `revenueGrowth`/`earningsGrowth` are latest-quarter YoY; `dividendYield` is in percent,
  `trailingAnnualDividendYield` a fraction. Yahoo's option `impliedVolatility` is often stale: recompute IV from
  mid quotes (`methods.md` §7).
- **akshare renames functions and arguments.** 1.20.4x: `index_hist_csindex`, `bond_zh_us_yield_em`,
  `index_second_info_sw`, `stock_main_stock_holder(symbol=)`. 1.20: `stock_financial_hk_report_em(symbol=<code>,
  indicator=<statement>, period="报告期")`, old form `stock=, symbol=` raises `TypeError`. The fetch template tries
  both; read the Actions log for `AttributeError`/`TypeError` after each run.
- **SEC**: `acceptanceDateTime` is UTC (convert to New York and HKT before choosing reaction days); `filings.recent`
  holds only the latest ~1,000 filings, older ones are in `filings.files` (`…-submissions-001.json`); Yum China
  files results around 06:00 New York since 2024 (HK reacts next day), after the US close before that.
- **Calendars**: align on the stock's exchange calendar, forward-fill benchmarks ≤5 days; for A-shares build the
  calendar from CSI 300 volume so suspensions show as flat days. A release in the HKEX lunch break counts that day.
- **Codes**: Yahoo HK 4 digits, akshare HK 5 digits; HKEXnews caps a query at ~1000 rows; cninfo times are epoch
  ms in UTC+8 with `<em>` tags in titles (`fetchlib` cleans both).
- **NBS**: the data API refuses runners; monthly figures can be rebuilt from press releases on www.stats.gov.cn,
  whose titles mix single months and year-to-date totals.

## 5. When a dataset will not come

After two routes and about 5 minutes, stop and give the user a copy-paste request, then keep working:

> 需要你帮忙下载：**<数据>**（<代码/名称>），<起止日期>，<频率>，字段：<…>。来源可以用 <网站/终端>。
> 请存成 CSV（第一列日期），放到仓库的 `<slug>_analysis/data/raw/manual/<文件名>.csv`，或直接贴在对话里。

Make the analysis read that file when it appears (as `analyze_volarb.py` does with `manual/yumc_iv30.csv`), so the
user's download drops straight in.
