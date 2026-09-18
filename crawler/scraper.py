import re
import sys
import time
from typing import List, Optional, Set

import requests
from bs4 import BeautifulSoup, NavigableString

from crawler.models import Product

URL = "https://www.coolpc.com.tw/evaluate.php"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)
# 重試次數與 backoff 基數：等待秒數 = BACKOFF_BASE ** attempt（3s、9s）
# Retry attempts and backoff base: wait = BACKOFF_BASE ** attempt (3s, 9s)
MAX_ATTEMPTS = 3
BACKOFF_BASE = 3.0
# option 文字中的價格，如 "$1,234" / Price inside option text, e.g. "$1,234"
PRICE_RE = re.compile(r"\$(\d[\d,]*)")
# 備註標記正面表列（含外圍符號），新增類型直接加入此列表
# Remark tag whitelist (with delimiters); add new tag patterns here
REMARK_PATTERNS = [
    r"~搭機價~",
    r"~限整機~",
    r"~限組裝~",
    r"【限組裝】",
    r"\[限組裝\]",
    r"\[限搭機\]",
    r"【客訂】",
    r"【訂】",
]
REMARK_RE = re.compile("|".join(REMARK_PATTERNS))
# 取 tag 文字時要去掉的外圍符號 / Delimiters stripped when extracting the tag text
REMARK_DELIMS = "~【】[]"
# 商品 select 的 name 為 n1～n30 / Product selects are named n1..n30
SELECT_NAME_RE = re.compile(r"^n(\d+)$")
# 正常頁面必含第一個 select 的 `name=n1`（原價屋屬性不加引號），缺少即視為內容異常
# Healthy pages contain the first select's `name=n1` (CoolPC leaves attributes unquoted);
# a missing sentinel means bad content (maintenance page, bot challenge, etc.)
CONTENT_SENTINEL = "name=n1"
# html.parser 遇到無法組成合法數字實體的 `&#` 會停止解析，其後整份文件變成純文字
# html.parser stops parsing at a `&#` that doesn't form a valid numeric charref and
# turns the rest of the document into plain text
BARE_CHARREF_RE = re.compile(r"&#(?!(?:[0-9]+|[xX][0-9a-fA-F]+)[^0-9a-fA-F])")


class EmptyContentError(Exception):
    """HTTP 成功但 HTML 缺少預期結構（維護頁、反爬蟲挑戰頁等）。
    HTTP succeeded but the HTML lacks the expected structure (maintenance / bot-challenge page)."""

    def __init__(self, html: str):
        super().__init__("Response missing expected <select> structure")
        self.html = html


def fetch_page() -> str:
    """抓取估價頁 HTML，HTTP 錯誤或內容異常時最多重試 MAX_ATTEMPTS 次。
    Fetch the estimate page HTML, retrying up to MAX_ATTEMPTS on HTTP errors or bad content."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=30)
            resp.raise_for_status()
            resp.encoding = "big5hkscs"
            text = resp.text
            if CONTENT_SENTINEL not in text:
                raise EmptyContentError(text)
            return text
        except (requests.RequestException, EmptyContentError) as exc:
            last_exc = exc
            if attempt < MAX_ATTEMPTS:
                wait = BACKOFF_BASE ** attempt
                print(
                    f"Fetch attempt {attempt} failed: {exc}. Retrying in {wait:.1f}s...",
                    file=sys.stderr,
                )
                time.sleep(wait)
    # 全部失敗，重拋最後一次例外 / All attempts failed, re-raise the last exception
    assert last_exc is not None
    raise last_exc


def _sanitize_html(html: str) -> str:
    """把會讓 html.parser 截斷的裸露 `&#` 轉為 `&amp;#`。2026-07-11 公告跑馬燈含此字元，
    整頁被解析成 0 筆商品。
    Escape bare `&#` that would truncate html.parser. On 2026-07-11 a marquee notice
    containing it made the whole page parse to zero products."""
    return BARE_CHARREF_RE.sub("&amp;#", html)


def _get_first_text(tag) -> str:
    """取得 tag 的第一個直接文字節點，跳過子元素。
    Return the tag's first direct text node, skipping child elements."""
    for child in tag.children:
        if isinstance(child, NavigableString):
            text = child.strip()
            if text:
                return text
    return ""


def parse_products(
        html: str,
        category_filter: Optional[Set[str]] = None,
) -> List[Product]:
    """解析估價頁 HTML 為商品列表。category_filter 為要保留的 select name 集合
    （如 {"n4", "n5"}），None 表示全部保留。
    Parse the estimate page into products. category_filter is the set of select names
    to keep (e.g. {"n4", "n5"}); None keeps every category."""
    soup = BeautifulSoup(_sanitize_html(html), "html.parser")
    products: List[Product] = []

    # 每個 <td class="t"> 對應一個分類，分類名稱是它的第一個文字節點
    # Each <td class="t"> is one category; the name is the td's first text node
    tds_t = soup.find_all("td", class_="t")

    for td in tds_t:
        category_name = _get_first_text(td)
        if not category_name:
            continue

        # 原始 HTML 的 td 未關閉，select 落在 td 同層，需從 parent 找
        # TDs are never closed in the source, so the select is a sibling; search from the parent
        parent = td.parent
        if not parent:
            continue
        select = parent.find("select", attrs={"name": SELECT_NAME_RE})
        if not select:
            continue

        select_name = select.get("name", "")
        if category_filter is not None and select_name not in category_filter:
            continue

        # optgroup 是子分類，option 是商品；disabled option 為說明文字
        # optgroup = subcategory, option = product; disabled options are info text
        for optgroup in select.find_all("optgroup"):
            subcategory = str(optgroup.get("label", "")).strip()
            if not subcategory:
                continue

            for opt in optgroup.find_all("option", recursive=False):
                if opt.has_attr("disabled"):
                    continue

                text = opt.get_text(strip=True)
                if not text or text.startswith("---"):
                    continue

                price_match = PRICE_RE.search(text)
                if not price_match:
                    continue

                price = int(price_match.group(1).replace(",", ""))

                # 價格符號之前的文字即商品名稱 / Text before the price is the product name
                name = PRICE_RE.split(text)[0].rstrip(", ")

                # 備註：整段匹配後去掉外圍符號、去重，再從名稱移除
                # Remarks: match whole tags, strip delimiters, dedupe, then remove from the name
                seen = set()
                remarks = []
                for match in REMARK_RE.finditer(name):
                    tag = match.group(0).strip(REMARK_DELIMS)
                    if tag not in seen:
                        seen.add(tag)
                        remarks.append(tag)
                remark = "/".join(remarks)
                name = REMARK_RE.sub("", name).strip()

                products.append(
                    Product(
                        category=category_name,
                        subcategory=subcategory,
                        name=name,
                        price=price,
                        remark=remark,
                    )
                )

    return products
