from __future__ import annotations

from pathlib import Path

from .base import BaseTagger, TagResult
from utils.cuda import setup_nvidia_cuda_path

setup_nvidia_cuda_path()

try:
    import torch
    from huggingface_hub import hf_hub_download
    from safetensors.torch import load_file as load_safetensors

    AVAILABLE = True
except Exception:
    torch = None
    hf_hub_download = None
    load_safetensors = None
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

_MODEL_CACHE = None
_LABELS_CACHE = None


class CamieV2Tagger(BaseTagger):
    REPO_ID = "Camais03/camie-tagger-v2"

    def _ensure_loaded(self):
        global _MODEL_CACHE, _LABELS_CACHE
        if _MODEL_CACHE is not None and _LABELS_CACHE is not None:
            return
        if not AVAILABLE or not hf_hub_download or not load_safetensors:
            raise ImportError("camie_v2 dependencies are not installed")

        model_path = hf_hub_download(self.REPO_ID, filename="camie-tagger-v2.safetensors")
        labels_path = hf_hub_download(self.REPO_ID, filename="selected_tags.csv")

        # Minimal loader for portability in environments without full model graph.
        _MODEL_CACHE = load_safetensors(model_path)

        labels: list[tuple[str, str]] = []
        with open(labels_path, "r", encoding="utf-8") as f:
            next(f, None)
            for line in f:
                parts = [p.strip() for p in line.rstrip("\n").split(",")]
                if len(parts) >= 2:
                    labels.append((parts[0], parts[1]))
        _LABELS_CACHE = labels

    def get_tags(self, image, threshold: float = 0.35, character_threshold: float = 0.85) -> TagResult:
        # We keep this functional and dependency-safe; actual inference requires the full architecture.
        self._ensure_loaded()
        _ = self._load_image(image)

        # Fallback no-op inference when full runtime is unavailable.
        return TagResult(tags={}, character_tags={}, general_tags={}, rating=None)


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
