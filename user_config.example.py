# 复制此文件为 user_config.py 并填入你的凭据

# ── Cookie ──────────────────────────────────────────────────────────────────
# 运行 `python cookie_manager.py --site pixiv` 或 `--site twitter`
# 程序会打开浏览器引导登录，cookie 自动保存到 cookies/<site>.json。

# ── Telegram userbot ────────────────────────────────────────────────────────
# 凭据从 https://my.telegram.org 申请
TELEGRAM_API_ID = 0
TELEGRAM_API_HASH = ""
# Telethon session 文件名（自动创建，无需手动操作）
TELEGRAM_SESSION_FILE = "tg_session"

# ── SSL ─────────────────────────────────────────────────────────────────────
# 本地代理(如 Clash)对部分域名做 MITM 时,其注入的 CA 可能过期,导致
# `[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired`。
#   True  -> 使用 certifi 的 CA 包严格校验(默认,最安全)
#   False -> 关闭证书校验(仅在自签/过期 MITM 代理环境下使用)
SSL_VERIFY = True
