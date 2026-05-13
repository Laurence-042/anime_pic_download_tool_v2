from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable
import re

if TYPE_CHECKING:
    from http_client import HttpClient


@dataclass
class ImageFile:
    """单张图片的下载信息。"""

    url: str
    filename: str
    headers: dict = field(default_factory=dict)
    post_process: Callable[[Path], Path] | None = None


@dataclass
class DownloadPlan:
    """adapter.parse() 的返回值。"""

    images: list[ImageFile]
    source_url: str
    tags: dict = field(default_factory=dict)
    artist: str | None = None
    original_source: str | None = None
    metadata: dict = field(default_factory=dict)


class BaseAdapter(ABC):
    URL_PATTERN: str = ""

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return bool(cls.URL_PATTERN and re.search(cls.URL_PATTERN, url))

    @abstractmethod
    async def parse(
        self,
        url: str,
        http: HttpClient,
        want_indices: list[int] | None = None,
    ) -> DownloadPlan:
        ...
