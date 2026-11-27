"""Event list for the Hong Kong line (9987.HK): quarterly results plus company, policy and market events.
Writes data/events.json. Day 0 is the first HKEX session that could react:
- results: from the SEC 8-K acceptance time (analyze_ops.py writes earnings_days.json);
- other company news: from the HKEXnews or SEC timestamp noted in each entry (announcements after 16:00 HKT move to the
  next session; one released in the lunch break, 12:00-13:00 HKT, counts for the same day).
"""
import json
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "data")
SEC = "https://www.sec.gov/Archives/edgar/data/1673358/"

MANUAL = [
    ("2021-09-15", "guidance", "三季度经营预警", "三季度经营更新：德尔塔疫情拖累销售",
     "2021-09-14 美东收盘后（8-K 21:16 UTC）公司披露 8 月疫情与汛情影响门店营业，三季度同店销售承压。", SEC + "000156459021047921/"),
    ("2021-09-23", "strategic", "2万店目标", "2021 投资者大会：提出 2 万家门店的下一个目标",
     "2021-09-22 美东收盘后发布（8-K 21:15 UTC），港股 9 月 22 日休市，9 月 23 日为首个反应日。", SEC + "000156459021048607/"),
    ("2022-03-11", "legal", "HFCAA名单", "被美国 SEC 列入《外国公司问责法》认定名单",
     "SEC 于美东 3 月 10 日点名 5 家公司（含百胜中国），公司于 3 月 11 日 08:21 在港交所公告回应。",
     "https://www.yicaiglobal.com/news/csrc-opposes-securities-politicization-after-us-puts-yum-china-four-others-on-notice-for-delisting"),
    ("2022-03-14", "macro", "深圳封城", "深圳封城、中概股恐慌抛售",
     "3 月 13 日深圳宣布全市封控，3 月 14 日恒生中国企业指数单日跌 7.2%；美股 YUMC 3 月 11 日已跌 15.5%。",
     "https://www.caixinglobal.com/2022-03-14/panic-selling-grips-china-tech-stocks-again-as-concerns-pile-up-101855372.html"),
    ("2022-03-15", "guidance", "一季度疫情更新", "一季度经营更新：3 月前两周同店销售同比下降约 20%",
     "3 月 14 日 20:30（香港时间）发布 8-K，港股 3 月 15 日为首个反应日。", SEC + "000156459022009966/"),
    ("2022-03-16", "policy", "金融委会议", "国务院金融委会议表态稳定市场",
     "刘鹤主持金融委会议，承诺出台有利于市场的政策，恒指当日涨 9.1%。",
     "https://fortune.com/2022/03/16/china-tech-stocks-market-today-covid-ukraine-russia-sanctions-economy-gdp/"),
    ("2022-03-18", "capital", "回购+10亿", "回购授权扩大 10 亿美元",
     "3 月 17 日 18:15（香港时间）发布。", SEC + "000156459022010715/"),
    ("2022-08-16", "strategic", "申请主要上市", "申请将香港第二上市转为双重主要上市",
     "8 月 15 日 21:06（香港时间）在港交所公告。", SEC + "000119312522220698/"),
    ("2022-10-24", "strategic", "纳入港股通", "港股转为主要上市并纳入港股通",
     "转换当日生效，同日纳入沪港通、深港通港股名单；当天恒指跌 6.4%。",
     "https://yumchinaholdingsinc.gcs-web.com/news-releases/news-release-details/yum-china-announces-primary-listing-hong-kong-stock-exchange-and"),
    ("2022-12-16", "legal", "PCAOB完成检查", "PCAOB 撤销 2021 年认定，退市风险解除",
     "PCAOB 于美东 12 月 15 日宣布已能完整检查内地及香港会计师事务所。", "https://www.sec.gov/hfcaa"),
    ("2023-09-15", "strategic", "2023投资者日", "2023 投资者日：RGM 2.0 战略与三年目标（2026 年 2 万店、三年回馈约 30 亿美元）",
     "9 月 14 日 19:04（香港时间）在港交所发布。",
     "https://ir.yumchina.com/news-releases/news-release-details/yum-china-unveils-rgm-20-strategy-and-introduces-3-year"),
    ("2024-03-20", "broker", "瑞银警示", "瑞银提示一季度利润低于指引的风险（第三方）",
     "美股 YUMC 3 月 19 日跌 7.5%，港股次日跟跌。", "https://ph.investing.com/news/stock-market-news/why-yum-china-stock-fell-10-today-432SI-1169145"),
    ("2024-09-24", "policy", "央行刺激", "人民银行一揽子刺激政策（降准、降息、降存量房贷利率）",
     "当日恒指涨 4.1%。", "https://fortune.com/asia/2024/09/24/china-central-bank-support-economy-hang-seng-shanghai-shares-bazooka-stimulus/"),
    ("2025-04-07", "macro", "关税冲击", "对等关税冲击：恒指单日跌 13.2%",
     "1997 年以来最大单日跌幅。", "https://www.aljazeera.com/economy/2025/4/7/hong-kong-stock-market-plunges-most-since-97-crisis-amid-tariffs-panic"),
    ("2025-04-23", "macro", "关税缓和", "美方释放中美关税降级信号",
     "美国财长贝森特 4 月 22 日称对华关税僵局不可持续；美股 YUMC 当天涨 7.4%，港股次日补涨。",
     "https://www.axios.com/2025/04/23/trump-china-tariffs-bessent"),
    ("2025-11-17", "strategic", "2025投资者日", "2025 投资者日：RGM 3.0 战略，2030 年 3 万家门店，2027 年起回馈约 100% 自由现金流",
     "11 月 17 日 12:25（香港时间，午间休市）在港交所发布。", SEC + "000119312525283928/"),
    ("2025-11-24", "strategic", "纳入国企指数", "获纳入恒生中国企业指数（12 月 8 日生效）",
     "恒生指数公司 11 月 21 日收市后公布季检结果。", "https://m.gelonghui.com/news/5123142"),
    ("2025-12-12", "capital", "回购+10亿", "回购授权扩大 10 亿美元",
     "12 月 12 日 12:10（香港时间，午间休市）在港交所发布。", SEC + "000119312525316788/"),
    ("2026-06-17", "deal", "收购必胜客品牌", "12 亿美元现金收购必胜客中国内地品牌所有权",
     "6 月 16 日 20:13（香港时间）在港交所公告；交割后不再向 Yum! Brands 支付必胜客特许经营费。", SEC + "000119312526271854/"),
    ("2026-08-10", "deal", "收购交割", "必胜客品牌收购完成交割",
     "8 月 7 日（周五）18:46（香港时间）发布。", SEC + "000119312526339048/"),
]

days = json.load(open(os.path.join(ROOT, "data", "processed", "earnings_days.json")))
kpi = {q["label"]: q for q in json.load(open(os.path.join(ROOT, "data", "processed", "ops_kpis.json")))["quarters"]}
subs = json.load(open(os.path.join(ROOT, "data", "raw", "sec", "submissions.json")))["filings"]["recent"]
acc_by_date = {}
for i, f in enumerate(subs["form"]):
    if f == "8-K":
        acc_by_date.setdefault(subs["filingDate"][i], subs["accessionNumber"][i].replace("-", ""))

events = []
for d in days:
    if d.get("next") or not d.get("day0_hk"):
        continue
    k = kpi.get(d["label"], {})
    y, q = d["label"][:4], d["label"][-1]
    bits = []
    if k.get("sssg") is not None:
        bits.append(f"同店销售 {k['sssg'] * 100:+.0f}%")
    if k.get("rm") is not None:
        bits.append(f"餐厅利润率 {k['rm'] * 100:.1f}%")
    if k.get("net_new") is not None:
        bits.append(f"净新增门店 {k['net_new']:,}")
    filed = d["file"][:10]
    events.append({"date": d["day0_hk"], "category": "earnings", "short": f"{y[2:]}Q{q}业绩",
                   "title": f"{y} 年{['一', '二', '三', '四'][int(q) - 1]}季度业绩",
                   "desc": f"发布时间 {d['release_hkt']}（香港时间）。" + "，".join(bits) + ("。" if bits else ""),
                   "source": SEC + acc_by_date.get(filed, "") + "/" if filed in acc_by_date else SEC})
for date, cat, short, title, desc, src in MANUAL:
    events.append({"date": date, "category": cat, "short": short, "title": title, "desc": desc, "source": src})
events.sort(key=lambda e: e["date"])
json.dump(events, open(os.path.join(OUT, "events.json"), "w"), ensure_ascii=False, indent=1)
print(len(events), "events;", sum(e["category"] == "earnings" for e in events), "results")
