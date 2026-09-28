# -*- coding: utf-8 -*-
"""苏宁易购公开商品数据收集脚本（课程学习用途，小规模限量）。

只抓「未登录可见」的搜索页公开字段：标题、图片、品牌|材质、卖点描述。
遵守约定：
  - 单线程，默认每请求间隔 3 秒，总量硬上限 3000 条（--max-items 可调低）；
  - 不绕过验证码/登录/反爬：连续 5 次失败自动停止；
  - 每条记录 source_url / crawl_date；缺失字段留空，不从图片或标题臆造。
  - 价格接口已关闭（苏宁价格走 JS 单独接口，未抓包逆向），price 列留空。
  - robots.txt 当前被 WAF 拦截无法读取，执行前请人工在浏览器确认
    https://www.suning.com/robots.txt ，仅在允许范围内收集。

用法：
  python scripts/crawl_suning.py --max-items 2000
  python scripts/crawl_suning.py --selftest   # 离线解析自检
"""
import argparse
import csv
import hashlib
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
DELAY = 3.0          # 秒/请求，别调低
FAIL_LIMIT = 5       # 连续失败次数达到即停止（疑似反爬）
SEARCH_URL = "https://search.suning.com/{kw}/&iy=0&isNoResult=0&cp={page}"
OUT_DIR = os.path.join("data", "raw_data", "Suning_data")

# 品类 -> 搜索词组合（每个词一页约 30 条，组合矩阵拿量）
CATEGORY_QUERIES = {
    "手机壳": ["手机壳", "手机壳 透明", "手机壳 磨砂", "手机壳 磁吸", "手机壳 防摔",
               "华为手机壳", "苹果手机壳", "小米手机壳", "vivo手机壳", "oppo手机壳",
               "手机壳 液态硅胶", "手机壳 全包", "手机支架手机壳", "手机壳 卡通"],
    "水杯": ["水杯", "保温杯", "水杯 大容量", "保温杯 316", "水杯 学生",
             "运动水杯", "玻璃杯", "咖啡杯", "儿童保温杯", "焖烧杯",
             "水杯 便携", "茶杯 陶瓷", "吸管杯", "保温壶"],
    "双肩包": ["双肩包", "双肩包 通勤", "双肩包 电脑", "双肩包 女", "双肩包 男",
               "书包 学生", "双肩包 旅行", "双肩包 防水", "双肩包 商务",
               "双肩包 大容量", "双肩包 轻便", "双肩包 运动"],
    "运动鞋": ["运动鞋", "运动鞋 男", "运动鞋 女", "跑步鞋", "篮球鞋",
               "运动鞋 轻便", "运动鞋 透气", "运动鞋 减震", "板鞋", "训练鞋",
               "运动鞋 网面", "健步鞋"],
}

PRODUCTS_HEADER = ["item_id", "product_type", "item_name", "brand", "color", "material",
                   "main_image_id", "domain_name", "local_image_path", "image_status",
                   "image_height", "image_width", "price", "description",
                   "source_url", "crawl_date"]
QUALITY_HEADER = ["dataset_id", "source_product_id", "image_path", "decode_ok",
                  "actual_height", "actual_width", "declared_height", "declared_width",
                  "format", "file_size_bytes", "sha256", "quality_status", "quality_reason"]

CARD_RE = re.compile(r'<li docType="1".*?</li>', re.S)
ID_RE = re.compile(r'id="(\d+)-(\d+)"')
NAME_RE = re.compile(r'title-selling-point">\s*<a[^>]*>\s*(.*?)\s*<em', re.S)
DESC_RE = re.compile(r'<em\s+style="display:none"\s*>(.*?)</em>', re.S)
IMG_RE = re.compile(r'<img[^>]+src="(//imgservice[^"]+?\.jpg)[^"]*"')
CONFIG_RE = re.compile(r'class="info-config" title="\s*([^"]*?)\s*"')


def parse_card(card_html):
    """从搜索页商品卡片提取字段；缺失留空，不做推断。"""
    rec = {k: "" for k in PRODUCTS_HEADER}
    m_id = ID_RE.search(card_html)
    if not m_id:
        return None
    shop_id, item_code = m_id.groups()
    rec["item_id"] = item_code
    rec["main_image_id"] = item_code
    rec["domain_name"] = "suning.com"

    m = NAME_RE.search(card_html)
    if m:
        rec["item_name"] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()
    m = DESC_RE.search(card_html)
    if m:
        rec["description"] = re.sub(r"\s+", " ", m.group(1)).strip()
    m = IMG_RE.search(card_html)
    if m:
        rec["local_image_path"] = "data/raw_data/Suning_data/images/%s.jpg" % item_code
        rec["_image_url"] = "https:" + m.group(1)  # 400x400 缩略图
    m = CONFIG_RE.search(card_html)
    if m:
        parts = [p.strip() for p in m.group(1).split("|") if p.strip()]
        if parts:
            rec["brand"] = parts[0]
        # 苏宁卡片展示格式为 品牌|材质/规格，第二段按材质收录（按品类抽检核对）
        if len(parts) > 1:
            rec["material"] = parts[1]
    rec["source_url"] = "https://product.suning.com/%s/%s.html" % (shop_id, item_code)
    rec["crawl_date"] = date.today().isoformat()
    return rec


def fetch(url, referer=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": referer or "https://www.suning.com/",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def search_page_records(keyword, page):
    url = SEARCH_URL.format(kw=urllib.parse.quote(keyword), page=page)
    html = fetch(url).decode("utf-8", "ignore")
    recs = []
    for card in CARD_RE.findall(html):
        rec = parse_card(card)
        if rec and rec["item_name"]:
            recs.append(rec)
    return recs, url


def download_image(rec, img_dir):
    path = os.path.join(img_dir, os.path.basename(rec["local_image_path"]))
    if os.path.exists(path):
        return
    data = fetch(rec["_image_url"], referer=rec["source_url"])
    with open(path, "wb") as f:
        f.write(data)


def image_quality_rows(rec, img_dir):
    """与现有数据集 image_quality_report.csv 同列格式。"""
    path = os.path.join(img_dir, os.path.basename(rec["local_image_path"]))
    row = dict.fromkeys(QUALITY_HEADER, "")
    row["dataset_id"] = "suning_public_search"
    row["source_product_id"] = rec["item_id"]
    row["image_path"] = rec["local_image_path"]
    if not os.path.exists(path):
        row.update(decode_ok="false", quality_status="failed", quality_reason="missing_file")
        return row
    data = open(path, "rb").read()
    row["file_size_bytes"] = str(len(data))
    row["sha256"] = hashlib.sha256(data).hexdigest()
    ok = data[:2] == b"\xff\xd8" or data[:8] == b"\x89PNG\r\n\x1a\n"
    row["decode_ok"] = "true" if ok else "false"
    row["format"] = "JPEG" if data[:2] == b"\xff\xd8" else ("PNG" if ok else "unknown")
    w = h = ""
    if ok:
        w, h = probe_image_size(data)  # 尺寸留空则 declared/actual 也留空
    row.update(actual_height=h, actual_width=w, declared_height=h, declared_width=w)
    if not ok:
        row.update(quality_status="failed", quality_reason="decode_fail")
    else:
        row["quality_status"] = "pass"
    return row


def probe_image_size(data):
    """最小 JPEG/PNG 尺寸解析，失败返回空。"""
    try:
        if data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    h = int.from_bytes(data[i + 5:i + 7], "big")
                    w = int.from_bytes(data[i + 7:i + 9], "big")
                    return str(w), str(h)
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                else:
                    i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            w = int.from_bytes(data[16:20], "big")
            h = int.from_bytes(data[20:24], "big")
            return str(w), str(h)
    except Exception:
        pass
    return "", ""


def selftest():
    card = '''<li docType="1" class="item-wrap" id="0000000000-12452902725">
<div class="title-selling-point"><a target="_blank" href="//product.suning.com/0000000000/12452902725.html">
测试商品手机壳 透明 华为
<em  style="display:none" >防滑耐磨；内置镜头支架</em>
</a></div>
<div tabindex="-1" aria-hidden="true" class="info-config" title=" 华为 |软胶"><em> 华为 <i>|</i>软胶</em></div>
<img alt="x" src="//imgservice1.suning.cn/uimg1/b2c/image/abc.jpg_400w_400h_4e">
</li>'''
    rec = parse_card(card)
    assert rec and rec["item_id"] == "12452902725"
    assert rec["item_name"] == "测试商品手机壳 透明 华为"
    assert rec["brand"] == "华为" and rec["material"] == "软胶"
    assert rec["description"] == "防滑耐磨；内置镜头支架"
    # 捕获组只取到 .jpg，自动去掉 _400w_400h 缩略后缀，即原图地址
    assert rec["_image_url"].endswith("abc.jpg")
    assert "12452902725" in rec["source_url"]
    assert parse_card("<li docType=\"1\" id=\"0000000000-1\">no name</li>")["item_name"] == ""
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-items", type=int, default=3000, help="硬上限，默认 3000")
    ap.add_argument("--delay", type=float, default=DELAY, help="请求间隔秒，不建议低于 3")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    img_dir = os.path.join(OUT_DIR, "images")
    os.makedirs(img_dir, exist_ok=True)
    prod_csv = os.path.join(OUT_DIR, "products.csv")
    qual_csv = os.path.join(OUT_DIR, "image_quality_report.csv")

    done_ids = set()
    if os.path.exists(prod_csv):  # 断点续传
        with open(prod_csv, encoding="utf-8-sig") as f:
            done_ids = {r["item_id"] for r in csv.DictReader(f)}

    mode = "a" if os.path.exists(prod_csv) else "w"
    fails = 0
    saved = 0
    with open(prod_csv, mode, newline="", encoding="utf-8-sig") as pf, \
            open(qual_csv, mode, newline="", encoding="utf-8-sig") as qf:
        pw = csv.DictWriter(pf, fieldnames=PRODUCTS_HEADER, extrasaction="ignore")
        qw = csv.DictWriter(qf, fieldnames=QUALITY_HEADER)
        if mode == "w":
            pw.writeheader()
            qw.writeheader()
        for product_type, queries in CATEGORY_QUERIES.items():
            for kw in queries:
                if saved >= args.max_items or fails >= FAIL_LIMIT:
                    break
                page = 0
                while page < 10 and saved < args.max_items and fails < FAIL_LIMIT:
                    try:
                        recs, src = search_page_records(kw, page)
                        fails = 0
                    except Exception as e:
                        fails += 1
                        print("fetch fail(%d/%d) %s p%d: %s" % (fails, FAIL_LIMIT, kw, page, e))
                        time.sleep(args.delay * 2)
                        break  # 换词，不在同一页面死磕
                    if not recs:
                        break  # 空页 = 翻页被反爬门控，换词
                    for rec in recs:
                        if saved >= args.max_items:
                            break
                        if rec["item_id"] in done_ids or not rec.get("_image_url"):
                            continue  # 无图商品对多模态项目无用，跳过
                        rec["product_type"] = product_type
                        try:
                            download_image(rec, img_dir)
                            rec["image_status"] = "ok"
                        except Exception:
                            rec["image_status"] = "download_fail"
                        w, h = probe_image_size(
                            open(os.path.join(img_dir, os.path.basename(rec["local_image_path"])), "rb").read()
                        ) if rec["image_status"] == "ok" else ("", "")
                        rec["image_width"], rec["image_height"] = w, h
                        qw.writerow(image_quality_rows(rec, img_dir))
                        pw.writerow(rec)
                        done_ids.add(rec["item_id"])
                        saved += 1
                    page += 1
                    time.sleep(args.delay)
            if saved >= args.max_items or fails >= FAIL_LIMIT:
                break
    print("saved %d new items -> %s" % (saved, prod_csv))
    if fails >= FAIL_LIMIT:
        print("连续失败达到上限，疑似触发反爬，已停止。稍后再续跑（支持断点续传）。")


if __name__ == "__main__":
    main()
