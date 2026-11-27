# Report: structure, writing, build, QA, delivery

## 1. Section plan

The skeleton (`assets/report_skeleton.html`) holds sections 00–12 with the data-driven parts wired. Keep the order
and the numbering style (`<span class="no">06</span>`); insert extra sections (e.g. 波动率套利、周期检验) before
the event study and renumber.

| No. | id | Heading | Must contain |
|---|---|---|---|
| 00 | summary | 核心结论 | 6 tiles; 6–9 key points, each a bold one-sentence claim plus 2–3 sentences of numbers |
| 01 | company | 公司概况与业务 | Business model, revenue mix, key KPIs, ownership |
| 02 | financials | 财务表现分析 | Revenue/profit chart, annual table, recent quarters or halves, one-offs, cash flow |
| 03 | debt | 债务结构与偿债能力 | Cash vs debt, rates, maturities, coverage, ND/EBITDA, payouts vs FCF |
| 04 | sensitivity | 对市场增长的敏感性 | Operating leverage table (示意), empirical check, FX, betas |
| 05 | outlook | 未来规划与公司议程 | Guidance table, projects or deals, dated catalyst table |
| 06 | peers | 同业对比 | 6.1 industry scale, 6.2 growth and profitability, 6.3 performance and volatility in the sector, 6.4 expectations |
| 07 | valuation | 估值 | Multiples vs history and peers, the fitting method, what the price implies, broker targets |
| 08 | volatility | 波动率分析（以…为基准） | Benchmark note, cumulative chart, risk and yearly tables, rolling vol + GARCH, models, rolling β, histogram, drawdowns |
| 09 | events | 股价与事件 | AR formula, event chart and table, AR bars, CAR by year, worked examples, special studies, patterns |
| 10 | risks | 主要风险因素 | 4–6 risks: mechanism, size (from the sensitivity), what to watch |
| 11 | conclusion | 结论 | 2–3 paragraphs, answers to the user's extra questions, the signals to watch |
| 12 | appendix | 方法说明与数据来源 | Methods (auto), data gaps callout, sources with links, disclaimer |

Company-specific blocks that earned their place: road tables and concession runoff (toll roads), pipeline and
royalty grids (biotech), IP/channel/region mix (consumer), backlog and debt stack (AI infrastructure), capacity
by fuel and tariffs (power), store counts and same-store sales (restaurants).

## 2. Writing rules (Chinese)

- Conclusion first; short paragraphs; no filler (值得注意的是、综上所述).
- Every number from the JSON or a linked source; say exactly what it is (归母/扣非, GAAP/adjusted, reported/
  restated, price/total return, period, currency). Prefer computing a sentence's numbers in JS from the data.
- Ranks and "only X is lower" claims come from a sort; "largest ever" or similar needs a source or goes.
- Label third-party (券商目标价（第三方）) and illustrative (示意) content.
- Statistics in plain words with the term once: "β 0.11（几乎不随大盘波动）", "t = −1.9，统计上偏弱". Write p-values
  as "p = 0.142" or "p < 0.001".
- Dates YYYY-MM-DD; the stamp gives the price cut-off, the financial cut-off (period and release date) and the
  report date. Disclaimer "仅供研究学习，不构成投资建议" in the stamp and the appendix.
- Units: 亿元/亿港元/亿美元 in text, 百万 in tables with the unit in the caption; signed changes with U+2212;
  pp (个百分点) for rate differences; multiples as 17.2x in tables.

## 3. Page mechanics

- `report/template.html` is a fragment (title, meta, fonts, style, body, one script). `report_kit/build_report.py`
  fills `/*__BASE_CSS__*/`, `/*__CHARTS_JS__*/` and `__DATA_JSON__` (= `market_analysis.json`, `fund` =
  `fundamentals.json`, and every other JSON in `data/processed/` under its file name, e.g. `DATA.volarb`).
- Edition CSS after the base: `--accent`, `--accent-ink`, `--info-bg` with dark variants; `.tbl tr.me`; print rules
  per wide table id. Keep colours as tokens with the light/dark/data-theme pattern.
- Helpers in the skeleton: `fillRows(tbody, rows)` (cell = string or `{text, n, cls, href}`; row `{me, cells}`),
  `head`, `legend(id, [[cls, label, box]])`, `bullets`, `tiles`, `tone`, `pct`, `spct`, `num`, `fmt0`;
  `data-need="sec|sty|rate|spread|exdiv|peers"` hides blocks without data. Register charts in `charts`.
- charts.js (SVG, responsive, tooltips):

| Function | Use | Key options |
|---|---|---|
| `lineChart` | time series, events, term structures | `x`, `series [{label, values, cls, thin, endLabel}]`, `labels` + `points` (category axis), `ylog` + `logTicks`, `yMin/yMax`, `refs`, `markers` |
| `barChart` | yearly values, grouped bars, histograms | `labels`, `series [{values, cls or fn}]`, `axisLabels`, `valueLabels`, `vfmt` |
| `hbarChart` | rankings, AR by event | `items [{label, v, cls, sub}]`, `labelWidth`, `row` |
| `scatterChart` | stock vs benchmark, KPI vs margin | `x`, `y`, `dates`, `a`, `b`, `xName`, `yName` |
| `stackChart`, `stackMulti` | R² split, mix | `items` / `rows` |

## 4. Build and QA

```bash
python report_kit/build_report.py <slug>_analysis       # counts leftover 【…】
PLAYWRIGHT=$PW node report_kit/shot.mjs <slug>_analysis/report/<slug>_report.html <scratch>/shots "#tbl-peer-fin"
PLAYWRIGHT=$PW FONT_DIR=$FONTS node report_kit/make_pdf.mjs <slug>_analysis/report/<slug>_report.html \
    <slug>_analysis/report/<slug>_report.pdf "<公司>（<代码>）财务分析报告 · <日期>"
python report_kit/pdf_pages.py <slug>_analysis/report/<slug>_report.pdf <scratch>/pages_1-12.png --pages 1-12
```

`shot.mjs` reports empty charts, row counts, too-wide elements and console errors at 1280px light and 400px dark;
crop the tall PNGs into ~2600px pieces before viewing. `make_pdf.mjs` lists overflowing blocks; `pdf_pages.py`
needs an output name ending in `.png`.

Checklist:
- [ ] Every number in the summary, key points, verdicts and conclusion checked against the JSON or the filing
  text; ranks and counts computed; ex-FX and period labels right (9M vs Q3); record vs ex-dividend dates right.
- [ ] Event examples match `ar`, `ar_t`, `car_0_p5` and use reaction days.
- [ ] No 【…】 left; no empty charts, overflow or console errors at either width; dark mode readable.
- [ ] Peer tables fit 1280px (≤11 columns); label columns `white-space: nowrap` so phones scroll instead of
  wrapping one character per line.
- [ ] PDF: no overflowing blocks, split figures or orphan captions. A `.two` pair holding a tall chart splits
  across pages: stack it in print (`display: block`) and shrink the rows.

Fixes seen before: value labels on narrow bars (`vfmt`), long hbar labels (≤8 characters), "−0%" (`fmt0`), wrong
colour named in a caption (keep the colour roles), empty chart (missing series key or a `data-need` block).

## 5. Delivery

- Folder: `<slug>_analysis/{README.md, data/raw, data/events.json, data/processed, scripts, report}`; README from
  `assets/README_template.md` (scope and cut-offs, files, data table, what failed, reproduction, disclaimer).
- Artifact: `quickstart` (intent `other`, `design_systems: false`), then publish `report/<slug>_report.html` with
  icon `chart` and a one-sentence Chinese description; republish the same path after fixes.
- Git: follow the session's branch, trailer and PR rules; push only when no fetch run is in progress; update the
  open PR's title and body (one section per report folder) or open a draft PR.
- Chinese reply:

```
<公司>（<代码>）的分析做完了。<框架与基准一句话>。
- **交互式报告：** <artifact link>
- **PDF：** `<slug>_analysis/report/<slug>_report.pdf`（A4，N 页）
- **代码与数据：** [PR #n](<link>)
## 核心结论      一句话 thesis + 4–6 bold claims with numbers
## <用户追问的专题>  verdict per question with the key statistics
## 同业对比      table of 6–10 rows + industry and expectations bullets
## 波动率        vs benchmarks, β, drawdown
## 股价与事件    4–6 examples with AR and t
## 说明          data route and gaps (with the data request), cut-offs, illustrative and third-party items
## 主要来源      markdown links actually used in the report
```
