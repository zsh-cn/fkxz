APP_NAME = "文件分块下载"
APP_VERSION = "4.0.2"
APP_LICENSE = "MPL-2.0"
APP_HOMEPAGE = "https://fkxz.zhshh.cn"

APP_ID_MAIN = "fkxz.main"
APP_ID_SPLITTER = "fkxz.splitter"
APP_ID_DOWNLOADER = "fkxz.downloader"

IMPERSONATE_TARGETS = ("chrome131", "chrome124", "chrome120", "chrome110", "chrome")

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Priority": "u=0, i",
}

HTTP_POOL_SIZE = 32
CONNECT_TIMEOUT = 15
CHUNK_TIMEOUT = 30

CHUNK_BUFFER = 65536
IO_BLOCK_SIZE = 1024 * 1024
PROGRESS_INTERVAL = 0.15
SPEED_MIN_INTERVAL = 0.5

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 0.5

MIN_WORKERS = 1
DEFAULT_WORKERS = 3
MAX_WORKERS = 16

DEFAULT_CHUNK_SIZE_MB = 10
MIN_CHUNK_SIZE_MB = 1
MAX_CHUNK_SIZE_MB = 1024
MAX_FILENAME_LENGTH = 120

FONT_FAMILY = "Microsoft YaHei UI"
FONT_SIZE = 10

SIDEBAR_BG = "#f4f5f7"
SIDEBAR_WIDTH = 200
NAV_ACTIVE_BG = "#e0e4eb"
NAV_HOVER_BG = "#eaecf0"
NAV_FG = "#333333"
NAV_ACCENT = "#3b71fe"
BORDER_COLOR = "#d5d8dc"

CONTENT_BG = "#ffffff"

CONTENT_BG = "#ffffff"

TEXT_PRIMARY = "#1a1a1a"
TEXT_SECONDARY = "#666666"
TEXT_NORMAL = "#333333"
TEXT_SUCCESS = "#006600"
TEXT_ERROR = "#cc0000"

MAIN_WINDOW_SIZE = (950, 700)
SPLITTER_WINDOW_SIZE = (700, 420)
DOWNLOADER_WINDOW_SIZE = (650, 650)
