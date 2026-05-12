from __future__ import annotations

import time
from pathlib import Path


def parse_cookie_file(file_path: str) -> list[dict]:
    """解析 Netscape cookie 文件并转为 playwright add_cookies 参数。"""
    cookies: list[dict] = []
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Cookie file not found: {file_path}")

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 7:
            continue
        domain, _include_sub, cookie_path, _secure, _expiry, name, value = parts
        if not name:
            continue
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": cookie_path or "/",
                "expires": int(time.time() + 3600),
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            }
        )
    return cookies
