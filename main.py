import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from crawler.models import get_category_filter
from crawler.scraper import EmptyContentError, fetch_page, parse_products


def _dump_debug_html(html: str, now: datetime) -> Path:
    """將失敗頁面寫入 output/debug/ 以便事後分析。
    Dump failing HTML into output/debug/ for post-mortem inspection."""
    debug_dir = Path("output/debug")
    debug_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    debug_path = debug_dir / f"coolpc_{timestamp}.html"
    debug_path.write_text(html, encoding="utf-8")
    return debug_path


def _signal_failure() -> None:
    """寫 status=failed 給 GitHub Actions step output（若不在 Action 內則 no-op）。
    Write status=failed to GitHub Actions step output (no-op outside Actions)."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write("status=failed\n")


def crawl(args):
    # 抓取原價屋估價單資料 Fetch CoolPC estimate page data
    print("Fetching CoolPC data...")
    now = datetime.now()
    try:
        html = fetch_page()
    except EmptyContentError as exc:
        # HTTP 成功但內容不對（維護頁/挑戰頁等）：dump HTML、發失敗訊號、綠燈退出
        # HTTP ok but bad content: dump HTML, signal failure, exit green
        debug_path = _dump_debug_html(exc.html, now)
        print(f"ERROR: {exc}. Dumped to {debug_path}", file=sys.stderr)
        _signal_failure()
        return

    category_filter = get_category_filter(fetch_all=args.all)
    products = parse_products(html, category_filter)
    print(f"Total products: {len(products)}")

    if not products:
        # 結構通過 sentinel 但解析出 0 筆：可能是 HTML 改版或解析 bug
        # Passed sentinel but parsed nothing: possible site change or parser bug
        debug_path = _dump_debug_html(html, now)
        print(f"ERROR: parsed 0 products. Dumped to {debug_path}", file=sys.stderr)
        _signal_failure()
        return

    # 決定輸出路徑 Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"coolpc_{timestamp}.csv"

    # 寫入 CSV Write CSV
    scraped_at = now.strftime("%Y-%m-%d %H:%M:%S")
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "subcategory", "name", "price", "remark", "scraped_at"])
        for p in products:
            writer.writerow([p.category, p.subcategory, p.name, p.price, p.remark, scraped_at])

    print(f"Output: {output_path}")

    # 僅在使用預設 output/ 路徑時更新爬取歷史（自訂路徑不納入）
    # Only update crawl history when using default output/ path
    if not args.output:
        mode = "ALL" if args.all else "MAIN"
        update_crawl_history(output_path.name, mode)


def update_crawl_history(filename, mode):
    """將新紀錄加入爬取歷史 JSON，並同步 output/ 目錄狀態。
    Append new entry to docs/crawl_history.json and sync with output/ directory."""
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    history_path = docs_dir / "crawl_history.json"

    # 讀取既有紀錄 Load existing entries
    existing = {}
    if history_path.exists():
        existing = {
            entry["file"]: entry["mode"]
            for entry in json.loads(history_path.read_text(encoding="utf-8"))
        }

    # 加入本次爬取紀錄 Add current crawl entry
    existing[filename] = mode

    # 比對 output/ 實際檔案，移除已刪除的紀錄
    # Sync with actual files in output/, remove deleted entries
    actual_files = {p.name for p in Path("output").glob("coolpc_*.csv")}
    entries = [
        {"file": f, "mode": m}
        for f, m in existing.items()
        if f in actual_files
    ]
    entries.sort(key=lambda e: e["file"], reverse=True)

    history_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"Crawl history updated: {history_path} ({len(entries)} files)")


def main():
    # CLI 入口，使用 argparse 子命令 CLI entry point with argparse subcommands
    parser = argparse.ArgumentParser(description="CoolPC product price crawler")
    subparsers = parser.add_subparsers(dest="command")

    # crawl 子命令：抓取商品資料並輸出 CSV
    crawl_parser = subparsers.add_parser("crawl", help="Fetch products and export CSV")
    # --all: 抓取全部 30 個分類（預設只抓主要零組件）
    crawl_parser.add_argument("--all", action="store_true",
                              help="Fetch all 30 categories (default: main components only)")
    # -o: 指定 CSV 輸出路徑
    crawl_parser.add_argument("-o", "--output", help="Output CSV path")

    args = parser.parse_args()
    if args.command == "crawl":
        crawl(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
