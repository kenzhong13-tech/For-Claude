# Delivery

## 1. Files in the repository

```
<slug>_analysis/
  README.md                      # Chinese: scope, data table (path / content / source), reproduction commands, disclaimer
  data/raw/...                   # written by the fetch workflow (commit it; it is the audit trail)
  data/events.json
  data/processed/market_analysis.json, fundamentals.json
  scripts/fetch_data.py [fetch_extra.py] analyze_market.py analyze_fundamentals.py
  report/template.html  <slug>_report.html  <slug>_report.pdf
report_kit/                      # shared kit, copied from the skill's scripts/ on first use
.github/workflows/fetch-market-data.yml
```

Use a short English slug (`coreweave`, `popmart`, `3sbio`, `gdexpressway`). Start the README from
`assets/README_template.md`; it follows the earlier reports: a one-paragraph scope that says when prices and financials end, a list of report files, a data table,
a note on how data was fetched (and which sources failed), the commands to reproduce, and a disclaimer.

## 2. Publish the Artifact

Follow the Artifact tool's current instructions. Earlier runs did this:
1. `quickstart` with intent `other` and `design_systems: false`;
2. publish the built HTML file (`report/<slug>_report.html`) as a plain page with icon `chart` and a one-sentence
   Chinese description.

The page already satisfies the page contract: a 2–4-word `<title>` ("<公司>财务分析报告"), tokens with dark mode,
no external scripts, and a phone layout. To update after fixes, publish the same file path again (same URL).

## 3. Commit, push, pull request

- Follow the session's git instructions (branch name, commit trailers, PR rules).
- Commit the report as one commit with a descriptive message, for example "Add <公司> financial analysis report
  with <peer group> peer comparison (Chinese)". The data commits from the workflow bot stay as they are.
- Push only when no fetch workflow is running on the branch.
- If a PR exists for the branch, update its title and body to include the new report. Otherwise open a draft PR.
  The body lists each report folder and what it covers, plus any data-source caveats.
- Before the final commit, make sure the workflow file is in the intended state (template version, push trigger
  limited to `claude/**` and fetch scripts).

## 4. The chat reply (Chinese)

Short, structured, and specific. This structure worked:

```
<公司>（<代码>）的分析做完了。<一句话说明框架和对比对象>。

- **交互式报告：** <artifact link>
- **PDF：** `<slug>_analysis/report/<slug>_report.pdf`（A4，N 页）
- **代码与数据：** 已合入草稿 [PR #n](<link>)

## 核心结论
**一句话：** <thesis>
- **<claim>** <2–3 short sub-points with numbers>
...

## 同业对比（N 家 …）
| 指标 | <公司> | 同业位置 |   ← 8–11 rows: ROE/payout, valuation, yield, leverage, growth, scale, returns by year, sector β, vol
+ 行业规模 / 经营预期 bullets

## 波动率（基准：…）
<vol and return vs benchmarks, β and asymmetry, drawdown>

## 股价与事件（举例）
<4–6 examples: date, event, move vs market/sector, AR and t, takeaway>

## 说明
<how data was obtained and what failed; cut-off dates; illustrative items; third-party data; 不构成投资建议>

## 主要来源
<markdown links, grouped: filings / policy & industry / market events / broker views>
```

- Every link in the reply must be one actually used in the report.
- Keep the conclusions consistent with the page. If you change one, change the other and republish.
- Mention anything left undone, or done differently from the request, in plain words (e.g. "东方财富行情接口拒绝了
  Actions 服务器，个股价格改用 Yahoo Finance").
