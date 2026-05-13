from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .base import BaseAdapter, DownloadPlan, ImageFile
from utils.filename import clean_source_from_url


class YandereAdapter(BaseAdapter):
    URL_PATTERN = r"https?://yande\.re/post/show/(\d+)"

    async def parse(self, url: str, http: "HttpClient", want_indices: list[int] | None = None) -> DownloadPlan:
        from bs4 import BeautifulSoup

        match = re.search(self.URL_PATTERN, url)
        if not match:
            raise ValueError(f"Invalid yandere url: {url}")
        post_id = match.group(1)

        async with http.get(url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to fetch yandere page: HTTP {resp.status}")
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        tags = self._parse_tags(soup)
        metadata, source_url = self._parse_stats(soup)
        link = soup.select_one("a#highres[href]")
        if not link:
            raise RuntimeError("Original image url not found")

        dl_url = link["href"]
        artist = next(iter(tags.get("Artist", {})), "unknown")
        clean_source = clean_source_from_url(source_url)
        ext = Path(urlparse(dl_url).path).suffix or ".jpg"
        filename = f"yandere_{post_id}_{artist}_{clean_source}{ext}"

        return DownloadPlan(
            images=[ImageFile(url=dl_url, filename=filename)],
            source_url=url,
            tags=tags,
            artist=artist,
            original_source=source_url,
            metadata=metadata,
        )

    def _parse_tags(self, soup):
        mapping = {
            "tag-type-artist": "Artist",
            "tag-type-copyright": "Copyright",
            "tag-type-character": "Character",
            "tag-type-general": "General",
        }
        tags = {v: {} for v in mapping.values()}
        for li in soup.select("ul#tag-sidebar li"):
            classes = li.get("class") or []
            category = None
            for cls in classes:
                if cls in mapping:
                    category = mapping[cls]
                    break
            if not category:
                continue
            links = [a for a in li.find_all("a") if a.get_text(strip=True)]
            if len(links) >= 2:
                tags[category][links[1].get_text(strip=True)] = {}
        return tags

    def _parse_stats(self, soup):
        metadata: dict[str, str] = {}
        source_url: str | None = None
        for li in soup.select("div#stats ul li"):
            text = li.get_text(" ", strip=True)
            if ":" not in text:
                continue
            key, value = text.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key.lower() == "source":
                link = li.find("a", href=True)
                source_url = link["href"] if link else value
                metadata[key] = source_url
            else:
                metadata[key] = value
        return metadata, source_url
