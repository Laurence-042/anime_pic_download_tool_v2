from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from zipfile import ZipFile

from apng import APNG
from PIL import Image

from .base import BaseAdapter, DownloadPlan, ImageFile
from cookie_manager import cookies_to_header_string, load_cookies

if TYPE_CHECKING:
    from http_client import HttpClient


def _build_pixiv_headers() -> dict:
    return {
        "accept": "*/*",
        "accept-encoding": "gzip",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "cookie": cookies_to_header_string(load_cookies("pixiv")),
        "referer": "https://www.pixiv.net/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }


class PixivAdapter(BaseAdapter):
    URL_PATTERN = r"https?://www\.pixiv\.net/artworks/(\d+)"

    async def parse(self, url: str, http: HttpClient, want_indices: list[int] | None = None) -> DownloadPlan:
        match = re.search(self.URL_PATTERN, url)
        if not match:
            raise ValueError(f"Invalid pixiv url: {url}")
        illust_id = match.group(1)
        headers = _build_pixiv_headers()

        async with http.get(f"https://www.pixiv.net/ajax/illust/{illust_id}", headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to fetch pixiv illust: HTTP {resp.status}")
            data = await resp.json()

        body = data.get("body")
        if not body:
            raise RuntimeError("Adult content, login required")

        images: list[ImageFile] = []
        if body.get("illustType") == 2:
            images.extend(await self._parse_ugoira(illust_id, http, headers, want_indices))
        elif int(body.get("pageCount", 1)) <= 1:
            original = body.get("urls", {}).get("original")
            if not original:
                raise RuntimeError("Pixiv original image url not found")
            images = self._build_static_images(illust_id, [original], want_indices)
        else:
            async with http.get(
                f"https://www.pixiv.net/ajax/illust/{illust_id}/pages?lang=zh",
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Failed to fetch pixiv pages: HTTP {resp.status}")
                pages_data = await resp.json()
            urls = [item.get("urls", {}).get("original") for item in pages_data.get("body", [])]
            urls = [u for u in urls if u]
            images = self._build_static_images(illust_id, urls, want_indices)

        return DownloadPlan(images=images, source_url=url)

    def _build_static_images(self, illust_id: str, urls: list[str], want_indices: list[int] | None) -> list[ImageFile]:
        selected = self._apply_indices(urls, want_indices)
        images: list[ImageFile] = []
        for idx, image_url in selected:
            ext = Path(urlparse(image_url).path).suffix or ".jpg"
            images.append(
                ImageFile(
                    url=image_url,
                    filename=f"pixiv_{illust_id}_p{idx}{ext}",
                    headers={"Referer": "https://www.pixiv.net/"},
                )
            )
        return images

    async def _parse_ugoira(self, illust_id: str, http: HttpClient, headers: dict, want_indices: list[int] | None) -> list[ImageFile]:
        if want_indices not in (None, [], [0]):
            return []

        async with http.get(
            f"https://www.pixiv.net/ajax/illust/{illust_id}/ugoira_meta?lang=zh",
            headers=headers,
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to fetch pixiv ugoira meta: HTTP {resp.status}")
            meta_data = await resp.json()

        body = meta_data.get("body") or {}
        zip_url = body.get("originalSrc")
        frames = body.get("frames") or []
        if not zip_url:
            raise RuntimeError("Pixiv ugoira source zip not found")

        delays = [int(frame.get("delay", 100)) for frame in frames] or [100]

        def _post_process(zip_path: Path) -> Path:
            return self._convert_ugoira_zip(zip_path, delays)

        return [
            ImageFile(
                url=zip_url,
                filename=f"pixiv_{illust_id}_p0.zip",
                headers={"Referer": "https://www.pixiv.net/"},
                post_process=_post_process,
            )
        ]

    def _convert_ugoira_zip(self, zip_path: Path, delays: list[int]) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="pixiv_ugoira_"))
        try:
            with ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_dir)

            frames = sorted([p for p in temp_dir.iterdir() if p.is_file()])
            if not frames:
                raise RuntimeError("Ugoira zip has no frames")

            apng_path = zip_path.with_suffix(".apng")
            apng = APNG()
            for i, frame in enumerate(frames):
                delay = delays[i] if i < len(delays) else delays[-1]
                apng.append_file(str(frame), delay=delay)
            apng.save(str(apng_path))

            gif_path = zip_path.with_suffix(".gif")
            pil_frames = [Image.open(frame).convert("RGB") for frame in frames]
            duration = delays + [delays[-1]] * max(0, len(pil_frames) - len(delays))
            pil_frames[0].save(
                gif_path,
                save_all=True,
                append_images=pil_frames[1:],
                loop=0,
                duration=duration[: len(pil_frames)],
            )

            zip_path.unlink(missing_ok=True)
            return apng_path
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _apply_indices(self, urls: list[str], want_indices: list[int] | None) -> list[tuple[int, str]]:
        if want_indices is None:
            indices = [0]
        elif want_indices == []:
            indices = list(range(len(urls)))
        else:
            indices = want_indices

        selected = []
        for idx in indices:
            if 0 <= idx < len(urls):
                selected.append((idx, urls[idx]))
        return selected
