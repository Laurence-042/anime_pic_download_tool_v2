"""
统一的 Cookie 管理模块。

所有站点的 cookie 以 Playwright 标准格式（list[dict]）存储在 cookies/ 目录下的 JSON 文件中。
可通过 `python cookie_manager.py --site <site>` 引导用户在浏览器中登录并自动保存 cookie。

支持的站点: pixiv, twitter
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from config import PROXY
from patchright.async_api import async_playwright

COOKIES_DIR = Path("cookies")

_SITE_CONFIG: dict[str, dict[str, str]] = {
    "pixiv": {
        "login_url": "https://accounts.pixiv.net/login",
        "wait_pattern": r"(?:www\.)?pixiv\.net(?!/login)",
    },
    "twitter": {
        "login_url": "https://x.com/i/flow/login",
        "wait_pattern": r"(?:twitter|x)\.com/home",
    },
}


def _cookie_path(site: str) -> Path:
    return COOKIES_DIR / f"{site}.json"


def load_cookies(site: str) -> list[dict]:
    """从 JSON 存储中加载指定站点的 cookie 列表。"""
    path = _cookie_path(site)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_cookies(site: str, cookies: list[dict]) -> None:
    """将 cookie 列表持久化到 JSON 存储。"""
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    _cookie_path(site).write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def cookies_to_header_string(cookies: list[dict]) -> str:
    """将 Playwright 格式的 cookie 列表转换为 HTTP Cookie 请求头字符串。"""
    return "; ".join(
        f"{c['name']}={c['value']}"
        for c in cookies
        if c.get("name") and c.get("value") is not None
    )


async def login(site: str, proxy: str | None = PROXY) -> list[dict]:
    """
    打开 Chromium 浏览器，引导用户登录指定站点，登录成功后自动保存并返回 cookie。

    用法::

        import asyncio
        from cookie_manager import login
        asyncio.run(login("pixiv"))
    """
    cfg = _SITE_CONFIG.get(site)
    if cfg is None:
        raise ValueError(
            f"未知站点 {site!r}，支持的站点: {list(_SITE_CONFIG)}"
        )

    print(f"[cookie_manager] 正在为 {site} 打开浏览器，请在浏览器中完成登录。")
    print("[cookie_manager] 登录成功后浏览器将自动关闭。")

    async with async_playwright() as pw:
        launch_kwargs: dict = {"headless": False, "channel": "chrome"}
        if proxy:
            launch_kwargs["proxy"] = {"server": proxy}
        browser = await pw.chromium.launch(**launch_kwargs)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(cfg["login_url"])
        await page.wait_for_url(cfg["wait_pattern"], timeout=300_000)
        raw_cookies = await context.cookies()
        await browser.close()

    now = int(time.time())
    cookies = [
        {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
            "expires": c.get("expires", now + 86400 * 30),
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", False),
            "sameSite": c.get("sameSite", "Lax"),
        }
        for c in raw_cookies
    ]
    save_cookies(site, cookies)
    print(
        f"[cookie_manager] 已保存 {len(cookies)} 条 cookie → {_cookie_path(site)}"
    )
    return cookies


def main() -> None:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(
        description="引导登录并保存站点 Cookie（支持系统代理）"
    )
    parser.add_argument(
        "--site",
        required=True,
        choices=list(_SITE_CONFIG),
        help="要登录的站点",
    )
    args = parser.parse_args()
    asyncio.run(login(args.site))


if __name__ == "__main__":
    main()
