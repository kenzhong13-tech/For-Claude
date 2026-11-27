---
name: stock-analysis-report
description: Produce a full Chinese-language equity research report on a listed company (A-share, Hong Kong or US) the way this user wants it. Covers business and financials, debt and ability to pay, sensitivity to market growth, future plans, a peer comparison (growth, industry size, volatility within the sector, product and operating expectations), valuation, a volatility analysis against benchmarks, and an event study of how the share price reacts to news, with worked examples; optional modules for dual listings, volatility-arbitrage feasibility and cycle or seasonality tests. Delivers an interactive HTML report published as an Artifact, an A4 PDF, reproducible scripts and data committed to the repo, and a Chinese summary. Use this whenever the user asks to analyse a stock or a company, for example 帮我分析下XX, 做一份XX的财务分析, 再跑一份XX的, 跟同行业对比一下, or analyze TICKER, even if they never say report. Prefer it over generic equity-research skills for single-company analysis.
---

# Stock analysis report (个股财务分析报告)

A long, data-driven Chinese report page with charts, a matching A4 PDF, and the code and data behind it. Seven
reports in this repository follow it; `yumchina_analysis/` (HK + US listing, the optional modules) and
`shpower_analysis/` (A-share) are the best references for tone, density and company-specific blocks.

## What the user expects

- **Chinese**, every essential part of a research report, plus:
  - debt and ability to pay;
  - sensitivity to the growth of the market;
  - the company's future plans and agenda;
  - a volatility analysis against a benchmark (theirs if they name one);
  - how the share price reacts to events, with worked examples;
  - a peer comparison: growth, industry size, volatility within the sector, product or operating expectations.
- Extra questions in the request (e.g. "波动套利可能性", "周期 pattern") get their own section with statistical tests
  and a plain verdict.
- **Data that won't come:** after about 5 minutes and two different routes, hand the user a precise request
  (`references/data.md` §5) and carry on with everything else.
- One short status line whenever a phase changes; reports take hours and the user follows from the app.

## Files

| Path | What it is |
|---|---|
| `report_kit/` (repo root) | Shared kit: `marketlib.py` (vol, betas, factor models, GARCH, peers, event study), `fetchlib.py` (Yahoo, akshare, cninfo, HKEXnews, SEC, FRED), `finlib.py` (SEC XBRL, Eastmoney HK, Yahoo peer rows), `build_report.py`, `base.css`, `charts.js`, `shot.mjs`, `make_pdf.mjs`, `pdf_pages.py`, `setup_env.sh` |
| `.github/workflows/fetch-market-data.yml` | Fetches data on a GitHub runner (the session sandbox can't reach finance sites) |
| `assets/fetch_template.py` | Per-market fetch script (A / HK / US) → `<slug>_analysis/scripts/fetch_data.py` |
| `assets/analyze_market_template.py` | Config-driven market analysis → `scripts/analyze_market.py` |
| `assets/analyze_fundamentals_template.py` | Fundamentals and peer table (`MARKET` switch) → `scripts/analyze_fundamentals.py` |
| `assets/report_skeleton.html` | Report page with all sections; market, peer and event parts wired to the data → `report/template.html` |
| `assets/events.example.json`, `assets/fundamentals.example.json`, `assets/README_template.md` | Shapes of the hand-built inputs; the folder README |
| `references/data.md` | Access route, sources by market, pitfalls, the data-request template (phase 2) |
| `references/methods.md` | What to compute and how to read it, including the optional modules (phase 3) |
| `references/report.md` | Section plan, writing rules, chart API, build commands, QA checklist, delivery (phases 4–6) |

`report_kit/` and the workflow live beside this skill in the same repository; copy them along if the skill moves.

## Workflow

**0. Scope (5 min).** Pin down the company, code and market, the benchmark (the user's, or the market's
total-return index), optional style or rate factors, 10–15 peers in the same market, and an English slug. Ask
only if the company itself is ambiguous (similar names, several listings); otherwise choose defaults and state
them in the report. Create a task list for the phases.

**1. Set up.** `mkdir -p <slug>_analysis/{scripts,report,data/processed}`; run `bash report_kit/setup_env.sh
<scratchpad>/fonts` (Python packages, offline Chinese fonts; prints `PLAYWRIGHT=… FONT_DIR=…`).

**2. Data** (`references/data.md`). Probe access; write `fetch_data.py` from the template; push it (the push
starts the workflow). Until the bot's "Refresh raw data" commit lands, push code only. Meanwhile research events
(`data/events.json`), industry size, guidance and broker views. Then fill gaps with `fetch_extra.py`.

**3. Analysis** (`references/methods.md`). Run the market template with `--events`; look up every large
unexplained abnormal day and add it to `events.json`. Build fundamentals: transcribe what the data lacks from the
filings (comment each figure with its document), separate one-offs, fix restatements. Compute every rank and
median you will quote. Print a fact sheet of the 30–50 numbers the narrative will use and write from it.

**4. Write** (`references/report.md`). Copy the skeleton, set the title, kicker, stamp and accent, write every
【…】 placeholder, add company-specific charts and tables. Lead with conclusions; give every claim its number and
comparison; label third-party and illustrative content; 3–6 worked event examples.

**5. Build and QA.** `build_report.py`, `shot.mjs` (desktop light, phone dark), `make_pdf.mjs`, `pdf_pages.py`.
Fix every empty chart, overflow and broken page. Do the numbers audit: check each claim against the JSON or the
filing text.

**6. Deliver.** README from the template, publish the Artifact, commit and push, update or open the draft PR,
reply in Chinese with links, conclusions, the peer table, volatility, event examples, caveats and sources.

## Rules

- **Numbers come from the JSON or a cited source, never from memory.** Ranks are computed; rounding never
  changes the meaning; a fact about the company is checked against the filing text (grep the releases).
- **Total-return prices** (Yahoo Adj Close, TR indices) for every performance comparison; raw prices only for
  price charts and yields. **Cut the sample at the last complete session** and say which date it is.
- **Mark illustrative calculations** (示意, with assumptions) and **label third-party data** (source and date).
- **While the fetch workflow runs, push code only**; never touch `*_analysis/data/` until the data commit lands.
- **Colour roles:** company orange (c2/f2), market blue (c1), sector green (c3), style amber (c4), a model or
  second series purple (c7). Captions must name colours correctly.
- **Defaults over questions:** benchmark, sample length, peers. Ask only for genuinely missing inputs.
