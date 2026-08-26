# coolpc-crawler — 原價屋價格爬蟲與歷史比價工具

原價屋（CoolPC）商品價格爬蟲，定期爬取[原價屋線上估價](https://www.coolpc.com.tw/evaluate.php)的電腦零組件價格資料，分類整理後輸出 CSV，並提供歷史價格對比頁面，追蹤漲跌變化。

[English version below ↓](#english)

---

## 主要功能

1. **價格爬取** — 爬取原價屋線上估價的商品價格，依分類整理後輸出 CSV
2. **歷史價格對比** — 比較不同時間點的價格快照，一目了然查看漲跌與異動（詳見下方對比頁面說明）

## 技術棧

- Python 3.9+（建議搭配 [uv](https://github.com/astral-sh/uv) 管理依賴，亦可直接以原生 Python + pip 執行）
- beautifulsoup4（HTML 解析）/ requests（HTTP 請求，內建 retry 與指數 backoff）/ jinja2（靜態頁面樣板）
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
uv run python main.py crawl -o out.csv # 指定輸出路徑

uv run python main.py build            # 由最新快照產生靜態網站到 _site/
```

預設輸出至 `output/coolpc_YYYYMMDD_HHMMSS.csv`。

## 分類篩選

預設只抓取以下 10 個主要 PC 零組件（定義在 `crawler/models.py` 的 `MAIN_CATEGORIES`）：

> 處理器 CPU、主機板 MB、記憶體 RAM、固態硬碟 M.2/SSD、傳統硬碟 HDD、散熱器、水冷、顯示卡 VGA、機殼 CASE、電源供應器 PSU

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
| `scraped_at` | 抓取時間 |

> 備註標記為正面表列，定義於 `crawler/scraper.py` 的 `REMARK_PATTERNS`，新增類型直接加入列表即可。

## 專案結構

```
├── main.py                 # CLI 入口（argparse 子命令：crawl / build）
├── crawler/
│   ├── models.py           # Product dataclass + 分類設定（MAIN_CATEGORIES、slug、短名）
│   ├── scraper.py          # fetch_page() + parse_products()
│   └── builder.py          # 靜態頁面產生器（讀最新兩份 CSV → HTML）
├── templates/              # Jinja2 樣板
│   ├── base.html           # 共用 head／導覽／頁尾／JSON-LD
│   ├── index.html          # 總覽首頁
│   └── category.html       # 分類價格頁
├── output/                 # CSV 輸出目錄（已納入版控）
├── docs/                   # 前端原始資源（非發布目錄）
│   ├── compare.html        # 歷史比價工具（SPA）
│   ├── style.css / pages.css
│   ├── app.js
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
2. **解析空集** — HTML 結構通過 sentinel 檢查但 `parse_products` 回傳 0 筆，可能是原價屋改版或解析邏輯有 bug。

debug HTML 位置：`output/debug/coolpc_YYYYMMDD_HHMMSS.html`（時間戳對齊原本 CSV 命名規則）。

> 注意：HTTP 層完全失敗（三次 retry 都連不上原價屋）仍會讓 Action 紅燈、不產生 commit，這跟「拿到壞內容」是不同的失敗模式。

## 網站

透過 GitHub Pages 發布，由 `main.py build` 在每次爬取後重新產生靜態頁面。

| 頁面 | 網址 | 說明 |
|---|---|---|
| 總覽首頁 | `/` | 最新報價統計、漲跌幅 TOP 20、分類索引、常見問題 |
| 分類頁 | `/c/<slug>.html` | 單一分類完整價格表，依子分類分組（30 頁） |
| 歷史比價工具 | `/compare.html` | 任選兩份快照比對（原本的 SPA） |

首頁與分類頁是**建置期產生的靜態 HTML**，商品名稱與價格直接寫在原始碼中，不依賴 JavaScript
即可被搜尋引擎與 AI 爬蟲讀取；比價工具維持 client-side 渲染。

### 部署

Pages 的 Source 需設為 **GitHub Actions**（不是 branch）。workflow 會在爬取後依序執行
`main.py build --with-data`、上傳 `_site/` 為 Pages artifact，再由 `deploy` job 發布。

```bash
uv run python main.py build                      # 只產生 HTML（快速預覽）
uv run python main.py build --with-data          # 一併複製全部 CSV（比價工具需要）
uv run python main.py build --with-data --data-months 6   # 只發布近 6 個月的快照
```

> `--data-months` 只影響「發布哪些快照」，repo 的 `output/` 永遠保持完整。
> 需要控制 Pages 站台體積時（上限 1 GB）調整此參數，並會同步裁切 `crawl_history.json`，
> 避免比價工具的下拉選單指向未發布的檔案。

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
最新一份 ALL 快照中約有 117 組同名商品、影響 239 列。

## License

MIT

---

## English

CoolPC price crawler and historical price comparison tool. Periodically scrapes PC component pricing data from [CoolPC Online Estimator](https://www.coolpc.com.tw/evaluate.php), exports structured CSV files, and provides a web-based price diff viewer to track price changes over time.

## Features

1. **Price Scraping** — Crawl CoolPC product prices by category and export to CSV
2. **Historical Price Comparison** — Compare price snapshots across dates to identify changes at a glance (see comparison page section below)

## Tech Stack

- Python 3.9+ (recommended with [uv](https://github.com/astral-sh/uv) for dependency management; also works with vanilla Python + pip)
- beautifulsoup4 (HTML parsing) / requests (HTTP, with retry and exponential backoff)
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
uv run python main.py crawl -o out.csv # Specify output path
```

Output defaults to `output/coolpc_YYYYMMDD_HHMMSS.csv`.

## Category Filtering

By default, only the following 10 main PC component categories are scraped (defined in `MAIN_CATEGORIES` in `crawler/models.py`):

> CPU, Motherboard, RAM, SSD, HDD, CPU Cooler, AIO Liquid Cooler, GPU, PC Case, PSU

Use `--all` to scrape all 30 categories.

## CSV Fields

`category, subcategory, name, price, remark, scraped_at`

| Field | Description |
|---|---|
| `category` | Category name |
| `subcategory` | Subcategory name |
| `name` | Product name |
| `price` | Price in NTD |
| `remark` | Remark tags (e.g. "In Stock", "Pre-order", "Assembly Only"), joined by `/` |
| `scraped_at` | Scrape timestamp |

> Remark tags are explicitly whitelisted in `REMARK_PATTERNS` (in `crawler/scraper.py`); extend the list to add new tag patterns.

## Project Structure

```
├── main.py                 # CLI entry point (argparse subcommands)
├── crawler/
│   ├── models.py           # Product dataclass + MAIN_CATEGORIES config
│   └── scraper.py          # fetch_page() + parse_products()
├── output/                 # CSV output directory (tracked by Git)
├── docs/                   # Frontend pages for GitHub Pages
│   ├── index.html          # Price comparison page
│   ├── style.css
│   ├── app.js
│   └── crawl_history.json  # Crawl history list (auto-generated)
├── index.html              # Root redirect → docs/index.html
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
2. **Empty parse result** — The HTML passes the sentinel check but `parse_products` returns zero products — possibly a site change or parser bug.

Debug HTML location: `output/debug/coolpc_YYYYMMDD_HHMMSS.html` (timestamp aligned with the normal CSV naming convention).

> Note: complete HTTP failure (all 3 retries fail to reach CoolPC) still turns the Action red without producing a commit — distinct from the "bad content" failure mode above.

## Price Comparison Page

A static price comparison page is served via GitHub Pages, allowing you to compare two crawl snapshots side by side.

- https://troywhitetw.github.io/coolpc-crawler/docs/index.html
- Features: cascading year/month/entry selectors, collapsible categories, price change indicators, automatic MAIN/ALL mode intersection

## Known Issues

1. The old price (A side) defaults to the 6th entry of the current month; if fewer than 6 entries exist, it picks the last one without rolling back to the previous month
2. **Cosmetic name changes are misdetected as add/remove pairs** — The comparison page uses the full product name string as the join key (`mapA`/`mapB` in `docs/app.js`). When CoolPC tweaks a name (e.g. `WIN11 PRO` → `WIN11 Pro`, whitespace differences, full-width vs half-width punctuation), the same product splits into one ✕ removed + one ✦ new row. The crawler stores the raw text without normalization, so this noise has to be recognized by eye when reading diffs.

## License

MIT