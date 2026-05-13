from __future__ import annotations

import os
import site
from pathlib import Path


def _candidate_site_packages() -> list[Path]:
    candidates: list[Path] = []

    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        candidates.extend(
            [
                Path(venv) / "Lib" / "site-packages",
                Path(venv) / "lib" / "site-packages",
                Path(venv) / "lib" / f"python{os.sys.version_info.major}.{os.sys.version_info.minor}" / "site-packages",
            ]
        )

    for p in site.getsitepackages() + [site.getusersitepackages()]:
        candidates.append(Path(p))

    seen: set[str] = set()
    unique: list[Path] = []
    for item in candidates:
        key = str(item.resolve()) if item.exists() else str(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def setup_nvidia_cuda_path():
    """
    将 site-packages/nvidia/*/bin 目录批量插入 PATH 开头。
    必须在任何 import onnxruntime 的代码执行前调用。
    """
    if os.name != "nt":
        return

    bin_paths: list[str] = []
    for sp in _candidate_site_packages():
        nvidia_dir = sp / "nvidia"
        if not nvidia_dir.exists():
            continue
        for child in nvidia_dir.iterdir():
            bin_dir = child / "bin"
            if bin_dir.exists() and bin_dir.is_dir():
                bin_paths.append(str(bin_dir))

    if not bin_paths:
        return

    current = os.environ.get("PATH", "")
    current_parts = current.split(os.pathsep) if current else []
    merged = bin_paths + [p for p in current_parts if p and p not in bin_paths]
    os.environ["PATH"] = os.pathsep.join(merged)
