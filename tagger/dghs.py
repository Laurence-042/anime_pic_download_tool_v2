from __future__ import annotations

from .base import BaseTagger, TagResult
from utils.cuda import setup_nvidia_cuda_path

setup_nvidia_cuda_path()

try:
    from imgutils.tagging import get_wd14_tags

    AVAILABLE = True
except Exception:
    get_wd14_tags = None
    AVAILABLE = False


class WD14Tagger(BaseTagger):
    def __init__(self, model_name: str = "EVA02_Large"):
        self.model_name = model_name

    def get_tags(self, image, threshold: float = 0.35, character_threshold: float = 0.85) -> TagResult:
        if not AVAILABLE or get_wd14_tags is None:
            raise ImportError("dghs-imgutils is not installed")

        img = self._load_image(image)
        rating_dict, feature_dict, char_dict = get_wd14_tags(
            img,
            model_name=self.model_name,
            general_threshold=threshold,
            character_threshold=character_threshold,
        )
        rating = None
        if rating_dict:
            rating = max(rating_dict.items(), key=lambda x: x[1])[0].removeprefix("rating:")
        tags = {**feature_dict, **char_dict}
        return TagResult(
            tags=tags,
            character_tags=char_dict,
            general_tags=feature_dict,
            rating=rating,
        )
