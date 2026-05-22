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
# 重試設定：總嘗試次數與 backoff 起始秒數（指數倍增）
# Retry config: total attempts and initial backoff seconds (exponential)
MAX_ATTEMPTS = 3
BACKOFF_BASE = 3.0
PRICE_RE = re.compile(r"\$(\d[\d,]*)")
# 備註標記正面表列：含外圍符號的整段 pattern，需要新增時在此列表添加即可
# Remark patterns whitelist (with delimiters) — add new patterns here as needed
REMARK_PATTERNS = [
    r"~搭機價~",
    r"~限整機~",
    r"~限組裝~",
    r"【限組裝】",
    r"【客訂】",
    r"\[限組裝\]",
    r"\[限搭機\]",
]
REMARK_RE = re.compile("|".join(REMARK_PATTERNS))
# 提取 tag 文字時要去掉的外圍符號 / Delimiter chars to strip when extracting tag text
REMARK_DELIMS = "~【】[]"
SELECT_NAME_RE = re.compile(r"^n(\d+)$")
# 正常頁面第一個 select 的 name 屬性為 n1（原價屋採無引號 attribute，全大寫 SELECT 標籤）
# 缺少此子字串視為內容失敗（維護頁/挑戰頁等）
# Healthy pages contain `name=n1` (CoolPC uses unquoted attributes + uppercase SELECT tags);
# missing this substring means bad content (maintenance page / bot challenge / etc.)
CONTENT_SENTINEL = "name=n1"


class EmptyContentError(Exception):
    """HTTP 成功但 HTML 缺少預期結構（例如維護頁、反爬蟲挑戰頁）。
    HTTP succeeded but HTML lacks expected structure (e.g. maintenance / bot-challenge page)."""

    def __init__(self, html: str):
        super().__init__("Response missing expected <select> structure")
        self.html = html


def fetch_page() -> str:
    """抓取原價屋估價頁面，回傳 HTML 字串。失敗時最多重試 MAX_ATTEMPTS 次。
    Fetch CoolPC estimate page and return HTML string. Retry up to MAX_ATTEMPTS on failure."""
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
                # 指數 backoff：3s, 9s, ...
                # Exponential backoff
                wait = BACKOFF_BASE ** attempt
                print(
                    f"Fetch attempt {attempt} failed: {exc}. Retrying in {wait:.1f}s...",
                    file=sys.stderr,
                )
                time.sleep(wait)
    # 所有嘗試皆失敗，重新拋出最後一次的例外 / All attempts failed, re-raise the last exception
    assert last_exc is not None
    raise last_exc


def _get_first_text(tag) -> str:
    """取得 tag 的第一個直接文字節點（跳過子元素）。
    Return the first direct text node of a tag, skipping child elements."""
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
    """解析 HTML，回傳商品列表。

    Args:
        html: 網頁 HTML 字串。
        category_filter: 要保留的 select name 集合 (如 {"n4", "n5"})。
                         None 表示全部保留。
    """
    soup = BeautifulSoup(html, "html.parser")
    products: List[Product] = []

    # 找所有 class=t 的 td，每個對應一個分類
    tds_t = soup.find_all("td", class_="t")

    for td in tds_t:
        # 分類名稱是 td 的第一個文字節點
        category_name = _get_first_text(td)
        if not category_name:
            continue

        # 從 td 的 parent 找 select (因為 HTML 結構破碎，select 可能在同層)
        # Search for <select> from td's parent (HTML is malformed, select may be at the same level)
        parent = td.parent
        if not parent:
            continue
        select = parent.find("select", attrs={"name": SELECT_NAME_RE})
        if not select:
            continue

        select_name = select.get("name", "")

        # 過濾分類
        if category_filter is not None and select_name not in category_filter:
            continue

        # 遍歷 optgroup → option
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

                # 從價格符號前截取商品名稱 Extract product name before price
                name = PRICE_RE.split(text)[0].rstrip(", ")

                # 備註標記：匹配整段（含外圍符號）後 strip 取 tag、去重，再從 name 移除
                # Remark tags: match whole segment (with delimiters), strip to tag, dedupe, remove from name
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
