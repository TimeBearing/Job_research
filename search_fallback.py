"""Search fallbacks — DuckDuckGo SERP + Sogou WeChat article search."""
import re
import random
import logging
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

SALARY_RE = re.compile(
    r"(\d+[kKk千]?\s*[-~—至到]\s*\d+[kKk千]?\s*(?:元|块|/月|万)?)",
    re.IGNORECASE,
)

STALE_YEAR_RE = re.compile(r"20(?:0\d|1[0-9]|2[0-3])年")
STALE_DATE_RE = re.compile(r"(?:发布于?|更新于?|发布时间?[:：]?\s*)?20(?:0\d|1\d|2[0-3])[\-/年]")


def _build_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }


# ── DuckDuckGo search (primary search engine) ─────────────────────────

def search_duckduckgo(city: str, keyword: str) -> list[dict]:
    """Search via DuckDuckGo non-JS HTML version. Returns excellent Chinese job results."""
    query = f"{city} {keyword} 招聘"
    url = f"https://html.duckduckgo.com/html/?q={quote(query)}"

    try:
        resp = httpx.get(url, headers=_build_headers(), timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
    except httpx.RequestError as e:
        logger.warning("[DuckDuckGo] Request failed: %s", e)
        return []

    return _parse_duckduckgo(resp.text, city)


def _parse_duckduckgo(html: str, city: str) -> list[dict]:
    """Parse DuckDuckGo non-JS HTML search results."""
    jobs = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for item in soup.select(".result, .web-result")[:15]:
            title_el = item.select_one(".result__title, .result__a")
            snippet_el = item.select_one(".result__snippet")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            # Extract URL from the title link or result__url
            link_el = title_el.select_one("a") or item.select_one(".result__url a, .result__url")
            href = link_el.get("href", "") if link_el else ""
            # Fix protocol-relative URLs
            if href.startswith("//"):
                href = "https:" + href

            if not _is_job_related(title, snippet):
                continue

            # Extract company from title or snippet
            company = _extract_company(title, snippet)
            if not company:
                company = _extract_company_from_title(title)

            jobs.append({
                "title": title,
                "company": company,
                "salary": _extract_salary(title + snippet),
                "location": city,
                "source": "搜索引擎",
                "post_date": "",
                "url": href,
            })
    except Exception as e:
        logger.warning("[DuckDuckGo parse] %s", e)
    return jobs


def _extract_company_from_title(title: str) -> str:
    """Try to extract company/organization name from a job title."""
    # Pattern: "城市XX公司招聘..." or "城市XX招聘..."
    m = re.search(r"[一-龥]{2,20}(?:公司|集团|科技|网络|信息|有限|技术|企业|单位)", title)
    if m:
        return m.group(0)
    # Pattern: "-BOSS直聘", "-智联招聘" etc → use as fallback hint
    for suffix in ["-BOSS直聘", "-智联招聘", "-51job", "-猎聘", "-前程无忧"]:
        if suffix in title:
            return suffix.lstrip("-")
    return ""


# ── Bing / Baidu search (kept as fallback) ────────────────────────────

def search_via_bing(city: str, keyword: str) -> list[dict]:
    query = f"{city} {keyword} 招聘"
    url = f"https://www.bing.com/search?q={quote(query)}&setlang=zh-cn"
    try:
        resp = httpx.get(url, headers=_build_headers(), timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
    except httpx.RequestError as e:
        logger.warning("[搜索兜底] Bing failed: %s", e)
        return _search_via_baidu(city, keyword)

    jobs = _parse_bing(resp.text, city)
    return jobs or _search_via_baidu(city, keyword)


def _search_via_baidu(city: str, keyword: str) -> list[dict]:
    query = f"{city} {keyword} 招聘"
    url = f"https://www.baidu.com/s?wd={quote(query)}"
    try:
        resp = httpx.get(url, headers=_build_headers(), timeout=10.0, follow_redirects=True)
    except httpx.RequestError:
        logger.warning("[搜索兜底] Baidu also failed")
        return []
    return _parse_baidu(resp.text, city)


def _parse_bing(html: str, city: str) -> list[dict]:
    jobs = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for item in soup.select("li.b_algo, .b_results li")[:15]:
            title_el = item.select_one("h2 a")
            snippet_el = item.select_one(".b_caption p, .b_lineclamp2, .b_algoSlug")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            if not _is_job_related(title, snippet):
                continue
            jobs.append({
                "title": title,
                "company": _extract_company(title, snippet),
                "salary": _extract_salary(title + snippet),
                "location": city,
                "source": "搜索引擎",
                "post_date": "",
                "url": title_el.get("href", ""),
            })
    except Exception as e:
        logger.warning("[Bing parse] %s", e)
    return jobs


def _parse_baidu(html: str, city: str) -> list[dict]:
    jobs = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for item in soup.select(".result, .c-result, .result-op")[:15]:
            title_el = item.select_one("h3 a, .t a")
            snippet_el = item.select_one(".c-abstract, .c-span-last, .c-row")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            if not _is_job_related(title, snippet):
                continue
            jobs.append({
                "title": title,
                "company": _extract_company(title, snippet),
                "salary": _extract_salary(title + snippet),
                "location": city,
                "source": "搜索引擎",
                "post_date": "",
                "url": title_el.get("href", ""),
            })
    except Exception as e:
        logger.warning("[Baidu parse] %s", e)
    return jobs


# ── Sogou WeChat article search ──────────────────────────────────────

def search_wechat(city: str, keyword: str) -> list[dict]:
    """Search WeChat public account articles via Sogou WeChat search."""
    query = f"{city} {keyword} 招聘"
    url = f"https://weixin.sogou.com/weixin?type=2&query={quote(query)}&ie=utf8"

    try:
        resp = httpx.get(url, headers=_build_headers(), timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
    except httpx.RequestError as e:
        logger.warning("[微信公众号] Sogou request failed: %s", e)
        return []

    return _parse_sogou_wechat(resp.text, city)


def _parse_sogou_wechat(html: str, city: str) -> list[dict]:
    """Parse Sogou WeChat search result page."""
    jobs = []
    try:
        soup = BeautifulSoup(html, "lxml")
        items = soup.select(".news-box .news-list2 li, .news-list li, .txt-box")
        if not items:
            items = soup.select("[class*=news-list] li, .wx-rb")

        for item in items[:15]:
            title_el = item.select_one("h3 a, .tit a, a[href*='mp.weixin.qq.com']")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            url = title_el.get("href", "")
            if not url:
                continue

            # Sogou returns relative /link?url=... paths; make absolute.
            # Do NOT try to resolve server-side — Sogou anti-spider blocks us.
            # The token in the URL authenticates real browser users.
            if url.startswith("/"):
                url = f"https://weixin.sogou.com{url}"

            snippet_el = item.select_one(".txt-info, .s-p, p, .summary")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            if not _is_job_related(title, snippet):
                continue

            date_el = item.select_one(".s2, .time, .date, [class*=time]")
            post_date = date_el.get_text(strip=True) if date_el else ""

            jobs.append({
                "title": title,
                "company": _extract_company(title, snippet),
                "salary": _extract_salary(title + snippet),
                "location": city,
                "source": "微信公众号",
                "post_date": post_date,
                "url": url,
            })
    except Exception as e:
        logger.warning("[微信公众号 parse] %s", e)
    return jobs


def _resolve_sogou_url(sogou_url: str) -> str:
    """Follow Sogou redirect to get the real WeChat article URL."""
    try:
        resp = httpx.get(sogou_url, headers=_build_headers(), timeout=5.0, follow_redirects=False)
        location = resp.headers.get("location", "")
        if "mp.weixin.qq.com" in location:
            return location
    except Exception:
        pass
    return sogou_url


# ── Shared helpers ────────────────────────────────────────────────────

def _is_job_related(title: str, snippet: str) -> bool:
    combined = (title + snippet).lower()
    keywords = ["招聘", "岗位", "职位", "薪资", "待遇", "hr", "求职", "就业", "job", "recruit", "hire"]
    return any(kw in combined for kw in keywords)


def _extract_company(title: str, snippet: str) -> str:
    for pat in [r"([一-龥]+(?:有限|科技|集团|网络|信息).*?(?:公司|技术))", r"([一-龥]{2,20}(?:招聘|诚聘|急招))"]:
        m = re.search(pat, snippet)
        if m:
            name = re.sub(r"(招聘|诚聘|急招|诚聘)$", "", m.group(1))
            if len(name) >= 3:
                return name
    return ""


def _extract_salary(text: str) -> str:
    m = SALARY_RE.search(text)
    return m.group(1) if m else ""
