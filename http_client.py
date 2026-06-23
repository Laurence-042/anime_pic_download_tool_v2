from contextlib import asynccontextmanager
from urllib.parse import urlparse
import asyncio
import ssl
import time

import aiohttp

try:
    import certifi
except Exception:  # pragma: no cover
    certifi = None

from config import DEFAULT_RATE_LIMIT, PROXY, RATE_LIMITS, SSL_VERIFY


def _build_ssl_context() -> ssl.SSLContext | bool | None:
    """构建用于 aiohttp 的 SSL 上下文。

    - SSL_VERIFY=True 且 certifi 可用时,使用 certifi 的 CA 包(比系统信任库更新)
    - SSL_VERIFY=False 时,返回 False 关闭证书校验
    """
    if not SSL_VERIFY:
        return False
    if certifi is not None:
        ctx = ssl.create_default_context(cafile=certifi.where())
        return ctx
    return None  # 让 aiohttp 使用默认行为


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
        ssl_ctx = _build_ssl_context()
        timeout = aiohttp.ClientTimeout(connect=30, sock_read=60, total=300)

        async with sem:
            async with self._locks[domain]:
                elapsed = time.monotonic() - self._last_request[domain]
                if elapsed < interval:
                    await asyncio.sleep(interval - elapsed)
                self._last_request[domain] = time.monotonic()
            async with self._session.get(
                url,
                proxy=self._proxy,
                timeout=timeout,
                ssl=ssl_ctx,
                **kwargs,
            ) as resp:
                yield resp
