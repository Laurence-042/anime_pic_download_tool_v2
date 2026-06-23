from __future__ import annotations

import os
from pathlib import Path

DOWNLOAD_DIR = Path("./download")
DOWNLOAD_CONCURRENCY = 8

RATE_LIMITS: dict[str, tuple[int, float]] = {
    "www.pixiv.net": (3, 0.5),
    "i.pximg.net": (5, 0.3),
    "gelbooru.com": (2, 0.5),
    "yande.re": (2, 0.5),
    "danbooru.donmai.us": (2, 0.5),
    "pbs.twimg.com": (5, 0.3),
}
DEFAULT_RATE_LIMIT = (5, 0.3)

WD14_THRESHOLD = 0.52
WD14_CHARACTER_THRESHOLD = 0.85
CAMIE_THRESHOLD = 0.51
CAMIE_CHARACTER_THRESHOLD = 0.85


def _detect_proxy() -> str | None:
    for var in (
        "HTTPS_PROXY",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
        "HTTP_PROXY",
        "http_proxy",
    ):
        value = os.environ.get(var)
        if value:
            return value

    if os.name == "nt":
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                if not winreg.QueryValueEx(key, "ProxyEnable")[0]:
                    return None
                server = winreg.QueryValueEx(key, "ProxyServer")[0]
            if not server:
                return None
            if "=" in server:
                parts = dict(
                    p.split("=", 1) for p in server.split(";") if "=" in p
                )
                server = parts.get("https") or parts.get("http") or ""
            if not server:
                return None
            return server if "://" in server else f"http://{server}"
        except Exception:
            return None
    return None


PROXY = _detect_proxy()

# ── SSL ─────────────────────────────────────────────────────────────────────
# 本地代理(如 Clash)对部分域名做 MITM 时,其注入的 CA 可能过期,导致
# `[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired`。
#   True  -> 使用 certifi 的 CA 包严格校验(默认,最安全)
#   False -> 关闭证书校验(仅在自签/过期 MITM 代理环境下使用)
SSL_VERIFY = True
try:
    from user_config import SSL_VERIFY as _SSL_VERIFY  # noqa: F401
    SSL_VERIFY = _SSL_VERIFY
except Exception:
    pass
