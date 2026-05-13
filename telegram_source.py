from __future__ import annotations

import argparse
import asyncio

import aiohttp

from config import DOWNLOAD_CONCURRENCY, DOWNLOAD_DIR, PROXY
from downloader import DownloadJob, download_all
from http_client import HttpClient
from main import _parse_one, parse_input_lines


async def _run_pipeline(url_list: list[tuple[str, list[int] | None]]):
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        http = HttpClient(session, proxy=PROXY)

        parse_tasks = [_parse_one(url, indices, http) for url, indices in url_list]
        parse_results = await asyncio.gather(*parse_tasks, return_exceptions=True)

        jobs: list[DownloadJob] = []
        for (url, _indices), parsed in zip(url_list, parse_results):
            if isinstance(parsed, Exception):
                print(f"[PARSE FAIL] {url}: {parsed}")
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

        await download_all(jobs, http, concurrency=DOWNLOAD_CONCURRENCY)


async def process_messages(messages):
    lines = [m.raw_text or "" for m in messages]
    parsed = parse_input_lines(lines)
    if parsed:
        await _run_pipeline(parsed)
    for msg in messages:
        await msg.delete()


async def run(once: bool = False):
    try:
        from telethon import TelegramClient, events
        from telethon.tl.types import PeerUser
        from user_config import (
            TELEGRAM_API_HASH,
            TELEGRAM_API_ID,
            TELEGRAM_SESSION_FILE,
        )
    except Exception as exc:
        raise RuntimeError(f"Telegram source unavailable: {exc}")

    from config import DOWNLOAD_DIR

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)

    async with client:
        me = await client.get_me()

        async def _handle_batch(batch_messages):
            if not batch_messages:
                return
            batch_messages.sort(key=lambda m: m.date)
            await process_messages(batch_messages)

        if once:
            msgs = await client.get_messages("me", limit=200)
            await _handle_batch(list(msgs))
            return

        pending: list = []

        @client.on(events.NewMessage(from_users="me"))
        async def handler(event):
            nonlocal pending
            pending.append(event.message)
            await _handle_batch(pending)
            pending = []

        print(f"Listening Saved Messages as {getattr(me, 'username', me.id)}")
        await client.run_until_disconnected()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(once=args.once))


if __name__ == "__main__":
    main()
