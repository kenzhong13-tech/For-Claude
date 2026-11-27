# 粤高速A（000429.SZ）财务分析

中文研究报告：路产与财务表现、债务与偿债能力（含改扩建期间的杠杆示意测算）、对车流与利率的敏感性、未来规划、与 15 家 A 股高速公路公司的同业对比（增长、行业规模、估值与分红、股价波动、经营预期），以及以沪深 300 全收益、公路同业指数和 10 年期国债收益率为基准的波动率分析与股价事件研究。股价与指数截至 2026-10-22 收盘，财务数据截至 2026 年中报（2026-08-25 公告）。

- `report/gdexpressway_report.html`：交互式报告（离线可直接用浏览器打开）
- `report/gdexpressway_report.pdf`：A4 打印版（28 页）
- `report/template.html`：报告模板，由 `scripts/build_report.py` 注入数据并内联 `report_kit/` 的样式与图表代码

## 数据

| 路径 | 内容 | 来源 |
|---|---|---|
| `data/raw/yahoo/` | 000429.SZ、200429.SZ（B 股）与 15 家同业（宁沪、招商公路、山东、深高速、皖通、四川成渝、赣粤、福建、现代投资、楚天、中原、东莞控股、吉林、龙江交通、五洲交通）的日度行情（含复权价） | Yahoo Finance（yfinance） |
| `data/raw/idx/` | 沪深 300、中证红利（价格与全收益）、中证红利低波 | 中证指数公司、新浪、腾讯（akshare） |
| `data/raw/em/` | 申万行业指数（含高速公路 851731）、中美国债收益率、LPR、部分东方财富行情 | 申万宏源研究、东方财富（akshare） |
| `data/raw/fin/` | 16 家公司的资产负债表、利润表、现金流量表、主要指标、分红送配、估值历史；粤高速研报列表与新闻 | 东方财富、新浪（akshare） |
| `data/raw/cninfo/` | 粤高速公告列表与定期报告、重要公告全文 | 巨潮资讯网 |
| `data/raw/peers_cninfo/` | 同业 2025 年年报与 2026 年半年报前 45 页 | 巨潮资讯网 |
| `data/events.json` | 25 个事件的日期、分类与来源链接 | 公司公告与媒体报道 |
| `data/processed/` | 分析结果（JSON） | 由脚本生成 |

路段车流与通行费、收费期限、改扩建预算与进度、借款利率等由 `scripts/analyze_fundamentals.py` 从年报和半年报中整理录入。原始数据由 `.github/workflows/fetch-market-data.yml` 在 GitHub Actions 上下载（会话环境无法直接访问行情与公告网站），该工作流为手动触发；东方财富行情接口拒绝了 Actions 运行器，个股行情因此改用 Yahoo Finance，指数由 `scripts/fetch_extra.py` 从中证指数公司等来源补充。

## 复现

```bash
pip install pandas numpy scipy statsmodels arch
python gdexpressway_analysis/scripts/analyze_market.py        # 波动率、单指数与多因子（含利率）模型、GARCH、股息率利差、同业波动、事件研究、除息日效应
python gdexpressway_analysis/scripts/analyze_fundamentals.py  # 财务摘要、路段数据、偿债指标、改扩建杠杆示意、敏感性、估值、同业对比
python gdexpressway_analysis/scripts/build_report.py          # 生成 report/gdexpressway_report.html
node report_kit/make_pdf.mjs gdexpressway_analysis/report/gdexpressway_report.html gdexpressway_analysis/report/gdexpressway_report.pdf "粤高速A（000429.SZ）财务分析报告 · 2026-10-22"
```

生成 PDF 需要 Node.js 与 Playwright（Chromium）。

本报告仅供研究学习，不构成投资建议。改扩建期间的杠杆路径与隐含股价为示意计算，结果依赖假设。
