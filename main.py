from __future__ import annotations

# 必须最先导入，在 onnxruntime/torch 被任何模块间接加载前设置 CUDA DLL 路径
import utils.cuda  # noqa: F401

import asyncio
from pathlib import Path

import aiohttp

from adapters import DownloadPlan, get_adapter
from config import DOWNLOAD_CONCURRENCY, DOWNLOAD_DIR, PROXY
from downloader import DownloadJob, download_all
from http_client import HttpClient
from post_process import process_file


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


async def _parse_one(url: str, indices: list[int] | None, http: HttpClient) -> DownloadPlan:
    adapter = get_adapter(url)
    if adapter is None:
        print(f"\033[31m[NO ADAPTER]\033[0m {url}")
        return DownloadPlan(images=[], source_url=url)
    print(f"parsing {url}")
    return await adapter.parse(url, http, want_indices=indices)


async def main(url_list: list[tuple[str, list[int] | None]]) -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        http = HttpClient(session, proxy=PROXY)

        parse_tasks = [_parse_one(url, indices, http) for url, indices in url_list]
        parse_results = await asyncio.gather(*parse_tasks, return_exceptions=True)

        jobs: list[DownloadJob] = []
        failed_parse: list[tuple[str, list[int] | None, Exception]] = []
        for (url, indices), parsed in zip(url_list, parse_results):
            if isinstance(parsed, Exception):
                failed_parse.append((url, indices, parsed))
                print(f"\033[31m[PARSE FAIL]\033[0m {url}: {parsed}")
                continue
            for img in parsed.images:
                jobs.append(
                    DownloadJob(
                        url=img.url,
                        save_path=DOWNLOAD_DIR / img.filename,
                        headers=img.headers,
                        post_process=img.post_process,
                    )
                )

        download_results = await download_all(jobs, http, concurrency=DOWNLOAD_CONCURRENCY)

    for item in download_results:
        if item.success and item.final_path is not None:
            process_file(item.final_path, skip_existing=True)

    failed_dl = [item for item in download_results if not item.success]
    if failed_parse or failed_dl:
        print("\n======= FAILED =======")
        for url, indices, _exc in failed_parse:
            index_str = " ".join(map(str, indices)) if indices else ""
            print(f"{url} {index_str}".strip())
        for item in failed_dl:
            print(f"{item.job.url}  →  {item.job.save_path.name}")


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
