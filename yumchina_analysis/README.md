# 百胜中国（9987.HK / YUMC）财务分析

中文研究报告，覆盖：
- 业务与财务表现、现金与债务、偿债能力、对同店销售与汇率的敏感性、未来规划（含必胜客品牌收购）；
- 与 15 家港股餐饮与茶饮企业的同业对比（增长、行业规模、估值、股价波动、经营预期），另附 7 家全球快餐与咖啡公司的估值；
- 以恒生指数（盈富基金含息）和港股餐饮同业等权指数为基准的波动率分析与股价事件研究（45 个事件）；
- **波动率套利可行性**：港交所期权类别、YUMC 期权链与隐含波动率、实现波动率估计与波动率锥、GARCH / HAR 样本外预测检验、财报波动、港美两地价差与领先—滞后关系、一个扣除成本的跨市场日内规则；
- **周期性检验**：月份、星期、月末月初、节日、财报前后漂移；Ljung–Box、ARCH-LM、方差比、游程检验；周期图与 Fisher g 检验；20% 涨跌波段与块自助法；业务季节性（趋势加季度哑变量 F 检验、Friedman 检验）；同店销售与社零、餐饮收入的相关与 Granger 检验；全部收益规律检验的 Benjamini–Hochberg 校正。

港股行情截至 2026-11-26 收盘，美股截至 2026-11-25（11-26 感恩节休市）；财务数据截至 2026 年三季报（2026-11-03 发布，10-Q 于 11-05 提交）。

- `report/yumchina_report.html`：交互式报告（离线可直接用浏览器打开）
- `report/yumchina_report.pdf`：A4 打印版（42 页）
- `report/template.html`：报告模板，由 `report_kit/build_report.py` 注入数据并内联 `report_kit/` 的样式与图表代码

## 数据

| 路径 | 内容 | 来源 |
|---|---|---|
| `data/raw/yahoo/` | 9987.HK、YUMC、15 家港股同业、7 家全球同业、盈富基金、标普 500、汇率的日度行情（含复权价），YUMC 1 小时与 5 分钟行情、分红、财报日期、公司概况 | Yahoo Finance（yfinance） |
| `data/raw/options/` | YUMC 期权链（全部到期日）、alphaquery 近三个月 30 天隐含波动率、港交所股票期权类别页与 2026-11-26 期权日报 | Yahoo、alphaquery、港交所 |
| `data/raw/sec/` | 业绩新闻稿（8-K 附件 99，2016 年起）、10-K、10-Q 正文，XBRL companyfacts，申报目录 | SEC EDGAR |
| `data/raw/fin/` | 港股同业的主要指标、利润表、资产负债表，分红，估值历史，盈利预测与评级，港股通持股 | 东方财富、百度股市通、经济通（akshare） |
| `data/raw/macro/` | 社会消费品零售总额、CPI、消费者信心（月度），国家统计局新闻稿中的餐饮收入 | 东方财富（akshare）、国家统计局 |
| `data/raw/filings/` | 公司在港交所的部分公告 | 披露易 |
| `data/raw/peers_filings/` | 同业最新业绩公告 | 披露易 |
| `data/events.json` | 45 个事件（25 次业绩 + 20 个公司、政策与市场事件）的日期、分类与来源链接 | SEC 申报、公司公告、媒体报道 |
| `data/processed/` | 分析结果（JSON） | 由脚本生成 |

手工整理录入的数据（`scripts/analyze_fundamentals.py` 顶部，逐项注明出处）：长期银行存款与票据（10-K、10-Q 资产负债表）、过桥贷款与授信（10-Q 附注）、前三季度餐厅成本结构（10-Q 利润表）、必胜客品牌收购条款（8-K 2026-06-16 与 2026-08-07）、管理层指引（三季报与 2025 投资者日）、券商目标价与行业统计（第三方，注明日期与链接）。季度经营指标（同店销售、门店数、餐厅利润率、外卖占比等）由 `scripts/analyze_ops.py` 从业绩新闻稿解析。

原始数据由 `.github/workflows/fetch-market-data.yml` 在 GitHub Actions 上下载：会话环境无法直接访问行情与公告网站，推送取数脚本时工作流会自动运行。未能取得的数据：

- **YUMC 长期隐含波动率历史**：CBOE 与 Barchart 拒绝访问，alphaquery 免费数据只有约三个月，因此报告没有做多年的方差风险溢价检验。如能提供 2017–2026 年 YUMC 每日 30 天平值隐含波动率（Bloomberg、iVolatility 或 OptionMetrics），存为 `data/raw/manual/yumc_iv30.csv`（列：`date,iv30`，小数或百分数均可）后重跑 `analyze_volarb.py` 与 `build_report.py`，报告 9.4 节会自动加上方差风险溢价检验和每月卖出方差互换的回测。
- **国家统计局月度餐饮收入**：统计局数据库拒绝访问，从新闻稿只能还原 2022 年以来的 14 个季度；长期周期检验改用社会消费品零售总额。

## 复现

```bash
pip install pandas numpy scipy statsmodels arch
python yumchina_analysis/scripts/analyze_market.py --events   # 波动率、单指数与多因子模型、GARCH、同业波动、事件研究
python yumchina_analysis/scripts/analyze_ops.py               # 业绩新闻稿中的季度经营指标、业绩发布时间与反应日、餐饮收入
python yumchina_analysis/scripts/build_events.py              # 事件列表（依赖上一步的业绩反应日）
python yumchina_analysis/scripts/analyze_fundamentals.py      # 财务摘要、现金与债务、敏感性、估值、同业对比
python yumchina_analysis/scripts/analyze_volarb.py            # 波动率套利可行性
python yumchina_analysis/scripts/analyze_cycles.py            # 周期与季节性检验
python report_kit/build_report.py yumchina_analysis           # 生成 report/yumchina_report.html
node report_kit/make_pdf.mjs yumchina_analysis/report/yumchina_report.html yumchina_analysis/report/yumchina_report.pdf "百胜中国（9987.HK）财务分析报告 · 2026-11-26"
```

`build_events.py` 生成事件列表后需再运行一次 `analyze_market.py --events` 计算事件的异常收益。生成 PDF 需要 Node.js 与 Playwright（Chromium）。

本报告仅供研究学习，不构成投资建议。敏感性测算、事件期权定价与跨市场日内规则为示意计算，结果依赖文中假设；券商目标价、一致预期与行业统计为第三方数据。
