# coolpc-crawler — 原價屋價格爬蟲與歷史比價工具

原價屋（CoolPC）商品價格爬蟲，定期爬取[原價屋線上估價](https://www.coolpc.com.tw/evaluate.php)的電腦零組件價格資料，分類整理後輸出 CSV，並產生可被搜尋引擎索引的靜態價格頁與歷史比價工具，追蹤漲跌變化。

[English version below ↓](#english)

---

## 主要功能

1. **價格爬取** — 爬取原價屋線上估價的商品價格，依分類整理後輸出 CSV
2. **靜態價格頁** — 由最新快照產生總覽首頁與各分類價格頁，商品名稱與價格直接寫在 HTML 中
3. **歷史價格對比** — 任選兩份快照比對漲跌、新上架與下架（詳見下方「網站」）

## 技術棧

- Python 3.9（`pyproject.toml` 鎖定 `==3.9.*`）。以 [uv](https://github.com/astral-sh/uv) 執行時，`.python-version` 會讓 uv 自動下載 **PyPy 3.9** 建立環境，CI 亦以 PyPy 執行；改用 CPython 3.9 + pip 亦可
- beautifulsoup4（HTML 解析，使用內建 `html.parser`）/ requests（HTTP 請求，內建 retry 與指數 backoff）/ jinja2（靜態頁面樣板）
- 目標網頁宣告為 Big5，但部分字元需以 `big5hkscs`（Big5 超集）解碼避免亂碼；所有資料在初始 HTML 中，無需 JS 渲染

## 安裝

以下以 uv 為例（亦可直接以原生 Python + pip 執行）：

```bash
uv sync
```

## 使用方式

以下以 uv 執行環境為例（若使用 pip，將 `uv run` 替換為直接執行即可）：

```bash
uv run python main.py crawl            # 只爬取 10 個主要零組件分類
uv run python main.py crawl --all      # 爬取全部 30 個分類
uv run python main.py crawl -o out.csv # 指定輸出路徑（不會更新爬取歷史）

uv run python main.py build            # 由最新 ALL 快照產生靜態網站到 _site/
```

預設輸出至 `output/coolpc_YYYYMMDD_HHMMSS.csv`，並把檔名與模式（MAIN／ALL）寫入 `docs/crawl_history.json`。

## 分類篩選

預設只抓取以下 10 個主要 PC 零組件（select name 定義在 `crawler/models.py` 的 `MAIN_CATEGORIES`，名稱即原價屋頁面上的分類標題）：

> 處理器 CPU、主機板 MB、記憶體 RAM、固態硬碟 M.2｜SSD、2.5/3.5 傳統內接硬碟HDD、散熱器｜散熱墊｜散熱膏、封閉式｜開放式水冷、顯示卡VGA、CASE 機殼(+電源)、電源供應器

使用 `--all` 可抓取全部 30 個分類。

## CSV 欄位

`category, subcategory, name, price, remark, scraped_at`

| 欄位 | 說明 |
|---|---|
| `category` | 分類名稱 |
| `subcategory` | 子分類名稱 |
| `name` | 商品名稱 |
| `price` | 價格（NTD）|
| `remark` | 備註標記，如「搭機價」「客訂」「限組裝」，多個用 `/` 串接 |
| `scraped_at` | 抓取時間（本次執行開始抓取的時間，與檔名時間戳相同） |

> 備註標記為正面表列，定義於 `crawler/scraper.py` 的 `REMARK_PATTERNS`，新增類型直接加入列表即可。

## 專案結構

```
├── main.py                 # CLI 入口（argparse 子命令：crawl / build）
├── crawler/
│   ├── models.py           # Product dataclass + 分類設定（MAIN_CATEGORIES、slug、說明、短名）
│   ├── scraper.py          # fetch_page() + parse_products()
│   └── builder.py          # 靜態頁面產生器（最新 ALL CSV 對前一日 ALL CSV → HTML）
├── templates/              # Jinja2 樣板
│   ├── base.html           # 共用 head／導覽／頁尾／JSON-LD
│   ├── index.html          # 總覽首頁
│   └── category.html       # 分類價格頁
├── output/                 # CSV 輸出目錄（已納入版控）
│   └── debug/              # 爬取失敗時的 HTML dump（最多保留 10 份）
├── docs/                   # 前端原始資源（非發布目錄）
│   ├── compare.html        # 歷史比價工具（SPA）
│   ├── style.css / pages.css
│   ├── app.js / theme.js   # 比價工具邏輯／主題開關
│   ├── og-image.png / favicon.svg
│   └── crawl_history.json  # 爬取歷史清單（自動產生）
├── _site/                  # build 產物（gitignored，Actions 部署來源）
└── pyproject.toml
```

## 自動排程

透過 GitHub Actions 自動定時爬取，無需手動執行。

| 台灣時間 | 模式 | 說明 |
|---|---|---|
| 07:05 / 15:05 / 23:05 | `--all` (ALL) | 全部 30 個分類 |
| 11:05 / 19:05 | default (MAIN) | 10 個主要零組件分類 |

> ⏱ cron 偏移 5 分鐘以錯開整點高峰，減少 GitHub Actions 排程延遲。

- commit 訊息格式：
  - 成功：`crawl: (cron 09:05) 2026-04-18 09:07 ALL`
  - 失敗：`crawl-fail: (cron 09:05) 2026-04-18 09:07 ALL`
- 支援從 GitHub Actions 頁面手動觸發，可選 MAIN 或 ALL

## 失敗處理

爬蟲在以下兩種情境會自我標記為失敗，產生 `crawl-fail:` 前綴的 commit，不寫 CSV、不更新爬取歷史，但仍會 commit 一份 debug HTML 供事後檢視：

1. **內容異常** — HTTP 200 但 HTML 缺少 `name=n1` 子字串（第一個 `<SELECT>` 的 `name` 屬性，原價屋使用無引號 attribute），通常是維護頁、反爬蟲挑戰頁或 CDN 攔截頁。`fetch_page` 會以指數 backoff (3s, 9s) 重試 3 次後認輸。
2. **解析空集** — HTML 通過 sentinel 檢查但 `parse_products` 回傳 0 筆，可能是原價屋改版或解析邏輯有 bug。2026-07-11 的失敗即屬此類：公告跑馬燈含裸露的 `&#`，Python 內建 `html.parser` 遇到無法組成數字實體的 `&#` 會停止解析、其後整頁變成純文字；現已在解析前把這類 `&#` 轉義為 `&amp;#`。

debug HTML 位置：`output/debug/coolpc_YYYYMMDD_HHMMSS.html`（時間戳對齊原本 CSV 命名規則），只保留最近 10 份，較舊的會在下次 dump 時自動刪除。

> 注意：HTTP 層完全失敗（三次 retry 都連不上原價屋）仍會讓 Action 紅燈、不產生 commit，這跟「拿到壞內容」是不同的失敗模式。

## 網站

透過 GitHub Pages 發布，由 `main.py build` 在每次爬取後重新產生靜態頁面。

| 頁面 | 網址 | 說明 |
|---|---|---|
| 總覽首頁 | `/` | 最新報價統計、漲跌幅 TOP 20、分類索引、常見問題 |
| 分類頁 | `/c/<slug>.html` | 單一分類完整價格表，依子分類分組；商品數達 5 項的分類各一頁（目前 30 頁） |
| 歷史比價工具 | `/compare.html` | 任選兩份快照比對（client-side 渲染的 SPA） |

首頁與分類頁是**建置期產生的靜態 HTML**，商品名稱與價格直接寫在原始碼中，不依賴 JavaScript
即可被搜尋引擎與 AI 爬蟲讀取；比價工具維持 client-side 渲染。

- 首頁與分類頁以**最新一份 ALL 快照**為準，並與至少 20 小時前（通常是前一日同時段）的 ALL 快照比較漲跌；MAIN 快照只會出現在比價工具，因此 11:05 與 19:05 的爬取不會更新首頁的「更新於」時間
- build 另會產生 `sitemap.xml`、`robots.txt`（明確允許主要 AI 爬蟲）與舊網址 `/docs/index.html` 的轉址頁；所有頁面皆含 GA4 追蹤碼
- 右上角開關可切換淺色／深色主題，預設深色，選擇存在瀏覽器的 localStorage

### 部署

Pages 的 Source 需設為 **GitHub Actions**（不是 branch）。workflow 會在爬取後依序執行
`main.py build --with-data`、上傳 `_site/` 為 Pages artifact，再由 `deploy` job 發布。

```bash
uv run python main.py build                      # 只產生 HTML（快速預覽）
uv run python main.py build --with-data          # 一併複製全部 CSV（比價工具需要）
uv run python main.py build --with-data --data-months 6   # 只發布近 6 個月的快照
```

> `--data-months` 只影響「發布哪些快照」（以 30 天為一個月計算，需搭配 `--with-data`），repo 的 `output/` 永遠保持完整。
> 需要控制 Pages 站台體積時（上限 1 GB）調整此參數，並會同步裁切 `_site/crawl_history.json`，
> 避免比價工具的下拉選單指向未發布的檔案。目前 workflow 未帶此參數，發布全部快照。

本機預覽：

```bash
uv run python main.py build --with-data --data-months 1
uv run python -m http.server 8000 --directory _site
```

## 已知問題

1. 舊價格（A 側）預設選擇當月第 6 筆資料，若當月不足 6 筆則選最後一筆，不會自動回推至前一個月
2. **商品名稱微調會被誤判為新增/下架** — 比對 key 包含商品名稱完整字串，若原價屋微調名稱（如 `WIN11 PRO` → `WIN11 Pro`、空格數量、全形/半形變動），同一個商品會被拆成一筆 ✕ 下架 + 一筆 ✦ 新增。crawler 忠實記錄原文不做正規化，這類雜訊只能在閱讀對比結果時自行辨識。

### 商品識別鍵

比對兩份快照時，商品的識別鍵為 **`(分類, 子分類, 名稱, 該組合的第幾次出現)`**，實作於
`crawler/builder.py` 的 `_row_key()` / `_occurrence_keys()` 與 `docs/app.js` 的
`rowKey()` / `buildKeyedMap()`。

之所以不能只用商品名稱，是因為原價屋的資料有兩種重複：

- **跨子分類同名** — 同一型號螢幕同時列在「27 吋」與「32 吋 4K」區塊，價格相差 7 倍
- **同子分類內同名** — 同一台螢幕在同一區塊出現兩次，掛著兩個不同價格

單用名稱建表時後者會覆蓋前者，導致兩份快照價格明明完全沒變，卻算出 −86% 的假降價。
以 2026-09-18 的 ALL 快照為例，同名商品共 100 組、201 列，其中同子分類內重複 9 組、18 列。

## License

MIT

---

## English

CoolPC price crawler and historical price comparison tool. Periodically scrapes PC component pricing data from [CoolPC Online Estimator](https://www.coolpc.com.tw/evaluate.php), exports structured CSV files, generates crawlable static price pages, and provides a web-based price diff viewer to track price changes over time.

## Features

1. **Price Scraping** — Crawl CoolPC product prices by category and export to CSV
2. **Static Price Pages** — Build an overview homepage and one page per category from the newest snapshot, with product names and prices written directly into the HTML
3. **Historical Price Comparison** — Pick any two snapshots and compare price changes, new listings and removals (see "Website" below)

## Tech Stack

- Python 3.9 (`pyproject.toml` pins `==3.9.*`). When run with [uv](https://github.com/astral-sh/uv), `.python-version` makes uv download **PyPy 3.9** for the environment, and CI runs on PyPy as well; CPython 3.9 + pip also works
- beautifulsoup4 (HTML parsing with the built-in `html.parser`) / requests (HTTP, with retry and exponential backoff) / jinja2 (static page templates)
- Target page declares Big5, but decoding with `big5hkscs` (a Big5 superset) is required to avoid garbled characters; all data lives in the initial HTML — no JS rendering required

## Installation

Examples below use uv (also works with vanilla Python + pip):

```bash
uv sync
```

## Usage

Examples below use uv (if using pip, replace `uv run` with `python` directly):

```bash
uv run python main.py crawl            # Only scrape 10 main component categories
uv run python main.py crawl --all      # Scrape all 30 categories
uv run python main.py crawl -o out.csv # Specify output path (crawl history is not updated)

uv run python main.py build            # Build the static site into _site/ from the newest ALL snapshot
```

Output defaults to `output/coolpc_YYYYMMDD_HHMMSS.csv`, and the filename plus mode (MAIN / ALL) is appended to `docs/crawl_history.json`.

## Category Filtering

By default, only the following 10 main PC component categories are scraped (select names are defined in `MAIN_CATEGORIES` in `crawler/models.py`; the labels are CoolPC's own category headings):

> 處理器 CPU, 主機板 MB, 記憶體 RAM, 固態硬碟 M.2｜SSD, 2.5/3.5 傳統內接硬碟HDD, 散熱器｜散熱墊｜散熱膏, 封閉式｜開放式水冷, 顯示卡VGA, CASE 機殼(+電源), 電源供應器
> (CPU, motherboard, RAM, SSD, HDD, CPU cooler, liquid cooling, GPU, case, PSU)

Use `--all` to scrape all 30 categories.

## CSV Fields

`category, subcategory, name, price, remark, scraped_at`

| Field | Description |
|---|---|
| `category` | Category name |
| `subcategory` | Subcategory name |
| `name` | Product name |
| `price` | Price in NTD |
| `remark` | Remark tags (e.g. 搭機價 bundle price, 客訂 special order, 限組裝 build-only), joined by `/` |
| `scraped_at` | Scrape timestamp (when this run started fetching; same as the filename timestamp) |

> Remark tags are explicitly whitelisted in `REMARK_PATTERNS` (in `crawler/scraper.py`); extend the list to add new tag patterns.

## Project Structure

```
├── main.py                 # CLI entry point (argparse subcommands: crawl / build)
├── crawler/
│   ├── models.py           # Product dataclass + category config (MAIN_CATEGORIES, slugs, blurbs, short names)
│   ├── scraper.py          # fetch_page() + parse_products()
│   └── builder.py          # Static site generator (newest ALL CSV vs previous-day ALL CSV → HTML)
├── templates/              # Jinja2 templates
│   ├── base.html           # Shared head / nav / footer / JSON-LD
│   ├── index.html          # Overview homepage
│   └── category.html       # Per-category price page
├── output/                 # CSV output directory (tracked by Git)
│   └── debug/              # HTML dumps from failed crawls (at most 10 kept)
├── docs/                   # Frontend source assets (not the publish directory)
│   ├── compare.html        # Historical comparison tool (SPA)
│   ├── style.css / pages.css
│   ├── app.js / theme.js   # comparison tool logic / theme toggle
│   ├── og-image.png / favicon.svg
│   └── crawl_history.json  # Crawl history list (auto-generated)
├── _site/                  # Build output (gitignored, deployed by Actions)
└── pyproject.toml
```

## Scheduled Crawling

Automated crawling via GitHub Actions — no manual execution needed.

| Taiwan Time | Mode | Description |
|---|---|---|
| 07:05 / 15:05 / 23:05 | `--all` (ALL) | All 30 categories |
| 11:05 / 19:05 | default (MAIN) | 10 main component categories |

> ⏱ Cron offset by 5 minutes to avoid on-the-hour peaks and reduce GitHub Actions scheduling delays.

- Commit message format:
  - Success: `crawl: (cron 09:05) 2026-04-18 09:07 ALL`
  - Failure: `crawl-fail: (cron 09:05) 2026-04-18 09:07 ALL`
- Supports manual trigger via `workflow_dispatch` with MAIN/ALL mode selection

## Failure Handling

The crawler self-marks as failed in the following two cases. It produces a commit with the `crawl-fail:` prefix, skips writing the CSV and updating the crawl history, but still commits a debug HTML snapshot for post-mortem inspection:

1. **Bad content** — HTTP 200 returned but the HTML lacks the `name=n1` substring (the `name` attribute on the first `<SELECT>` tag — CoolPC uses unquoted attributes) — typically a maintenance page, anti-bot challenge, or CDN intercept. `fetch_page` retries 3 times with exponential backoff (3s, 9s) before giving up.
2. **Empty parse result** — The HTML passes the sentinel check but `parse_products` returns zero products — possibly a site change or parser bug. The 2026-07-11 failure was this case: a marquee notice contained a bare `&#`, and Python's built-in `html.parser` stops at a `&#` that doesn't form a numeric character reference, turning the rest of the page into plain text. Such `&#` sequences are now escaped to `&amp;#` before parsing.

Debug HTML location: `output/debug/coolpc_YYYYMMDD_HHMMSS.html` (timestamp aligned with the normal CSV naming convention). Only the 10 most recent dumps are kept; older ones are deleted on the next dump.

> Note: complete HTTP failure (all 3 retries fail to reach CoolPC) still turns the Action red without producing a commit — distinct from the "bad content" failure mode above.

## Website

Published via GitHub Pages; `main.py build` regenerates the static pages after every crawl.

| Page | URL | Description |
|---|---|---|
| Overview | `/` | Latest stats, top 20 movers, category index, FAQ |
| Category page | `/c/<slug>.html` | Full price table for one category grouped by subcategory; one page per category with at least 5 items (currently 30 pages) |
| Comparison tool | `/compare.html` | Compare any two snapshots (client-side rendered SPA) |

The homepage and category pages are **static HTML generated at build time**, with product names and prices written directly into the source so search engines and AI crawlers can read them without JavaScript; the comparison tool remains client-side rendered.

- The homepage and category pages use the **newest ALL snapshot** and diff it against the newest ALL snapshot at least 20 hours older (normally the same slot on the previous day); MAIN snapshots only appear in the comparison tool, so the 11:05 and 19:05 crawls don't move the "updated at" time on the homepage
- The build also emits `sitemap.xml`, `robots.txt` (explicitly allowing major AI crawlers) and a redirect page for the legacy `/docs/index.html` URL; every page includes the GA4 tag
- A switch in the top-right corner toggles the light / dark theme; dark is the default and the choice is kept in the browser's localStorage

### Deployment

The Pages source must be set to **GitHub Actions** (not a branch). After crawling, the workflow runs `main.py build --with-data`, uploads `_site/` as the Pages artifact, and the `deploy` job publishes it.

```bash
uv run python main.py build                      # HTML only (quick preview)
uv run python main.py build --with-data          # Also copy every CSV (needed by the comparison tool)
uv run python main.py build --with-data --data-months 6   # Publish only the last 6 months of snapshots
```

> `--data-months` only controls which snapshots are published (a month counts as 30 days; requires `--with-data`); the repo's `output/` always stays complete.
> Adjust it to keep the Pages site under the 1 GB limit. `_site/crawl_history.json` is trimmed to match so the comparison tool's dropdown never points at an unpublished file. The workflow currently doesn't pass it, so every snapshot is published.

Local preview:

```bash
uv run python main.py build --with-data --data-months 1
uv run python -m http.server 8000 --directory _site
```

## Known Issues

1. The old price (A side) defaults to the 6th entry of the current month; if fewer than 6 entries exist, it picks the last one without rolling back to the previous month
2. **Cosmetic name changes are misdetected as add/remove pairs** — The join key includes the full product name string. When CoolPC tweaks a name (e.g. `WIN11 PRO` → `WIN11 Pro`, whitespace differences, full-width vs half-width punctuation), the same product splits into one ✕ removed + one ✦ new row. The crawler stores the raw text without normalization, so this noise has to be recognized by eye when reading diffs.

### Product Identity Key

When diffing two snapshots, a product is identified by **`(category, subcategory, name, nth occurrence of that combination)`**, implemented in `_row_key()` / `_occurrence_keys()` in `crawler/builder.py` and `rowKey()` / `buildKeyedMap()` in `docs/app.js`.

Name alone isn't enough because CoolPC's data contains two kinds of duplicates:

- **Same name across subcategories** — the same monitor model is listed under both the "27-inch" and "32-inch 4K" blocks, 7x apart in price
- **Same name within one subcategory** — the same monitor appears twice in one block with two different prices

Keyed by name only, the latter overwrites the former and two snapshots with identical prices produce a fake −86% drop.
In the 2026-09-18 ALL snapshot there are 100 duplicated names covering 201 rows, 9 of which (18 rows) repeat within a single subcategory.

## License

MIT
