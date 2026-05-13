from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable
import asyncio

if TYPE_CHECKING:
    from http_client import HttpClient


@dataclass
class DownloadJob:
    url: str
    save_path: Path
    headers: dict = field(default_factory=dict)
    post_process: Callable[[Path], Path] | None = None


@dataclass
class DownloadResult:
    job: DownloadJob
    success: bool
    final_path: Path | None = None
    error: Exception | None = None


async def download_all(
    jobs: list[DownloadJob],
    http: HttpClient,
    concurrency: int = 8,
) -> list[DownloadResult]:
    sem = asyncio.Semaphore(concurrency)
    tasks = [_download_one(job, http, sem) for job in jobs]
    return await asyncio.gather(*tasks)


async def _download_one(job: DownloadJob, http: HttpClient, sem: asyncio.Semaphore) -> DownloadResult:
    async with sem:
        if job.save_path.exists() and job.save_path.stat().st_size > 0:
            final = job.post_process(job.save_path) if job.post_process else job.save_path
            return DownloadResult(job=job, success=True, final_path=final)
        try:
            async with http.get(job.url, headers=job.headers) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}: {job.url}")
                content = await resp.read()
            job.save_path.parent.mkdir(parents=True, exist_ok=True)
            job.save_path.write_bytes(content)
            final = job.post_process(job.save_path) if job.post_process else job.save_path
            print(f"✓ {job.save_path.name}")
            return DownloadResult(job=job, success=True, final_path=final)
        except Exception as exc:
            print(f"✗ {job.url}: {exc}")
            return DownloadResult(job=job, success=False, error=exc)
