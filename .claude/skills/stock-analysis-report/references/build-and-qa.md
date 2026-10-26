# Building the page and checking it

## Contents
1. How the page is put together
2. charts.js API
3. Table and text helpers in the skeleton
4. Build, screenshots, PDF
5. QA checklist (run all of it before publishing)
6. Problems seen before and their fixes

## 1. How the page is put together

- `report/template.html` is a **fragment**: `<title>`, `<meta>`, font links, `<style>`, then body content and one
  `<script>`. There is no `<!doctype>`/`<html>`; the Artifact host, `shot.mjs` and `make_pdf.mjs` wrap it.
- Three placeholders are filled by `report_kit/build_report.py`:
  - `/*__BASE_CSS__*/` ← `base.css`, which has the design tokens, light and dark themes, layout, tables, tiles,
    callouts and print basics;
  - `/*__CHARTS_JS__*/` ← `charts.js`;
  - `__DATA_JSON__` ← `market_analysis.json`, plus `fund` = `fundamentals.json`.
- **Edition CSS** goes right after the base CSS:
  - an accent colour that fits the company (`--accent`, `--accent-ink`, `--info-bg`, each with dark variants);
  - `.tbl tr.me` for the highlighted row;
  - print rules for wide tables (smaller font and padding, wrapping headers, keyed by table id).
- The page is self-contained (no external scripts). Data, CSS and JS are inlined, so the built HTML (≈0.6–1 MB)
  opens offline and publishes as a single Artifact.
- Theme: `base.css` defines tokens on `:root` and redefines them under `prefers-color-scheme: dark`
  (guarded by `:root:not([data-theme="light"])`) and under `:root[data-theme="dark"]`. Keep that pattern for
  any new colour.

## 2. charts.js API

All charts are SVG, responsive to the container's width (re-rendered on resize), with tooltips and keyboard
focus. `el` is the `.chart-box` element.

| Function | Use for | Key options |
|---|---|---|
| `lineChart(el, cfg)` | time series, rebased performance, rolling stats, event markers | `x` (dates), `series: [{label, values, cls:'c1'..'c7', thin, endLabel, area}]`, `yfmt`, `tfmt`, `ylog` + `logTicks`, `yMin`/`yMax`, `refs: [{y, label, side}]`, `markers: [{i, n, up, cls, title, rows, desc, aria}]`, `labels` (category x-axis), `points`, `height` |
| `barChart(el, cfg)` | yearly values, grouped bars, histograms | `labels`, `series: [{label, values, cls or (v,i)=>cls}]`, `yfmt`, `tfmt`, `vfmt`, `valueLabels: true or (i,k)=>bool`, `axisLabels` (sparse x labels), `rotateNarrow`, `every`, `height` |
| `hbarChart(el, cfg)` | rankings (peers, AR by event); diverging around 0 | `items: [{label, v, cls, title, sub, desc}]`, `fmt`, `tfmt(d)`, `labelWidth`, `row` |
| `stackChart(el, cfg)` | explained vs specific variance | `items: [{label, share}]` |
| `stackMulti(el, cfg)` | revenue mix, 100% stacked | `rows: [{label, parts: [{name, v, cls}]}]`, `vfmt`, `labelWidth` |
| `scatterChart(el, cfg)` | stock vs benchmark excess returns, with a fit line | `x`, `y`, `dates`, `a`, `b`, `xName`, `yName` |

Formatters: `pct(v,d)`, `spct(v,d)` (signed, uses −), `num(v,d)`, `usd(v,d)`. Classes: `c1..c4, c7` for lines,
`f1..f4, f7` for fills, `fpos/fneg/fmid` for signed bars. Legends are HTML (`.legend` with
`<span class="leg-c2"><i></i>名称</span>`; add `class="box"` on the `<i>` for bars), or use `legend(id, items)`
in the skeleton.

Register every chart in the `charts` object (`'ch-id': e => lineChart(e, {...})`); `renderAll()` draws them and
skips containers hidden with `[hidden]` / `data-need`.

## 3. Table and text helpers in the skeleton

- `fillRows(tbody, rows)`. Each row is an array of cells, or `{me: true, cells: [...]}` to highlight the company's
  row. A cell is a string or `{text, n: 1 (numeric, right-aligned), cls: 'pos-t'|'neg-t'|'sig'|'w'|'nw'|'small', href}`.
- `head(theadId, labels, textCols)` builds a header row; the first `textCols` columns are left-aligned.
- `tone(v)` colours by sign. `bullets(id, [[bold, text], …])` and `tiles(id, [[label, value, small, desc], …])`
  fill lists and tiles.
- `data-need="sec|sty|rate|spread|exdiv|peers"` hides a block when that data is absent.
- Auto-filled text (benchmark note, GARCH sentence, beta bullets, event lede, AR formula, methods list, sources)
  comes from the data, so it stays correct after a re-run. The narrative in `【…】` placeholders is yours to write.

## 4. Build, screenshots, PDF

From the repository root:

```bash
python <slug>_analysis/scripts/analyze_market.py --events      # prints events, top abnormal days, peers
python <slug>_analysis/scripts/analyze_fundamentals.py
python report_kit/build_report.py <slug>_analysis               # -> report/<slug>_report.html, counts 【…】 left
PW=/opt/node-tools/node_modules/playwright/index.js             # Claude cloud sessions; locally just "playwright"
PLAYWRIGHT=$PW node report_kit/shot.mjs <slug>_analysis/report/<slug>_report.html <scratch>/shots "#ch-price" "#tbl-peer-vol"
PLAYWRIGHT=$PW FONT_DIR=<scratch>/fonts node report_kit/make_pdf.mjs <slug>_analysis/report/<slug>_report.html \
    <slug>_analysis/report/<slug>_report.pdf "<公司>（<代码>）财务分析报告 · <日期>"
python report_kit/pdf_pages.py <slug>_analysis/report/<slug>_report.pdf <scratch>/pages.png --cols 6
```

- `shot.mjs` takes full-page screenshots at desktop light (1280px) and phone dark (400px), plus 2× element shots
  for any selectors. It prints empty charts, table row counts, elements wider than the viewport, leftover `【】`
  placeholders, and console errors.
- Full-page PNGs are tall. Crop them into chunks of about 3000px with PIL before viewing them with Read.
- `make_pdf.mjs` prints at A4 with a 703px content width. Chromium matches print media queries against 794px, so
  the script renders at that viewport. It lists **overflowing blocks**; fix every one with print CSS for that
  table id. `FONT_DIR` holds local Noto Sans/Serif SC for machines without Google Fonts access
  (`scripts/setup_env.sh` downloads them from npm).
- `pdf_pages.py` builds a contact sheet. Look for split figures, orphaned headings, blank pages and clipped tables.

## 5. QA checklist

Do this before publishing; earlier reports needed several rounds of these fixes.

**Numbers and claims**
- [ ] Every number in the narrative matches the JSON or a cited source. For the summary, the key points and the
  conclusion, check each one against the data in a scratch script.
- [ ] Ranks and "最高/最低" statements come from `rank_of` or a sort, and the count of companies is right.
- [ ] Reported vs core profit, restated vs as-reported, price vs total return, and periods are labelled.
- [ ] Each illustrative calculation is marked as such, with its assumptions shown.
- [ ] Third-party data (broker targets, consensus, industry figures) has a source and date.
- [ ] Event examples match `market_analysis.json` (`ar`, `ar_t`, `car_0_p5`, same-day moves) and their dates
  are reaction days.
- [ ] No 【…】 placeholders are left (`build_report.py` and `shot.mjs` both count them).
- [ ] Re-read the whole text once as a sceptical reader: does any sentence claim more than the data shows?

**Rendering**
- [ ] `shot.mjs` reports no empty charts, no too-wide elements and no errors at either width.
- [ ] Desktop and phone screenshots: labels don't collide, legends match the series, tooltips work, and the
  company is highlighted in every peer chart.
- [ ] Dark mode is readable (no hard-coded colours outside the tokens).

**PDF**
- [ ] `make_pdf.mjs` lists no overflowing blocks and no page errors.
- [ ] The contact sheet shows no broken tables or figures. Add `break-inside: avoid` to the print CSS for small
  tables that split.

## 6. Problems seen before and their fixes

| Symptom | Fix |
|---|---|
| Value labels overlap on narrow bar charts | `barChart` already hides them when they don't fit; use `vfmt` for shorter text |
| Negative values in `hbarChart` collide with category labels on phones | Handled in charts.js (label inside the bar or right of zero) |
| Long Chinese labels overflow `hbarChart` | Label width is estimated (CJK = 12px); shorten `short` labels to ≤8 characters |
| Wide tables clipped in the PDF | Print CSS: `font-size: 10–10.5px`, `padding: 4px`, `white-space: normal` on `th` (ids as in the skeleton) |
| A caption names the wrong colour | Use the fixed colour roles; the company is always f2/c2 |
| "−0%" labels | Use `fmt0` (prints "0%" for \|v\| < 0.5%) |
| Mixed date formats (2016/01 vs 16/01) | Pick one per table (`dt()` gives YY/MM) |
| Tiles leave an empty grey cell | Use 3 or 6 tiles per grid |
| A chart is empty with no console error | The container was hidden by `data-need`, or the series key is missing from the JSON: check `S.<key>` |
| A sector chart is missing on a stock without peers | Expected; HAS.sec is false, so those blocks hide themselves |
