from __future__ import annotations

import argparse
import json
from pathlib import Path

from config import (
    CAMIE_CHARACTER_THRESHOLD,
    CAMIE_THRESHOLD,
    WD14_CHARACTER_THRESHOLD,
    WD14_THRESHOLD,
)
from tagger.camie_v2 import CamieV2Tagger
from tagger.dghs import WD14Tagger
from utils.filename import infer_url_from_filename
from utils.image import ALL_IMAGE_EXTENSIONS, ANIMATED_IMAGE_EXTENSIONS, find_static_version, is_comfy_image


def _merge_sidecar(sidecar_path: Path, tags: set[str], urls: set[str], dry_run: bool):
    existing = {"tags": [], "urls": []}
    if sidecar_path.exists():
        try:
            existing = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {"tags": [], "urls": []}

    merged_tags = sorted(set(existing.get("tags", [])) | tags)
    merged_urls = sorted(set(existing.get("urls", [])) | urls)

    payload = {"tags": merged_tags, "urls": merged_urls}
    if dry_run:
        print(f"[DRY] {sidecar_path}: {payload}")
        return
    sidecar_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )


def _pick_tagger_input(path: Path) -> Path:
    if path.suffix.lower() in ANIMATED_IMAGE_EXTENSIONS:
        static = find_static_version(str(path))
        if static:
            return Path(static)
    return path


def _collect_tags(path: Path, threshold: float):
    tags: set[str] = set()
    source_for_tagger = _pick_tagger_input(path)

    try:
        wd = WD14Tagger().get_tags(
            str(source_for_tagger),
            threshold=threshold or WD14_THRESHOLD,
            character_threshold=WD14_CHARACTER_THRESHOLD,
        )
        tags.update(wd.tags.keys())
        if wd.rating:
            tags.add(f"rating:{wd.rating}")
    except Exception as exc:
        print(f"[WD14] {path.name}: {exc}")

    try:
        camie = CamieV2Tagger().get_tags(
            str(source_for_tagger),
            threshold=threshold or CAMIE_THRESHOLD,
            character_threshold=CAMIE_CHARACTER_THRESHOLD,
        )
        tags.update(camie.tags.keys())
        if camie.rating:
            tags.add(f"rating:{camie.rating}")
    except Exception as exc:
        print(f"[CAMIE] {path.name}: {exc}")

    return tags


def _maybe_rename_comfy(path: Path, dry_run: bool) -> Path:
    if path.suffix.lower() != ".png" or ".comfy." in path.name:
        return path
    if not is_comfy_image(str(path)):
        return path
    new_path = path.with_name(f"{path.stem}.comfy{path.suffix}")
    if dry_run:
        print(f"[DRY] rename {path} -> {new_path}")
        return new_path
    if new_path.exists():
        path.unlink()
        return new_path
    path.rename(new_path)
    return new_path


def process_file(path: Path, dry_run: bool = False, skip_existing: bool = False, threshold: float | None = None):
    if path.suffix.lower() not in ALL_IMAGE_EXTENSIONS:
        return

    path = _maybe_rename_comfy(path, dry_run=dry_run)
    sidecar = Path(f"{path}.json")
    if skip_existing and sidecar.exists():
        return

    tags = _collect_tags(path, threshold or WD14_THRESHOLD)
    if ".comfy." in path.name:
        tags.add("comfyui")

    source_url = infer_url_from_filename(path.name)
    urls = {source_url} if source_url else set()
    _merge_sidecar(sidecar, tags, urls, dry_run=dry_run)


def iter_targets(root: Path, recursive: bool):
    if root.is_file():
        yield root
        return

    pattern = "**/*" if recursive else "*"
    for p in root.glob(pattern):
        if p.is_file() and p.suffix.lower() in ALL_IMAGE_EXTENSIONS:
            yield p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--threshold", type=float, default=None)
    args = parser.parse_args()

    target = Path(args.target)
    for p in iter_targets(target, recursive=not args.no_recursive):
        process_file(
            p,
            dry_run=args.dry_run,
            skip_existing=args.skip_existing,
            threshold=args.threshold,
        )


if __name__ == "__main__":
    main()
