import json
import re
import logging
from urllib.parse import quote

from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)

# 51job city codes (first 6 digits of area code) — common cities
CITY_MAP = {
    "北京": "010000", "上海": "020000", "广州": "030200", "深圳": "040000",
    "杭州": "080200", "成都": "090200", "武汉": "180200", "南京": "070200",
    "西安": "110200", "重庆": "060000", "长沙": "190200", "苏州": "070300",
    "天津": "050000", "郑州": "170200", "青岛": "120300", "厦门": "110300",
    "合肥": "080300", "济南": "120200", "东莞": "030800", "佛山": "030600",
    "福州": "110100", "大连": "230300", "昆明": "250200", "宁波": "080400",
    "沈阳": "230200", "无锡": "070400",
}


class WuyouScraper(BaseScraper):
    """51job scraper using the search page."""

    timeout = 10.0

    @property
    def name(self) -> str:
        return "51job"

    def search(self, city: str, keyword: str) -> list[dict]:
        city_code = self._resolve_city(city)
        encoded_kw = quote(keyword, safe="")
        # 51job search URL pattern
        url = (
            f"https://search.51job.com/list/{city_code},000000,0000,00,9,99,"
            f"{encoded_kw},2,1.html? lang=c&postchannel=0000&workyear=99"
            f"&cotype=99&degreefrom=99&jobterm=99&companysize=99"
            f"&providesalary=99&lonlat=0,0&radius=-1"
            f"&ord_field=0&confirmdate=9&fromType=&dibiaoid=0"
            f"&address=&line=&specialarea=00&from=&welfare="
        )
        self._delay()
        resp = self._get(url)
        if resp is None:
            logger.info("[51job] Request failed, skipping")
            return []

        return self._parse(resp.text)

    def _resolve_city(self, city: str) -> str:
        if city in CITY_MAP:
            return CITY_MAP[city]
        for name, code in CITY_MAP.items():
            if city in name or name in city:
                return code
        return "000000"  # 全国

    def _parse(self, html: str) -> list[dict]:
        """Parse 51job search result page."""
        jobs = []
        try:
            soup = BeautifulSoup(html, "lxml")
            items = soup.select(".j_joblist .e, .j_joblist .joblist_item")
            if not items:
                # Try alternate selectors
                items = soup.select(".joblist-item")
            for item in items[:15]:
                job = self._parse_item(item)
                if job["title"]:
                    jobs.append(job)
        except Exception as e:
            logger.warning("[51job] Parse error: %s", e)
        return jobs

    def _parse_item(self, item) -> dict:
        title_el = item.select_one(".jname, .job_name, [class*=title]")
        company_el = item.select_one(".cname, .company_name, [class*=cname]")
        salary_el = item.select_one(".sal, .salary, [class*=sal]")
        location_el = item.select_one(".d_at, .location, [class*=d_at]")
        date_el = item.select_one(".tme, .time, [class*=time]")
        link_el = item.select_one("a") if item.name != "a" else item

        title = title_el.get_text(strip=True) if title_el else ""
        company = company_el.get_text(strip=True) if company_el else ""
        salary = salary_el.get_text(strip=True) if salary_el else ""
        location = location_el.get_text(strip=True) if location_el else ""
        post_date = date_el.get_text(strip=True) if date_el else ""
        href = link_el.get("href", "") if link_el else ""

        return {
            "title": title,
            "company": company,
            "salary": salary,
            "location": location,
            "source": self.name,
            "post_date": post_date,
            "url": href if href.startswith("http") else f"https://jobs.51job.com{href}",
        }
