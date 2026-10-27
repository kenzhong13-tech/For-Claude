# 泡泡玛特（9992.HK）财务分析

中文研究报告：财务表现、债务与偿债能力、对市场增长的敏感性、未来规划，以及以恒生指数为基准的波动率分析和股价事件研究。行情数据截至 2026-10-20 收盘，财务数据截至 2026 年中期业绩（2026-08-20 公告）。

- `report/popmart_report.html`：交互式报告（离线可直接用浏览器打开）
- `report/popmart_report.pdf`：A4 打印版（25 页）
- `report/template.html`：报告模板，由 `scripts/build_report.py` 注入数据并内联 `report_kit/` 的样式与图表代码

## 数据

| 路径 | 内容 | 来源 |
|---|---|---|
| `data/raw/*.csv` | 9992.HK、恒生指数、国企指数、名创优品、老铺黄金、蜜雪集团、安踏、万代南梦宫、孩之宝、美泰、标普 500、13 周美债、美元兑人民币等日度行情；公司财务摘要 | Yahoo Finance（yfinance） |
| `data/raw/hkex/` | 港交所披露易公告列表与主要公告全文（业绩、季度业务更新、盈利预告等） | HKEXnews |
| `data/events.json` | 24 个事件的日期、分类与来源链接 | 港交所公告与媒体报道 |
| `data/processed/` | 分析结果（JSON） | 由脚本生成 |

利润表、资产负债表、地区与 IP 收入等数据由 `scripts/analyze_fundamentals.py` 从港交所业绩公告中整理录入。原始数据由 `.github/workflows/fetch-market-data.yml` 在 GitHub Actions 上下载（会话环境无法直接访问行情与港交所网站），该工作流为手动触发。

## 复现

```bash
pip install pandas numpy scipy statsmodels arch
python popmart_analysis/scripts/analyze_market.py        # 波动率、单指数与多因子模型、GARCH、事件研究
python popmart_analysis/scripts/analyze_fundamentals.py  # 偿债指标、经营杠杆、情景与敏感性、估值
python popmart_analysis/scripts/build_report.py          # 生成 report/popmart_report.html
node report_kit/make_pdf.mjs popmart_analysis/report/popmart_report.html popmart_analysis/report/popmart_report.pdf "泡泡玛特（9992.HK）财务分析报告"
```

生成 PDF 需要 Node.js 与 Playwright（Chromium）。

本报告仅供研究学习，不构成投资建议。
