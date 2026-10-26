# Worked example: 粤高速A (000429.SZ), October 2026

The fourth report in the series. It follows the same framework as the 3SBio report, which the user called 非常好.
Use it as the reference for tone, density and company-specific blocks. Don't copy its numbers.

| File | What to borrow |
|---|---|
| `gdexpressway_template.html` | Narrative style throughout. Section 00 has 6 tiles and 7 key points, each opening with a bold claim followed by numbers. Company-specific blocks: a road table with stakes, traffic, tolls and expiries; a toll chart; a capex project table; an illustrative debt path; a leverage table; a yield-gap valuation grid; a rate grid; a peer expectations table; the ex-dividend study. Also shows print CSS for wide tables, `fillRows` usage, and text filled from data. |
| `gdexpressway_analyze_fundamentals.py` | Patterns for transcribed operating data (`TOLL`, `ROADS`) with source comments, restated-comparatives handling, the debt-path function with an explicit capex schedule, the sensitivity (toll ±1%) and leverage tables, and the yield-gap valuation grid |
| `gdexpressway_events.json` | 25 events with categories, short labels, descriptions noting weekend/after-close announcements, and source links |
| `gdexpressway_README.md` | The README format: scope, file list, data table, how data was fetched and what failed, reproduction commands, disclaimer |

The market analysis for this report is what `assets/analyze_market_template.py` reproduces exactly when configured
with the 粤高速 settings (15 expressway peers, CSI 300 TR, CSI Dividend TR, 10-year CGB). The page itself was
written before the generic skeleton existed, so its JS uses report-specific keys (`gd`, `csi`, `sec`, `div`)
instead of the skeleton's `tgt`, `mkt`, `sec`, `sty`.
