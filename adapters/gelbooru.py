from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .base import BaseAdapter, DownloadPlan, ImageFile
from utils.filename import clean_source_from_url


class GelbooruAdapter(BaseAdapter):
    URL_PATTERN = r"https?://gelbooru\.com/index\.php\?.*id=(\d+)"

    async def parse(self, url: str, http: "HttpClient", want_indices: list[int] | None = None) -> DownloadPlan:
        from bs4 import BeautifulSoup

        parsed = urlparse(url)
        post_id = parse_qs(parsed.query).get("id", [None])[0]
        if not post_id:
            raise ValueError(f"Invalid gelbooru url: {url}")

        async with http.get(url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to fetch gelbooru page: HTTP {resp.status}")
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        tags, metadata, source_url, dl_url = self._parse_aside(soup)
        if not dl_url:
            raise RuntimeError("Original image url not found")

        artist = next(iter(tags.get("Artist", {})), "unknown")
        clean_source = clean_source_from_url(source_url)
        ext = Path(urlparse(dl_url).path).suffix or ".jpg"
        filename = f"gelbooru_{post_id}_{artist}_{clean_source}{ext}"

        return DownloadPlan(
            images=[ImageFile(url=dl_url, filename=filename)],
            source_url=url,
            tags=tags,
            artist=artist,
            original_source=source_url,
            metadata=metadata,
        )

    def _parse_aside(self, soup):
        tags: dict[str, dict[str, dict]] = {
            "Artist": {},
            "Copyright": {},
            "Metadata": {},
            "Tag": {},
        }
        metadata: dict[str, str] = {}
        source_url: str | None = None
        download_url: str | None = None

        current = None
        for li in soup.select("section.aside li"):
            title = None
            b = li.find(["b", "h3"])
            if b:
                title = b.get_text(strip=True).rstrip(":")
            if title in {"Artist", "Copyright", "Metadata", "Tag", "Statistics", "Options"}:
                current = title
                continue

            if current in {"Artist", "Copyright", "Metadata", "Tag"}:
                links = [a for a in li.find_all("a") if a.get_text(strip=True)]
                if len(links) >= 2:
                    tags[current][links[1].get_text(strip=True)] = {}
            elif current == "Statistics":
                text = li.get_text(" ", strip=True)
                if ":" in text:
                    key, value = text.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    if key.lower() == "source":
                        src = li.find("a", href=True)
                        source_url = src["href"] if src else value
                        metadata[key] = source_url
                    else:
                        metadata[key] = value
            elif current == "Options":
                text = li.get_text(" ", strip=True).lower()
                link = li.find("a", href=True)
                if link and "original image" in text:
                    download_url = link["href"]

        return tags, metadata, source_url, download_url
