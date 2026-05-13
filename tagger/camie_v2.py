from __future__ import annotations

import json

import numpy as np
from PIL import Image as PILImage

from .base import BaseTagger, TagResult
from utils.cuda import setup_nvidia_cuda_path

setup_nvidia_cuda_path()

try:
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download

    AVAILABLE = True
except Exception:
    ort = None
    hf_hub_download = None
    AVAILABLE = False

META_BLACKLIST = {
    "bad_id",
    "bad_pixiv_id",
    "bad_twitter_id",
    "bad_tumblr_id",
    "bad_deviantart_id",
    "bad_nicoseiga_id",
    "bad_source",
    "md5_mismatch",
    "commentary",
    "commentary_request",
    "commentary_typo",
    "partial_commentary",
    "english_commentary",
    "chinese_commentary",
    "korean_commentary",
    "translated",
    "translation_request",
    "check_translation",
    "partial_translation",
    "symbol-only_commentary",
    "character_name",
    "revision",
    "annotated",
    "third-party_edit",
    "duplicate",
    "year_2021",
    "year_2022",
    "year_2023",
    "year_2024",
    "year_2025",
    "tagme",
    "check_copyright",
    "check_character",
    "check_artist",
    "artist_request",
    "character_request",
    "copyright_request",
}

# (ort.InferenceSession, idx_to_tag, tag_to_category, img_size)
_SESSION_CACHE: ort.InferenceSession | None = None
_LABELS_CACHE: tuple[dict, dict, int] | None = None


class CamieV2Tagger(BaseTagger):
    REPO_ID = "Camais03/camie-tagger-v2"

    def _ensure_loaded(self) -> None:
        global _SESSION_CACHE, _LABELS_CACHE
        if _SESSION_CACHE is not None and _LABELS_CACHE is not None:
            return
        if not AVAILABLE or not hf_hub_download or not ort:
            raise ImportError("camie_v2 dependencies are not installed (onnxruntime, huggingface_hub)")

        model_path = hf_hub_download(self.REPO_ID, filename="camie-tagger-v2.onnx")
        metadata_path = hf_hub_download(self.REPO_ID, filename="camie-tagger-v2-metadata.json")

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        tag_mapping = metadata["dataset_info"]["tag_mapping"]
        idx_to_tag: dict[str, str] = tag_mapping["idx_to_tag"]
        tag_to_category: dict[str, str] = tag_mapping["tag_to_category"]
        img_size: int = metadata["model_info"]["img_size"]
        _LABELS_CACHE = (idx_to_tag, tag_to_category, img_size)

        providers: list[str] = []
        if "CUDAExecutionProvider" in ort.get_available_providers():
            providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")
        _SESSION_CACHE = ort.InferenceSession(model_path, providers=providers)

    @staticmethod
    def _preprocess(image: PILImage.Image, img_size: int) -> np.ndarray:
        """Letterbox resize + ImageNet normalization → (1, 3, H, W) float32."""
        if image.mode != "RGB":
            image = image.convert("RGB")

        w, h = image.size
        scale = img_size / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        image = image.resize((new_w, new_h), PILImage.Resampling.LANCZOS)

        # Pad with ImageNet-mean grey
        canvas = PILImage.new("RGB", (img_size, img_size), (124, 116, 104))
        canvas.paste(image, ((img_size - new_w) // 2, (img_size - new_h) // 2))

        arr = np.array(canvas, dtype=np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        arr = (arr - mean) / std
        return arr.transpose(2, 0, 1)[np.newaxis]  # (1, 3, H, W)

    def get_tags(self, image, threshold: float = 0.35, character_threshold: float = 0.85) -> TagResult:
        self._ensure_loaded()
        assert _SESSION_CACHE is not None and _LABELS_CACHE is not None
        idx_to_tag, tag_to_category, img_size = _LABELS_CACHE

        pil_img = self._load_image(image)
        inp = self._preprocess(pil_img, img_size)

        input_name = _SESSION_CACHE.get_inputs()[0].name
        outputs = _SESSION_CACHE.run(None, {input_name: inp})

        # outputs[0] = initial logits, outputs[1] = refined logits (preferred)
        logits = outputs[1] if len(outputs) >= 2 else outputs[0]
        probs: np.ndarray = 1.0 / (1.0 + np.exp(-logits[0]))  # sigmoid

        all_tags: dict[str, float] = {}
        character_tags: dict[str, float] = {}
        general_tags: dict[str, float] = {}
        rating: str | None = None
        best_rating_score = -1.0

        for idx, prob in enumerate(probs):
            tag_name = idx_to_tag.get(str(idx))
            if tag_name is None:
                continue
            category = tag_to_category.get(tag_name, "general")

            if category == "rating":
                if float(prob) > best_rating_score:
                    best_rating_score = float(prob)
                    rating = tag_name
                continue

            thr = character_threshold if category == "character" else threshold
            if float(prob) < thr:
                continue

            normalized = normalize_camie_tag(tag_name, category)
            if normalized is None:
                continue

            score = float(prob)
            all_tags[normalized] = score
            if category == "character":
                character_tags[normalized] = score
            elif category == "general":
                general_tags[normalized] = score

        return TagResult(tags=all_tags, character_tags=character_tags, general_tags=general_tags, rating=rating)


def normalize_camie_tag(name: str, category: str) -> str | None:
    if category == "meta" and name in META_BLACKLIST:
        return None
    if category == "artist":
        return f"creator:{name}"
    if category == "character":
        return f"character:{name}"
    if category == "copyright":
        return f"series:{name}"
    return name
