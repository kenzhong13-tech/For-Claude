# 三生制药（1530.HK）财务分析

中文研究报告：财务表现、债务与偿债能力、对市场增长的敏感性、未来规划、与 15 家港股创新药同业的对比（增长、行业规模、股价波动、产品预期），以及以恒生指数和创新药板块为基准的波动率分析与股价事件研究。股价截至 2026-10-22 收盘（指数与波动率分析截至 10-21），财务数据截至 2026 年中期业绩（2026-08-20 公告）。

- `report/sbio_report.html`：交互式报告（离线可直接用浏览器打开）
- `report/sbio_report.pdf`：A4 打印版（28 页）
- `report/template.html`：报告模板，由 `scripts/build_report.py` 注入数据并内联 `report_kit/` 的样式与图表代码

## 数据

| 路径 | 内容 | 来源 |
|---|---|---|
| `data/raw/*.csv` | 1530.HK 与 15 家同业（恒瑞、百济、信达、康方、翰森、石药、中国生物制药、科伦博泰、君实、荣昌、先声、和黄、再鼎、映恩、康诺亚）、恒生指数、国企指数、生物科技 ETF（3069.HK 等）、13 周美债、美元兑人民币等日度行情 | Yahoo Finance（yfinance） |
| `data/raw/info/` | 各公司市值、分析师目标价等概况 | Yahoo Finance |
| `data/raw/ak/` | 港股财务指标与利润表 | 东方财富（akshare） |
| `data/raw/hkex/`、`data/raw/peers_hkex/` | 三生制药公告全文（业绩、授权、配售、分拆等）与同业近期业绩公告 | HKEXnews |
| `data/events.json` | 23 个事件的日期、分类与来源链接 | 港交所公告与媒体报道 |
| `data/processed/` | 分析结果（JSON） | 由脚本生成 |

三生制药的利润表、收入构成、现金与借款、外币存款等数据由 `scripts/analyze_fundamentals.py` 从港交所业绩公告中整理录入；行业交易额、新药审批数和竞品交易条款来自报告附录所列的媒体与公司公告。原始数据由 `.github/workflows/fetch-market-data.yml` 在 GitHub Actions 上下载（会话环境无法直接访问行情与港交所网站），该工作流为手动触发。

## 复现

```bash
pip install pandas numpy scipy statsmodels arch
python 3sbio_analysis/scripts/analyze_market.py        # 波动率、单指数与两因子模型、GARCH、同业波动、事件研究
python 3sbio_analysis/scripts/analyze_fundamentals.py  # 偿债指标、经营杠杆、707 分成示意、分部估值、同业财务对比
python 3sbio_analysis/scripts/build_report.py          # 生成 report/sbio_report.html
node report_kit/make_pdf.mjs 3sbio_analysis/report/sbio_report.html 3sbio_analysis/report/sbio_report.pdf "三生制药（1530.HK）财务分析报告 · 2026-10-22"
```

生成 PDF 需要 Node.js 与 Playwright（Chromium）。

本报告仅供研究学习，不构成投资建议。707 分成与分部估值为示意计算，结果依赖假设。
