---
name: stock-analysis-report
description: Produce a full Chinese-language equity research report on a listed company (A-share, Hong Kong or US) the way this user wants it. Covers business and financials, debt and ability to pay, sensitivity to market growth, future plans, a peer comparison (growth, industry size, volatility within the sector, product and operating expectations), valuation, a volatility analysis against benchmarks, and an event study of how the share price reacts to news, with worked examples. Delivers an interactive HTML report published as an Artifact, an A4 PDF, reproducible scripts and data committed to the repo, and a Chinese summary. Use this whenever the user asks to analyse a stock or a company, for example 帮我分析下XX, 做一份XX的财务分析, 再跑一份XX的, 跟同行业对比一下, or analyze TICKER, even if they never say report. Prefer it over generic equity-research skills for single-company analysis.
---

# Stock analysis report (个股财务分析报告)

This skill turns "帮我分析下 XX" into the report format the user approved four times (CoreWeave, Pop Mart, 3SBio,
粤高速A). Each report is a long, data-driven Chinese page with charts, a matching PDF, and the code and data
behind it. The steps below encode what worked and what had to be fixed along the way. The tested building
blocks in `scripts/` and `assets/` let the next report start from the analysis rather than the plumbing.

## What the user expects

From the user's own requests:
- **Language:** Chinese.
- **Content:** every essential part of a research report, plus:
  - **debt and the ability to pay**;
  - **sensitivity to the growth of the market**;
  - **the company's future plans and agenda**;
  - a **volatility analysis against a benchmark** (use theirs if they name one);
  - **how the share price reacts to events, with examples**;
  - a **peer comparison** of growth rates, industry size, the stock's volatility within its sector, and product or operating expectations.
- **When data won't come:** they would rather fetch it themselves than wait. If a dataset still can't be
  obtained after about 5 minutes and two different routes, hand them a precise request (template in
  `references/data-sources.md` §6) and carry on with everything else.

Keep the user posted with one short status line when a phase changes. Each report took several hours of work,
and the user follows along from the app.

## Skill files

| Path | What it is | Where it goes in the repo |
|---|---|---|
| `scripts/marketlib.py` | Volatility, betas, factor models, GARCH, peers (leave-one-out), event study, ex-dividend study, yield spread, CDS/Merton helpers | `report_kit/` |
| `scripts/fetchlib.py` | Yahoo, akshare, cninfo, HKEXnews, SEC and FRED download helpers with the endpoints that work | `report_kit/` |
| `scripts/finlib.py` | US and HK fundamentals: SEC XBRL quarters and years, Eastmoney HK indicators, Yahoo-based peer rows (P/E and P/B computed with FX) | `report_kit/` |
| `scripts/build_report.py` | Inlines CSS, JS and data into the template; counts leftover 【…】 placeholders | `report_kit/` |
| `scripts/base.css`, `scripts/charts.js` | Page design (light and dark) and the SVG chart library | `report_kit/` |
| `scripts/shot.mjs`, `scripts/make_pdf.mjs`, `scripts/pdf_pages.py` | Screenshots with layout diagnostics, A4 PDF export, PDF contact sheet | `report_kit/` |
| `scripts/setup_env.sh` | Python packages and offline Chinese fonts for PDF export | run it; don't commit |
| `assets/fetch-market-data.yml` | GitHub Actions workflow that fetches data on a runner with open internet | `.github/workflows/` |
| `assets/fetch_template.py` | Per-market fetch script (A / HK / US) | `<slug>_analysis/scripts/fetch_data.py` |
| `assets/analyze_market_template.py` | Config-driven market analysis; reproduces the 粤高速 numbers exactly | `<slug>_analysis/scripts/analyze_market.py` |
| `assets/analyze_fundamentals_template.py` | Standard fundamentals and peer table for A / HK / US (`MARKET` switch) | `<slug>_analysis/scripts/analyze_fundamentals.py` |
| `assets/report_skeleton.html` | Report page with all 13 sections; market, peer and event parts already wired to the data | `<slug>_analysis/report/template.html` |
| `assets/events.example.json`, `assets/fundamentals.example.json` | Shapes of the two hand-built inputs | reference |
| `assets/README_template.md` | The report folder's Chinese README | `<slug>_analysis/README.md` |
| `assets/example/` | The approved 粤高速A report: page, fundamentals script, events, README (see `EXAMPLE.md`) | reference for style and company-specific blocks |
| `references/data-sources.md` | Data access route, sources by market, pitfalls, the "ask the user" template | read in phase 2 |
| `references/methods.md` | What to compute, why, and how to interpret it | read in phase 3 |
| `references/report-spec.md` | Section plan, writing rules (Chinese), units, chart roles | read in phase 4 |
| `references/build-and-qa.md` | Template mechanics, chart API, build commands, QA checklist, known fixes | read in phase 5 |
| `references/delivery.md` | Repository layout, Artifact, git and PR, the chat reply format | read in phase 6 |

`SKILL_DIR` below means this skill's folder.

## Workflow

### Phase 0: Scope (about 5 minutes)

Pin down these items, then create a task list for the phases:
- the company, its code and market (A / HK / US);
- the benchmark: the user's choice, or the market's total-return index;
- an optional style index and whether rates matter (bond proxies, banks, utilities, toll roads, REITs);
- 10–15 listed peers in the same market;
- a short English slug (e.g. `gdexpressway`).

Ask only if the company itself is ambiguous (e.g. A and H shares, or several listings). Otherwise choose
sensible defaults and state them in the report.

### Phase 1: Set up the repository

```bash
mkdir -p report_kit <slug>_analysis/{scripts,report,data/processed} .github/workflows
cp -n SKILL_DIR/scripts/{marketlib.py,fetchlib.py,finlib.py,build_report.py,base.css,charts.js,shot.mjs,make_pdf.mjs,pdf_pages.py} report_kit/
bash SKILL_DIR/scripts/setup_env.sh <scratchpad>/fonts      # prints PLAYWRIGHT=… FONT_DIR=…
grep -qx '__pycache__/' .gitignore 2>/dev/null || printf '__pycache__/\n*.pyc\n' >> .gitignore
```

`cp -n` keeps an existing `report_kit/`. If the repository's copy differs from the skill's, diff the two and keep
the newer fixes. Install the workflow from `assets/fetch-market-data.yml`: read any existing workflow first and
merge, don't overwrite blindly.

### Phase 2: Data (read `references/data-sources.md`)

1. Probe access to the finance hosts. Cloud sessions are usually blocked, so plan on GitHub Actions.
2. Write `<slug>_analysis/scripts/fetch_data.py` from `assets/fetch_template.py` (set MARKET, TARGET, PEERS,
   dates and filters). Commit it and push. The push starts the workflow.
3. **Until the bot's data commit lands, push only code** (no files under `<slug>_analysis/data/`). The workflow
   rebases its data commit onto newer commits, so code-only pushes are safe. Wait for the data with the
   background loop in `references/data-sources.md` §2.
   Meanwhile, research in parallel with WebSearch and WebFetch:
   - events and their sources (`data/events.json`, see `assets/events.example.json`);
   - industry size;
   - guidance, pipeline and projects;
   - broker targets.
4. Pull, read the run log, and fill gaps with `fetch_extra.py`. Apply the 5-minute rule to any dataset that won't
   come.

### Phase 3: Analysis (read `references/methods.md`)

1. Copy `assets/analyze_market_template.py`, edit CONFIG and LOAD, and run it with `--events`.
   - Read the top abnormal days.
   - Look up any big unexplained day, and add real events to `events.json`.
   - Re-run until the event list explains the large moves.
2. Copy `assets/analyze_fundamentals_template.py` and set `MARKET`.
   - **A-shares:** it builds the annual table, the balance sheet, solvency, valuation and the full peer table
     from Eastmoney data.
   - **HK:** growth, margins, ROE and BPS come from Eastmoney HK indicators, which are in RMB for every company.
     Market cap, debt, cash and EBITDA come from Yahoo. P/E and P/B are recomputed with CNY per HKD, because
     Yahoo's P/E differed by 5–17%.
   - **US:** quarters and years come from SEC XBRL; peers come from Yahoo, whose growth fields are
     latest-quarter year-on-year.
   - Transcribe whatever the data files lack (cash and debt for HK, segments, operating KPIs) from the filings
     text, with a comment citing each document.
   - Then add the company-specific blocks: segments, assets or pipeline, debt stack, scenarios, debt path.
     `assets/example/` shows how the 粤高速 report did these.
   - Fix restated comparatives and separate out one-offs.
3. Compute every rank and median you intend to quote (`rank_of`, `peer_ranks`, `peer_medians`).
4. Before writing, print a compact "fact sheet" of the 30–50 numbers the narrative will use. Write from that
   sheet, never from memory.

### Phase 4: Write (read `references/report-spec.md`)

Copy `assets/report_skeleton.html` to `report/template.html`. Skim `assets/example/gdexpressway_template.html` for
the tone and density the user approved. Then set:
- the title, kicker, stamp and an accent colour;
- the narrative in every 【…】 placeholder;
- the company-specific charts and tables (register them in `charts`).

The skeleton already renders the tiles, the volatility, model, peer-risk and event sections, the auto text, the
methods list and the sources from the JSON. Lead with conclusions, give every claim its number and comparison,
label third-party and illustrative content, and write 3–6 worked event examples.

### Phase 5: Build and QA (read `references/build-and-qa.md`)

1. Run `build_report.py` and `shot.mjs` (desktop light and phone dark). View the cropped screenshots, then fix
   and repeat.
2. Run `make_pdf.mjs` and `pdf_pages.py`. Fix every overflowing block and broken page.
3. Work through the QA checklist. The numbers audit matters most: earlier drafts had wrong ranks, a "recovered to
   pre-COVID" claim that was really 98%, restated-vs-reported mix-ups and unverifiable peer claims, all caught
   here.

### Phase 6: Deliver (read `references/delivery.md`)

1. Write the README from `assets/README_template.md`.
2. Publish the Artifact.
3. Commit and push, then create or update the draft PR.
4. Reply in Chinese with links, conclusions, the peer table, volatility, event examples, caveats and sources.

## Rules that keep the report trustworthy

- **Numbers come from the JSON or a cited source**, never from memory. Ranks are computed. Rounding never changes
  the meaning. These are the errors that slipped into earlier drafts.
- **Use returns that include dividends** (Yahoo Adj Close, total-return indices) for every performance comparison.
  Raw prices are only for price charts and yield.
- **Cut the sample at the last complete session** and say which date it is. A fetch during trading hours leaves a
  partial last row.
- **Mark illustrative calculations** (scenarios, debt paths, valuation grids) with 示意 and list their
  assumptions. **Label third-party data** (broker targets, consensus, industry statistics) with source and date.
- **While the fetch workflow runs, push code only.** The bot rebases its data commit onto your pushes, but changes
  under `*_analysis/data/` would conflict with it. Never push the old manual-only workflow over the new one.
- **Keep the colour roles:** the company is always orange (c2/f2), the market blue, the sector green, style amber.
  Captions must name colours correctly.
- **Use defaults instead of asking:** benchmark, sample length, peers. State them in the report. Ask the user
  only for genuinely missing inputs, or for data you couldn't get (the 5-minute rule).
