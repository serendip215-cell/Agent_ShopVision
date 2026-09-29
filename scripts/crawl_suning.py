# -*- coding: utf-8 -*-
"""苏宁易购公开商品数据收集脚本（课程学习用途，小规模限量）。

只抓「未登录可见」的搜索页公开字段：标题、图片、品牌|材质、卖点描述。
遵守约定：
  - 4 个线程同时拉搜索页。代理先试一次，页面传不完就改直连；封面图直连。每批之间停约 3 秒，总量硬上限 6000 条；
  - 请求头在几份常见浏览器配置间轮换；代理从仓库根目录 .env 读取，某个 IP 失败 3 次才换；
  - 不绕过验证码/登录：连续 3 个 IP 都失败才停止；
  - 每条记录 source_url / crawl_date；缺失字段留空，不从图片或标题臆造。
  - 价格接口已关闭（苏宁价格走 JS 单独接口，未抓包逆向），price 列留空。
  - robots.txt 当前被 WAF 拦截无法读取，执行前请人工在浏览器确认
    https://www.suning.com/robots.txt ，仅在允许范围内收集。

品类：水杯、双肩包、运动鞋，以及 2026-09-28 搜索页上核对过的女装、男装、运动服。
每类写满 1000 条即停。童装搜索页当时只有 2 条商品卡，没有收。
标题对不上该类的不入库。

用法：仓库根目录 .env 里写 PROXY_POOL_URL=代理池链接，然后
  python scripts/crawl_suning.py
  python scripts/crawl_suning.py --selftest   # 离线解析自检
"""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import http.client
import os
import random
import re
import time
import urllib.parse
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path):
    """读仓库根目录 .env。不覆盖已经存在的环境变量。"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))


load_env(os.path.join(ROOT, ".env"))

# 请求头级浏览器差异：UA / 语言 / Chromium 客户端提示。不含 TLS、画布伪装。
FINGERPRINTS = [
    {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    },
    {
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
        "Accept-Language": "zh-CN,zh;q=0.9",
        "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    },
    {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "sec-ch-ua": '"Microsoft Edge";v="126", "Chromium";v="126", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    },
    {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) "
                       "Gecko/20100101 Firefox/127.0"),
        "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5",
    },
    {
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:126.0) "
                       "Gecko/20100101 Firefox/126.0"),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    },
    {
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                       "(KHTML, like Gecko) Version/17.5 Safari/605.1.15"),
        "Accept-Language": "zh-CN,zh-Hans;q=0.9",
    },
]
DELAY = 3.0          # 每批页面之间的间隔，别调低
WORKERS = 4          # 同时使用的 IP 和线程数
FAIL_LIMIT = 3       # 连续 3 批都失败才停止
PAGE_RETRY = 3        # 同一个 IP 失败 3 次才换下一个
FETCH_TIMEOUT = 45
MAX_PAGES = 20       # 每个搜索词最多翻页
PER_CATEGORY = 1000  # 每类最多 1000，实验 1 建议区间是 300–1000
HARD_CAP = 6000       # 6 个品类 × 1000。可调低，但不要高于这个数
SEARCH_URL = "https://search.suning.com/{kw}/&iy=0&isNoResult=0&cp={page}"
OUT_DIR = os.path.join("data", "raw_data", "Suning_data")

# 搜索词来自苏宁搜索页左侧/顶部类目筛选项（2026-09-28 公开页核对），不是自造类目。
# 水杯: 保温杯、塑料杯、玻璃杯、马克杯、水具、户外水具
# 双肩包: 双肩背包、书包、女士双肩包、登山包
# 运动鞋: 跑步鞋、运动休闲鞋、篮球鞋、训练鞋、羽毛球鞋、网球鞋
# 女装: 连衣裙、女士针织/毛衣、女士羽绒服
# 男装: 男士衬衫、男士T恤、男士牛仔裤、男士夹克
# 运动服: 运动夹克、运动套装、卫衣、运动T恤、休闲运动套装
CATEGORY_QUERIES = {
    "水杯": ["保温杯", "塑料杯", "玻璃杯", "马克杯", "水杯", "户外水具"],
    "双肩包": ["双肩背包", "双肩包", "书包", "女士双肩包", "登山包"],
    "运动鞋": ["跑步鞋", "运动鞋", "篮球鞋", "训练鞋", "运动休闲鞋", "羽毛球鞋", "网球鞋"],
    "女装": ["连衣裙", "女士毛衣", "女士针织衫", "女士羽绒服", "女装"],
    "男装": ["男士衬衫", "男士T恤", "男士牛仔裤", "男士夹克", "男装"],
    "运动服": ["运动套装", "运动夹克", "卫衣", "运动T恤", "休闲运动套装"],
}
# 标题必须命中本类词，并丢掉配件和串类。不靠标题补颜色、材质。
ACCEPT = {
    "水杯": ("杯", "壶", "水具"),
    "双肩包": ("双肩", "背包", "书包", "登山包"),
    "运动鞋": ("鞋",),
    "女装": ("女", "裙", "毛衣", "羽绒服", "针织"),
    "男装": ("男",),
    "运动服": ("运动", "卫衣", "套装", "夹克", "T恤"),
}
REJECT = {
    "水杯": ("杯垫", "杯套", "杯盖", "杯刷", "贴纸"),
    "双肩包": ("单肩", "斜挎", "腰包", "胸包", "拉杆"),
    "运动鞋": ("鞋垫", "鞋带", "袜子", "鞋油", "鞋撑"),
    "女装": ("男", "童", "婴儿"),
    "男装": ("女", "童", "婴儿"),
    "运动服": ("鞋",),
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
# 女装等卡片的标题 </a> 后面没有 <em>，不能把 <em> 当成标题结束标志。
NAME_RE = re.compile(r'title-selling-point">\s*<a[^>]*>\s*(.*?)\s*</a>', re.S)
DESC_RE = re.compile(r'<em\s+style="display:none"\s*>(.*?)</em>', re.S)
# 保留 _400w_400h 这类后缀。去掉后缀会下到 200KB 以上的原图，代理经常在约 32KB 处把连接掐断。
# 搜索卡片的 img-block 里只有这一张图，就是封面。详情页相册不打开。
IMG_RE = re.compile(
    r'src="(//imgservice[^"]+?/b2c/image/[^"]+?\.(?:jpg|jpeg|png|webp)(?:_[^"]*)?)"', re.I)
COVER_RE = re.compile(r'/b2c/image/([^./]+)\.', re.I)
CONFIG_RE = re.compile(r'class="info-config" title="\s*([^"]*?)\s*"')


def log(msg):
    """运行日志：时分秒 + 当前在做什么。立刻刷出，避免长时间看起来像卡住。"""
    print("%s  %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def proxy_label(proxy):
    """只显示 ip:port。用户名密码留在代理 URL 里，不写进日志。"""
    if not proxy:
        return "直连"
    return proxy["http"].split("@")[-1]


# 搜索卡片不带款式 id。商品页 colorList 才把「白/黑/绿、240ml/480ml」收成一个款。
# 这里不去请求详情页，只在判重时丢掉这些规格尾巴。入库标题仍是原文。
_VARIANT_TOKEN = re.compile(
    r"^(?:\d+(?:\.\d+)?(?:ml|mL|ML|l|L)|个|只|套|组|"
    r"[A-Za-z]{2,}[-_]?[A-Za-z]?\d{2,}[A-Za-z0-9-]*|"
    r"(?:经典)?(?:白|黑|红|蓝|绿|粉|灰|银|金|黄|紫|橙|棕|青|米白|象牙|磨砂黑|梦幻黑|雪山落日)色?)$"
)


def title_key(name):
    """去掉空格、容量、型号和末尾颜色后再比较。同一款只留第一次见到的封面。"""
    parts = re.sub(r"\s+", " ", (name or "").strip()).split(" ")
    while parts and _VARIANT_TOKEN.match(parts[-1].strip("，,。/")):
        parts.pop()
    s = "".join(parts)
    s = re.sub(r"\d+(?:\.\d+)?(?:ml|mL|ML|l|L)", "", s)
    s = re.sub(r"[A-Za-z]{2,}[-_]?[A-Za-z]?\d{2,}[A-Za-z0-9-]*", "", s)
    s = re.sub(r"(?:雪山落日|磨砂黑|梦幻黑|象牙白|米白|[白黑红蓝绿粉灰银金黄紫橙棕青]色)", "", s)
    return re.sub(r"[()（）\[\]【】]", "", s)


def cover_key(url):
    """封面文件名。同一张图配不同商品编号时只保留第一次。"""
    m = COVER_RE.search(url or "")
    return m.group(1) if m else ""


def in_category(product_type, name):
    """标题必须像这个品类。先排除配件和串类，再看是否命中该类的词。"""
    if any(w in name for w in REJECT[product_type]):
        return False
    return any(w in name for w in ACCEPT[product_type])


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
        # 卖点 <em> 如果包在标题链接里，切掉，避免和标题粘成一行
        title = m.group(1).split("<em")[0]
        rec["item_name"] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title)).strip()
    m = DESC_RE.search(card_html)
    if m:
        rec["description"] = re.sub(r"\s+", " ", m.group(1)).strip()
    m = IMG_RE.search(card_html)
    if m:
        # 本地文件名只用 jpg/png。下载地址保留页面上的缩略图后缀，避免去拉原图。
        ext = re.search(r'\.(jpg|jpeg|png|webp)', m.group(1), re.I).group(1).lower()
        if ext == "jpeg":
            ext = "jpg"
        rec["local_image_path"] = "data/raw_data/Suning_data/images/%s.%s" % (item_code, ext)
        rec["_image_url"] = "https:" + m.group(1)
        rec["_cover_key"] = cover_key(rec["_image_url"])
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


def normalize_proxy(raw):
    """ip:port、http://ip:port，或 服务器:端口:用户名:密码。空串 / 无法识别返回 None。"""
    raw = (raw or "").strip()
    if not raw:
        return None
    if "://" in raw:
        return {"http": raw, "https": raw}
    parts = raw.split(":")
    if len(parts) >= 4 and parts[1].isdigit():
        host, port, user = parts[0], parts[1], urllib.parse.quote(parts[2], safe="")
        password = urllib.parse.quote(":".join(parts[3:]), safe="")
        url = "http://%s:%s@%s:%s" % (user, password, host, port)
        return {"http": url, "https": url}
    if len(parts) == 2 and parts[1].isdigit():
        url = "http://" + raw
        return {"http": url, "https": url}
    return None


def pick_headers(referer=None):
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": referer or "https://www.suning.com/",
    }
    headers.update(random.choice(FINGERPRINTS))
    return headers


class ProxyPool:
    """一个 IP 一直用到失败满 3 次再换。都没配则直连。"""

    def __init__(self, api="", path=""):
        self.api = api
        self.lines = []
        self.i = 0
        self.cur = None
        if path:
            with open(path, encoding="utf-8") as f:
                self.lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]

    def current(self):
        if self.cur is None and (self.api or self.lines):
            return self.rotate()
        return self.cur

    def rotate(self):
        if self.api:
            self.cur = self._from_api()
        elif self.lines:
            self.cur = normalize_proxy(self.lines[self.i % len(self.lines)])
            self.i += 1
        else:
            self.cur = None
        log("当前代理 %s" % proxy_label(self.cur))
        return self.cur

    def _from_api(self):
        """向代理池要一个 IP。接口慢或握手超时就再试，不是站点封禁。"""
        last = None
        for attempt in range(PAGE_RETRY):
            try:
                req = urllib.request.Request(
                    self.api, headers={"User-Agent": FINGERPRINTS[0]["User-Agent"]})
                with urllib.request.urlopen(req, timeout=20) as r:
                    text = r.read().decode("utf-8", "ignore")
                line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
                proxy = normalize_proxy(line)
                if not proxy:
                    raise RuntimeError("代理接口没有返回 ip:端口:用户名:密码")
                return proxy
            except Exception as e:
                last = e
                log("代理接口第 %d/%d 次没要到：%s" % (attempt + 1, PAGE_RETRY, e))
                time.sleep(2)
        raise last


def fetch(url, referer=None, proxy=None, allow_partial=False, timeout=None):
    handlers = [urllib.request.ProxyHandler(proxy)] if proxy else []
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers=pick_headers(referer))
    try:
        with opener.open(req, timeout=timeout or FETCH_TIMEOUT) as r:
            return r.read()
    except http.client.IncompleteRead as e:
        data = e.partial or b""
        # 搜索页商品卡在正文后半段，半截里已经有卡片就用，不再为此换 IP
        if allow_partial and b'docType="1"' in data:
            return data
        raise


def parse_search_html(html):
    recs = []
    for card in CARD_RE.findall(html):
        rec = parse_card(card)
        if rec and rec["item_name"]:
            recs.append(rec)
    return recs


def search_page_records(keyword, page, proxy=None, timeout=None):
    url = SEARCH_URL.format(kw=urllib.parse.quote(keyword), page=page)
    html = fetch(url, proxy=proxy, allow_partial=True, timeout=timeout).decode("utf-8", "ignore")
    return parse_search_html(html), url


def load_page(proxy, keyword, page):
    """先用分配到的 IP 拉搜索页。代理经常在商品卡出现前把连接掐断，失败就改直连。

    直连实测约 1 秒能拿到整页。不再对同一个坏 IP 空等 3 次 45 秒。
    """
    log("第 %d 页开始 经由 %s" % (page + 1, proxy_label(proxy)))
    if not proxy:
        try:
            recs, _src = search_page_records(keyword, page, None, timeout=20)
            log("第 %d 页直连返回 %d 个商品卡" % (page + 1, len(recs)))
            return recs, None, True
        except Exception as e:
            log("第 %d 页直连也失败：%s" % (page + 1, e))
            return None, e, False
    if proxy:
        try:
            recs, _src = search_page_records(keyword, page, proxy, timeout=12)
            if recs:
                log("第 %d 页代理返回 %d 个商品卡" % (page + 1, len(recs)))
                return recs, None, True
            log("第 %d 页代理没有商品卡，改直连" % (page + 1))
        except Exception as e:
            log("第 %d 页代理未完成（%s），改直连" % (page + 1, e))
    try:
        recs, _src = search_page_records(keyword, page, None, timeout=20)
        log("第 %d 页直连返回 %d 个商品卡" % (page + 1, len(recs)))
        return recs, None, False
    except Exception as e:
        log("第 %d 页直连也失败：%s" % (page + 1, e))
        return None, e, False


def fetch_cover(rec, img_dir):
    """封面直连。代理下载图片时经常在大约 32KB 被掐断。"""
    try:
        download_image(rec, img_dir, None)
        return rec, None
    except Exception as e:
        return rec, e


def download_image(rec, img_dir, proxy=None):
    """先走当前代理下缩略图，失败再直连一次。半截文件不当作成功。"""
    path = os.path.join(img_dir, os.path.basename(rec["local_image_path"]))
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return
    last = None
    # 图片走代理时，连接经常在大约 32KB 被掐断（原图 200KB+，400 像素图也有 100KB）。
    # 搜索页继续用代理；图片先直连，直连失败再用当前代理试一次。
    for use_proxy in (None, proxy):
        try:
            data = fetch(rec["_image_url"], referer=rec["source_url"], proxy=use_proxy)
            if not (data[:2] == b"\xff\xd8" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"RIFF"):
                raise RuntimeError("不是图片，只有 %d 字节" % len(data))
            with open(path, "wb") as f:
                f.write(data)
            return
        except Exception as e:
            last = e
            if os.path.exists(path):
                os.remove(path)
    raise last


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
    assert rec["_image_url"].endswith("abc.jpg_400w_400h_4e")
    assert rec["_cover_key"] == "abc"
    assert title_key("健 卡侬 跑鞋") == "健卡侬跑鞋"
    pocket = "[官方旗舰店]小米米家保温杯口袋版 女儿童学生水杯便携大容量保冷杯子男316不锈钢壶 "
    assert title_key(pocket + "白色") == title_key(pocket + "黑色") == title_key(pocket + "雪山落日")
    assert title_key("铁洋 手提保温杯 1000ML 个") == title_key("铁洋 手提保温杯 800ML 个")
    assert title_key("虎牌(TIGER)保温杯水杯MJA-B024 240ML") == title_key(
        "虎牌(TIGER)保温杯水杯MJA-B048 480ML")
    assert title_key("小米 米家保温杯弹盖版2 粉色") != title_key(pocket + "白色")
    assert rec["local_image_path"].endswith(".jpg")
    png = parse_card('<li docType="1" id="0000000000-2"><img src="//imgservice1.suning.cn/uimg1/b2c/image/abc.png_400w_400h_4e">')
    assert png["_image_url"].endswith("abc.png_400w_400h_4e")
    assert "12452902725" in rec["source_url"]
    assert parse_card("<li docType=\"1\" id=\"0000000000-1\">no name</li>")["item_name"] == ""
    assert all("User-Agent" in fp for fp in FINGERPRINTS)
    assert normalize_proxy("1.2.3.4:8080") == {
        "http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"}
    assert normalize_proxy("http://user:pass@1.2.3.4:8080")["https"].startswith("http://user:pass@")
    assert normalize_proxy("123.184.97.49:15401:user:pass") == {
        "http": "http://user:pass@123.184.97.49:15401",
        "https": "http://user:pass@123.184.97.49:15401"}
    assert normalize_proxy("not-a-proxy") is None
    assert normalize_proxy("  ") is None
    headers = pick_headers()
    assert headers["User-Agent"] and headers["Referer"].startswith("https://")
    assert list(CATEGORY_QUERIES) == ["水杯", "双肩包", "运动鞋", "女装", "男装", "运动服"]
    assert in_category("水杯", "虎牌保温杯") and not in_category("水杯", "硅胶杯垫")
    assert in_category("双肩包", "耐克双肩包") and not in_category("双肩包", "斜挎包女")
    assert in_category("运动鞋", "男款跑步鞋") and not in_category("运动鞋", "运动鞋垫")
    dress = '''<li docType="1" id="0010257466-12445237125">
<div class="title-selling-point"><a href="//product.suning.com/0010257466/12445237125.html">
纯欲风韩系Polo领连衣裙女装夏季新款
</a></div>
<img src="//imgservice3.suning.cn/uimg1/b2c/image/Yzo.jpg_400w_600h_1e_1c">
</li>'''
    dress_rec = parse_card(dress)
    assert dress_rec["item_name"] == "纯欲风韩系Polo领连衣裙女装夏季新款"
    assert dress_rec["_image_url"].endswith("Yzo.jpg_400w_600h_1e_1c")
    assert dress_rec["local_image_path"].endswith(".jpg")
    assert in_category("女装", dress_rec["item_name"])
    assert not in_category("男装", dress_rec["item_name"])
    assert in_category("男装", "男士夹克春秋外套") and not in_category("男装", "女士衬衫")
    assert in_category("运动服", "篮球运动套装") and not in_category("运动服", "跑步鞋男")
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-items", type=int, default=HARD_CAP, help="硬上限 6000，可调低")
    ap.add_argument("--delay", type=float, default=DELAY, help="请求间隔秒，不建议低于 3")
    ap.add_argument("--proxy-file", default="", help="代理列表，每行 ip:port 或 http://ip:port")
    ap.add_argument("--proxy-api", default=os.environ.get("PROXY_POOL_URL", ""),
                    help="代理接口，默认读仓库根目录 .env 的 PROXY_POOL_URL")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if args.delay < DELAY:
        args.delay = DELAY
    if args.max_items > HARD_CAP:
        args.max_items = HARD_CAP
    pool = ProxyPool(args.proxy_api, args.proxy_file)

    img_dir = os.path.join(OUT_DIR, "images")
    os.makedirs(img_dir, exist_ok=True)
    prod_csv = os.path.join(OUT_DIR, "products.csv")
    qual_csv = os.path.join(OUT_DIR, "image_quality_report.csv")

    # 没下到图的行、以及同一款的颜色/容量重复，启动时只留第一条
    if os.path.exists(prod_csv):
        with open(prod_csv, encoding="utf-8-sig") as f:
            old_rows = list(csv.DictReader(f))
        ok_rows = []
        seen = set()
        dropped = []
        for r in old_rows:
            if r.get("image_status") != "ok":
                dropped.append(r)
                continue
            k = title_key(r.get("item_name"))
            if k in seen:
                dropped.append(r)
                continue
            seen.add(k)
            ok_rows.append(r)
        if dropped:
            with open(prod_csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=PRODUCTS_HEADER, extrasaction="ignore")
                w.writeheader()
                w.writerows(ok_rows)
            ok_ids = {r["item_id"] for r in ok_rows}
            if os.path.exists(qual_csv):
                with open(qual_csv, encoding="utf-8-sig") as f:
                    qrows = [r for r in csv.DictReader(f) if r.get("source_product_id") in ok_ids]
                with open(qual_csv, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.DictWriter(f, fieldnames=QUALITY_HEADER)
                    w.writeheader()
                    w.writerows(qrows)
            for r in dropped:
                path = os.path.join(img_dir, os.path.basename(r.get("local_image_path") or ""))
                if path and os.path.exists(path):
                    os.remove(path)
            log("去掉 %d 条重复或没图的记录，只留每款的第一张封面" % len(dropped))
    done_ids = set()
    seen_titles = set()
    seen_covers = set()
    counts = {k: 0 for k in CATEGORY_QUERIES}
    if os.path.exists(prod_csv):  # 断点续传：跳过已成功的商品，同标题也不再下
        with open(prod_csv, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                done_ids.add(r["item_id"])
                seen_titles.add(title_key(r["item_name"]))
                if r["product_type"] in counts:
                    counts[r["product_type"]] += 1
    log("启动 品类 %s" % "、".join(CATEGORY_QUERIES))
    slots = []
    for n in range(WORKERS):
        try:
            slots.append(pool.rotate())
            time.sleep(0.5)
        except Exception as e:
            log("第 %d 个 IP 没要到，用已有的 %d 个继续：%s" % (n + 1, len(slots), e))
            break
    if not slots:
        log("一个 IP 都没要到，改为直连")
        slots = [None]
    workers = len(slots)
    log("上限 每类 %d 条，本次最多 %d 条，%d 个 IP 并发，每批间隔不少于 %.0f 秒" % (
        PER_CATEGORY, args.max_items, workers, args.delay))
    log("代理 %s" % ("搜索页先走代理，页面传不完就改直连" if args.proxy_api else "未配置，直连"))
    log("已有 " + " ".join("%s %d/%d" % (k, counts[k], PER_CATEGORY) for k in counts))
    log("写入 %s" % prod_csv)

    mode = "a" if os.path.exists(prod_csv) else "w"
    fails = 0
    saved = 0
    ex = ThreadPoolExecutor(max_workers=workers)
    with open(prod_csv, mode, newline="", encoding="utf-8-sig") as pf, \
            open(qual_csv, mode, newline="", encoding="utf-8-sig") as qf:
        pw = csv.DictWriter(pf, fieldnames=PRODUCTS_HEADER, extrasaction="ignore")
        qw = csv.DictWriter(qf, fieldnames=QUALITY_HEADER)
        if mode == "w":
            pw.writeheader()
            qw.writeheader()
        for product_type, queries in CATEGORY_QUERIES.items():
            for kw in queries:
                if counts[product_type] >= PER_CATEGORY or saved >= args.max_items or fails >= FAIL_LIMIT:
                    break
                log("进入品类【%s】搜索词「%s」 已有 %d/%d" % (
                    product_type, kw, counts[product_type], PER_CATEGORY))
                page = 0
                while (page < MAX_PAGES and counts[product_type] < PER_CATEGORY
                       and saved < args.max_items and fails < FAIL_LIMIT):
                    pages = list(range(page, min(page + workers, MAX_PAGES)))
                    log("同时爬取【%s】「%s」第 %d-%d 页" % (
                        product_type, kw, pages[0] + 1, pages[-1] + 1))
                    futs = {
                        ex.submit(load_page, slots[i], kw, p): (i, p)
                        for i, p in enumerate(pages)
                    }
                    got = {}
                    for fut in as_completed(futs):
                        i, p = futs[fut]
                        recs, err, proxy_ok = fut.result()
                        got[p] = (i, recs, err)
                        if err is not None:
                            log("第 %d 页失败，更换该 IP：%s" % (p + 1, err))
                            try:
                                slots[i] = pool.rotate()
                            except Exception as e:
                                log("换 IP 失败，这个线程改直连：%s" % e)
                                slots[i] = None
                        elif not proxy_ok and slots[i] is not None:
                            log("第 %d 页的代理传不完页面，这个线程之后改直连" % (p + 1))
                            slots[i] = None
                    if all(err is not None for _i, _recs, err in got.values()):
                        fails += 1
                        log("这一批 %d 页都失败 %d/%d" % (len(pages), fails, FAIL_LIMIT))
                        if fails >= FAIL_LIMIT:
                            break
                        continue
                    fails = 0
                    todo = []
                    skipped = 0
                    cards = 0
                    stop_kw = False
                    for p in pages:
                        _i, recs, err = got[p]
                        if err is not None:
                            continue
                        cards += len(recs)
                        if not recs:
                            log("【%s】「%s」第 %d 页没有商品卡，换下一个搜索词" % (
                                product_type, kw, p + 1))
                            stop_kw = True
                            break
                        for rec in recs:
                            if (counts[product_type] + len(todo) >= PER_CATEGORY
                                    or saved + len(todo) >= args.max_items):
                                break
                            if rec["item_id"] in done_ids or not rec.get("_image_url"):
                                continue
                            if not in_category(product_type, rec["item_name"]):
                                continue
                            tk = title_key(rec["item_name"])
                            ck = rec.get("_cover_key") or ""
                            if tk in seen_titles or (ck and ck in seen_covers):
                                skipped += 1
                                continue
                            rec["product_type"] = product_type
                            rec["_tk"] = tk
                            seen_titles.add(tk)
                            if ck:
                                seen_covers.add(ck)
                            done_ids.add(rec["item_id"])
                            todo.append(rec)
                    kept = 0
                    if todo:
                        log("本批新商品 %d 个，开始下封面" % len(todo))
                    cover_futs = [ex.submit(fetch_cover, rec, img_dir) for rec in todo]
                    for fut in as_completed(cover_futs):
                        rec, err = fut.result()
                        if err is not None:
                            seen_titles.discard(rec.get("_tk"))
                            if rec.get("_cover_key"):
                                seen_covers.discard(rec["_cover_key"])
                            done_ids.discard(rec["item_id"])
                            log("图片失败，本条不计入 %s %s" % (rec["item_id"], err))
                            continue
                        rec["image_status"] = "ok"
                        img_path = os.path.join(img_dir, os.path.basename(rec["local_image_path"]))
                        w, h = probe_image_size(open(img_path, "rb").read())
                        rec["image_width"], rec["image_height"] = w, h
                        qw.writerow(image_quality_rows(rec, img_dir))
                        pw.writerow(rec)
                        pf.flush()
                        counts[product_type] += 1
                        saved += 1
                        kept += 1
                        log("写入【%s】%d/%d 总 %d  %s  %s  图:ok" % (
                            product_type, counts[product_type], PER_CATEGORY, saved,
                            rec["item_id"], rec["item_name"][:36]))
                    log("【%s】「%s」第 %d-%d 页结束 卡片 %d 新写入 %d 跳过重复 %d" % (
                        product_type, kw, pages[0] + 1, pages[-1] + 1, cards, kept, skipped))
                    if stop_kw:
                        break
                    page = pages[-1] + 1
                    wait = random.uniform(args.delay, args.delay + 1)
                    log("等待 %.1f 秒后继续" % wait)
                    time.sleep(wait)
            if saved >= args.max_items or fails >= FAIL_LIMIT:
                break
    ex.shutdown(wait=True)
    log("结束 本次新写入 %d 条 -> %s" % (saved, prod_csv))
    log("结果 " + " ".join("%s %d/%d" % (k, counts[k], PER_CATEGORY) for k in counts))
    if fails >= FAIL_LIMIT:
        log("连续 %d 个代理都失败，已停止。稍后再运行同一条命令会接着写。" % FAIL_LIMIT)


if __name__ == "__main__":
    main()
