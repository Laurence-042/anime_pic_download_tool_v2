from __future__ import annotations

import asyncio
import re
from pathlib import Path
from urllib.parse import urlparse

from .base import BaseAdapter, DownloadPlan, ImageFile
from config import PROXY
from cookie_parser import parse_cookie_file

_BROWSER_SEM = asyncio.Semaphore(2)


class TwitterAdapter(BaseAdapter):
    URL_PATTERN = r"https?://(?:twitter|x)\.com/[^/]+/status/(\d+)"

    async def parse(self, url: str, http: "HttpClient", want_indices: list[int] | None = None) -> DownloadPlan:
        from playwright.async_api import async_playwright

        author, post_id = self._extract_parts(url)
        legacy = await self._fetch_legacy(url, async_playwright)
        media_items = self._extract_media(legacy)
        selected = self._apply_indices(media_items, want_indices)

        images: list[ImageFile] = []
        for idx, media_url in selected:
            clean_url = media_url.split("?", 1)[0]
            ext = Path(urlparse(clean_url).path).suffix or ".jpg"
            images.append(
                ImageFile(
                    url=media_url,
                    filename=f"twitter_{author}_{post_id}_{idx + 1}{ext}",
                )
            )

        return DownloadPlan(images=images, source_url=url)

    def _extract_parts(self, url: str) -> tuple[str, str]:
        m = re.search(r"https?://(?:twitter|x)\.com/(?P<author>[^/]+)/status/(?P<id>\d+)", url)
        if not m:
            raise ValueError(f"Invalid twitter/x url: {url}")
        return m.group("author"), m.group("id")

    async def _fetch_legacy(self, url: str, async_playwright):
        try:
            from user_config import TWITTER_COOKIE_FILE
        except ImportError:
            TWITTER_COOKIE_FILE = "x.com_cookies.txt"

        retries = 3
        last_exc: Exception | None = None
        for attempt in range(retries):
            browser = None
            page = None
            async with _BROWSER_SEM:
                try:
                    async with async_playwright() as pw:
                        launch_kwargs: dict = {"headless": False}
                        if PROXY:
                            launch_kwargs["proxy"] = {"server": PROXY}
                        browser = await pw.chromium.launch(**launch_kwargs)
                        context = await browser.new_context()
                        context_cookies = parse_cookie_file(TWITTER_COOKIE_FILE)
                        if context_cookies:
                            await context.add_cookies(context_cookies)
                        page = await context.new_page()

                        def _filter(resp):
                            return (
                                resp.request.method == "GET"
                                and resp.status == 200
                                and (
                                    "TweetDetail" in resp.url
                                    or "TweetResultByRestId" in resp.url
                                )
                            )

                        goto_task = page.goto(url)
                        response_task = page.wait_for_response(_filter, timeout=30_000)
                        await asyncio.gather(goto_task, response_task)
                        response = response_task.result()
                        payload = await response.json()
                        legacy = self._parse_legacy_from_payload(payload)
                        if not legacy:
                            raise RuntimeError("Adult content, login required")
                        return legacy
                except Exception as exc:
                    last_exc = exc
                    if attempt < retries - 1:
                        await asyncio.sleep(2)
                finally:
                    if page:
                        try:
                            await asyncio.wait_for(page.close(), timeout=5)
                        except Exception:
                            pass
                    if browser:
                        try:
                            await asyncio.wait_for(browser.close(), timeout=5)
                        except Exception:
                            pass

        if last_exc:
            raise last_exc
        raise RuntimeError("Failed to fetch twitter status payload")

    def _parse_legacy_from_payload(self, payload: dict) -> dict | None:
        result = payload.get("data", {}).get("tweetResult", {}).get("result")
        if isinstance(result, dict):
            tweet = result.get("tweet", result)
            legacy = tweet.get("legacy") if isinstance(tweet, dict) else None
            if legacy:
                return legacy

        instructions = (
            payload.get("data", {})
            .get("threaded_conversation_with_injections_v2", {})
            .get("instructions", [])
        )
        for instruction in instructions:
            if instruction.get("type") != "TimelineAddEntries":
                continue
            for entry in instruction.get("entries", []):
                entry_id = entry.get("entryId", "")
                if not entry_id.startswith("tweet-"):
                    continue
                item = entry.get("content", {}).get("itemContent", {})
                result = item.get("tweet_results", {}).get("result", {})
                tweet = result.get("tweet", result)
                legacy = tweet.get("legacy") if isinstance(tweet, dict) else None
                if legacy:
                    return legacy
        return None

    def _extract_media(self, legacy: dict) -> list[str]:
        entities = legacy.get("extended_entities") or legacy.get("entities") or {}
        media = entities.get("media") or []
        urls: list[str] = []

        for item in media:
            mtype = item.get("type")
            if mtype == "photo":
                photo_url = item.get("media_url_https")
                if photo_url:
                    urls.append(f"{photo_url}?name=4096x4096")
            elif mtype == "video":
                variants = item.get("video_info", {}).get("variants", [])
                candidates = [
                    v
                    for v in variants
                    if v.get("content_type") == "video/mp4" and v.get("url")
                ]
                if not candidates:
                    continue
                best = max(candidates, key=lambda x: x.get("bitrate", 0))
                urls.append(best["url"].split("?", 1)[0])
        return urls

    def _apply_indices(self, media_urls: list[str], want_indices: list[int] | None):
        if want_indices is None:
            indices = [0]
        elif want_indices == []:
            indices = list(range(len(media_urls)))
        else:
            indices = want_indices

        selected = []
        for idx in indices:
            if 0 <= idx < len(media_urls):
                selected.append((idx, media_urls[idx]))
        return selected
