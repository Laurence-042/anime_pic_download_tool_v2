from __future__ import annotations

from pathlib import Path

STATIC_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
ANIMATED_IMAGE_EXTENSIONS = {".gif", ".apng"}
ALL_IMAGE_EXTENSIONS = STATIC_IMAGE_EXTENSIONS | ANIMATED_IMAGE_EXTENSIONS


def is_comfy_image(file_path: str) -> bool:
    path = Path(file_path)
    if path.suffix.lower() != ".png":
        return False

    try:
        from PIL import Image

        with Image.open(path) as img:
            info = getattr(img, "info", {}) or {}
    except Exception:
        return False

    if any(key in info for key in ("prompt", "workflow", "parameters")):
        return True

    for value in info.values():
        if isinstance(value, str) and (
            '"class_type"' in value or '"inputs"' in value
        ):
            return True
    return False


def find_static_version(animated_path: str) -> str | None:
    path = Path(animated_path)
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = path.with_suffix(ext)
        if candidate.exists():
            return str(candidate)
    return None
