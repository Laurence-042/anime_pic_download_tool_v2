
# 新项目 Story：动漫图片批量下载与 Hydrus 标签工具

---

## 项目概述

一个命令行工具，用于从多个动漫图片网站批量下载图片，并为每张图片生成 Hydrus 媒体管理器兼容的 JSON 侧车标签文件。

**支持的下载源：**
- Pixiv（普通插画 + ugoira 动图）
- Twitter / X
- Danbooru
- Gelbooru
- Yande.re

---

## 依赖库

```
aiohttp>=3.9
playwright>=1.40        # 浏览器自动化（用于 Twitter）
beautifulsoup4
Pillow
apng                    # APNG 生成（ugoira 转换）
onnxruntime-gpu         # ONNX 推理（标签器）
dghs-imgutils[gpu]      # WD14 标签器封装
torch                   # Camie V2 标签器
safetensors
huggingface_hub
```

安装完 playwright 后需额外执行：
```
playwright install chromium
```

---

## 项目结构

```
project/
├── main.py                  # CLI 入口
├── config.py                # 非敏感配置（路径、并发数、限速规则、tagger 阈值）
├── user_config.py           # 用户密钥（此文件加入 .gitignore，不提交）
├── user_config.example.py   # 配置模板（提交进 git）
├── http_client.py           # HttpClient：共享 session + 限速
├── downloader.py            # download_all()：下载引擎
├── post_process.py          # 下载后处理（tagger、侧车生成、ComfyUI 重命名）
├── cookie_parser.py         # Twitter cookie 文件解析
├── telegram_source.py       # Telegram Saved Messages 输入源（可选）
├── adapters/
│   ├── __init__.py          # 注册表 + get_adapter(url) 工厂
│   ├── base.py              # BaseAdapter, DownloadPlan, ImageFile
│   ├── pixiv.py
│   ├── danbooru.py
│   ├── gelbooru.py
│   ├── yandere.py
│   └── twitter.py
├── tagger/
│   ├── __init__.py
│   ├── base.py              # BaseTagger, TagResult
│   ├── dghs.py              # WD14（via dghs-imgutils）
│   └── camie_v2.py          # Camie V2（via transformers + safetensors）
└── utils/
    ├── __init__.py
    ├── cuda.py              # NVIDIA CUDA DLL 路径设置（Windows）
    ├── image.py             # 图片扩展名常量、ComfyUI 检测
    └── filename.py          # 文件名 → 来源 URL 互推
```

---

## 用户配置

### `user_config.py`（gitignored，用户自行创建）

```python
# Pixiv：从浏览器 DevTools → Network → 任意 pixiv 请求 → Request Headers 复制整个 Cookie 字段
PIXIV_COOKIE = "PHPSESSID=xxxxx; ..."

# Twitter cookie 文件路径（使用 EditThisCookie 等插件导出的 Netscape 格式）
TWITTER_COOKIE_FILE = "x.com_cookies.txt"
```

### `user_config.example.py`（提交进 git）

```python
# 复制此文件为 user_config.py 并填入你的凭据
PIXIV_COOKIE = ""
TWITTER_COOKIE_FILE = "x.com_cookies.txt"
```

### `config.py`

```python
from pathlib import Path

DOWNLOAD_DIR = Path("./download")
DOWNLOAD_CONCURRENCY = 8

# 每域名限速：{domain: (max_concurrent_requests, min_interval_seconds)}
RATE_LIMITS: dict[str, tuple[int, float]] = {
    "www.pixiv.net":      (3, 0.5),
    "i.pximg.net":        (5, 0.3),
    "gelbooru.com":       (2, 0.5),
    "yande.re":           (2, 0.5),
    "danbooru.donmai.us": (2, 0.5),
    "pbs.twimg.com":      (5, 0.3),
}
# 未在 RATE_LIMITS 中的域名使用此默认值
DEFAULT_RATE_LIMIT = (5, 0.3)

# Tagger 阈值
WD14_THRESHOLD = 0.52
WD14_CHARACTER_THRESHOLD = 0.85
CAMIE_THRESHOLD = 0.51
CAMIE_CHARACTER_THRESHOLD = 0.85

# 代理：自动从环境变量 / Windows 注册表检测，检测不到则为 None
def _detect_proxy() -> str | None:
    import os
    for var in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy"):
        v = os.environ.get(var)
        if v:
            return v
    if os.name == "nt":
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
                if not winreg.QueryValueEx(k, "ProxyEnable")[0]:
                    return None
                server = winreg.QueryValueEx(k, "ProxyServer")[0]
            if not server:
                return None
            if "=" in server:
                parts = dict(p.split("=", 1) for p in server.split(";") if "=" in p)
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
```

---

## 核心数据模型

### `adapters/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import re

@dataclass
class ImageFile:
    """单张图片的下载信息。"""
    url: str
    filename: str                                          # 不含路径，含扩展名
    headers: dict = field(default_factory=dict)
    post_process: Callable[[Path], Path] | None = None    # 下载完成后的处理（如 ugoira → apng）

@dataclass
class DownloadPlan:
    """adapter.parse() 的返回值。"""
    images: list[ImageFile]
    source_url: str
    tags: dict = field(default_factory=dict)       # {category: {tag_name: metadata}}
    artist: str | None = None
    original_source: str | None = None             # 如 danbooru 帖子的 Source 字段值
    metadata: dict = field(default_factory=dict)

class BaseAdapter(ABC):
    URL_PATTERN: str = ""   # 子类覆盖：能匹配的 URL 正则

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return bool(cls.URL_PATTERN and re.search(cls.URL_PATTERN, url))

    @abstractmethod
    async def parse(
        self,
        url: str,
        http: "HttpClient",
        want_indices: list[int] | None = None,
        # None  → 只下第 0 张
        # []    → 下载全部
        # [0,2] → 按 0-based 下标选取
    ) -> DownloadPlan:
        ...
```

### `http_client.py`

```python
from contextlib import asynccontextmanager
from urllib.parse import urlparse
import asyncio, time
import aiohttp
from config import RATE_LIMITS, DEFAULT_RATE_LIMIT, PROXY

class HttpClient:
    """
    封装共享的 aiohttp.ClientSession，提供带限速的请求接口。
    整个程序运行周期内只创建一个实例，通过依赖注入传入各 adapter。
    """
    def __init__(self, session: aiohttp.ClientSession, proxy: str | None = PROXY):
        self._session = session
        self._proxy = proxy
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._last_request: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc

    def _get_limiter(self, domain: str) -> tuple[asyncio.Semaphore, float]:
        if domain not in self._semaphores:
            max_c, interval = RATE_LIMITS.get(domain, DEFAULT_RATE_LIMIT)
            self._semaphores[domain] = asyncio.Semaphore(max_c)
            self._last_request[domain] = 0.0
            self._locks[domain] = asyncio.Lock()
        return self._semaphores[domain], RATE_LIMITS.get(domain, DEFAULT_RATE_LIMIT)[1]

    @asynccontextmanager
    async def get(self, url: str, **kwargs):
        """
        带限速的 GET 请求 context manager。
        用法：
            async with http.get(url, headers=...) as resp:
                data = await resp.json()
        """
        domain = self._domain(url)
        sem, interval = self._get_limiter(domain)
        async with sem:
            async with self._locks[domain]:
                elapsed = time.monotonic() - self._last_request[domain]
                if elapsed < interval:
                    await asyncio.sleep(interval - elapsed)
                self._last_request[domain] = time.monotonic()
            timeout = aiohttp.ClientTimeout(connect=30, sock_read=60, total=300)
            async with self._session.get(url, proxy=self._proxy, timeout=timeout, **kwargs) as resp:
                yield resp
```

### `downloader.py`

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import asyncio
import aiohttp

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
    http: "HttpClient",
    concurrency: int = 8,
) -> list[DownloadResult]:
    """
    并发下载所有 job，返回与 jobs 等长的结果列表，不抛出异常。
    - 跳过已存在且非空的文件（仍返回 success=True）。
    - 每个 job 完成后若有 post_process 则调用之，并以其返回值更新 final_path。
    """
    sem = asyncio.Semaphore(concurrency)
    tasks = [_download_one(job, http, sem) for job in jobs]
    return await asyncio.gather(*tasks)

async def _download_one(job: DownloadJob, http: "HttpClient", sem: asyncio.Semaphore) -> DownloadResult:
    async with sem:
        # 跳过已存在文件
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
        except Exception as e:
            print(f"✗ {job.url}: {e}")
            return DownloadResult(job=job, success=False, error=e)
```

---

## 各 Adapter 规格

### Pixiv (`adapters/pixiv.py`)

**URL 匹配：** `https?://www\.pixiv\.net/artworks/(\d+)`

**解析流程：**

1. 使用 `config.build_pixiv_headers()` 构建请求头。

2. GET `https://www.pixiv.net/ajax/illust/{illust_id}`
   - 若 `body.pageCount == 1` 且非 ugoira：`body.urls.original` 即为唯一图片 URL
   - 若 `body.pageCount > 1`：GET `https://www.pixiv.net/ajax/illust/{illust_id}/pages?lang=zh`，从 `body[].urls.original` 取所有 URL
   - 若 `body.illustType == 2`（ugoira）：GET `https://www.pixiv.net/ajax/illust/{illust_id}/ugoira_meta?lang=zh`，取 `body.originalSrc`（zip URL）和 `body.frames[].delay`（毫秒列表）

3. 按 `want_indices` 过滤（0-based）。

4. 文件名：普通图片为 `pixiv_{illust_id}_p{index}.{ext}`；ugoira zip 为 `pixiv_{illust_id}_p0.zip`。

5. 所有图片下载请求额外附加 `Referer: https://www.pixiv.net/` 头。

6. Ugoira 的 `post_process` 回调（同步函数，接受 zip 文件 `Path`，返回 apng 文件 `Path`）：
   - 解压 zip 到临时目录
   - 按 delays 列表用 `apng` 库合成 APNG，输出 `pixiv_{illust_id}_p0.apng`
   - 用 Pillow 另存 GIF（`pixiv_{illust_id}_p0.gif`，帧 mode 转 RGB，供 Windows 缩略图）
   - 删除原始 zip 文件
   - 返回 apng 路径

7. 认证：依靠请求头 cookie。R-18 内容未登录时 API 返回 body 为空，检测到时抛出 `RuntimeError("Adult content, login required")`。

---

### Danbooru (`adapters/danbooru.py`)

**URL 匹配：** `https?://danbooru\.donmai\.us/posts/(\d+)`

**解析流程（HTML 解析，无需认证）：**

1. GET 帖子页面，BeautifulSoup 解析。

2. 标签提取，来自 `<section id="tag-list">`：
   - `<ul class="artist-tag-list">` → Artist 分类
   - `<ul class="copyright-tag-list">` → Copyright 分类
   - `<ul class="character-tag-list">` → Character 分类
   - `<ul class="general-tag-list">` → General 分类
   - 每个 `<li>` 包含三个有文字的子元素：wiki 链接、标签链接（文字即标签名）、计数文字

3. Statistics 来自 `<section id="post-information"> <li>` 列表，文字格式为 `Key: Value`；Source 行的值是子链接的 `href`。

4. 原图下载链接：`<li id="post-option-download"> <a href="...">` 的 `href`。

5. 文件名：`danbooru_{id}_{artist}_{clean_source}.{ext}`
   - `artist`：Artist 分类第一个标签名；空则 `unknown`
   - `clean_source`：由 Source URL 推导（见"文件名规则"一节）

---

### Gelbooru (`adapters/gelbooru.py`)

**URL 匹配：** `https?://gelbooru\.com/index\.php\?.*id=(\d+)`

**解析流程（HTML 解析，无需认证）：**

1. GET 帖子页面，BeautifulSoup 解析。

2. 侧边栏 `<section class="aside"> <li>` 按 `<b>` 或 `<h3>` 文字分组，分组名：Artist、Copyright、Metadata、Tag、Statistics、Options。
   - 每个标签 `<li>` 包含：wiki 链接（含 `<a>`）、标签链接（文字即标签名）、计数文字
   - Statistics 每行文字为 `Key: Value`
   - Options 中文字为 "Original image" 的 `<a href>` 是原图链接

3. 文件名：`gelbooru_{id}_{artist}_{clean_source}.{ext}`

---

### Yande.re (`adapters/yandere.py`)

**URL 匹配：** `https?://yande\.re/post/show/(\d+)`

**解析流程（HTML 解析，无需认证）：**

1. GET 帖子页面，BeautifulSoup 解析。

2. 标签来自 `<ul id="tag-sidebar"> <li>` 按 class 分类：
   - `tag-type-artist`、`tag-type-copyright`、`tag-type-character`、`tag-type-general`
   - 每个 `<li>` 的非空子元素：wiki 链接、标签链接（文字即标签名）、计数

3. Statistics 来自 `<div id="stats"> <ul> <li>` 列表；Source 行值为子 `<a href>`。

4. 原图链接：`<a id="highres" href="...">` 的 `href`。

5. 文件名：`yandere_{id}_{artist}_{clean_source}.{ext}`

---

### Twitter/X (`adapters/twitter.py`)

**URL 匹配：** `https?://(?:twitter|x)\.com/[^/]+/status/(\d+)`

**认证：** 用 `cookie_parser.parse_cookie_file()` 读取 Netscape cookie 文件，通过 playwright `context.add_cookies()` 注入。

**解析流程（playwright async API）：**

1. 全局 `asyncio.Semaphore(2)` 控制最多并发 2 个浏览器实例。

2. 在 semaphore 保护下：
   ```python
   async with async_playwright() as pw:
       launch_kwargs = {"headless": False}
       if PROXY:
           launch_kwargs["proxy"] = {"server": PROXY}
       browser = await pw.chromium.launch(**launch_kwargs)
       context = await browser.new_context()
       await context.add_cookies(load_twitter_cookies())
       page = await context.new_page()
   ```

3. 响应过滤条件：URL 含 `TweetDetail` 或 `TweetResultByRestId`，method 为 GET，status 为 200。

4. 并发执行 `page.goto(url)` 与 `page.wait_for_response(filter, timeout=30_000)`；捕获到目标响应后取 JSON。失败时最多重试 3 次，每次重试前 `await asyncio.sleep(2)`。

5. finally 块（各设 5 秒超时）：关闭 page → 关闭 browser。

6. 响应 JSON 解析（两种结构均需支持）：

   **结构 A**（`TweetResultByRestId`）：
   ```
   data.tweetResult.result[.tweet].legacy
   ```

   **结构 B**（`TweetDetail`）：
   ```
   data.threaded_conversation_with_injections_v2.instructions
     → [type="TimelineAddEntries"].entries
     → [entryId startswith "tweet-"].content.itemContent.tweet_results.result[.tweet].legacy
   ```

   若两种结构均解析失败（KeyError），说明是成人内容需要登录，抛出 `RuntimeError("Adult content, login required")`。

7. 从 `legacy.extended_entities.media` 或 `legacy.entities.media` 提取媒体列表：
   - `type == "photo"`：URL 为 `media_url_https + "?name=4096x4096"`
   - `type == "video"`：过滤 `content_type == "video/mp4"` 的 variants，取 bitrate 最高者的 url（去除 `?` 后的 query string）

8. 按 `want_indices`（0-based）从媒体列表选取。

9. 文件名：`twitter_{author}_{post_id}_{1based_index}.{ext}`（对外接口 0-based，文件名中 index 展示为 1-based）

---

## Cookie 解析 (`cookie_parser.py`)

解析 Netscape 格式 cookie 文件（EditThisCookie 等插件导出）：

```
# Netscape HTTP Cookie File
.twitter.com	TRUE	/	TRUE	0	auth_token	xxxxx
```

每行 tab 分隔 7 列：`domain, include_subdomains, path, secure, expiry, name, value`。

忽略空行和 `#` 开头的注释行。

返回适合传入 playwright `context.add_cookies()` 的 dict 列表：

```python
{
    "name": name,
    "value": value,
    "domain": domain,
    "path": path,
    "expires": int(time.time() + 3600),
    "httpOnly": True,
    "secure": True,
    "sameSite": "Lax",
}
```

---

## 下载后处理 (`post_process.py`)

每个文件下载完成后按顺序执行：

### 1. ComfyUI 检测与重命名

- 仅对 `.png` 文件检测。用 Pillow 读取 PNG metadata（`img.info`）：
  - 若 `info` 中存在 `prompt`、`workflow`、`parameters` 中任意键，判定为 ComfyUI。
  - 或任意 value 字符串中含 `"class_type"` 或 `"inputs"`，也判定为 ComfyUI。
- 重命名规则：`image.png` → `image.comfy.png`（路径中已含 `.comfy.` 则跳过）。

### 2. 标签提取

- 对动图（`.gif`、`.apng`），若同目录下存在同 stem 的静态版本（`.jpg`/`.png`/`.webp`），使用静态版本作为 tagger 输入。
- 依次运行 WD14 和 Camie V2（见"标签器"一节），取两者标签的**并集**。
- 若 ComfyUI 图，额外添加 `comfyui` 标签。
- 保留 `rating:*` 标签。

### 3. 来源 URL 推断

由文件名推断（见 `utils/filename.py`）。

### 4. Hydrus 侧车文件

- 路径：`{image_path}.json`（如 `download/image.png.json`）
- 格式：
  ```json
  {
      "tags": ["tag1", "tag2", "rating:safe", "comfyui"],
      "urls": ["https://www.pixiv.net/artworks/12345"]
  }
  ```
- 若已存在侧车文件则合并（取并集），不覆盖。

### 批处理 CLI

`post_process.py` 可独立运行：

```
python post_process.py ./download                    # 递归处理目录
python post_process.py ./download --dry-run          # 预览，不写入
python post_process.py ./download --skip-existing    # 跳过已有侧车的文件
python post_process.py ./download --no-recursive     # 不递归
python post_process.py ./download/image.png          # 处理单个文件
python post_process.py ./download --threshold 0.5   # 自定义阈值
```

---

## 文件名规则与 URL 互推 (`utils/filename.py`)

### 文件名格式

| 来源 | 格式 |
|------|------|
| Pixiv | `pixiv_{illust_id}_p{0based_index}.{ext}` |
| Twitter | `twitter_{author}_{post_id}_{1based_index}.{ext}` |
| Danbooru | `danbooru_{post_id}_{artist}_{clean_source}.{ext}` |
| Gelbooru | `gelbooru_{post_id}_{artist}_{clean_source}.{ext}` |
| Yande.re | `yandere_{post_id}_{artist}_{clean_source}.{ext}` |
| ComfyUI 图 | 在原扩展名前插入 `.comfy`，如 `image.comfy.png` |

### `clean_source` 生成规则

由来源 URL 生成（用于 danbooru/gelbooru/yandere 的文件名中）：

- Pixiv URL（含 `/artworks/{id}`）→ `pixiv_{id}`
- Twitter/X URL →  `twitter_{author}_{post_id}`
- 其他 URL → 去掉协议和 `www.` 前缀后，将 `/` 替换为 `_`
- 空或无法识别 → `unknown`

### 文件名 → URL 反推

```python
PATTERNS = [
    (r'^pixiv_(?P<id>\d+)_p\d+',
     'https://www.pixiv.net/artworks/{id}'),

    (r'^twitter_(?P<author>.+)_(?P<id>\d{15,19})_\d{1,2}$',
     'https://x.com/{author}/status/{id}'),

    (r'^danbooru_(?P<id>\d+)_',
     'https://danbooru.donmai.us/posts/{id}'),

    (r'^gelbooru_(?P<id>\d+)_',
     'https://gelbooru.com/index.php?page=post&s=view&id={id}'),

    (r'^yandere_(?P<id>\d+)_',
     'https://yande.re/post/show/{id}'),
]

def infer_url_from_filename(filename: str) -> str | None:
    """去除 .comfy. 修饰和扩展名后，按 PATTERNS 顺序匹配，返回 URL 或 None。"""
    ...
```

---

## 标签器 (`tagger/`)

### `tagger/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Union
from PIL import Image

@dataclass
class TagResult:
    tags: dict[str, float]             # {tag_name: confidence}，包含所有分类
    character_tags: dict[str, float]   # 角色标签子集
    general_tags: dict[str, float]     # 通用标签子集
    rating: str | None = None          # "safe" / "questionable" / "explicit"

class BaseTagger(ABC):
    @abstractmethod
    def get_tags(
        self,
        image: Union[str, "Image.Image"],
        threshold: float = 0.35,
        character_threshold: float = 0.85,
    ) -> TagResult:
        ...

    def _load_image(self, image: Union[str, "Image.Image"]) -> "Image.Image":
        from PIL import Image as PILImage
        return PILImage.open(image) if isinstance(image, str) else image
```

### `tagger/dghs.py` — WD14

使用 `imgutils.tagging.get_wd14_tags(img, model_name, general_threshold, character_threshold)`。

默认 model：`EVA02_Large`。可选：`ViT_Large`、`ViT`、`SwinV2`、`ConvNext`、`MOAT`、`ConvNextV2`。

返回 `(rating_dict, feature_dict, char_dict)`：
- `rating`：取置信度最高的 key，去掉 `rating:` 前缀
- `tags`：合并 feature_dict 和 char_dict（含置信度）
- 若 dghs-imgutils 未安装，import 时将 `AVAILABLE = False`，调用时抛出 `ImportError`

### `tagger/camie_v2.py` — Camie V2

模型：[`Camais03/camie-tagger-v2`](https://huggingface.co/Camais03/camie-tagger-v2)，safetensors 格式。

- 用单例（模块级变量）缓存已加载的模型权重和标签映射，避免重复加载。
- 首次调用时从 HuggingFace Hub 下载模型文件（`hf_hub_download`）。

**标签命名空间前缀规则（按 tag 的分类）：**

| 分类 | 前缀 |
|------|------|
| artist | `creator:` |
| character | `character:` |
| copyright | `series:` |
| general / meta | 无前缀 |

**Meta 标签黑名单**（以下标签不输出）：

```python
META_BLACKLIST = {
    "bad_id", "bad_pixiv_id", "bad_twitter_id", "bad_tumblr_id", "bad_deviantart_id",
    "bad_nicoseiga_id", "bad_source", "md5_mismatch",
    "commentary", "commentary_request", "commentary_typo", "partial_commentary",
    "english_commentary", "chinese_commentary", "korean_commentary", "translated",
    "translation_request", "check_translation", "partial_translation",
    "symbol-only_commentary", "character_name",
    "revision", "annotated", "third-party_edit", "duplicate",
    "year_2021", "year_2022", "year_2023", "year_2024", "year_2025",
    "tagme", "check_copyright", "check_character", "check_artist",
    "artist_request", "character_request", "copyright_request",
}
```

---

## 主程序 (`main.py`)

### 输入文件格式

```
# 以 # 开头的行为注释，忽略
# 不以 http 开头且非 rvk 的行也忽略（包括含时间戳的聊天记录格式行）

https://www.pixiv.net/artworks/144299291             # 无下标 → 只下第 0 张
https://www.pixiv.net/artworks/144282138 all         # all → 全部
https://www.pixiv.net/artworks/144276143 0 16        # 0-based 下标列表
https://x.com/i/status/2050190318986011004           # 只下第 0 张
rvk                                                  # 撤销上一条 URL
```

**解析规则：**

将原始行序列转换为 `(url, want_indices)` 列表的逻辑提取为独立函数 `parse_input_lines(lines: list[str]) -> list[tuple[str, list[int] | None]]`，供 `main.py` 和 `telegram_source.py` 共用。

1. 过滤：只处理以 `http` 开头或 strip 后为 `rvk`（大小写不敏感）的行。
2. `rvk` 行：从已收集列表中移除最后一项；列表为空则忽略。
3. `http` 开头的行，第一个空格前为 URL，其余为可选的下标说明：
   - 无说明 → `want_indices = None`（只下第 0 张）
   - `all` → `want_indices = []`（全部）
   - 整数列表 → `want_indices = [int(x) for x in parts]`（0-based）

### 调用方式

```
python main.py input.txt    # 从文件读取 URL 列表
python main.py              # 交互式输入，输入 q 结束
```

### 主流程

```python
async def main(url_list: list[tuple[str, list[int] | None]]):
    from config import DOWNLOAD_DIR, DOWNLOAD_CONCURRENCY, PROXY
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    import aiohttp
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        http = HttpClient(session, proxy=PROXY)

        # 1. 并发解析
        parse_tasks = [_parse_one(url, indices, http) for url, indices in url_list]
        parse_results = await asyncio.gather(*parse_tasks, return_exceptions=True)

        # 2. 展开 DownloadJob
        jobs: list[DownloadJob] = []
        failed_parse: list[tuple] = []
        for (url, indices), result in zip(url_list, parse_results):
            if isinstance(result, Exception):
                failed_parse.append((url, indices, result))
                print(f"\033[31m[PARSE FAIL]\033[0m {url}: {result}")
            else:
                for img in result.images:
                    jobs.append(DownloadJob(
                        url=img.url,
                        save_path=DOWNLOAD_DIR / img.filename,
                        headers=img.headers,
                        post_process=img.post_process,
                    ))

        # 3. 并发下载
        download_results = await download_all(jobs, http, concurrency=DOWNLOAD_CONCURRENCY)

    # 4. 汇报失败
    failed_dl = [r for r in download_results if not r.success]
    if failed_parse or failed_dl:
        print("\n======= FAILED =======")
        for url, indices, e in failed_parse:
            index_str = " ".join(map(str, indices)) if indices else ""
            print(f"{url} {index_str}".strip())
        for r in failed_dl:
            print(f"{r.job.url}  →  {r.job.save_path.name}")


async def _parse_one(url: str, indices, http: HttpClient) -> DownloadPlan:
    from adapters import get_adapter
    adapter = get_adapter(url)
    if adapter is None:
        print(f"\033[31m[NO ADAPTER]\033[0m {url}")
        return DownloadPlan(images=[], source_url=url)
    print(f"parsing {url}")
    return await adapter.parse(url, http, want_indices=indices)
```

---

## CUDA 路径设置 (`utils/cuda.py`)

在 Windows 上，`onnxruntime-gpu` 依赖 nvidia 包提供的 DLL（`cublas`、`cuda_nvrtc`、`cuda_runtime`、`cudnn`、`cufft`、`curand`、`cusolver`、`cusparse`、`nvjitlink`），这些 DLL 所在目录默认不在 PATH 中。

```python
def setup_nvidia_cuda_path():
    """
    将 site-packages/nvidia/*/bin 目录批量插入 PATH 开头。
    必须在任何 import onnxruntime 的代码执行前调用。
    优先查 venv 下的 site-packages，再查全局 site-packages。
    """
    ...
```

在 `tagger/dghs.py` 和 `tagger/camie_v2.py` 的模块顶部（import onnxruntime/torch 之前）调用此函数。

---

## 图片工具 (`utils/image.py`)

```python
STATIC_IMAGE_EXTENSIONS   = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
ANIMATED_IMAGE_EXTENSIONS  = {'.gif', '.apng'}
ALL_IMAGE_EXTENSIONS       = STATIC_IMAGE_EXTENSIONS | ANIMATED_IMAGE_EXTENSIONS

def is_comfy_image(file_path: str) -> bool:
    """
    判断 PNG 是否由 ComfyUI 生成。
    读取 PNG metadata（Pillow img.info）：
    - info 中有 'prompt'、'workflow'、'parameters' 任一键 → True
    - 任意 value 字符串含 '"class_type"' 或 '"inputs"' → True
    非 PNG 文件直接返回 False。读取失败返回 False。
    """
    ...

def find_static_version(animated_path: str) -> str | None:
    """
    在同目录下查找与 animated_path 同 stem 的静态图片。
    按 .jpg, .jpeg, .png, .webp 顺序尝试，返回第一个存在的路径，否则 None。
    """
    ...
```

---

## Adapter 注册表 (`adapters/__init__.py`)

```python
from .base import BaseAdapter, DownloadPlan, ImageFile
from .pixiv    import PixivAdapter
from .danbooru import DanbooruAdapter
from .gelbooru import GelbooruAdapter
from .yandere  import YandereAdapter
from .twitter  import TwitterAdapter

_REGISTRY: list[type[BaseAdapter]] = [
    PixivAdapter,
    DanbooruAdapter,
    GelbooruAdapter,
    YandereAdapter,
    TwitterAdapter,
]

def get_adapter(url: str) -> BaseAdapter | None:
    for cls in _REGISTRY:
        if cls.can_handle(url):
            return cls()
    return None
```

---

## 错误处理约定

- **解析失败**（网络错误、登录墙、HTML 结构变化）：在 adapter 内抛出标准 `RuntimeError` 或 `ValueError`，带有说明性消息。`_parse_one()` 不捕获，由 `asyncio.gather(return_exceptions=True)` 收集后统一打印。
- **下载失败**（非 200、超时、写文件失败）：在 `_download_one()` 内捕获为 `DownloadResult(success=False, error=e)`，不中断其他下载任务。
- **程序结束时统一打印所有失败项**，格式与输入文件相同（方便用户直接复制重试）。

---

## Telegram 输入源 (`telegram_source.py`)

作为文件输入之外的第二种输入方式。用户在手机上把 URL 发到 Telegram Saved Messages（发给自己），`telegram_source.py` 作为 userbot 轮询该会话，提取 URL 后触发下载，完成后删除对应消息。

### 依赖

```
telethon>=1.36    # Telegram MTProto 客户端
```

追加到 `requirements.txt`，但设为可选（主程序不 import 它，单独运行）。

### `user_config.py` 追加

```python
# Telegram userbot 凭据（从 https://my.telegram.org 申请）
TELEGRAM_API_ID = 0
TELEGRAM_API_HASH = ""
# Telethon session 文件名（自动创建，无需手动操作）
TELEGRAM_SESSION_FILE = "tg_session"
```

### 消息格式

与文件输入格式相同：

```
https://www.pixiv.net/artworks/144299291
https://www.pixiv.net/artworks/144282138 all
https://www.pixiv.net/artworks/144276143 0 16
rvk
```

### `rvk` 撤销语义

`rvk`（revoke 的缩写）是用于撤销上一条有效 URL 行的标记，使用场景是用户在发出一条 URL 后发现发错了，紧接着发一条 `rvk` 消息来取消它。

**解析规则（适用于文件输入和 Telegram 输入两种模式）：**

在将原始行序列转换为 `(url, want_indices)` 列表时：

1. 按顺序处理每一行。
2. 若当前行（strip 后）为 `rvk`（大小写不敏感）：从已收集的 URL 列表中移除最后一项；若列表为空则忽略。
3. `rvk` 本身不加入 URL 列表。
4. 非 `http` 开头且非 `rvk` 的行直接忽略。

**示例：**

```
https://www.pixiv.net/artworks/111   # 加入队列
https://www.pixiv.net/artworks/222   # 加入队列
rvk                                  # 移除 222
https://www.pixiv.net/artworks/333   # 加入队列
# 最终队列：[111, 333]
```

### `telegram_source.py` 运行模式

```
python telegram_source.py           # 持续监听模式：实时处理新消息
python telegram_source.py --once    # 单次模式：处理当前所有未读消息后退出
```

**行为规范：**

1. 启动时使用 `TELEGRAM_SESSION_FILE` 登录（首次运行会交互式要求输入手机号和验证码，之后复用 session 文件无需重复登录）。

2. 获取 Saved Messages 中的消息，**按时间顺序（从旧到新）**处理，提取 URL 列表（含 `rvk` 处理）。

3. 将提取出的 URL 列表传给与 `main.py` 相同的 pipeline（`_parse_one` + `download_all`），复用全部下载逻辑。

4. 无论成功还是失败，处理完成后删除对应的 Telegram 消息（`message.delete()`）。失败项另行打印到终端，不保留消息作为重试机制（用户可以重新发）。

5. 持续监听模式下，用 `client.add_event_handler` 监听 `events.NewMessage(from_users='me')`，每条新消息到达时触发处理（仍按 `rvk` 语义与当前待处理缓冲区联动）。

### 与 `main.py` 的关系

`telegram_source.py` 直接 import 并调用 `main.py` 中的 `_parse_one`、`download_all`、`HttpClient` 等组件，不重复实现下载逻辑。`main.py` 本身不感知 Telegram 的存在。

---

## 实现顺序

1. `utils/`（cuda、image、filename）
2. `config.py` + `user_config.example.py`
3. `adapters/base.py`（数据类只，无业务逻辑）
4. `http_client.py`
5. `downloader.py`
6. Danbooru、Gelbooru、Yande.re adapters（无需认证，最简单）
7. Pixiv adapter（含 ugoira post_process）
8. `tagger/base.py` → `tagger/dghs.py` → `tagger/camie_v2.py`
9. `post_process.py`（含批处理 CLI）
10. `cookie_parser.py`
11. Twitter adapter（playwright，依赖前置步骤最多）
12. `main.py`（最后组装整个 pipeline，同时将 `rvk` 解析逻辑提取为独立函数供 `telegram_source.py` 复用）
13. `telegram_source.py`

每步完成后项目应保持可运行（Twitter 在步骤 11 前不可用，Telegram 在步骤 13 前不可用）。
