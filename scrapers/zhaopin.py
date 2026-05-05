import re
import logging
from urllib.parse import quote

from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)

# 智联 city codes
CITY_MAP = {
    "北京": "530", "上海": "538", "广州": "763", "深圳": "765",
    "杭州": "653", "成都": "801", "武汉": "736", "南京": "635",
    "西安": "854", "重庆": "551", "长沙": "749", "苏州": "639",
    "天津": "533", "郑州": "719", "青岛": "905", "厦门": "588",
    "合肥": "648", "济南": "702", "东莞": "764", "佛山": "766",
    "福州": "586", "大连": "600", "昆明": "826", "宁波": "658",
    "沈阳": "599", "无锡": "641",
}


class ZhaopinScraper(BaseScraper):
    """智联招聘 scraper."""

    timeout = 10.0

    @property
    def name(self) -> str:
        return "智联招聘"

    def search(self, city: str, keyword: str) -> list[dict]:
        city_code = self._resolve_city(city)
        encoded_kw = quote(keyword, safe="")
        url = f"https://sou.zhaopin.com/?jl={city_code}&kw={encoded_kw}&p=1"
        self._delay()
        resp = self._get(url)
        if resp is None:
            logger.info("[智联招聘] Request failed, skipping")
            return []

        return self._parse(resp.text)

    def _resolve_city(self, city: str) -> str:
        if city in CITY_MAP:
            return CITY_MAP[city]
        for name, code in CITY_MAP.items():
            if city in name or name in city:
                return code
        return "0"  # 全国

    def _parse(self, html: str) -> list[dict]:
        jobs = []
        try:
            soup = BeautifulSoup(html, "lxml")
            items = soup.select(".jobsearch-box .joblist-item, .joblist-box__item")
            if not items:
                items = soup.select("[class*=joblist] [class*=item]")
            for item in items[:15]:
                job = self._parse_item(item)
                if job["title"]:
                    jobs.append(job)
        except Exception as e:
            logger.warning("[智联招聘] Parse error: %s", e)
        return jobs

    def _parse_item(self, item) -> dict:
        title_el = item.select_one(".jobinfo__name, .job-name, [class*=jobname], [class*=job_title]")
        company_el = item.select_one(".company__name, .company-name, [class*=company_name], [class*=cname]")
        salary_el = item.select_one(".jobinfo__salary, .job-salary, [class*=salary]")
        location_el = item.select_one(".jobinfo__city, [class*=city], [class*=location]")
        date_el = item.select_one(".jobinfo__time, [class*=time], [class*=date]")
        link_el = item.select_one("a[href]")

        title = title_el.get_text(strip=True) if title_el else ""
        company = company_el.get_text(strip=True) if company_el else ""
        salary = salary_el.get_text(strip=True) if salary_el else ""
        location = location_el.get_text(strip=True) if location_el else ""
        post_date = date_el.get_text(strip=True) if date_el else ""
        href = link_el.get("href", "") if link_el else ""

        if href and not href.startswith("http"):
            href = "https:" + href if href.startswith("//") else "https://sou.zhaopin.com" + href

        return {
            "title": title,
            "company": company,
            "salary": salary,
            "location": location,
            "source": self.name,
            "post_date": post_date,
            "url": href,
        }
