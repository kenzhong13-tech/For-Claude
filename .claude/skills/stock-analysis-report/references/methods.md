# Analysis methods

## Contents
1. Benchmarks and conventions
2. Volatility and risk (section 08 of the report)
3. Betas and factor models (sections 04 and 08)
4. Peers inside the sector (section 06)
5. Event study (section 09)
6. Fundamentals: financials, debt and ability to pay, sensitivity, plans, valuation (sections 01–07)
7. Interpreting results: what is worth saying

`assets/analyze_market_template.py` computes everything in sections 1–5 with `scripts/marketlib.py`.
The reports on CoreWeave, Pop Mart, 3SBio and 粤高速A used exactly these calculations; the template reproduces
the 粤高速 numbers to the last digit.

## 1. Benchmarks and conventions

- **Market:** the broad index of the stock's listing market, total-return version where available (S&P 500 TR,
  CSI 300 TR `H00300`; HSI is price-only on Yahoo, so say so). The user may name the benchmark (e.g. "use the
  S&P 500"); use theirs.
- **Sector:** an equal-weight daily-return index of 10–15 listed peers in the same market. This is better than an
  ETF or official index when those are short, cap-weighted toward one name, or absent. Check it against an
  official index (Shenwan, an ETF) and report the correlation (粤高速: 0.97 with SW 851731). Require a minimum
  number of names per day (about half the peers).
- **Style (optional):** when the stock trades as part of a style, e.g. CSI Dividend TR for high-dividend A-shares.
- **Rates (optional):** the daily change of the 10-year government yield, for bond proxies such as utilities,
  toll roads, REITs, banks and insurers. Report the beta per +10bp.
- **Returns:** stock levels are dividend-adjusted closes. Volatility uses log returns; betas, events and drawdowns
  use simple returns; models use excess returns (minus the daily risk-free rate). Annualise with 252 days.
- **Sample:** for seasoned stocks, about 10 years (2016 onward worked well); for recent IPOs, everything since
  listing (CoreWeave had about 19 months). Then add sub-periods split at regime changes: a policy shift, a
  business-model change, or a rate cycle.

## 2. Volatility and risk

| Statistic | Function | Why it matters |
|---|---|---|
| Annualised vol, downside deviation | `risk_stats` | Overall riskiness against the benchmarks |
| VaR/CVaR 95/99 (historical, daily) | `risk_stats` | Tail size in plain terms ("on 1 day in 20, it loses more than x%") |
| Skew, excess kurtosis, days with \|r\| above 3% / 5% | `risk_stats` | Fat tails and jumpiness |
| Max drawdown with dates, current drawdown | `max_drawdown` | Pain and recovery |
| Sharpe, Sortino | `risk_stats` | Return per unit of risk against the benchmarks |
| 63-day rolling vol | `rolling_metrics` | Regimes; spikes line up with events |
| GARCH(1,1)-t: persistence, half-life, long-run and current conditional vol | `garch_t` | Whether shocks fade fast and whether vol is high now relative to normal |
| Share of variance from the 10 largest days | `top_days_variance_share` | Whether risk is concentrated in a few events |
| Calendar-year table | `by_year` | Return, vol, betas and drawdown per year; yield change if rates matter |
| Histogram of daily returns | `return_histogram` | Shape; use ±20% bins for very volatile names |
| Implied vol term structure (US) | `atm_iv_term` | What options price in, compared with realised vol |

## 3. Betas and factor models

- **Single-index model** (`sim`): beta with OLS and HAC (Newey-West, 5 lags) standard errors, R², alpha (and its
  t), residual vol, and the share of variance that is systematic. Run it against the market, sector and style.
- **Robustness:** weekly and monthly betas (`resampled_sim`) guard against non-synchronous trading. Dimson beta
  (`dimson_beta`) does the same for thin trading or cross-market timing, e.g. HK stocks against US news.
  Up-market and down-market betas (`up_down_beta`) show asymmetry. Capture ratios, tracking error and information
  ratio come from `capture_and_active`.
- **Multi-factor** (`factor_model`): market plus the sector **orthogonalised** to the market. The sector index's
  residual on the market enters as a factor, so its beta measures pure industry co-movement and the market beta
  is unchanged. Add Δ10Y for rate sensitivity (HAC). Report R² gains: market only, then + sector, then + rates.
  Run the model on sub-periods (`factors_periods`), because betas drift.
- **Rolling** 252-day beta and 126-day correlation against the market and the sector, plus a 252-day rolling rate
  beta. These show "decoupling" or "re-rating" episodes better than any single number.
- **Operating sensitivity** is part of the same story; put it in section 04 next to the betas (see section 6).
- **CAPM required return:** rf + β × ERP (use 5–6%), as context for the valuation, not as a target.

## 4. Peers inside the sector

- **Choosing peers:** same listing market (so prices, accounting and investors are comparable), same business
  model, and a range of sizes. 10–15 names. Name the selection rule in the report.
- **Leave-one-out:** each name's sector beta and correlation are computed against the equal-weight index
  *without that name* (`peer_risk_table`). Otherwise a peer is partly regressed on itself.
- Market-side metrics per name: 1-year vol, vol since a cut-off date, beta to the market and the sector,
  correlation with the sector, rate beta, calendar-year returns, YTD, 3-year return, drawdown since a date,
  distance from high.
- Fundamental metrics per name (`fundamentals.json` `peers`): market cap, revenue and growth, profit and growth
  (both reported and core), ROE, margins, P/E, P/B, EV/EBITDA, dividend yield and payout, net debt/EBITDA.
  Source them from the same provider for every name, and use the same fiscal period.
- **Ranks are computed, never eyeballed.** Use `rank_of(rows, key, code)` and say "第 N（共 M 家）". A rank in the
  report must match a computed rank.
- **Industry scale:** market size and growth, structure (concentration, state vs private), policy, and the
  company's share. Each figure needs a source and a date.
- **Expectations:** company guidance, consensus EPS and revenue, broker targets and ratings (label them
  third-party, with date and broker), and the product pipeline or capex plan. For pharma, give phase, indication,
  expected readout or approval timing, and peak-sales estimates (labelled). For infrastructure and utilities,
  give tariff resets, concession expiries and expansion projects.

## 5. Event study

- **Event list** (`data/events.json`): date, category, a short label for chart axes (≤8 Chinese characters), a
  full title, a one-line description, and a source URL. Aim for 15–30 events covering every category that
  matters. The skeleton translates these categories: earnings, guidance, deal, mna, capital, financing,
  dividend, product, contract, strategic, operations, supply, sector, policy, macro, credit, management, legal.
- **Day 0** is the first session in which the market could react. Announcements after the close, on weekends or
  on holidays move to the next trading day. Write that date in `date`, and keep the announcement date in `desc`.
- **Abnormal return** (`abnormal_returns`): actual excess return minus the prediction of the full-sample
  market (+ orthogonalised sector) model. t = AR / σ(residual); |t| > 1.96 is significant at 5%.
  CAR[0,+5] shows follow-through and CAR[−5,+5] shows leakage or anticipation. Note in the methods section that
  the model is estimated on the full sample.
- **Also report:** the average absolute move on earnings days compared with normal days (`earnings_move`), CAR
  by calendar year (`car_by_year`, which shows when the stock beat its model), the top abnormal days (to find
  missing events), and the biggest sector days and how the stock moved on them.
- **Special studies** where they fit: ex-dividend and record days (`ex_dividend_table`; with dividend-adjusted
  prices a negative ex-day return means the price fell by more than the dividend); lock-up expiries; index
  inclusions; placements; licensing deals (pre-announcement run-up).
- **Examples:** the user asks for examples every time. Pick 3–6 cases that teach something different: a
  significant positive reaction, a significant negative one, a big headline that the market ignored, a macro shock
  where the stock was defensive or not, and a slow drift after an event. For each case give the date, what
  happened (with a source), the same-day move against the market and sector, AR and t, CAR, and the reason.

## 6. Fundamentals

**Business (01):** what it sells, to whom and how it gets paid; revenue mix by segment, product, region or asset;
key operating KPIs (volumes, prices, traffic, users, GMV, utilisation, pipeline); ownership and control.

**Financials (02):** annual statements for 5–7 years, plus the latest halves or quarters. Cover revenue, gross
margin, operating profit, reported and core profit, ROE, operating cash flow, capex, free cash flow and
dividends. Explain the drivers of growth and margin changes. Call out one-offs and restatements explicitly. A
half-year table often explains the latest trend better than the annual one.

**Debt and ability to pay (03):** use the template that fits the balance sheet.
- *Leveraged* (CoreWeave): a debt stack table (instrument, amount, rate, maturity, security); a maturity
  ladder; interest coverage (EBIT and EBITDA over interest, capitalised interest included); debt/EBITDA;
  liquidity runway; covenants. Market-implied risk: CDS spread → default probability (`cds_default_prob`); a
  Merton distance to default (`merton_pd`); bond yields.
- *Net cash* (Pop Mart, 3SBio): cash and investments, working capital (inventory days, receivables), FX
  exposure, capacity to fund buy-backs, dividends and M&A.
- *Capex-heavy* (粤高速): current net debt/EBITDA and loan rates. Then an **illustrative** debt path through
  the investment cycle: capex schedule, OCF, dividends (parent and minority), equity share of funding, interest
  rate. Show net debt and ND/EBITDA per year, and test whether the dividend commitment still fits.

**Sensitivity to market growth (04):**
- operating leverage: profit change for ±1% (and ±10%) in volume, price or traffic;
- scenarios (bear/base/bull) for the next full year, with stated drivers;
- the market, sector and rate betas from section 3;
- FX for exporters or RMB reporters with HKD/USD listings;
- for dividend stocks, the dividend-yield spread over the 10-year government yield (`dividend_yield_spread`).

**Future plans (05):** guidance, capex projects (budget, spend to date, timing, IRR), pipeline or new products,
M&A, shareholder-return plans (payout policy and its expiry), and management changes. Each item needs a
source. Put dated milestones in a table: these are the catalysts.

**Valuation (07):** P/E, P/B, EV/EBITDA and dividend yield compared with the stock's own history (percentile since
a date, `percentile_rank`) and with peers. Add the method that fits the company:
- yield-gap pricing for bond proxies (price implied by a spread of 2–4pp over the 10-year yield, on current and
  forecast DPS);
- sum-of-the-parts for conglomerates or licensing-heavy biotech;
- scenario P/E for growth names.
Close with broker targets (third-party). Always state what the current price implies.

**Illustrative calculations** (scenarios, debt paths, royalty NPVs, valuation grids): list the assumptions in a
table or callout. Mark the results 示意 / 情景 in the text and caption. Never present them as forecasts.

## 7. Interpreting results: what is worth saying

- Lead with contrasts that a reader can act on. Examples: "β to the market fell from 0.6 to 0.1 after 2023, but β
  to the sector stayed at 0.7, so it trades as a sector and dividend asset, not as a market asset"; "9 of 11
  ex-dates fell by more than the dividend".
- Put a magnitude on every adjective: "高" or "低" must come with the number and the comparison.
- Separate statistical from economic significance. A rate beta with t = −1.9 is "weak evidence"; a monthly
  correlation of 0 means the link does not hold at a monthly horizon.
- Where sub-periods disagree, say which one you trust for the outlook and why.
- When a result is surprising, check the data before writing it up: partial last day, suspension, a split, the
  adjustment method, the units.
