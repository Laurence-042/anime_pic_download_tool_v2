from .base import BaseAdapter, DownloadPlan, ImageFile
from .danbooru import DanbooruAdapter
from .gelbooru import GelbooruAdapter
from .pixiv import PixivAdapter
from .twitter import TwitterAdapter
from .yandere import YandereAdapter

_REGISTRY: list[type[BaseAdapter]] = [
    PixivAdapter,
    DanbooruAdapter,
    GelbooruAdapter,
    YandereAdapter,
    TwitterAdapter,
]


def get_adapter(url: str) -> BaseAdapter | None:
    for cls in _REGISTRY:
        if cls.can_handle(url):
            return cls()
    return None


__all__ = ["BaseAdapter", "DownloadPlan", "ImageFile", "get_adapter"]
