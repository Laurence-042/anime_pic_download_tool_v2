from contextlib import asynccontextmanager
from urllib.parse import urlparse
import asyncio
import time

import aiohttp

from config import DEFAULT_RATE_LIMIT, PROXY, RATE_LIMITS


class HttpClient:
    """
    封装共享的 aiohttp.ClientSession，提供带限速的请求接口。
    """

    def __init__(self, session: aiohttp.ClientSession, proxy: str | None = PROXY):
        self._session = session
        self._proxy = proxy
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._last_request: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc

    def _get_limiter(self, domain: str) -> tuple[asyncio.Semaphore, float]:
        if domain not in self._semaphores:
            max_concurrent, interval = RATE_LIMITS.get(domain, DEFAULT_RATE_LIMIT)
            self._semaphores[domain] = asyncio.Semaphore(max_concurrent)
            self._last_request[domain] = 0.0
            self._locks[domain] = asyncio.Lock()
        return self._semaphores[domain], RATE_LIMITS.get(domain, DEFAULT_RATE_LIMIT)[1]

    @asynccontextmanager
    async def get(self, url: str, **kwargs):
        domain = self._domain(url)
        sem, interval = self._get_limiter(domain)
        async with sem:
            async with self._locks[domain]:
                elapsed = time.monotonic() - self._last_request[domain]
                if elapsed < interval:
                    await asyncio.sleep(interval - elapsed)
                self._last_request[domain] = time.monotonic()
            timeout = aiohttp.ClientTimeout(connect=30, sock_read=60, total=300)
            async with self._session.get(
                url, proxy=self._proxy, timeout=timeout, **kwargs
            ) as resp:
                yield resp
