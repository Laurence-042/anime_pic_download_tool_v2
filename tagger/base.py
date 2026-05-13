from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Union


@dataclass
class TagResult:
    tags: dict[str, float]
    character_tags: dict[str, float]
    general_tags: dict[str, float]
    rating: str | None = None


class BaseTagger(ABC):
    @abstractmethod
    def get_tags(
        self,
        image: Union[str, "Image.Image"],
        threshold: float = 0.35,
        character_threshold: float = 0.85,
    ) -> TagResult:
        ...

    def _load_image(self, image: Union[str, "Image.Image"]):
        from PIL import Image as PILImage

        return PILImage.open(image) if isinstance(image, str) else image
