from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

PATTERNS = [
    (r"^pixiv_(?P<id>\d+)_p\d+", "https://www.pixiv.net/artworks/{id}"),
    (
        r"^twitter_(?P<author>.+)_(?P<id>\d{15,19})_\d{1,2}$",
        "https://x.com/{author}/status/{id}",
    ),
    (r"^danbooru_(?P<id>\d+)_", "https://danbooru.donmai.us/posts/{id}"),
    (
        r"^gelbooru_(?P<id>\d+)_",
        "https://gelbooru.com/index.php?page=post&s=view&id={id}",
    ),
    (r"^yandere_(?P<id>\d+)_", "https://yande.re/post/show/{id}"),
]


_PIXIV_RE = re.compile(r"https?://(?:www\.)?pixiv\.net/artworks/(?P<id>\d+)")
_TWITTER_RE = re.compile(
    r"https?://(?:twitter|x)\.com/(?P<author>[^/]+)/status/(?P<id>\d{15,19})"
)


def clean_source_from_url(url: str | None) -> str:
    if not url:
        return "unknown"

    pixiv_match = _PIXIV_RE.search(url)
    if pixiv_match:
        return f"pixiv_{pixiv_match.group('id')}"

    tw_match = _TWITTER_RE.search(url)
    if tw_match:
        return f"twitter_{tw_match.group('author')}_{tw_match.group('id')}"

    parsed = urlparse(url)
    if not parsed.netloc:
        return "unknown"

    host = parsed.netloc
    if host.startswith("www."):
        host = host[4:]
    body = (host + parsed.path).strip("/")
    if not body:
        return "unknown"
    return body.replace("/", "_")


def infer_url_from_filename(filename: str) -> str | None:
    name = Path(filename).name
    for ext in Path(name).suffixes:
        if ext == ".comfy":
            name = name.replace(".comfy", "", 1)
            break

    stem = Path(name).stem
    for pattern, template in PATTERNS:
        match = re.match(pattern, stem)
        if match:
            return template.format(**match.groupdict())
    return None
