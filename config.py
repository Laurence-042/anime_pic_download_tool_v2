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
    import os

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


def build_pixiv_headers() -> dict:
    """构建 Pixiv 请求头，cookie 从 user_config 读取。"""
    try:
        from user_config import PIXIV_COOKIE
    except ImportError:
        PIXIV_COOKIE = ""

    return {
        "accept": "*/*",
        "accept-encoding": "gzip",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "cookie": PIXIV_COOKIE,
        "referer": "https://www.pixiv.net/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
