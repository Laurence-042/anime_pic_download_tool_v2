from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .base import BaseAdapter, DownloadPlan, ImageFile
from utils.filename import clean_source_from_url


class DanbooruAdapter(BaseAdapter):
    URL_PATTERN = r"https?://danbooru\.donmai\.us/posts/(\d+)"

    async def parse(self, url: str, http: "HttpClient", want_indices: list[int] | None = None) -> DownloadPlan:
        from bs4 import BeautifulSoup

        match = re.search(self.URL_PATTERN, url)
        if not match:
            raise ValueError(f"Invalid danbooru url: {url}")
        post_id = match.group(1)

        async with http.get(url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to fetch danbooru page: HTTP {resp.status}")
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")

        tags: dict[str, dict[str, dict]] = {
            "Artist": self._parse_tag_list(soup, "artist-tag-list"),
            "Copyright": self._parse_tag_list(soup, "copyright-tag-list"),
            "Character": self._parse_tag_list(soup, "character-tag-list"),
            "General": self._parse_tag_list(soup, "general-tag-list"),
        }

        metadata, source_url = self._parse_information(soup)
        dl_url = self._parse_download_url(soup)
        if not dl_url:
            raise RuntimeError("Original image url not found")

        artist = next(iter(tags["Artist"]), "unknown")
        clean_source = clean_source_from_url(source_url)
        ext = Path(urlparse(dl_url).path).suffix or ".jpg"
        filename = f"danbooru_{post_id}_{artist}_{clean_source}{ext}"

        return DownloadPlan(
            images=[ImageFile(url=dl_url, filename=filename)],
            source_url=url,
            tags=tags,
            artist=artist,
            original_source=source_url,
            metadata=metadata,
        )

    def _parse_tag_list(self, soup, class_name: str) -> dict[str, dict]:
        tags: dict[str, dict] = {}
        ul = soup.select_one(f"section#tag-list ul.{class_name}")
        if not ul:
            return tags
        for li in ul.find_all("li"):
            links = [a for a in li.find_all("a") if a.get_text(strip=True)]
            if len(links) >= 2:
                tag_name = links[1].get_text(strip=True)
                tags[tag_name] = {}
        return tags

    def _parse_information(self, soup) -> tuple[dict, str | None]:
        info: dict[str, str] = {}
        source_url: str | None = None
        section = soup.select_one("section#post-information")
        if not section:
            return info, source_url
        for li in section.find_all("li"):
            text = li.get_text(" ", strip=True)
            if ":" not in text:
                continue
            key, value = text.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key.lower() == "source":
                link = li.find("a", href=True)
                source_url = link["href"] if link else value
                info[key] = source_url
            else:
                info[key] = value
        return info, source_url

    def _parse_download_url(self, soup) -> str | None:
        link = soup.select_one("li#post-option-download a[href]")
        if not link:
            return None
        return link["href"]
