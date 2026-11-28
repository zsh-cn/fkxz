from collections import namedtuple

APP_NAME = "文件分块下载"
APP_VERSION = "4.2.1"
APP_LICENSE = "MPL-2.0"
APP_HOMEPAGE = "https://fkxz.zhshh.cn"
APP_REPO_URL = "https://github.com/zsh-cn/fkxz"

APP_ID_MAIN = "fkxz.main"
APP_ID_SPLITTER = "fkxz.splitter"
APP_ID_DOWNLOADER = "fkxz.downloader"

CONFIG_DIR_NAME = "fkxz"

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

HTTP_POOL_SIZE = 4
CONNECT_TIMEOUT = 15
CHUNK_TIMEOUT = 30

CHUNK_BUFFER = 65536
IO_BLOCK_SIZE = 1024 * 1024
PROGRESS_INTERVAL = 0.15
SPEED_MIN_INTERVAL = 0.5
SPEED_WINDOW = 1.0
UI_PUMP_INTERVAL = 40
UI_IDLE_PUMP_INTERVAL = 400

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 0.5
RETRY_ROUNDS = 2
RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

NetworkSetting = namedtuple(
    'NetworkSetting', 'key const label low high default hint')

NETWORK_SETTING_SPECS = (
    NetworkSetting('retry_attempts', 'RETRY_ATTEMPTS', '单分片重试次数',
                   1, 20, RETRY_ATTEMPTS, '单个分片失败后的重试次数'),
    NetworkSetting('retry_rounds', 'RETRY_ROUNDS', '整体重试轮数',
                   1, 10, RETRY_ROUNDS, '整轮失败后重新再来的轮数'),
    NetworkSetting('connect_timeout', 'CONNECT_TIMEOUT', '连接超时(秒)',
                   5, 300, CONNECT_TIMEOUT, '获取清单、建立连接的等待时间'),
    NetworkSetting('chunk_timeout', 'CHUNK_TIMEOUT', '分片超时(秒)',
                   5, 3600, CHUNK_TIMEOUT, '单个分片无响应时的等待时间'),
)

MIN_WORKERS = 1
DEFAULT_WORKERS = 3
MAX_WORKERS = 16

DEFAULT_CHUNK_SIZE_MB = 10
MIN_CHUNK_SIZE_MB = 1
MAX_CHUNK_SIZE_MB = 1024
MAX_FILENAME_LENGTH = 120

DISK_SPACE_MARGIN = 64 * 1024 * 1024

SHUTDOWN_DELAY_SECONDS = 60

HASH_MODE_BOTH = "both"
HASH_MODE_CHUNKS = "chunks"
HASH_MODE_FILE = "file"
HASH_MODE_NONE = "none"
DEFAULT_HASH_MODE = HASH_MODE_BOTH

VERIFY_OPTIONS = (
    ("双校验（分片 + 整文件）", HASH_MODE_BOTH),
    ("只校验分片", HASH_MODE_CHUNKS),
    ("只校验整文件", HASH_MODE_FILE),
    ("不校验（仅核对大小）", HASH_MODE_NONE),
)

FONT_FAMILY = "Microsoft YaHei UI"
FONT_SIZE = 10

THEME_AUTO = "auto"
DEFAULT_THEME = THEME_AUTO
THEME_PREFERENCE = ("vista", "xpnative", "winnative", "clam", "alt", "default", "classic")

DEFAULT_OPEN_FOLDER = True
DEFAULT_KEEP_CHUNKS = False

SIDEBAR_BG = "#f4f5f7"
SIDEBAR_WIDTH = 200
NAV_ACTIVE_BG = "#e0e4eb"
NAV_HOVER_BG = "#eaecf0"
NAV_FG = "#333333"
NAV_ACCENT = "#3b71fe"
BORDER_COLOR = "#d5d8dc"

CONTENT_BG = "#ffffff"

TEXT_PRIMARY = "#1a1a1a"
TEXT_SECONDARY = "#666666"
TEXT_NORMAL = "#333333"
TEXT_SUCCESS = "#006600"
TEXT_ERROR = "#cc0000"

MAIN_WINDOW_SIZE = (950, 700)
SPLITTER_WINDOW_SIZE = (700, 450)
DOWNLOADER_WINDOW_SIZE = (650, 660)
