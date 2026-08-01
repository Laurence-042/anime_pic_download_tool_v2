from __future__ import annotations

import argparse
import asyncio

from main import parse_input_lines
from pipeline import run_pipeline


async def process_messages(messages):
    lines = [m.raw_text or "" for m in messages]
    parsed = parse_input_lines(lines)
    if parsed:
        await run_pipeline(parsed)
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
