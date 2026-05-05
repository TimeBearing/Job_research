import json
import logging
from urllib.parse import quote

from .base import BaseScraper

logger = logging.getLogger(__name__)

# BOSS直聘 city codes for common cities
CITY_MAP = {
    "北京": "100010000", "上海": "101020100", "广州": "101280100", "深圳": "101280600",
    "杭州": "101210100", "成都": "101270100", "武汉": "101200100", "南京": "101190100",
    "西安": "101110100", "重庆": "100040000", "长沙": "101250100", "苏州": "101190400",
    "天津": "101030100", "郑州": "101180100", "青岛": "101120200", "厦门": "101230200",
    "合肥": "101220100", "济南": "101120100", "东莞": "101281600", "佛山": "101280800",
    "福州": "101230100", "大连": "101070200", "昆明": "101290100", "宁波": "101210400",
    "沈阳": "101070100", "无锡": "101190200",
}


class ZhipinScraper(BaseScraper):
    """BOSS直聘 scraper using the internal search API."""

    timeout = 10.0
    search_url = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"

    @property
    def name(self) -> str:
        return "BOSS直聘"

    def search(self, city: str, keyword: str) -> list[dict]:
        city_code = self._resolve_city(city)
        params = {
            "query": keyword,
            "city": city_code,
            "page": 1,
            "pageSize": 15,
        }
        self._delay()
        resp = self._get(self.search_url, params=params)
        if resp is None:
            logger.info("[BOSS直聘] Request failed, skipping")
            return []

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            logger.warning("[BOSS直聘] Non-JSON response")
            return []

        if data.get("code") != 0:
            logger.warning("[BOSS直聘] API error: %s", data.get("message", "unknown"))
            return []

        jobs = data.get("zpData", {}).get("jobList", [])
        return [self._normalize(j) for j in jobs]

    def _resolve_city(self, city: str) -> str:
        """Try exact match first, then partial match, fallback to 100010000 (全国)."""
        if city in CITY_MAP:
            return CITY_MAP[city]
        for name, code in CITY_MAP.items():
            if city in name or name in city:
                return code
        return "100010000"  # 全国 fallback

    def _normalize(self, job: dict) -> dict:
        return {
            "title": job.get("jobName", ""),
            "company": job.get("brandName", "") or job.get("brandComName", ""),
            "salary": job.get("salaryDesc", ""),
            "location": job.get("cityName", "") + (job.get("areaDistrict", "") or ""),
            "source": self.name,
            "post_date": job.get("jobModifyTime", "") or job.get("activeTimeDesc", ""),
            "url": f"https://www.zhipin.com/job_detail/{job.get('encryptJobId', '')}.html",
        }
