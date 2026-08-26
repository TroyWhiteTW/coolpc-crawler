"""靜態頁面產生器：讀取最新兩份 CSV 快照，產出可直接被爬蟲索引的 HTML。
Static site generator: reads the two latest CSV snapshots and emits crawlable HTML.

產出結構 Output layout (_site/)：
    index.html          總覽首頁 Overview homepage
    c/<slug>.html       各分類價格頁 Per-category price pages
    sitemap.xml         網站地圖 Sitemap
    compare.html 等     由 docs/ 複製的既有前端資源 Existing assets copied from docs/
"""
import csv
import json
import re
import shutil
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape

from crawler.models import (CATEGORY_BLURBS, CATEGORY_SHORT, CATEGORY_SLUGS,
                            PRIMARY_SLUGS)

BASE_URL = "https://troywhitetw.github.io/coolpc-crawler/"
SITE_DIR = Path("_site")
DOCS_DIR = Path("docs")
OUTPUT_DIR = Path("output")
TEMPLATE_DIR = Path("templates")

# 首頁漲跌榜顯示筆數 Number of rows in the homepage movers tables
TOP_N = 20
# 分類頁異動摘要顯示筆數 Number of rows in the per-category movers table
CAT_MOVERS_N = 15
# JSON-LD ItemList 收錄上限，避免 structured data 過肥
# Cap on ItemList entries to keep the structured data payload reasonable
ITEMLIST_MAX = 100
# 商品數低於此值的分類不另開頁面，避免 thin content
# Categories below this item count get no page, to avoid thin content
MIN_ITEMS_PER_PAGE = 5

TW_TZ = timezone(timedelta(hours=8))

FAQ = [
    {
        "q": "這個網站的價格資料多久更新一次？",
        "a": "每天自動擷取 5 次，台灣時間 07:05、11:05、15:05、19:05、23:05 各一次。"
             "其中 07:05、15:05、23:05 三次涵蓋原價屋全部 30 個商品分類，"
             "11:05 與 19:05 兩次只擷取 10 個主要 PC 零組件分類。",
    },
    {
        "q": "價格資料的來源是什麼？準確嗎？",
        "a": "資料直接擷取自原價屋（CoolPC）官方線上估價單網頁，未經人工修改。"
             "但價格僅為擷取當下的快照，原價屋可能隨時調整售價，"
             "且部分商品標示「搭機價」或「客訂」，實際成交價需以原價屋官方網站與門市報價為準。",
    },
    {
        "q": "可以查詢某個商品過去的價格嗎？",
        "a": "可以。本站保留自 2026 年 4 月起的所有歷史快照，"
             "使用「歷史比價工具」選擇任意兩個時間點，即可比對該期間內所有商品的漲跌幅度、新上架與下架情況。",
    },
    {
        "q": "「搭機價」「客訂」「限組裝」是什麼意思？",
        "a": "這些是原價屋在商品名稱後標註的購買條件。「搭機價」指需搭配整機組裝才適用的優惠價；"
             "「客訂」指需另行訂貨、非現貨供應；「限組裝」指該商品僅在組裝整機時販售，不單獨零售。",
    },
    {
        "q": "這是原價屋的官方網站嗎？",
        "a": "不是。本站是一個開源的第三方價格記錄工具，與原價屋（欣亞數位股份有限公司）沒有任何隸屬或合作關係，"
             "也不販售任何商品。原始碼公開於 GitHub。",
    },
]


def _parse_timestamp(filename: str) -> Optional[datetime]:
    """從 coolpc_YYYYMMDD_HHMMSS.csv 檔名解析時間 Parse timestamp from filename."""
    m = re.search(r"coolpc_(\d{8})_(\d{6})", filename)
    if not m:
        return None
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=TW_TZ)


def _load_history() -> List[Dict[str, str]]:
    """讀取爬取歷史清單 Load the crawl history list."""
    path = DOCS_DIR / "crawl_history.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _pick_snapshots(history: List[Dict[str, str]]) -> Tuple[Path, Optional[Path]]:
    """挑選要呈現的最新快照與其比較基準。

    優先選 ALL 模式（涵蓋 30 分類），並與前一份「同模式」快照比較，
    避免 MAIN/ALL 分類數不同造成誤判為新增或下架。
    Prefer ALL snapshots (30 categories) and diff against the previous snapshot of the
    SAME mode, so MAIN/ALL category differences aren't mistaken for additions/removals.
    """
    existing = [e for e in history if (OUTPUT_DIR / e["file"]).exists()]
    if not existing:
        raise FileNotFoundError("No CSV snapshots found in output/")

    # history 已按檔名降序（最新在前）History is sorted newest-first by filename
    all_mode = [e for e in existing if e["mode"] == "ALL"]
    chosen = all_mode if len(all_mode) >= 2 else existing

    latest = OUTPUT_DIR / chosen[0]["file"]
    previous = OUTPUT_DIR / chosen[1]["file"] if len(chosen) >= 2 else None
    return latest, previous


def _read_snapshot(path: Path) -> List[Dict[str, str]]:
    """讀取單份 CSV 快照 Read one CSV snapshot."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _to_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _row_key(row: Dict[str, str]) -> Tuple[str, str, str]:
    """商品識別鍵。原價屋有同名但屬於不同子分類的商品（例如同型號螢幕分列
    27 吋與 32 吋區塊，價差達 7 倍），單用 name 比對會互相覆蓋而產生假漲跌。
    Product identity key. CoolPC lists same-named products under different
    subcategories (e.g. one monitor model under both the 27" and 32" blocks, 7x apart
    in price); keying on name alone lets them overwrite each other and fabricates
    price swings."""
    return (row.get("category", ""), row.get("subcategory", ""), row.get("name", ""))


def _occurrence_keys(rows: List[Dict[str, str]]):
    """為每列產生 (識別鍵, 該鍵的第幾次出現)。

    原價屋在同一子分類內也會重複列出同名商品且價格不同（例如同型號螢幕同時掛
    $6,399 與 $19,988），單純以識別鍵建表會讓後者覆蓋前者、配對錯位。改以出現序
    配對：第 n 筆對第 n 筆。
    Yield (identity key, nth occurrence) per row. CoolPC repeats same-named products
    within one subcategory at different prices, so keying alone misaligns the pairing;
    matching by occurrence order pairs the nth with the nth.
    """
    seen = {}
    for row in rows:
        key = _row_key(row)
        n = seen.get(key, 0)
        seen[key] = n + 1
        yield row, (key, n)


def _build_rows(latest: List[Dict[str, str]],
                previous: Optional[List[Dict[str, str]]]) -> List[Dict]:
    """比對兩份快照，組出帶漲跌狀態的商品列表。
    Diff the two snapshots into a product list carrying price-change status."""
    prev_prices = {}
    if previous:
        for row, okey in _occurrence_keys(previous):
            price = _to_int(row.get("price", ""))
            if row.get("name") and price is not None:
                prev_prices[okey] = price

    rows = []
    for row, okey in _occurrence_keys(latest):
        name = row.get("name")
        price = _to_int(row.get("price", ""))
        if not name or price is None:
            continue

        category = row.get("category", "")
        slug = CATEGORY_SLUGS.get(category)
        if not slug:
            continue

        prev_price = prev_prices.get(okey)
        if prev_price is None:
            status, diff, pct = ("new", None, None) if previous else ("same", None, None)
        elif price > prev_price:
            status, diff = "up", price - prev_price
            pct = diff / prev_price * 100
        elif price < prev_price:
            status, diff = "down", price - prev_price
            pct = diff / prev_price * 100
        else:
            status, diff, pct = "same", 0, 0.0

        rows.append({
            "name": name,
            "category": category,
            "slug": slug,
            "subcategory": row.get("subcategory") or "其他",
            "price": price,
            "prev_price": prev_price,
            "remark": row.get("remark") or "",
            "status": status,
            "diff": diff,
            "pct": pct,
        })
    return rows


def _count_removed(latest: List[Dict[str, str]],
                   previous: Optional[List[Dict[str, str]]]) -> int:
    """計算下架商品數 Count products present in previous but gone from latest."""
    if not previous:
        return 0
    latest_keys = {k for r, k in _occurrence_keys(latest) if r.get("name")}
    return sum(1 for r, k in _occurrence_keys(previous)
               if r.get("name") and k not in latest_keys)


def _jsonld(data) -> str:
    """序列化為 JSON-LD。角括號與 & 改用 \\uXXXX escape，
    避免商品名稱中的字元提前終止 <script> 區塊（JSON 解析後仍還原為原字元）。
    Serialize to JSON-LD with angle brackets and & escaped as \\uXXXX, so a product
    name can't break out of the <script> block. JSON parsing restores them."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return (text.replace("<", "\\u003c")
                .replace(">", "\\u003e")
                .replace("&", "\\u0026"))


def _render_index(env, rows, meta, categories) -> str:
    up = [r for r in rows if r["status"] == "up"]
    down = [r for r in rows if r["status"] == "down"]
    stats = {
        "total": len(rows),
        "up": len(up),
        "down": len(down),
        "new": sum(1 for r in rows if r["status"] == "new"),
        "removed": meta["removed"],
        "changed": len(up) + len(down) + sum(1 for r in rows if r["status"] == "new"),
    }

    dataset_desc = (
        "自 %s 起，每日 5 次擷取原價屋線上估價單的商品名稱、分類與價格，"
        "以 CSV 格式保存的歷史價格快照資料集。" % meta["history_start"]
    )

    graph = [
        {
            "@type": "WebSite",
            "@id": BASE_URL + "#website",
            "name": "原價屋價格追蹤",
            "alternateName": "CoolPC Price Tracker",
            "url": BASE_URL,
            "inLanguage": "zh-TW",
            "description": "記錄原價屋（CoolPC）線上估價單電腦零組件的每日價格與歷史漲跌。",
        },
        {
            "@type": "Dataset",
            "@id": BASE_URL + "#dataset",
            "name": "原價屋電腦零組件歷史價格資料集",
            "description": dataset_desc,
            "url": BASE_URL,
            "inLanguage": "zh-TW",
            "isAccessibleForFree": True,
            "license": "https://github.com/TroyWhiteTW/coolpc-crawler/blob/main/LICENSE",
            "creator": {
                "@type": "Person",
                "name": "TroyWhiteTW",
                "url": "https://github.com/TroyWhiteTW",
            },
            "temporalCoverage": "%s/%s" % (meta["history_start"], meta["updated_date"]),
            "dateModified": meta["updated_iso"],
            "measurementTechnique": "HTML scraping of the CoolPC online quotation page",
            "variableMeasured": [
                {"@type": "PropertyValue", "name": "price", "unitCode": "TWD",
                 "description": "商品標示售價（新台幣）"},
                {"@type": "PropertyValue", "name": "category",
                 "description": "商品分類"},
                {"@type": "PropertyValue", "name": "scraped_at",
                 "description": "擷取時間"},
            ],
            "keywords": ["原價屋", "CoolPC", "電腦零組件", "價格追蹤", "歷史價格",
                         "CPU", "顯示卡", "SSD", "記憶體", "台灣"],
            "distribution": [{
                "@type": "DataDownload",
                "encodingFormat": "text/csv",
                "contentUrl": BASE_URL + "output/" + meta["latest_file"],
            }],
        },
        {
            "@type": "FAQPage",
            "@id": BASE_URL + "#faq",
            "mainEntity": [
                {"@type": "Question", "name": item["q"],
                 "acceptedAnswer": {"@type": "Answer", "text": item["a"]}}
                for item in FAQ
            ],
        },
    ]

    description = (
        "每日追蹤原價屋（CoolPC）%d 項電腦零組件報價，涵蓋 CPU、顯示卡、SSD、記憶體等 %d 個分類，"
        "提供歷史價格快照比對與漲跌查詢。開源、免費、每日自動更新。"
        % (stats["total"], len(categories))
    )

    return env.get_template("index.html").render(
        page_title="原價屋價格追蹤 — 電腦零組件每日價格與歷史漲跌 | CoolPC Price Tracker",
        description=description,
        canonical=BASE_URL,
        base_url=BASE_URL,
        root="",
        nav_active="home",
        nav_categories=categories,
        categories=categories,
        stats=stats,
        top_down=sorted([r for r in down if r["pct"] is not None],
                        key=lambda r: r["pct"])[:TOP_N],
        top_up=sorted([r for r in up if r["pct"] is not None],
                      key=lambda r: r["pct"], reverse=True)[:TOP_N],
        faq=FAQ,
        jsonld=_jsonld({"@context": "https://schema.org", "@graph": graph}),
        **meta
    )


def _render_category(env, cat, rows, meta, categories) -> str:
    items = [r for r in rows if r["slug"] == cat["slug"]]
    prices = [r["price"] for r in items]

    movers = sorted(
        [r for r in items if r["status"] in ("up", "down") and r["pct"] is not None],
        key=lambda r: abs(r["pct"]), reverse=True
    )[:CAT_MOVERS_N]

    # 依子分類分組，保留 CSV 原始順序 Group by subcategory, preserving CSV order
    grouped = {}
    for r in items:
        grouped.setdefault(r["subcategory"], []).append(r)
    subcategories = [{"name": k, "products": v} for k, v in grouped.items()]

    url = BASE_URL + "c/" + cat["slug"] + ".html"
    list_desc = "原價屋 %s 的最新報價列表，共 %d 項商品。" % (cat["name"], len(items))
    graph = [
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1,
                 "name": "原價屋價格追蹤", "item": BASE_URL},
                {"@type": "ListItem", "position": 2,
                 "name": cat["name"], "item": url},
            ],
        },
        {
            "@type": "ItemList",
            "name": cat["name"] + " 價格列表",
            "description": list_desc,
            "url": url,
            "numberOfItems": len(items),
            "itemListOrder": "https://schema.org/ItemListUnordered",
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": r["name"]}
                for i, r in enumerate(items[:ITEMLIST_MAX])
            ],
        },
    ]

    page_title = ("%s 價格列表 — 原價屋 %d 項商品即時報價 | CoolPC Price Tracker"
                  % (cat["name"], len(items)))
    description = (
        "原價屋（CoolPC）%s報價一覽，共 %d 項商品，價格 $%s 起。%s 更新，含近期漲跌異動。"
        % (cat["blurb"], len(items), format(min(prices), ","), meta["updated_display"])
    )

    return env.get_template("category.html").render(
        page_title=page_title,
        description=description,
        canonical=url,
        base_url=BASE_URL,
        root="../",
        nav_active=cat["slug"],
        nav_categories=categories,
        category=cat,
        items=items,
        movers=movers,
        subcategories=subcategories,
        price_min=min(prices),
        price_max=max(prices),
        price_median=int(statistics.median(prices)),
        cat_stats={
            "up": sum(1 for r in items if r["status"] == "up"),
            "down": sum(1 for r in items if r["status"] == "down"),
            "new": sum(1 for r in items if r["status"] == "new"),
        },
        jsonld=_jsonld({"@context": "https://schema.org", "@graph": graph}),
        **meta
    )


def _write_sitemap(categories, updated_date: str) -> None:
    urls = [(BASE_URL, "daily", "1.0"), (BASE_URL + "compare.html", "daily", "0.8")]
    urls += [(BASE_URL + "c/" + c["slug"] + ".html", "daily", "0.9") for c in categories]

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, freq, priority in urls:
        lines += ["  <url>",
                  "    <loc>%s</loc>" % loc,
                  "    <lastmod>%s</lastmod>" % updated_date,
                  "    <changefreq>%s</changefreq>" % freq,
                  "    <priority>%s</priority>" % priority,
                  "  </url>"]
    lines.append("</urlset>")
    (SITE_DIR / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_robots() -> None:
    """產生 robots.txt。GitHub Pages project site 下不生效，綁定自訂網域後才會被讀取。
    Emit robots.txt. Ignored under a GitHub Pages project path; effective once a custom
    domain is attached."""
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "# AI／回答引擎爬蟲：明確允許，讓價格資料可被摘要引用\n"
        "# AI and answer-engine crawlers: explicitly allowed so prices can be cited\n"
        "User-agent: GPTBot\n"
        "Allow: /\n"
        "\n"
        "User-agent: ClaudeBot\n"
        "Allow: /\n"
        "\n"
        "User-agent: PerplexityBot\n"
        "Allow: /\n"
        "\n"
        "User-agent: Google-Extended\n"
        "Allow: /\n"
        "\n"
        "Sitemap: %ssitemap.xml\n" % BASE_URL
    )
    (SITE_DIR / "robots.txt").write_text(content, encoding="utf-8")


def _write_legacy_redirect() -> None:
    """保留舊網址 /docs/index.html，轉址到 /compare.html。

    改用 Actions 部署前，比價工具的網址是 /docs/index.html，該網址已被搜尋引擎索引。
    直接消失會變成 404，因此留一頁 canonical 指向新位置的轉址頁，讓既有排名合併過去。
    GitHub Pages 無法送 301，只能用 canonical + meta refresh。
    Keep the old /docs/index.html URL alive, redirecting to /compare.html. That URL is
    already indexed; dropping it would 404. GitHub Pages can't emit a 301, so this uses
    canonical + meta refresh to consolidate ranking signals onto the new location.
    """
    legacy_dir = SITE_DIR / "docs"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    html = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <title>歷史比價工具 — 原價屋價格追蹤</title>
  <link rel="canonical" href="%(base)scompare.html">
  <meta http-equiv="refresh" content="0; url=../compare.html">
  <script>window.location.replace("../compare.html");</script>
</head>
<body>
  <p>此頁已移至 <a href="../compare.html">歷史比價工具</a>。</p>
</body>
</html>
""" % {"base": BASE_URL}
    (legacy_dir / "index.html").write_text(html, encoding="utf-8")


def build(args) -> None:
    """產生靜態站台到 _site/ Build the static site into _site/."""
    history = _load_history()
    latest_path, prev_path = _pick_snapshots(history)
    print("Latest snapshot: %s" % latest_path.name)
    print("Compare against: %s" % (prev_path.name if prev_path else "(none)"))

    latest_raw = _read_snapshot(latest_path)
    prev_raw = _read_snapshot(prev_path) if prev_path else None
    rows = _build_rows(latest_raw, prev_raw)
    if not rows:
        raise ValueError("No usable rows parsed from %s" % latest_path)

    updated = _parse_timestamp(latest_path.name)
    prev_ts = _parse_timestamp(prev_path.name) if prev_path else None
    oldest = min((t for t in (_parse_timestamp(e["file"]) for e in history) if t),
                 default=updated)

    # 只保留商品數達門檻的分類 Keep only categories meeting the item-count threshold
    counts = {}
    for r in rows:
        counts[r["slug"]] = counts.get(r["slug"], 0) + 1

    categories = []
    for name, slug in CATEGORY_SLUGS.items():
        if counts.get(slug, 0) < MIN_ITEMS_PER_PAGE:
            continue
        cat_rows = [r for r in rows if r["slug"] == slug]
        categories.append({
            "name": name,
            "slug": slug,
            "short": CATEGORY_SHORT.get(slug, name),
            "blurb": CATEGORY_BLURBS.get(slug, name),
            "count": counts[slug],
            "up": sum(1 for r in cat_rows if r["status"] == "up"),
            "down": sum(1 for r in cat_rows if r["status"] == "down"),
        })

    # 主要 PC 零組件依固定順序排前面，周邊分類接在後面依商品數遞減
    # Main PC components first in a fixed order, peripherals after by item count
    categories.sort(key=lambda c: (
        PRIMARY_SLUGS.index(c["slug"]) if c["slug"] in PRIMARY_SLUGS else len(PRIMARY_SLUGS),
        -c["count"],
    ))

    meta = {
        "updated_iso": updated.isoformat(),
        "updated_display": updated.strftime("%Y-%m-%d %H:%M"),
        "updated_date": updated.strftime("%Y-%m-%d"),
        "compare_from_display": prev_ts.strftime("%Y-%m-%d %H:%M") if prev_ts else "—",
        "history_start": oldest.strftime("%Y-%m-%d"),
        "snapshot_count": len(history),
        "latest_file": latest_path.name,
        "removed": _count_removed(latest_raw, prev_raw),
    }

    # 準備輸出目錄 Prepare output directory
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    (SITE_DIR / "c").mkdir(parents=True)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    (SITE_DIR / "index.html").write_text(
        _render_index(env, rows, meta, categories), encoding="utf-8")
    for cat in categories:
        (SITE_DIR / "c" / (cat["slug"] + ".html")).write_text(
            _render_category(env, cat, rows, meta, categories), encoding="utf-8")

    _write_sitemap(categories, meta["updated_date"])
    _write_robots()
    _write_legacy_redirect()

    # 複製既有前端資源 Copy existing frontend assets
    for asset in ("compare.html", "app.js", "style.css", "pages.css",
                  "crawl_history.json", "og-image.png", "favicon.svg"):
        src = DOCS_DIR / asset
        if src.exists():
            shutil.copy2(src, SITE_DIR / asset)

    if getattr(args, "with_data", False):
        _copy_snapshots(history, updated, getattr(args, "data_months", 0))

    print("Built %d category pages + index into %s/" % (len(categories), SITE_DIR))


def _copy_snapshots(history: List[Dict[str, str]], newest: datetime,
                    data_months: int) -> None:
    """複製 CSV 快照到 _site/output/，供比價工具讀取。

    data_months > 0 時只發布最近 N 個月的快照，並同步裁切 crawl_history.json，
    避免比價工具的下拉選單指向未發布的檔案而 404。
    repo 內的 output/ 一律保持完整，這裡只決定「對外發布哪些」。
    Copy CSV snapshots into _site/output/ for the comparison tool. With data_months > 0
    only the last N months are published, and crawl_history.json is trimmed to match so
    the tool's dropdown never points at a file that wasn't deployed. The repo's output/
    is always left intact; this only controls what gets published.
    """
    dest = SITE_DIR / "output"
    dest.mkdir(parents=True, exist_ok=True)

    cutoff = None
    if data_months > 0:
        cutoff = newest - timedelta(days=30 * data_months)

    published, total_bytes = [], 0
    for entry in history:
        src = OUTPUT_DIR / entry["file"]
        if not src.exists():
            continue
        if cutoff is not None:
            ts = _parse_timestamp(entry["file"])
            if ts is None or ts < cutoff:
                continue
        shutil.copy2(src, dest / entry["file"])
        total_bytes += src.stat().st_size
        published.append(entry)

    # 讓比價工具只看得到實際發布的快照 Keep the tool in sync with what shipped
    (SITE_DIR / "crawl_history.json").write_text(
        json.dumps(published, indent=2), encoding="utf-8")

    skipped = len(history) - len(published)
    print("Published %d CSV snapshots (%.0f MB)%s"
          % (len(published), total_bytes / 1024 / 1024,
             ", skipped %d older than %d month(s)" % (skipped, data_months)
             if skipped else ""))
