# Analysis methods

`assets/analyze_market_template.py` computes sections 1–5 with `report_kit/marketlib.py`;
`assets/analyze_fundamentals_template.py` covers section 6.

## 1. Benchmarks and conventions

- **Market:** the listing market's broad index, total-return where possible, or the user's choice.
- **Sector:** equal-weight daily-return index of 10–15 same-market peers, at least ~half the names per day, new
  listings skipped for their first 20 sessions; check it against an official index or ETF when one exists.
- **Optional factors:** a style index (e.g. CSI Dividend TR for dividend stocks); Δ10Y yield for bond proxies
  (utilities, toll roads, REITs, banks), reported per +10bp.
- **Returns:** dividend-adjusted. Log returns for volatility; simple returns for betas, events and drawdowns;
  excess returns (minus daily rf) in models; 252 days a year.
- **Sample:** ~10 years for seasoned stocks, all history for recent IPOs; add sub-periods split at regime changes.

## 2. Volatility and risk

`risk_stats` (vol, downside deviation, VaR/CVaR 95/99, skew, kurtosis, days beyond 3%/5%, Sharpe, Sortino),
`max_drawdown`, `rolling_metrics` (63-day vol), `garch_t` (persistence, half-life, long-run and current vol),
`top_days_variance_share`, `by_year`, `return_histogram`, `atm_iv_term` (US options).

## 3. Betas and factor models

- `sim`: OLS beta with HAC (5 lags) errors, R², alpha and t, residual vol, systematic share; against market,
  sector and style.
- Robustness: `resampled_sim` (weekly, monthly), `dimson_beta` (thin trading, cross-time-zone news),
  `up_down_beta`, `capture_and_active`.
- `factor_model`: market plus the sector **orthogonalised** to the market (its residual), plus Δ10Y if relevant;
  report R² market-only → + sector → + rates; rerun per sub-period (`factors_periods` in the output).
- Rolling 252-day beta and 126-day correlation show decoupling or re-rating episodes.
- CAPM required return (rf + β × 5–6% ERP) as context only.

## 4. Peers

- Same listing market, same business model, a range of sizes; state the selection rule.
- `peer_risk_table` computes each name's sector beta and correlation **leave-one-out**, plus 1-year vol, returns
  by year, YTD, 3-year return and distance from high.
- Fundamentals per name from one provider and one fiscal period: market cap, revenue and profit growth, ROE,
  margins, P/E, P/B, EV/EBITDA, dividend yield, leverage, latest-period growth.
- **Ranks are computed** (`rank_of`, `peer_ranks`, `peer_medians` in the outputs) and quoted as "第 N（共 M 家）".
- Industry scale (size, growth, structure, company share) and expectations (guidance, consensus, broker targets,
  pipeline or capex), each with source and date.

## 5. Event study

- `data/events.json`: date (day 0 = first session that could react), category, short label (≤8 characters), title,
  description with the announcement time, source URL. 15–45 events; all results days for frequent reporters.
- `abnormal_returns`: AR = excess return minus the full-sample market (+ sector) model; t = AR/σ(e); CAR[0,+5]
  and CAR[−5,+5]. Also `earnings_move` (earnings vs normal days), `car_by_year`, top abnormal days (to find missing
  events), `ex_dividend_table` where dividends matter.
- Worked examples (3–6): a big positive and a big negative reaction, a headline the market ignored, a macro
  shock, a slow drift; each with date, source, move vs market and sector, AR, t, CAR, and the lesson.

## 6. Fundamentals

- **Sources:** A-shares Eastmoney; US SEC XBRL (`finlib.sec_periods`, quarters from YTD values) plus 8-K releases
  for KPIs and adjusted figures; HK Eastmoney indicators plus the results announcement for cash, debt and cash
  flow.
- **Business (01):** what it sells, how it is paid, mix, operating KPIs, ownership.
- **Financials (02):** 5–9 years plus recent quarters or halves; revenue, margins, reported and core profit, ROE,
  OCF, capex, FCF, shareholder returns; explain drivers; call out one-offs and restatements.
- **Debt (03):** leveraged → debt stack, maturities, coverage, ND/EBITDA, covenants, CDS/Merton
  (`cds_default_prob`, `merton_pd`); net cash → cash and deposits vs borrowings and leases, FCF vs payouts;
  capex-heavy → an illustrative debt path through the investment cycle.
- **Sensitivity (04):** operating leverage per ±1% of the key driver, checked against history where possible
  (e.g. margin change regressed on same-store sales); FX; betas; dividend-yield spread for income stocks
  (`dividend_yield_spread`).
- **Plans (05):** guidance, projects, M&A, payout policy, dated catalysts, each sourced.
- **Valuation (07):** multiples vs own history (`percentile_rank`) and peers, the method that fits (yield gap,
  SOTP, scenario P/E), what the price implies, broker targets (third-party).

## 7. Optional modules (when the request asks)

**Dual listings (HK/US, A/H).** Use the line the user named as the main sample and the other for a longer
history. Set each line's reaction day from the filing timestamp. Compare daily and weekly vol (time-zone
mismatch inflates daily differences); measure the price gap after FX (ADF, KPSS, AR(1) half-life) and lead–lag
(next-session return on the other line, HAC, with index controls); report turnover share by year.

**Volatility-arbitrage feasibility** (`yumchina_analysis/scripts/analyze_volarb.py`). Answer in order:
1. Is there a liquid options market? HKEX daily report class list; for US chains, expiries, OI vs ADV,
   two-sided quotes, ATM bid–ask in vol points.
2. Implied vs forecast: recompute Black–Scholes IV from mid quotes (OTM options, ATM at the forward, 25Δ skew);
   realised-vol estimators (close, Parkinson, Garman–Klass, Rogers–Satchell, Yang–Zhang) and the vol cone;
   GARCH-t and HAR-RV forecasts tested out of sample (RMSE, QLIKE, bias, Diebold–Mariano, Mincer–Zarnowitz).
3. Variance risk premium needs years of daily IV (IV minus later RV, Newey–West t, monthly short variance swaps).
   Free sources give ~3 months: ask the user (data.md §5).
4. Earnings jumps: mean |move| × √(π/2) as the jump's sd, and the IV it adds to a one-month option.
5. Cross-market or intraday rules: split in-sample and later sample, subtract realistic costs (HK stamp duty 0.1%
   per side, 0.13% from Aug 2021 to Nov 2023), list execution caveats (open auction, borrow, capacity).
Close with a verdict list (feasible / not, and why) rather than a single sentence.

**Cycles and seasonality** (`yumchina_analysis/scripts/analyze_cycles.py`).
- Calendar effects on raw and excess returns: month (OLS F, 20,000-shuffle permutation, Alexander–Govern,
  Kruskal–Wallis, per-month Welch t with BH q, and the minimum detectable effect), weekday, turn of month,
  Halloween, local holiday windows (Chinese New Year, Golden Week), earnings drift.
- Dependence: Ljung–Box (daily, weekly, monthly), ARCH-LM, Lo–MacKinlay variance ratios (robust), runs test;
  spectral: periodogram with Fisher's g and Bartlett's test.
- Swing phases (20% rule) against a stationary block bootstrap (mean block ~20 days) for regularity.
- Business seasonality: trend plus quarter dummies (F test) for revenue; Friedman test on margins by year;
  persistence of the key KPI (AC1, AC4); link to macro data (Pearson and Spearman, ex-COVID, Granger).
- Benjamini–Hochberg across every return test; stress any survivor (drop the 20 largest days, sub-periods).
Separate "returns have no exploitable pattern" from "the business is seasonal": both are usually true.

**Operating KPIs from results releases** (`yumchina_analysis/scripts/analyze_ops.py`): parse same-store sales,
margins, stores and other KPIs from 8-K ex-99 text with ordered regexes; derive net new units from store counts;
cross-check a few quarters by hand.

## 8. What is worth saying

- Lead with contrasts a reader can act on, each with its number and comparison.
- Separate statistical from economic significance (t = −1.9 is weak evidence; an R² of 1% has no trading value).
- Where sub-periods disagree, say which one you trust and why.
- Check surprising results against the data first: partial last day, suspension, split, adjustment, units.
