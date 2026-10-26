# Data sources and how to reach them

## Contents
1. Check access first
2. The GitHub Actions route
3. Sources by market (US, Hong Kong, A-shares)
4. Web research (news, industry, broker views)
5. Known pitfalls
6. When a dataset will not come: hand the user a precise request

## 1. Check access first

Cloud sessions usually reach package registries (PyPI, npm, Google Fonts) but not finance hosts. Probe before
planning, using an 8-second timeout so a blocked host fails fast:

```bash
for u in https://query1.finance.yahoo.com/v8/finance/chart/AAPL https://datacenter-web.eastmoney.com/api/data/v1/get \
         http://www.cninfo.com.cn/new/data/szse_stock.json https://www1.hkexnews.hk/ https://data.sec.gov/ \
         https://fred.stlouisfed.org/ https://www.csindex.com.cn/; do
  printf "%-70s " "$u"; curl -s -o /dev/null -m 8 -w "%{http_code}\n" "$u" || echo blocked; done
```

- **Hosts reachable** (local machine, open network): run the fetch script directly with `python <slug>_analysis/scripts/fetch_data.py`.
- **Hosts blocked** (the usual case in Claude cloud sessions): use GitHub Actions (section 2). Don't spend time
  on proxies or mirrors; in earlier sessions this route was the only one that worked.
- WebSearch and WebFetch run on Anthropic's servers, so they work even when the sandbox is blocked. Use them for
  articles and pages, not for price series: WebFetch returns a summary, not raw data.

## 2. The GitHub Actions route

The workflow `assets/fetch-market-data.yml` runs on a GitHub-hosted runner, which has open internet. It installs
yfinance, akshare, pdfminer and poppler, runs the fetch script(s), and commits `*_analysis/data/` back to the same
branch.

Setup, once per repository:
1. Copy `assets/fetch-market-data.yml` to `.github/workflows/fetch-market-data.yml`. If an older version exists,
   read it first and keep anything repository-specific.
2. The workflow triggers on pushes to `claude/**` branches that change a `*_analysis/scripts/fetch*.py` file. It
   runs only the scripts changed in that push. Manual runs use `workflow_dispatch` with a `script` path, but
   GitHub only offers dispatch for workflows that exist on the default branch. On a fresh branch, the push trigger
   is the reliable way.

Each run:
1. Commit the fetch script and push. The push starts the run. The commit should not contain other changes you
   still need to iterate on.
2. **While the run is in progress, push code only.** The bot commits data to the same branch and rebases onto
   anything pushed in the meantime (`git pull --rebase` in the workflow). Code-only pushes are therefore safe, but
   don't push files under `*_analysis/data/`. Wait for the data commit in the background, without polling in the
   foreground:
   ```bash
   B=$(git rev-parse --abbrev-ref HEAD)
   until git fetch -q origin "$B" && git log -1 --format=%s "origin/$B" | grep -q '^Refresh raw data'; do sleep 30; done; echo data landed
   ```
   Run this with `run_in_background` and a timeout of about 70 minutes. Meanwhile do web research, write
   `events.json`, or draft the report text.
3. `git pull` (fast-forward) and read `data/raw/`. Then check the log for `ERR` and `empty` lines, using the GitHub
   MCP tools `actions_list` and `get_job_logs`. A run usually takes 5–25 minutes; filings PDFs take most of it.
4. For gaps, write a second script, `fetch_extra.py` (same folder name pattern), with alternative sources for what
   failed, then push it. Two or three rounds are normal.
5. If the workflow never starts, check that the file is on the branch, that the path matches `*_analysis/scripts/fetch*.py`,
   and that Actions are enabled for the repository.

## 3. Sources by market

Benchmarks: use total-return indices where they exist, so that dividends are on both sides of the comparison.

| | US | Hong Kong | A-shares (SH/SZ) |
|---|---|---|---|
| Stock prices | Yahoo (`yfinance`, Adj Close) | Yahoo `NNNN.HK` (4 digits) | Yahoo `6xxxxx.SS` / `0xxxxx.SZ`, `3xxxxx.SZ` (Adj Close reinvests dividends) |
| Market index | `^SP500TR` (fallback `^GSPC`); FRED `SP500`; Stooq | `^HSI`, `^HSCE` (price only) | CSI site via `ak.stock_zh_index_hist_csindex`: `H00300` CSI 300 TR, `000300` price (has volume for the trading calendar) |
| Style / sector | sector ETFs (SMH, XLU …); peers' equal-weight index | equal-weight peer index; HK sector ETFs (e.g. 3069.HK) as a check | `H00922` CSI Dividend TR, `H30269` dividend low-vol; Shenwan industry `ak.index_hist_sw(symbol)` (code list: `ak.sw_index_second_info()` / `third_info()`) |
| Risk-free / rates | Yahoo `^IRX` (3M bill), `^TNX` (10Y); FRED `DGS3MO`, `DGS10`, `BAMLH0A0HYM2` when reachable (it timed out from GitHub runners in October 2026) | `^IRX` (US 3M bill, HKD is pegged) | `ak.bond_zh_us_rate()`: 中国国债收益率2年 (rf), 10年 (rate factor); `ak.macro_china_lpr()` |
| Statements | SEC XBRL companyfacts; Yahoo statements as a check | `ak.stock_financial_hk_analysis_indicator_em(symbol="01530", indicator="报告期")`, `ak.stock_financial_hk_report_em(stock, symbol="利润表"/"资产负债表"/"现金流量表")` | `ak.stock_profit_sheet_by_report_em(symbol="SZ000429")`, `…balance_sheet…`, `…cash_flow_sheet…`, `ak.stock_financial_analysis_indicator_em(symbol="000429.SZ", indicator="按报告期")` |
| Dividends | Yahoo `dividends`; 8-K | results announcements | `ak.stock_fhps_detail_em(symbol)` (ex-date 除权除息日, record date 股权登记日, cash per 10 shares 现金分红-现金分红比例, plan date 预案公告日) |
| Valuation history | compute from price × shares | compute | `ak.stock_value_em(symbol)` (PE TTM, PB, market cap, daily) |
| Filings (text) | EDGAR: submissions JSON → 10-K/10-Q primary docs, 8-K ex-99 press releases (User-Agent with contact required) | HKEXnews: `prefix.do` → stockId → `titleSearchServlet.do` (≤1000 rows per date range); results announcements are PDFs | cninfo: `szse_stock.json` → orgId; POST `hisAnnouncement/query` (`stock="code,orgId"`, categories `category_ndbg_szsh` annual, `category_bndbg_szsh` interim); PDFs at `static.cninfo.com.cn/<adjunctUrl>` |
| Options / implied vol | Yahoo option chain (`ticker.options`, `option_chain`) | — | — |
| Research / news lists | Yahoo news; company IR | AAStocks / company IR via WebSearch | `ak.stock_research_report_em(symbol)` (broker, rating, EPS forecasts), `ak.stock_news_em(symbol)` |

`scripts/fetchlib.py` wraps all of these, and `assets/fetch_template.py` calls them for one market at a time.
For HK and US peers, the fetch template also saves Yahoo `info` per peer (`yahoo/<ticker>_info.json`).
`scripts/finlib.py` turns these files into the standard fundamentals keys:
- US: the company's quarters and fiscal years come from XBRL;
- HK: growth, margins and ROE come from Eastmoney HK indicators;
- both: peer rows come from Yahoo info.
Convert filings to text on the runner: `pdftotext -layout` keeps table columns aligned. Then grep them locally
(`grep -n "营业收入\|通行费" data/raw/filings/*.txt`) and transcribe the figures you need into
`analyze_fundamentals.py`, with a comment naming the document and page or section.

## 4. Web research (news, industry size, broker views, product expectations)

- Use `WebSearch` in standard mode for news and dates. Switch to extended mode for industry statistics, recent
  events, consensus figures or anything niche. Send several searches in one turn.
- Prefer primary sources: company filings and IR pages, exchanges, regulators, statistical bureaus, and industry
  associations. Media is fine for broker targets and channel checks, labelled as third-party.
- For every fact that will appear in the report, keep the URL and the publication date in `events.json`
  (`source`) or in `fundamentals.json` (`sources`, `industry[].url`, `broker_targets[].url`).
- Put events in their own list (`data/events.json`, see `assets/events.example.json`):
  1. Start from the filings list: results, M&A, financing, dividends, buy-backs, guidance.
  2. Add policy and macro shocks that hit the sector.
  3. Run the analysis, read the **top abnormal days** printed by `--events`, and look up what happened on any big
     unexplained day. These are usually the most instructive examples.

## 5. Known pitfalls (each one cost time before)

- **Eastmoney quote endpoints refuse GitHub runners.** `ak.stock_zh_a_hist` and `ak.index_zh_a_hist` hit
  push2/push2his and fail with a connection error. Use Yahoo for A-share stock prices and the CSI site for
  indices. The Eastmoney datacenter endpoints (statements, dividends, valuation, research) still work.
- **Yahoo A-share indices are unreliable.** `000300.SS` came back with one row. Use `stock_zh_index_hist_csindex`,
  with Sina (`ak.stock_zh_index_daily`) and Tencent (`…_tx`) as fallbacks.
- **Eastmoney back-adjusted prices (hfq) add dividends back as fixed amounts.** That understates percentage
  returns, so compute returns from Yahoo Adj Close, which reinvests dividends multiplicatively. Use raw close
  only for price charts and dividend yield.
- **Partial last session.** A fetch run during trading hours writes an incomplete last row. Set `END` to the last
  complete session that every source has (the template defaults to the earlier of the stock's and the index's
  last dates) and say so in the report's date stamp.
- **Restated comparatives.** After a common-control acquisition (同一控制下企业合并), data providers show the
  restated prior year. Growth for the year of the deal must use the figures *as originally reported*, so check
  the annual report's comparative columns.
- **One-off items.** Separate 归母净利润 from 扣非净利润 (A-shares), and GAAP from adjusted figures (HK/US).
  A large write-back or disposal gain can turn a falling core profit into reported growth.
- **Units and currencies.** HK-listed Chinese companies report in RMB but trade in HKD; convert before computing
  P/E or market cap. Yahoo `marketCap` is in the trading currency. Eastmoney amounts are in yuan; divide by 1e6
  for RMB million.
- **HK figures from Eastmoney are in RMB** for every company, even when the `CURRENCY` column says 美元. BeOne's,
  HUTCHMED's and Zai Lab's revenue there is about 7× Yahoo's USD figure. Convert HKD prices and market caps with
  CNY per HKD for every HK name.
- **Yahoo's P/E for HK-listed names** differed by 5–17% from P/E on TTM attributable profit across the 3SBio peers
  (3SBio: 3.7 vs 3.5). Compute P/E and P/B from Eastmoney profit and BPS (`finlib.hk_peer_row`), and say how in the
  table note.
- **Yahoo growth and yield fields.** `revenueGrowth` and `earningsGrowth` are the latest quarter year-on-year.
  `dividendYield` is in percent in recent yfinance; `trailingAnnualDividendYield` is a fraction.
- **Calendars.** Align on the stock's exchange calendar and forward-fill benchmarks for at most 5 days. For
  A-shares, build the calendar from CSI 300 volume above 0, so that suspensions show up as flat days, not
  missing ones.
- **Code formats.** Yahoo HK is 4 digits (`0013.HK`) and akshare HK is 5 (`00013`). A-share B shares are
  `200xxx.SZ` and `900xxx.SS`.
- **SEC** rejects requests without a descriptive User-Agent. **HKEXnews** caps a query at about 1000 rows, so
  split long date ranges. **cninfo** titles contain `<em>` tags and times are epoch milliseconds in UTC+8;
  `fetchlib` cleans both.

## 6. When a dataset will not come

The user said: if data can't be found within about 5 minutes, they would rather fetch it themselves than wait.
So when one dataset has failed twice by two different routes, stop and give the user a precise, copy-pasteable
request. Keep working on everything else in the meantime. Template:

> 需要你帮忙下载：**<数据>**（<代码/名称>），<起止日期>，<频率>，字段：<…>。来源可以用 <网站/终端>。
> 请存成 CSV（第一列日期），放到仓库的 `<slug>_analysis/data/raw/manual/<文件名>.csv`，或直接贴在对话里。
