from __future__ import annotations

import asyncio
from pathlib import Path

import aiohttp

from adapters import DownloadPlan, get_adapter
from config import DOWNLOAD_CONCURRENCY, DOWNLOAD_DIR, PROXY
from downloader import DownloadJob, download_all
from http_client import HttpClient
from post_process import process_file


async def _parse_one(url: str, indices: list[int] | None, http: HttpClient) -> DownloadPlan:
    adapter = get_adapter(url)
    if adapter is None:
        print(f"\033[31m[NO ADAPTER]\033[0m {url}")
        return DownloadPlan(images=[], source_url=url)
    print(f"parsing {url}")
    return await adapter.parse(url, http, want_indices=indices)


async def run_pipeline(url_list: list[tuple[str, list[int] | None]]) -> None:
    """统一下载管线：解析 → 下载 → 后处理(tag/侧车)。

    供 CLI (main.py) 与 Telegram (telegram_source.py) 共用。
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        http = HttpClient(session, proxy=PROXY)

        parse_tasks = [_parse_one(url, indices, http) for url, indices in url_list]
        parse_results = await asyncio.gather(*parse_tasks, return_exceptions=True)

        jobs: list[DownloadJob] = []
        skipped_paths: list[Path] = []
        failed_parse: list[tuple[str, list[int] | None, Exception]] = []
        for (url, indices), parsed in zip(url_list, parse_results):
            if isinstance(parsed, Exception):
                failed_parse.append((url, indices, parsed))
                print(f"\033[31m[PARSE FAIL]\033[0m {url}: {parsed}")
                continue
            for img in parsed.images:
                save_path = DOWNLOAD_DIR / img.filename
                if save_path.exists() and save_path.stat().st_size > 0:
                    skipped_paths.append(save_path)
                else:
                    jobs.append(
                        DownloadJob(
                            url=img.url,
                            save_path=save_path,
                            headers=img.headers,
                            post_process=img.post_process,
                            source_url=url,
                            source_indices=indices,
                        )
                    )

        download_results = await download_all(jobs, http, concurrency=DOWNLOAD_CONCURRENCY)

    for path in skipped_paths:
        process_file(path, skip_existing=True)

    for item in download_results:
        if item.success and item.final_path is not None:
            process_file(item.final_path, skip_existing=True)

    failed_dl = [item for item in download_results if not item.success]
    if failed_parse or failed_dl:
        print("\n======= FAILED =======")
        for url, indices, _exc in failed_parse:
            index_str = " ".join(map(str, indices)) if indices else ""
            print(f"{url} {index_str}".strip())
        seen: set[tuple] = set()
        for item in failed_dl:
            key = (item.job.source_url, tuple(item.job.source_indices) if item.job.source_indices is not None else None)
            if key in seen:
                continue
            seen.add(key)
            index_str = " ".join(map(str, item.job.source_indices)) if item.job.source_indices else ""
            print(f"{item.job.source_url} {index_str}".strip())
