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


_CUDA_PATH_SETUP_DONE = False


def setup_nvidia_cuda_path():
    """
    将 CUDA 相关 DLL 目录插入 PATH 开头，必须在 import onnxruntime 之前调用。

    搜索两类来源：
    - site-packages/nvidia/*/bin/  （nvidia-*-cu12 独立 wheel 方式）
    - site-packages/torch/lib/     （PyTorch 自带 CUDA bundle 方式）
    """
    global _CUDA_PATH_SETUP_DONE
    if _CUDA_PATH_SETUP_DONE:
        return
    _CUDA_PATH_SETUP_DONE = True

    if os.name != "nt":
        return

    bin_paths: list[str] = []
    for sp in _candidate_site_packages():
        # nvidia-*-cu12 独立 wheel: site-packages/nvidia/<pkg>/bin/
        nvidia_dir = sp / "nvidia"
        if nvidia_dir.exists():
            for child in nvidia_dir.iterdir():
                bin_dir = child / "bin"
                if bin_dir.exists() and bin_dir.is_dir():
                    bin_paths.append(str(bin_dir))

        # PyTorch 自带 CUDA bundle: site-packages/torch/lib/
        torch_lib = sp / "torch" / "lib"
        if torch_lib.exists() and torch_lib.is_dir():
            bin_paths.append(str(torch_lib))

    if not bin_paths:
        return

    current = os.environ.get("PATH", "")
    current_parts = current.split(os.pathsep) if current else []
    merged = bin_paths + [p for p in current_parts if p and p not in bin_paths]
    os.environ["PATH"] = os.pathsep.join(merged)


# 模块导入时自动执行，确保早于任何 onnxruntime import
setup_nvidia_cuda_path()
