"""Second fetch for 百胜中国: what the first run could not reach.

- sec/: 8-K exhibit-99 press releases from the spin-off to February 2018. SEC's submissions.json lists only the latest
  1,000 filings (from 2018-02-13 for Yum China); the older ones are in CIK0001673358-submissions-001.json.
- macro/nbs_retail_releases.json: national catering revenue (餐饮收入) from the NBS monthly retail-sales releases.
  The NBS database API (data.stats.gov.cn) returned 403 to the runner, so this reads the press releases on
  www.stats.gov.cn instead (listing pages, then each release whose title mentions 社会消费品零售总额).
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "report_kit"))
import fetchlib as fl  # noqa: E402

SLUG = os.path.basename(os.path.dirname(HERE))
OUT = os.path.join(SLUG, "data", "raw")
CIK, CONTACT = "1673358", "research@example.com"
for sub in ("sec", "macro"):
    os.makedirs(os.path.join(OUT, sub), exist_ok=True)

# ------------------------------------------------------------ SEC: older 8-K press releases
H = fl.sec_headers(CONTACT)
try:
    old = json.loads(fl.http(f"https://data.sec.gov/submissions/CIK{int(CIK):010d}-submissions-001.json", headers=H))
    json.dump(old, open(os.path.join(OUT, "sec", "submissions-001.json"), "w"), indent=1)
    filings = [dict(zip(old.keys(), vals)) for vals in zip(*old.values())]
    fl.log("older filings", len(filings))
    from bs4 import BeautifulSoup

    def text(raw):
        soup = BeautifulSoup(raw, "lxml")
        for tag in soup(["script", "style"]):
            tag.decompose()
        for tr in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            tr.replace_with(" | ".join(c for c in cells if c) + "\n")
        return re.sub(r"\n\s*\n+", "\n\n", soup.get_text("\n"))

    for f in filings:
        if f["form"] != "8-K" or f["filingDate"] < "2016-10-01":
            continue
        base = f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}/{f['accessionNumber'].replace('-', '')}"
        try:
            idx = json.loads(fl.http(f"{base}/index.json", headers=H))
            for item in idx["directory"]["item"]:
                n = item["name"].lower()
                if re.search(r"ex-?99", n) and n.endswith((".htm", ".html")):
                    name = f"{f['filingDate']}_8-K_ex99_{re.sub(r'[^a-z0-9]', '', n)[:30]}.txt"
                    open(os.path.join(OUT, "sec", name), "w").write(text(fl.http(f"{base}/{item['name']}", headers=H)))
                    fl.log("saved", name)
                    time.sleep(0.3)
        except Exception as e:  # noqa: BLE001
            fl.log("index ERR", base, repr(e)[:200])
        time.sleep(0.3)
except Exception as e:  # noqa: BLE001
    fl.log("ERR older submissions", repr(e)[:300])

# ------------------------------------------------------------ NBS monthly releases: catering revenue
rows, seen = [], set()
try:
    pages = ["https://www.stats.gov.cn/sj/zxfb/index.html"] + [f"https://www.stats.gov.cn/sj/zxfb/index_{i}.html" for i in range(1, 100)]
    links, misses = [], 0
    for u in pages:
        try:
            html = fl.http(u, timeout=30).decode("utf-8", "ignore")
            misses = 0
        except Exception as e:  # noqa: BLE001
            fl.log("nbs list ERR", u, repr(e)[:120])
            misses += 1
            if u.endswith("index.html") or misses >= 3:
                break
            continue
        for href, title in re.findall(r'<a[^>]+href="([^"]+)"[^>]*title="([^"]*)"', html) + re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,80})</a>', html):
            if "社会消费品零售总额" in title and href not in seen:
                seen.add(href)
                links.append((title.strip(), href if href.startswith("http") else "https://www.stats.gov.cn/sj/zxfb/" + href.lstrip("./")))
        time.sleep(0.5)
    fl.log("nbs release links", len(links))
    for title, url in links:
        try:
            t = re.sub(r"<[^>]+>", "", fl.http(url, timeout=30).decode("utf-8", "ignore"))
            t = re.sub(r"\s+", "", t)
            i = t.find("社会消费品零售总额")
            rec = {"title": title, "url": url, "text": t[i:i + 2500] if i >= 0 else ""}
            m = re.search(r"(\d{4})年(\d{1,2})月份?，?社会消费品零售总额(\d+(?:\.\d+)?)亿元，同比(增长|下降)(\d+(?:\.\d+)?)%", t)
            if m:
                rec.update({"y": int(m.group(1)), "m": int(m.group(2)), "retail": float(m.group(3)),
                            "retail_yoy": float(m.group(5)) * (1 if m.group(4) == "增长" else -1)})
            m2 = re.search(r"餐饮收入(\d+(?:\.\d+)?)亿元，(?:同比)?(增长|下降)(\d+(?:\.\d+)?)%", t)
            if m2:
                rec.update({"catering": float(m2.group(1)), "catering_yoy": float(m2.group(3)) * (1 if m2.group(2) == "增长" else -1)})
            rows.append(rec)
        except Exception as e:  # noqa: BLE001
            fl.log("nbs page ERR", url, repr(e)[:120])
        time.sleep(0.5)
except Exception as e:  # noqa: BLE001
    fl.log("ERR nbs releases", repr(e)[:300])
json.dump(rows, open(os.path.join(OUT, "macro", "nbs_retail_releases.json"), "w"), ensure_ascii=False, indent=1)
fl.log("nbs releases parsed", len(rows), "with catering", sum("catering" in r for r in rows))
fl.log("done")
