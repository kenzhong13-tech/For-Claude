# CoreWeave（CRWV）财务分析

中文研究报告：财务表现、债务与偿债能力、对市场增长的敏感性、未来规划，以及以标普 500 为基准的波动率分析和股价事件研究。行情数据截至 2026-10-19 收盘，财务数据截至 2026 年第二季度 10-Q。

- `report/coreweave_report.html`：交互式报告（离线可直接用浏览器打开）
- `report/coreweave_report.pdf`：A4 打印版（29 页）
- `report/template.html`：报告模板，由 `scripts/build_report.py` 注入数据生成上面的 HTML

## 数据

| 路径 | 内容 | 来源 |
|---|---|---|
| `data/raw/*.csv` | CRWV、^GSPC、^VIX、^IRX 等日度行情；CRWV 期权链与财务摘要 | Yahoo Finance（yfinance） |
| `data/raw/sec/` | 10-K、10-Q、8-K 财报新闻稿与融资公告（文本），XBRL companyfacts | SEC EDGAR |
| `data/kpis.json` | 季度调整后 EBITDA、积压订单、电力等公司口径指标 | 财报新闻稿 |
| `data/events.json` | 27 个事件的日期、分类与新闻来源 | 媒体报道与 SEC 公告 |
| `data/processed/` | 分析结果（JSON） | 由脚本生成 |

原始数据由 `.github/workflows/fetch-market-data.yml` 在 GitHub Actions 上下载（会话环境无法直接访问行情与 SEC 网站）。该工作流现为手动触发，可在 Actions 页面选择 `fetch_data.py` 或 `fetch_extra.py` 刷新数据。

## 复现

```bash
pip install pandas numpy scipy statsmodels arch
python coreweave_analysis/scripts/build_financials.py     # XBRL → 季度财务表
python coreweave_analysis/scripts/analyze_market.py       # 波动率、单指数模型、GARCH、事件研究
python coreweave_analysis/scripts/analyze_fundamentals.py # 偿债指标、情景与敏感性、估值
python coreweave_analysis/scripts/build_report.py         # 生成 report/coreweave_report.html
node report_kit/make_pdf.mjs coreweave_analysis/report/coreweave_report.html coreweave_analysis/report/coreweave_report.pdf "CoreWeave（CRWV）财务分析报告"
```

本报告仅供研究学习，不构成投资建议。
