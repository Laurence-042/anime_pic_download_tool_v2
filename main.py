from __future__ import annotations

# 必须最先导入，在 onnxruntime/torch 被任何模块间接加载前设置 CUDA DLL 路径
import utils.cuda  # noqa: F401

import asyncio
from pathlib import Path

from pipeline import run_pipeline


def parse_input_lines(lines: list[str]) -> list[tuple[str, list[int] | None]]:
    """解析输入行为 (url, want_indices) 列表，支持 rvk 撤销。"""
    result: list[tuple[str, list[int] | None]] = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if line.lower() == "rvk":
            if result:
                result.pop()
            continue

        if not line.startswith("http"):
            continue

        content = line.split("#", 1)[0].strip()
        if not content:
            continue

        parts = content.split()
        url = parts[0]

        if len(parts) == 1:
            want_indices: list[int] | None = None
        else:
            tail = parts[1:]
            if len(tail) == 1 and tail[0].lower() == "all":
                want_indices = []
            else:
                try:
                    want_indices = [int(x) for x in tail]
                except ValueError:
                    continue

        result.append((url, want_indices))

    return result


async def main(url_list: list[tuple[str, list[int] | None]]) -> None:
    await run_pipeline(url_list)


def _load_lines_from_file(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def _load_lines_from_stdin() -> list[str]:
    print("请输入 URL（q 结束）：")
    lines: list[str] = []
    while True:
        line = input().strip()
        if line.lower() == "q":
            break
        lines.append(line)
    return lines


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        lines = _load_lines_from_file(Path(sys.argv[1]))
    else:
        lines = _load_lines_from_stdin()
    asyncio.run(main(parse_input_lines(lines)))
