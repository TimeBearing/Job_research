import random
import time
import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


class BaseScraper(ABC):
    """Base class for job board scrapers with anti-detection measures."""

    timeout: float = 10.0
    base_url: str = ""

    def __init__(self):
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers=self._build_headers(),
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    def _build_headers(self) -> dict:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    def _rotate_headers(self):
        """Rotate User-Agent to avoid fingerprinting."""
        self.client.headers.update({"User-Agent": random.choice(USER_AGENTS)})

    def _delay(self):
        """Random delay between requests to avoid rate limiting."""
        time.sleep(random.uniform(1.5, 3.5))

    def _get(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """GET with retry logic. Returns None on persistent failure."""
        self._rotate_headers()
        for attempt in range(3):
            try:
                resp = self.client.get(url, **kwargs)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                logger.warning("[%s] HTTP %d on %s (attempt %d)", self.name, e.response.status_code, url, attempt + 1)
                if e.response.status_code in (403, 429):
                    time.sleep(2 ** attempt)
                    continue
                return None
            except httpx.RequestError as e:
                logger.warning("[%s] Request error on %s: %s (attempt %d)", self.name, url, e, attempt + 1)
                if attempt < 2:
                    time.sleep(1)
        return None

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def search(self, city: str, keyword: str) -> list[dict]:
        """Search for jobs. Returns list of normalized job dicts."""
        ...

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
