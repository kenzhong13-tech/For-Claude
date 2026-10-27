# Report specification: structure and writing

## Contents
1. What the user expects
2. Section plan (00–12)
3. Writing rules (Chinese)
4. Numbers, units and formatting
5. Charts and tables per section

## 1. What the user expects

Every report so far was built around what the user asked for in the first request, plus the peer comparison
they asked for later and then praised:
- all the essential parts of an equity research report, written in **Chinese** (unless asked otherwise);
- **debt and ability to pay**;
- **sensitivity to the growth of the market**;
- the **company's future plans and agenda**;
- a **volatility analysis against a benchmark** (the user may name it, e.g. S&P 500);
- **how the share price reacts to events, with examples**;
- a **peer comparison**: growth rates, industry size, the stock's volatility within its sector, and product or
  operating expectations.

Deliverables: an interactive HTML page published as an Artifact, an A4 PDF in the repository, code and data
committed, and a Chinese summary in chat (see `delivery.md`).

## 2. Section plan

The skeleton (`assets/report_skeleton.html`) contains every section below, with the data-driven parts already
wired. Adapt the headings to the company, but keep the order and the numbering style (`<span class="no">06</span>`):
readers of earlier reports find their way by them.

| No. | id | Heading | Must contain |
|---|---|---|---|
| 00 | summary | 核心结论 | 6 tiles (price and market cap, valuation, vol, β, drawdown, return); 6–8 key points, each a bold one-sentence claim followed by 2–3 sentences of numbers |
| 01 | company | 公司概况与业务 | Business model, revenue mix, key assets / products / KPIs, ownership |
| 02 | financials | 财务表现分析 | Revenue/profit chart, annual table, latest halves or quarters, one-offs, cash flow |
| 03 | debt | 债务结构与偿债能力 | Cash vs debt, structure, rates, maturities, coverage, ND/EBITDA, forward funding needs (illustrative path if capex-heavy) |
| 04 | sensitivity | 对市场增长的敏感性 | Operating leverage, scenarios, market / sector / rate betas, FX where relevant |
| 05 | outlook | 未来规划与公司议程 | Guidance, projects, pipeline, M&A, payout plans, a dated catalyst list |
| 06 | peers | 同业对比：增长、行业规模、股价波动与经营预期 | 6.1 industry scale (sourced), 6.2 growth and profitability, 6.3 stock performance and volatility within the sector, 6.4 expectations |
| 07 | valuation | 估值 | Multiples against history and peers, the method that fits, what the price implies, broker targets |
| 08 | volatility | 波动率分析（以…为基准） | Benchmark note, cumulative chart, risk table, yearly table, rolling vol + GARCH, model table + R² split, rolling β/correlation, histogram, drawdowns, a short wrap-up |
| 09 | events | 股价与事件：事件研究 | AR formula, event chart, event table, AR bars, CAR by year, 3–6 worked examples, special studies, patterns |
| 10 | risks | 主要风险因素 | 4–6 risks, each with mechanism, size (from the sensitivity numbers) and a signal to watch |
| 11 | conclusion | 结论 | 2–3 paragraphs, then "接下来最值得关注的 N 个信号" |
| 12 | appendix | 方法说明与数据来源 | Methods (auto-filled), data sources with links, disclaimer |

Company-specific additions that earned their place before:
- toll roads: a road table (stake, traffic, toll, expiry), the effect of a competing bridge, concession runoff;
- biotech: a pipeline table (phase, indication, timing, partner), licensing economics, a royalty scenario grid;
- consumer: revenue by IP, channel and region, overseas growth, inventory;
- AI infrastructure: backlog and RPO, a capex and debt stack, customer concentration, implied vol.

A closing callout may compare the company with earlier reports in the repository (CoreWeave, Pop Mart, 3SBio,
粤高速) when that helps the reader place it.

## 3. Writing rules (Chinese)

- **Conclusion first.** Every section and every key point opens with the claim; numbers follow. Keep paragraphs
  short (2–4 sentences) and avoid filler such as "值得注意的是" or "综上所述".
- **Every number comes from the data or a cited source.** Copy it from `market_analysis.json` /
  `fundamentals.json`, or from a source that is linked in the appendix. Never use remembered numbers, and never
  round in a way that changes the meaning.
- **Say exactly what the number is:** 归母 vs 扣非 (or GAAP vs adjusted), reported vs restated, price vs total
  return, the period, and the currency. Earlier drafts were corrected for exactly these slips. Examples:
  - "收入恢复到疫情前" was wrong; the figure was 98% of 2019.
  - A growth rate needed the as-reported prior year, not the restated one.
- **Ranks** ("第 3 高"、"16 家中最低") only from computed ranks. Ties and missing values must be handled.
- **No unverified claims about peers or the industry.** If a claim can't be sourced, drop it. Earlier peer claims
  about capacity expansion and M&A that could not be verified were removed.
- **Label third-party and illustrative content:** "券商目标价（第三方）" and "示意测算（假设见表）". Write
  "约" only when the number is genuinely approximate.
- **Plain language for statistics,** with the technical term once. Examples: "β 0.11（几乎不随大盘波动）";
  "t = −1.9，统计上偏弱"; "波动冲击的半衰期约 26 个交易日".
- **Dates:** write YYYY-MM-DD or YYYY 年 M 月 D 日, and use one format consistently within a table. The masthead
  stamp states the price cut-off date, the financial cut-off (period and announcement date), and the report date.
- **Disclaimer:** "仅供研究学习，不构成投资建议" in the stamp and the appendix.
- Use names consistently: one short name for the company in charts (e.g. "粤高速") and the full name with the
  code in the title.

## 4. Numbers, units and formatting

- Money in the text is in 亿元, 亿港元 or 亿美元 (one decimal place when under 100). Tables use 百万元 or
  millions, with the unit in the caption or a `cap-sub`. Per-share figures keep 2–3 decimals.
- Percentages: changes carry a sign (+15.3% / −7.4%). Use U+2212 "−" for negatives in display text; the JS
  helpers `spct`/`num` already do this. Use pp (个百分点) for differences between rates.
- Multiples: 17.2x (P/E), 2.59x (P/B), 0.96 倍 (in sentences).
- Bigger is not automatically better. Colour returns by sign (`tone()`), not by "good" or "bad", except where
  the table says so.

## 5. Charts and tables per section

Use the existing chart types (see `build-and-qa.md` for the API) and the fixed colour roles:
- c2/f2 (orange) is always the company;
- c1/f1 (blue) is the market, or "other" bars in peer charts;
- c3/f3 (green) is the sector;
- c4/f4 (amber) is the style index;
- c7 (purple) is a secondary series such as GARCH or one named peer;
- fpos/fneg are positive/negative values.

Captions must name the colours correctly. One earlier chart said "green" while the company bar was blue; check
the colours whenever a class changes.

- 00: tiles (`tiles()`), key points (`ol.keypoints`).
- 02: `ch-rev` grouped bars, `tbl-annual`; optionally a half-year table and a mix chart (`stackMulti`).
- 03: `ch-bal`, `tbl-bal`, solvency bullets; optionally a debt-stack table, a maturity bar chart, a debt-path bar
  chart and table.
- 04: beta summary bullets, `ch-rate` and `ch-gap` (rate-sensitive stocks), a leverage or scenario table.
- 05: a catalyst table (date, event, what to watch, source).
- 06: an industry list, `ch-peer-growth`, `ch-peer-roe`, `tbl-peer-fin`, `ch-rebased`, `ch-peer-vol`,
  `ch-peer-ytd`, `tbl-peer-vol`, an expectations table. Highlight the company row (`me: true`) and the company bar
  (f2).
- 07: valuation tiles, a broker table, and optionally a valuation grid (spread × DPS, scenario P/E).
- 08: `ch-price` (log), `tbl-risk`, `tbl-year`, `ch-vol`, `ch-scatter` + `ch-r2`, `tbl-sim`, `tbl-factors`,
  `ch-beta`, `ch-corr`, `ch-hist`, `ch-dd`.
- 09: `ch-events` (numbered markers), `tbl-events` (title links to the source), `ch-ar`, `ch-car`, worked
  examples, and `ch-exdiv` + `tbl-exdiv` when dividends matter.
