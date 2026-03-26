"""Shared async HTTP client with retry, rate limiting, and Cloudflare bypass."""

import asyncio
import logging
import random

from curl_cffi.requests import AsyncSession, Response

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.5,en;q=0.3",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Browser to impersonate for TLS fingerprint (bypasses Cloudflare)
IMPERSONATE_BROWSER = "chrome"


class HttpClient:
    """Async HTTP client with automatic retry, rate limiting, and Cloudflare bypass.

    Uses curl_cffi to impersonate a real browser TLS fingerprint,
    which is required for sites behind Cloudflare (e.g. Momox).
    """

    def __init__(
        self,
        user_agents: list[str] | None = None,
        timeout: float = 15.0,
        max_retries: int = 3,
        delay_min: float = 2.0,
        delay_max: float = 5.0,
    ) -> None:
        self.user_agents = user_agents or DEFAULT_USER_AGENTS
        self.timeout = timeout
        self.max_retries = max_retries
        self.delay_min = delay_min
        self.delay_max = delay_max
        self._session: AsyncSession | None = None

    async def _get_session(self) -> AsyncSession:
        if self._session is None:
            self._session = AsyncSession(
                timeout=self.timeout,
                impersonate=IMPERSONATE_BROWSER,
                allow_redirects=True,
            )
        return self._session

    def _random_headers(self) -> dict[str, str]:
        headers = dict(DEFAULT_HEADERS)
        headers["User-Agent"] = random.choice(self.user_agents)
        return headers

    async def _rate_limit_delay(self) -> None:
        delay = random.uniform(self.delay_min, self.delay_max)
        await asyncio.sleep(delay)

    async def get(
        self,
        url: str,
        params: dict | None = None,
        extra_headers: dict | None = None,
    ) -> Response:
        """GET with retry + exponential backoff on 429/5xx."""
        session = await self._get_session()
        headers = self._random_headers()
        if extra_headers:
            headers.update(extra_headers)

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            if attempt > 0:
                backoff = (2**attempt) + random.uniform(0, 1)
                logger.debug("Retry %d, backoff %.1fs", attempt, backoff)
                await asyncio.sleep(backoff)

            try:
                resp = await session.get(url, params=params, headers=headers)
                if resp.status_code == 429:
                    logger.warning("Rate limited (429) on %s", url)
                    continue
                if resp.status_code >= 500:
                    logger.warning("Server error %d on %s", resp.status_code, url)
                    continue
                return resp
            except Exception as e:
                logger.warning("HTTP error on %s: %s", url, e)
                last_error = e

        raise last_error or Exception(f"Failed after {self.max_retries} retries: {url}")

    async def get_json(
        self,
        url: str,
        params: dict | None = None,
        extra_headers: dict | None = None,
    ) -> dict:
        """GET and parse JSON response."""
        ajax_headers = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*"}
        if extra_headers:
            ajax_headers.update(extra_headers)
        resp = await self.get(url, params=params, extra_headers=ajax_headers)
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
