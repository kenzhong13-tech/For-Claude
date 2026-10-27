# 紫金矿业（601899.SH / 2899.HK）财务分析

中文研究报告，覆盖：
- 业务与财务表现（金、铜、锌银、锂的产量、单位售价与成本、毛利结构）、债务与偿债能力、对金价和铜价的利润敏感性（示意测算）、2026–2028 年产量规划与 2035 年远景目标；
- **与金价走势的比较**：长期与分阶段收益、相对强弱、金价与铜价双因子回归（日度、周度、分时段、滚动 β 与相关系数）、月度上涨与下跌捕获率、领先滞后、金价大涨大跌日与金价回撤期间的表现、季度利润与金属价格、市盈率与金价、A/H 溢价、紫金黄金国际持股价值，以及与全球金矿和铜矿股的对照；
- 与 13 家 A 股金铜同业（山东黄金、中金黄金、山金国际、湖南黄金、西部黄金、恒邦股份、四川黄金；江西铜业、铜陵有色、洛阳钼业、西部矿业、云南铜业、金诚信）的对比：增长、行业规模、估值与分红、股价波动、经营预期；
- 以沪深 300 全收益、金铜同业等权指数和人民币金价（上海金 Au99.99）为基准的波动率分析与股价事件研究。

股价、金价与指数截至 2026-10-27 收盘，财务数据截至 2026 年三季报（2026-10-23 晚公告）。赤峰黄金已于 2026-10-22 成为紫金控股子公司，只下载数据、不计入同业。

- `report/zijin_report.html`：交互式报告（离线可直接用浏览器打开）
- `report/zijin_report.pdf`：A4 打印版（37 页）
- `report/template.html`：报告模板，由 `report_kit/build_report.py` 注入数据并内联 `report_kit/` 的样式与图表代码

## 数据

| 路径 | 内容 | 来源 |
|---|---|---|
| `data/raw/yahoo/` | 601899.SS、2899.HK（H 股）、2259.HK（紫金黄金国际）与 14 家 A 股同业的日度行情（含复权价）；全球矿业股（纽蒙特、伊格尔、巴里克、自由港、南方铜业）、GDX、GLD、COMEX 金银铜期货、美元指数、美国 10 年期国债收益率、标普 500、人民币与港币汇率；公司概况与 Yahoo 财务报表 | Yahoo Finance（yfinance） |
| `data/raw/commod/` | 上海金 Au99.99 与 Au(T+D) 现货、上海金基准价；上期所黄金、铜、白银、锌主力合约与广期所碳酸锂主力合约；伦敦金、COMEX 金与铜、LME 铜；黄金与外汇储备 | 上海黄金交易所、新浪财经（akshare） |
| `data/raw/idx/` | 沪深 300、中证申万有色金属（价格与全收益）；申万有色金属、贵金属、工业金属、黄金、铜行业指数 | 中证指数公司、申万宏源研究（akshare） |
| `data/raw/rates/` | 中美国债收益率 | 东方财富（akshare） |
| `data/raw/fin/` | 15 家公司的资产负债表、利润表、现金流量表、主要指标、分红送配、估值历史；紫金研报列表、新闻与主要股东 | 东方财富、新浪（akshare） |
| `data/raw/filings/` | 紫金 2018 年年报以来的定期报告与重要公告全文（112 份），以及 1,343 条公告目录 | 巨潮资讯网 |
| `data/raw/peers_filings/` | 同业 2025 年年报与 2026 年半年报前 45 页 | 巨潮资讯网 |
| `data/events.json` | 31 个事件的日期、分类与来源链接 | 公司公告与媒体报道 |
| `data/processed/` | 分析结果：`market_analysis.json`（波动率、模型、同业、事件）、`gold_analysis.json`（与金价、铜价的比较）、`fundamentals.json`（财务、偿债、敏感性、估值、同业） | 由脚本生成 |

矿产金、铜、锌、银、锂的产量与产量规划，各产品的销量、单位售价与单位成本（2023、2025 年年报“成本及毛利率分析”，2026 年三季报），资本化利息、债务结构、紫金黄金国际持股、券商目标价与行业数据，由 `scripts/analyze_fundamentals.py` 整理录入，并在代码注释中注明出处。原始数据由 `.github/workflows/fetch-market-data.yml` 在 GitHub Actions 上下载：会话环境无法直接访问行情与公告网站，推送取数脚本时工作流会自动运行。akshare 的上海金 Au99.99 现货数据始于 2016-12-19，此前的金价用上期所黄金主力合约按衔接日的比例换算；铜价用上期所铜主力合约连续价。

## 复现

```bash
pip install pandas numpy scipy statsmodels arch
python zijin_analysis/scripts/analyze_market.py        # 波动率、单指数与多因子模型、GARCH、同业波动、事件研究
python zijin_analysis/scripts/analyze_gold.py          # 与金价、铜价的比较（须在 analyze_market.py 之后运行）
python zijin_analysis/scripts/analyze_fundamentals.py  # 财务摘要、产量与单位经济、偿债指标、金属价格敏感性、估值、同业对比
python report_kit/build_report.py zijin_analysis       # 生成 report/zijin_report.html
node report_kit/make_pdf.mjs zijin_analysis/report/zijin_report.html zijin_analysis/report/zijin_report.pdf "紫金矿业（601899.SH）财务分析报告 · 2026-10-27"
```

生成 PDF 需要 Node.js 与 Playwright（Chromium）。

本报告仅供研究学习，不构成投资建议。金价与铜价的利润敏感性、现价下的利润估算为示意计算，结果依赖假设；券商目标价、一致预期与行业数据为第三方数据，已注明来源与日期。
