# 上海电力（600021.SH）财务分析

中文研究报告，覆盖：
- 业务与财务表现（装机、发电量、上网电价、燃料成本、分地区收入、主要子公司利润、单季利润与税负）、债务与偿债能力（含超短期融资券和融资租赁的有息负债口径、永续债、应收补贴）、对电价、煤价、发电量与利率的利润敏感性（示意测算）、“十五五”规划与在建项目；
- 电价、煤价与用电需求：平均上网电价、入炉标煤单价、公司发电量增速与全社会用电量增速的对比；
- 与 14 家 A 股发电企业（华能国际、华电国际、国电电力、大唐发电、浙能电力、申能股份、粤电力A、深圳能源、皖能电力、京能电力、内蒙华电、江苏国信、福能股份、吉电股份）的同业对比：增长、行业规模、估值与分红、杠杆、股价波动、经营预期；
- 以沪深 300 全收益、电力同业等权指数、中证红利全收益和 10 年期国债收益率为基准的波动率分析与股价事件研究（34 个事件）。

股价与指数截至 2026-11-23 收盘，财务数据截至 2026 年三季报（2026-10-30 晚公告）。

- `report/shpower_report.html`：交互式报告（离线可直接用浏览器打开）
- `report/shpower_report.pdf`：A4 打印版（34 页）
- `report/template.html`：报告模板，由 `report_kit/build_report.py` 注入数据并内联 `report_kit/` 的样式与图表代码

## 数据

| 路径 | 内容 | 来源 |
|---|---|---|
| `data/raw/yahoo/` | 600021.SS 与 14 家同业的日度行情（含复权价）、中国电力（2380.HK）、鹿特丹煤炭期货、人民币与港币汇率；公司概况与 Yahoo 财务报表 | Yahoo Finance（yfinance） |
| `data/raw/idx/` | 沪深 300、中证红利、中证全指公用事业（价格与全收益）；申万公用事业、电力、火电、水电、风电、光伏等行业指数 | 中证指数公司、申万宏源研究（akshare） |
| `data/raw/rates/` | 中美国债收益率 | 东方财富（akshare） |
| `data/raw/power/` | 全社会用电量（月度）、郑商所动力煤期货、焦煤与焦炭期货主力合约 | 东方财富、新浪财经（akshare） |
| `data/raw/fin/` | 15 家公司的资产负债表、利润表、现金流量表、主要指标、分红送配、估值历史；上海电力研报列表、新闻与主要股东 | 东方财富、新浪（akshare） |
| `data/raw/filings/` | 上海电力 2018 年年报以来的定期报告、季度发电量完成情况公告和重要公告全文（135 份），2016–2018 年及 2019 年以来的公告目录 | 巨潮资讯网 |
| `data/raw/peers_filings/` | 同业 2025 年年报与 2026 年半年报前 45 页 | 巨潮资讯网 |
| `data/events.json` | 34 个事件的日期、分类与来源链接 | 公司公告与媒体报道 |
| `data/processed/` | 分析结果：`market_analysis.json`（波动率、模型、同业、事件）、`fundamentals.json`（财务、偿债、估值、同业）、`power_analysis.json`（装机、发电量、电价、单季利润、债务结构、敏感性） | 由脚本生成 |

装机、发电量、上网电价和市场化交易电量由 `scripts/analyze_power.py` 从 2018 年以来的季度发电量完成情况公告中提取；入炉标煤单价、利用小时、资本性支出、分地区收入、子公司利润、在建项目、资本化利息、永续债利息和普通股每股收益从年报和季报中整理录入，并在代码注释中注明出处。

原始数据由 `.github/workflows/fetch-market-data.yml` 在 GitHub Actions 上下载：会话环境无法直接访问行情与公告网站，推送取数脚本时工作流会自动运行。第一次运行时，akshare 已更名中证指数、国债收益率和申万行业列表等函数，`scripts/fetch_extra.py` 改用新函数名补齐。动力煤现货价格两条路径都没有取到：99 期货的接口返回格式已变，生意社的期现表也不再列出动力煤。郑商所动力煤期货 2022 年后基本停止交易，所以报告只用 2016–2022 年的期货价格和公司年报中的入炉标煤单价。

## 复现

```bash
pip install pandas numpy scipy statsmodels arch
python shpower_analysis/scripts/analyze_market.py        # 波动率、单指数与多因子（含利率）模型、GARCH、同业波动、事件研究、除息日效应
python shpower_analysis/scripts/analyze_fundamentals.py  # 财务摘要、偿债指标、估值、同业对比
python shpower_analysis/scripts/analyze_power.py         # 装机、发电量、电价、单季利润、债务结构、利润敏感性
python report_kit/build_report.py shpower_analysis        # 生成 report/shpower_report.html
node report_kit/make_pdf.mjs shpower_analysis/report/shpower_report.html shpower_analysis/report/shpower_report.pdf "上海电力（600021.SH）财务分析报告 · 2026-11-23"
```

生成 PDF 需要 Node.js 与 Playwright（Chromium）。

本报告仅供研究学习，不构成投资建议。利润敏感性等示意测算依赖文中假设；券商预测、行业统计为第三方数据，已注明来源与日期。
