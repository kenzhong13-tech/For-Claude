# 【公司】（【代码】）财务分析

中文研究报告，覆盖：
- 业务与财务表现、债务与偿债能力、对市场增长的敏感性、未来规划；
- 与 【N】 家【同业范围】的同业对比（增长、行业规模、估值、股价波动、经营预期）；
- 以【市场基准】【、板块指数、其他基准】为基准的波动率分析与股价事件研究。

股价与指数截至 【YYYY-MM-DD】 收盘，财务数据截至 【最新报告期】（【公告日】公告）。

- `report/【slug】_report.html`：交互式报告（离线可直接用浏览器打开）
- `report/【slug】_report.pdf`：A4 打印版（【页数】 页）
- `report/template.html`：报告模板，由 `report_kit/build_report.py` 注入数据并内联 `report_kit/` 的样式与图表代码

## 数据

| 路径 | 内容 | 来源 |
|---|---|---|
| `data/raw/yahoo/` | 个股、同业、指数的日度行情（含复权价）【、公司概况】 | Yahoo Finance（yfinance） |
| `data/raw/idx/` | 【指数（价格与全收益）】 | 【中证指数公司等】 |
| `data/raw/rates/` | 【国债收益率 / FRED 利率】 | 【akshare / FRED】 |
| `data/raw/fin/` | 【财务报表、主要指标、分红、估值历史、研报与新闻】 | 【东方财富（akshare）】 |
| `data/raw/filings/` | 公司公告与定期报告全文 | 【巨潮资讯网 / 披露易 / SEC EDGAR】 |
| `data/raw/peers_filings/` | 同业最新年报与中报的前若干页 | 【同上】 |
| `data/events.json` | 【N】 个事件的日期、分类与来源链接 | 公司公告与媒体报道 |
| `data/processed/` | 分析结果（JSON） | 由脚本生成 |

【哪些数据由脚本从定期报告中手工整理录入（注明报告与章节）。】原始数据由 `.github/workflows/fetch-market-data.yml` 在 GitHub Actions 上下载：会话环境无法直接访问行情与公告网站，推送取数脚本时工作流会自动运行。【哪些来源失败了、用什么替代。】

## 复现

```bash
pip install pandas numpy scipy statsmodels arch
python 【slug】_analysis/scripts/analyze_market.py        # 波动率、单指数与多因子模型、GARCH、同业波动、事件研究
python 【slug】_analysis/scripts/analyze_fundamentals.py  # 财务摘要、偿债指标、敏感性、估值、同业对比
python report_kit/build_report.py 【slug】_analysis        # 生成 report/【slug】_report.html
node report_kit/make_pdf.mjs 【slug】_analysis/report/【slug】_report.html 【slug】_analysis/report/【slug】_report.pdf "【公司】（【代码】）财务分析报告 · 【日期】"
```

生成 PDF 需要 Node.js 与 Playwright（Chromium）。

本报告仅供研究学习，不构成投资建议。【情景、示意测算与估值区间】为示意计算，结果依赖假设。
