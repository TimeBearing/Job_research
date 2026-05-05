import re
import logging
import concurrent.futures

from flask import Flask, render_template, request, jsonify

from scrapers import ZhipinScraper, WuyouScraper, ZhaopinScraper
from search_fallback import search_duckduckgo, search_wechat

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

SCRAPER_CLASSES = [ZhipinScraper, WuyouScraper, ZhaopinScraper]

# Regex to detect years that indicate stale postings (2023 and earlier)
STALE_YEAR_RE = re.compile(r"(?:20(?:0\d|1[0-9]|2[0-3]))年")
# Also match standalone old years in contexts like "2020-01" or "发布于2021"
STALE_DATE_RE = re.compile(r"(?:发布于?|更新于?|发布时间?[:：]?\s*)?20(?:0\d|1\d|2[0-3])[\-/年]")
# Match titles/snippets that are clearly annual summaries, not real job postings
ARCHIVE_RE = re.compile(r"(20(?:0\d|1\d|2[0-3]))(?:年|届|级).*(?:招聘|校招|春招|秋招|汇总|合集|专场合集)")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search", methods=["POST"])
def search():
    data = request.get_json(silent=True) or {}
    city = (data.get("city") or "").strip()
    keyword = (data.get("keyword") or "").strip()
    subfield = (data.get("subfield") or "").strip()

    if not city or not keyword:
        return jsonify({"error": "城市和专业方向不能为空"}), 400

    # Combine keyword + subfield for richer search
    full_keyword = f"{keyword} {subfield}".strip() if subfield else keyword

    logger.info("Search: city=%r keyword=%r subfield=%r → full=%r", city, keyword, subfield, full_keyword)

    all_jobs = []
    working_sources = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        # Launch all sources in parallel
        futures = {}

        # Platform scrapers (best effort — often anti-bot blocked)
        for cls in SCRAPER_CLASSES:
            futures[pool.submit(_scrape_one, cls, city, full_keyword)] = cls.__name__

        # WeChat public account search
        futures[pool.submit(search_wechat, city, full_keyword)] = "微信公众号"

        # DuckDuckGo search (reliable web search that returns Chinese job results)
        futures[pool.submit(search_duckduckgo, city, full_keyword)] = "搜索引擎"

        # Collect all results
        for fut in concurrent.futures.as_completed(futures):
            source_label = futures[fut]
            try:
                results = fut.result(timeout=15)
                if results:
                    all_jobs.extend(results)
                    working_sources.append(source_label)
                    logger.info("Source %s returned %d results", source_label, len(results))
                else:
                    logger.info("Source %s returned 0 results", source_label)
            except Exception as e:
                logger.warning("Source %s failed: %s", source_label, e)

    # Last resort: try Bing if we have nothing
    if not all_jobs:
        logger.info("All sources empty, trying Bing as last resort")
        try:
            from search_fallback import search_via_bing
            bing_jobs = search_via_bing(city, full_keyword)
            if bing_jobs:
                all_jobs = bing_jobs
                working_sources = ["搜索引擎"]
        except Exception as e:
            logger.warning("Bing last resort also failed: %s", e)

    # Deduplicate by URL
    seen = set()
    unique_jobs = []
    for job in all_jobs:
        url = job.get("url", "")
        if url and url in seen:
            continue
        seen.add(url)
        unique_jobs.append(job)

    # Filter stale results (pre-2024)
    filtered_jobs = _filter_stale(unique_jobs)

    source_names = _resolve_source_names(working_sources)

    return jsonify({
        "jobs": filtered_jobs,
        "total": len(filtered_jobs),
        "sources": source_names,
    })


def _filter_stale(jobs: list[dict]) -> list[dict]:
    """Remove job postings that appear to be from 2023 or earlier."""
    keep = []
    for job in jobs:
        text = job.get("title", "") + job.get("post_date", "")
        text_lower = text.lower()

        # Exclude titles that are clearly archive/annual summary pages
        if ARCHIVE_RE.search(text):
            continue

        # Check for old dates in post_date or embedded in title
        if STALE_YEAR_RE.search(text) or STALE_DATE_RE.search(text):
            continue

        keep.append(job)
    return keep


def _scrape_one(scraper_cls, city, keyword) -> list[dict]:
    scraper = scraper_cls()
    try:
        return scraper.search(city, keyword)
    finally:
        scraper.close()


def _resolve_source_names(classes_or_names) -> list[str]:
    mapping = {
        "ZhipinScraper": "BOSS直聘",
        "WuyouScraper": "51job",
        "ZhaopinScraper": "智联招聘",
        "微信公众号": "微信公众号",
        "搜索引擎": "搜索引擎",
    }
    return [mapping.get(s, s) for s in classes_or_names]


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
