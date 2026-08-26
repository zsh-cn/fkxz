# 文件分块下载 - 大文件分片传输工具

将大文件拆分为多个小分片，支持本地合并与远程下载合并分片，可用于绕过文件上传大小限制或便于文件传输。

## 项目功能特点

- **文件拆分**：将大文件按指定大小拆分为多个 `.fk` 分片，并生成 `.fkx` 信息文件
- **本地合并**：读取 `.fkx` 信息文件和同目录下的 `.fk` 分片，自动合并还原为原始文件
- **远程下载**：从远程服务器下载 `.fkx` 信息文件及所有 `.fk` 分片，自动合并还原，支持 SHA-256 完整性校验
- **增强模式**：集成 `curl_cffi` 浏览器指纹模拟，可伪装 Chrome 浏览器请求头（User-Agent、Sec-Ch-Ua、Sec-Fetch-\* 等），绕过 Cloudflare 验证、EdgeOne Pages、防盗链等反爬虫保护
- **多端支持**：提供命令行工具（CLI）、新版 GUI 应用（集成侧边栏）、旧版独立 GUI 工具、网页端工具等多种使用方式
- **跨平台**：Python 工具支持 Windows / Linux / macOS；网页端工具支持所有现代浏览器
- **实时进度**：终端进度条 / GUI 进度条，实时显示分块进度、总进度和下载速度
- **自动清理**：远程下载完成后自动清理临时分片文件

## 项目结构

```
fkxz/
├── cli/                           # 命令行工具 (CLI)
│   ├── __init__.py
│   ├── main.py                    # CLI 入口，argparse 参数解析
│   ├── utils.py                   # 公共工具函数（格式化、校验、解析）
│   ├── splitter.py                # split 命令实现
│   ├── merger.py                  # merge 命令实现
│   └── downloader.py              # download 命令实现
│
├── app/                           # 新版 GUI 应用 (Tkinter, 带侧边栏导航)
│   ├── main.py                    # GUI 入口，集成三大功能页面
│   ├── theme.py                   # 主题配色常量
│   ├── core/                      # 核心业务逻辑
│   │   ├── __init__.py
│   │   ├── base_worker.py         # Worker 基类（线程管理）
│   │   ├── splitter.py            # 文件拆分核心逻辑
│   │   ├── downloader.py          # 远程下载核心逻辑
│   │   └── merger.py              # 本地合并核心逻辑
│   ├── ui/                        # 图形界面组件
│   │   ├── __init__.py
│   │   ├── base_page.py           # 页面基类（通用 UI 布局）
│   │   ├── sidebar.py             # 侧边栏导航
│   │   ├── splitter_page.py       # 文件分块页面
│   │   ├── merger_page.py         # 本地合并页面
│   │   └── downloader_page.py     # 远程下载页面
│   └── utils/                     # 工具函数
│       ├── __init__.py
│       └── helpers.py             # 文件格式化、校验、FKX 解析、自定义组件
│
├── icon/                          # 图标资源
│   ├── wjfk.ico                   # 文件分块图标（.ico 用于打包程序图标）
│   ├── wjfk.png                   # 文件分块图标（.png 用于窗口、任务栏图标）
│   ├── wjfkxz.ico                 # 应用主图标（.ico 用于打包程序图标）
│   ├── wjfkxz.png                 # 应用主图标（.png 用于窗口、任务栏图标）
│   ├── wjfkxz-cli.ico             # CLI 命令行工具图标（.ico 用于打包程序图标）
│   ├── wjxz.ico                   # 文件下载图标（.ico 用于打包程序图标）
│   └── wjxz.png                   # 文件下载图标（.png 用于窗口、任务栏图标）
│
├── web/                           # 网页端工具
│   ├── favicon.png                # 网站图标
│   ├── index.html                 # 网页端文件下载器
│   ├── sw.html                    # Service Worker 下载器页面
│   ├── sw.js                      # Service Worker 脚本
│   └── worker.js                  # Cloudflare Workers 脚本
│
├── docs/                          # 项目官网 (GitHub Pages)
│   ├── index.html                 # 官网主页
│   ├── download.html              # 下载页面
│   ├── favicon.png                # 官网图标
│   ├── css/                       # 样式文件
│   │   └── style.css
│   ├── js/                        # 公共脚本
│   │   └── main.js
│   ├── icons/                     # 程序图标
│   │   ├── wjfk.ico
│   │   ├── wjfkxz.ico
│   │   ├── wjfkxz-cli.ico
│   │   └── wjxz.ico
│   └── wjxz/                      # Web 在线体验工具
│       ├── index.html
│       ├── sw.html
│       ├── sw.js
│       └── favicon.png
│
├── file_splitter.py               # 旧版独立拆分器 (GUI)
├── file_downloader.py             # 旧版独立下载/合并器 (GUI, 支持增强模式)
├── pyproject.toml                 # 项目元数据与构建配置
├── requirements.txt               # Python 依赖（兼容传统 pip install -r）
├── LICENSE                        # MPL 2.0 许可证
└── .gitignore
```

## 前往 Releases 下载已打包程序

如果您不想安装 Python 环境，可以直接下载已打包好的 Windows 可执行程序（`.exe`），开箱即用。

前往 [Releases 页面](https://github.com/zsh-cn/fkxz/releases) 下载最新版本，或访问 [项目官网](https://zsh-cn.github.io/fkxz/) 查看各版本信息和在线体验。提供以下四个独立的可执行程序：

| 程序 | 文件名 | 说明 |
|------|--------|------|
| 命令行工具 | `cli.exe` | 命令行版，支持 split / merge / download 命令 |
| 新版 GUI | `main.exe` | 集成侧边栏导航的图形界面，三大功能合一 |
| 文件拆分器 | `file_splitter.exe` | 独立 GUI，专注于文件拆分 |
| 文件下载器 | `file_downloader.exe` | 独立 GUI，支持本地合并与远程下载（含增强模式） |

> **注意**：`file_downloader.exe` 的增强模式需要 `curl_cffi` 支持，已打包版本内置了增强模式能力。如果增强模式不可用，程序会自动回退到标准模式。

## Releases 已打包程序使用说明

### cli.exe — 命令行工具

`cli.exe` 是命令行版本，提供 `split`、`merge`、`download` 三个子命令，适合批处理和脚本自动化场景。

#### 基本用法

打开命令提示符（cmd）或 PowerShell，进入 `cli.exe` 所在目录：

```cmd
cli.exe split -i "D:\video.mp4" -o "D:\chunks" -c 10
cli.exe merge -i "D:\chunks\video.mp4.fkx" -o "D:\output"
cli.exe download -u "https://example.com/files/video.mp4.fkx" -o "D:\output"
```

#### 参数说明

**split（拆分文件）**

| 参数 | 说明 | 必填 |
|------|------|------|
| `-i, --input` | 要拆分的文件路径 | 是 |
| `-o, --output` | 输出目录 | 是 |
| `-c, --chunk-size` | 分片大小（MB），范围 1-1024，默认 10 | 否 |

**merge（本地合并）**

| 参数 | 说明 | 必填 |
|------|------|------|
| `-i, --input` | `.fkx` 信息文件路径 | 是 |
| `-o, --output` | 输出目录 | 是 |

**download（远程下载）**

| 参数 | 说明 | 必填 |
|------|------|------|
| `-u, --url` | `.fkx` 信息文件的 URL | 是 |
| `-o, --output` | 输出目录 | 是 |
| `-e, --enhanced` | 启用增强模式（浏览器指纹伪装） | 否 |
| `-t, --timeout` | 请求超时时间（秒），默认 120 | 否 |

#### 使用示例

```cmd
REM 将 video.mp4 拆分为 10MB 的分片
cli.exe split -i "D:\video.mp4" -o "D:\chunks" -c 10

REM 本地合并分片
cli.exe merge -i "D:\chunks\video.mp4.fkx" -o "D:\output"

REM 远程下载并合并
cli.exe download -u "https://example.com/files/video.mp4.fkx" -o "D:\output"

REM 启用增强模式下载（绕过反爬虫）
cli.exe download -u "https://example.com/files/video.mp4.fkx" -o "D:\output" -e

REM 自定义超时时间
cli.exe download -u "https://example.com/files/video.mp4.fkx" -o "D:\output" -t 300
```

---

### main.exe — 新版 GUI 应用

`main.exe` 是集成式图形界面，采用侧边栏导航设计，将文件拆分、本地合并、远程下载三大功能整合在一个窗口中。

#### 启动

双击 `main.exe` 即可启动，无需任何命令行参数。

#### 界面功能

- **文件分块**：选择文件 → 设置输出目录 → 调整分片大小（1-1024 MB）→ 点击"开始拆分"
- **本地合并**：选择 `.fkx` 信息文件 → 设置输出目录 → 点击"开始合并"
- **远程下载**：输入 `.fkx` 文件 URL → 设置输出目录 → 可选启用增强模式 → 点击"开始下载"

#### 特性

- 侧边栏一键切换功能页面
- 实时分块进度 + 总进度 + 下载速度显示
- 文件信息预览（文件名、大小、分片数）
- 支持取消操作
- HiDPI 高 DPI 自适应
- 右键上下文菜单（剪切/复制/粘贴/全选）

---

### file_splitter.exe — 文件拆分器

`file_splitter.exe` 是独立的文件拆分 GUI 工具，专注于将大文件拆分为多个小分片。

#### 启动

双击 `file_splitter.exe` 即可启动。

#### 使用步骤

1. 点击"浏览"选择要拆分的文件
2. 点击"浏览"选择输出目录
3. 设置每个分片的大小（1-1024 MB，默认 10 MB）
4. 界面会自动显示文件大小和预计分片数
5. 点击"开始拆分"

拆分完成后会在输出目录生成：
- `{文件名}-1.fk`、`{文件名}-2.fk`、... — 分片文件
- `{文件名}.fkx` — 信息文件

将 `.fk` 分片和 `.fkx` 文件上传到服务器（保持相同目录结构），即可通过 `.fkx` 文件的 URL 分享给他人下载。

---

### file_downloader.exe — 文件下载/合并器

`file_downloader.exe` 是独立的文件下载与合并 GUI 工具，支持本地合并和远程下载两种模式。

#### 启动

双击 `file_downloader.exe` 即可启动。

#### 本地模式

1. 点击"浏览"选择本地 `.fkx` 信息文件
2. 点击"浏览"选择输出目录
3. 点击"开始合并"

程序会自动读取同目录下的 `.fk` 分片并合并还原。

#### 远程模式

1. 在输入框中填入 `.fkx` 文件的完整 URL（如 `https://example.com/files/video.mp4.fkx`）
2. 点击"浏览"选择输出目录
3. 勾选或取消"启用增强模式"（默认勾选）
4. 点击"开始下载"

程序会自动下载 `.fkx` 信息文件、逐个下载 `.fk` 分片、合并还原并校验 SHA-256。

#### 增强模式

- **默认启用**：勾选后使用 `curl_cffi` 模拟 Chrome 浏览器指纹，自动伪装浏览器请求头，可绕过 Cloudflare 验证、EdgeOne Pages、防盗链等反爬虫保护
- **取消勾选**：使用标准 `requests` 库进行下载

## 快速开始

### 方式一：pip 安装（推荐）

```bash
git clone https://github.com/zsh-cn/fkxz.git
cd fkxz
pip install .
```

安装后可直接使用 `fkxz` 命令：

```bash
fkxz split -i ./video.mp4 -o ./chunks -c 10
fkxz merge -i ./chunks/video.mp4.fkx -o ./output
fkxz download -u https://example.com/files/video.mp4.fkx -o ./output
```

如需增强模式（浏览器指纹模拟）：

```bash
pip install ".[enhanced]"
fkxz download -u https://example.com/files/video.mp4.fkx -o ./output --enhanced
```

### 方式二：源码运行

```bash
git clone https://github.com/zsh-cn/fkxz.git
cd fkxz
python -m venv .venv        # 创建虚拟环境（可选）
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux / macOS
pip install -r requirements.txt
python app/main.py             # 启动 GUI
```

### 方式三：直接下载 exe（无需 Python 环境）

前往 [Releases](https://github.com/zsh-cn/fkxz/releases) 下载已打包的 `.exe` 程序，解压后直接双击运行即可。详见上方 [Releases 已打包程序使用说明](#releases-已打包程序使用说明)。

## 组件说明

### 命令行工具 — `cli/main.py`

基于 `argparse` 的统一命令行入口，提供三大命令：

| 命令 | 说明 |
|------|------|
| `split` | 将大文件拆分为 `.fk` 分片和 `.fkx` 信息文件 |
| `merge` | 读取本地 `.fkx` 和 `.fk` 文件合并还原 |
| `download` | 从远程 URL 下载 `.fkx` 和 `.fk` 分片后合并 |

- 支持 SHA-256 完整性校验
- 支持 `--enhanced` 增强模式（curl_cffi 浏览器指纹模拟）
- 支持 `--timeout` 自定义请求超时时间（默认 120 秒）
- 终端实时进度条显示
- 下载完成后自动清理临时文件

### 新版 GUI 应用 — `app/main.py`

Tkinter 现代化图形界面，采用侧边栏导航设计，集成三大功能于一体：

- **文件分块**：选择文件 → 设置分片大小 → 一键拆分，生成 `.fk` 分片和 `.fkx` 信息文件
- **本地合并**：选择 `.fkx` 信息文件 → 自动读取同目录分片 → 合并还原
- **远程下载**：输入 `.fkx` 文件 URL → 可选增强模式 → 下载分片并合并

**特性：**
- 侧边栏导航，三页无缝切换
- 自定义圆角进度条和按钮组件，现代化视觉风格
- HiDPI 高 DPI 自适应（Windows）
- 多线程异步处理，界面不阻塞
- 实时分块进度 + 总进度 + 下载速度显示
- 远程模式支持 curl_cffi 浏览器指纹模拟（绕过反爬虫）
- 文件信息预览（文件名、大小、分片数）
- 支持取消操作
- 右键上下文菜单（剪切/复制/粘贴/全选）

### 旧版独立 GUI 工具

#### file_splitter.py — 文件拆分器

Tkinter 图形界面，将大文件拆分为多个 `.fk` 分片，并生成 `.fkx` 信息文件。

- 支持自定义分片大小（1-1024 MB）
- 每个分片及原始文件均计算 SHA-256 校验值
- 支持取消拆分操作

#### file_downloader.py — 文件下载/合并器

Tkinter 图形界面，读取 `.fkx` 信息文件，获取所有分片并合并还原。

- **本地模式**：从本地目录读取 `.fkx` 和 `.fk` 文件直接合并
- **远程模式**：从 URL 下载 `.fkx` 文件，逐个下载 `.fk` 分片后合并
- 实时进度显示（分块进度 / 总进度 / 下载速度）
- SHA-256 完整性校验
- 自动清理临时文件
- **增强模式**（默认启用）：界面提供复选框，勾选后使用 `curl_cffi` 模拟 Chrome 浏览器指纹，自动伪装浏览器请求头（User-Agent、Sec-Ch-Ua、Sec-Fetch-\* 等），支持 Referer 头信息传递，可绕过反爬虫保护（如 Cloudflare 验证、EdgeOne Pages、防盗链等）。取消勾选则使用标准请求模式

### 网页端工具 — `web/`

#### worker.js — Cloudflare Workers 后端

部署在 Cloudflare Workers 上的 HTTP 服务，接收 `?fkx=` 参数，流式合并分片并提供直链下载。

- 自动解析 `.fkx` 文件获取分片列表
- 使用 `FixedLengthStream` 流式合并
- 自动设置 `Content-Disposition` 触发浏览器下载
- 支持跨域（CORS）
- 注：此脚本不适用于大文件

#### index.html — 网页端文件下载器

轻量级的浏览器端文件下载器，支持通过 URL 参数直接解析 `.fkx` 文件并下载合并后的完整文件。

- 纯前端实现，无需后端支持
- 支持流式下载和实时进度显示
- 自动检测并使用 File System Access API（现代浏览器）
- 支持回退到传统下载方式

#### sw.js + sw.html — Service Worker 下载器

基于 Service Worker 的浏览器端文件下载器，通过 SW 拦截请求并在浏览器端流式合并分片后返回完整文件。

- **sw.js**：Service Worker 脚本，拦截 `/fkxz` 路径的请求，解析 `.fkx` 文件获取分片列表，逐个抓取 `.fk` 分片并通过 `ReadableStream` 流式合并，最终以单个文件形式返回给浏览器下载。
- **sw.html**：配套前端页面，自动注册 Service Worker，解析 `.fkx` 文件并展示文件信息，点击下载按钮后通过 SW 代理完成流式合并下载。

相比 `index.html`，Service Worker 方案的优势在于：
- 无需 File System Access API，兼容性更好
- 合并过程在 SW 后台线程完成，不阻塞主线程
- 直接触发浏览器原生下载行为，用户体验更流畅
- 同样支持跨域资源（通过 SW 代理绕过 CORS 限制）

## 使用方式

### 命令行工具 (CLI)

安装后可使用 `fkxz` 命令，也可以直接运行源码：

#### 拆分文件

```bash
# 安装后使用 fkxz 命令
fkxz split -i ./video.mp4 -o ./chunks -c 10

# 或直接运行源码
python cli/main.py split -i ./video.mp4 -o ./chunks -c 10
```

参数说明：
- `-i, --input`：要拆分的文件路径（必填）
- `-o, --output`：输出目录（必填）
- `-c, --chunk-size`：分片大小（MB），范围 1-1024，默认 10

#### 本地合并

```bash
# 安装后使用 fkxz 命令
fkxz merge -i ./chunks/video.mp4.fkx -o ./output

# 或直接运行源码
python cli/main.py merge -i ./chunks/video.mp4.fkx -o ./output
```

参数说明：
- `-i, --input`：`.fkx` 信息文件路径（必填）
- `-o, --output`：输出目录（必填）

#### 远程下载

```bash
# 安装后使用 fkxz 命令
fkxz download -u https://example.com/files/video.mp4.fkx -o ./output
fkxz download -u https://example.com/files/video.mp4.fkx -o ./output --enhanced
fkxz download -u https://example.com/files/video.mp4.fkx -o ./output -t 300

# 或直接运行源码
python cli/main.py download -u https://example.com/files/video.mp4.fkx -o ./output
python cli/main.py download -u https://example.com/files/video.mp4.fkx -o ./output --enhanced
python cli/main.py download -u https://example.com/files/video.mp4.fkx -o ./output -t 300
```

参数说明：
- `-u, --url`：`.fkx` 信息文件的 URL（必填）
- `-o, --output`：输出目录（必填）
- `-e, --enhanced`：启用增强模式（可选，需安装 curl_cffi）
- `-t, --timeout`：请求超时时间（秒），默认 120（可选）

### 新版 GUI 应用

```bash
python app/main.py
```

启动后通过左侧导航栏切换功能：
- **文件分块**：选择文件、输出目录和分片大小，点击"开始拆分"
- **本地合并**：选择 `.fkx` 信息文件、输出目录，点击"开始合并"
- **远程下载**：输入 `.fkx` 文件 URL、选择输出目录，可选启用增强模式，点击"开始下载"

### 旧版 GUI 工具

#### 拆分文件

```bash
python file_splitter.py
```

在 GUI 中选择要拆分的文件、输出目录和分片大小，点击"开始拆分"。

拆分完成后可将 `.fk` 分片和 `.fkx` 文件上传到服务器，保持相同目录结构，使用 `.fkx` 文件信息 URL 以供分享、下载。

#### 合并文件（本地/远程）

```bash
python file_downloader.py
```

在输入框中填入 `.fkx` 文件的本地路径或完整 URL，选择输出目录。界面默认勾选**增强模式**（使用 curl_cffi 浏览器指纹模拟以绕过反爬虫），可根据需要取消勾选切换为标准模式。点击"开始合并"（本地）或"开始下载"（远程）。

### 网页端方式

#### 方式一：使用 Cloudflare Workers

1. 部署 `web/worker.js` 到 Cloudflare Workers
2. 访问 `https://your-worker.workers.dev/?fkx=https://example.com/file.fkx`

#### 方式二：使用网页端下载器

1. 将 `web/index.html` 部署到任意静态文件服务器
2. 通过 URL 参数提供 `.fkx` 文件地址：
   `https://your-domain.com/index.html?fkx=https://example.com/file.fkx`
- 使用时应注意浏览器跨域限制

#### 方式三：使用 Service Worker 下载器

1. 将 `web/sw.html` 和 `web/sw.js` 部署到同一目录下的静态文件服务器
2. 通过 URL 参数提供 `.fkx` 文件地址：
   `https://your-domain.com/sw.html?fkx=https://example.com/file.fkx`
3. 页面自动解析文件信息，点击"下载"按钮即可触发 SW 流式合并下载
- 要求站点必须使用 HTTPS 或 localhost（Service Worker 安全策略要求）
- `sw.js` 必须与 `sw.html` 同源部署

## 环境要求

### Python 工具

| 组件 | 最低版本 | 依赖 |
|------|---------|------|
| CLI 工具 (`cli/`) | Python 3.8+ | `requests` |
| 新版 GUI (`app/`) | Python 3.8+ | `requests`、`tkinter`（Linux 需 `apt install python3-tk`） |
| 旧版 GUI | Python 3.8+ | `requests`、`tkinter`（Linux 需 `apt install python3-tk`） |
| 增强模式 | Python 3.8+ | `requests` + `curl_cffi` |

安装依赖：

```bash
# 使用 pyproject.toml（推荐）
pip install .              # 基础安装
pip install ".[enhanced]"  # 含增强模式（curl_cffi）

# 或使用 requirements.txt（传统方式）
pip install -r requirements.txt
```

- `requests`：HTTP 请求库（必需）
- `curl_cffi`：浏览器指纹模拟库（可选，用于增强模式绕过反爬虫）

### Cloudflare Workers（可选）

- Cloudflare Workers 账户

### 网页端

- 现代浏览器（推荐 Chrome 90+、Firefox 89+）
- 使用 Service Worker 下载器需浏览器支持 Service Worker API（Chrome 45+、Firefox 44+）

## 文件格式

### .fkx 信息文件

命名格式：`{原文件名}.fkx`（如 `video.mp4.fkx`），内容格式如下：

```
filename=原始文件名
total_size=文件总字节数
chunk_size=分片字节数
num_chunks=分片总数
chunk_0=分片文件名,分片大小
chunk_1=分片文件名,分片大小
...
sha256=原始文件SHA-256值
```

### .fk 分片文件

命名格式：`{原文件名}-{索引}.fk`

## PyInstaller 打包说明

如果你想自行从源码打包为 `.exe` 可执行程序，可以使用 PyInstaller。

### 安装 PyInstaller

```bash
pip install pyinstaller
```

### 打包命令

在项目根目录下执行以下命令：

#### 打包 cli.exe（命令行工具）

```bash
pyinstaller --onefile --console --name cli --icon icon/wjfkxz-cli.ico cli/main.py
```

- `--onefile`：打包为单个 exe 文件
- `--console`：控制台程序（显示命令行窗口）
- `--name cli`：输出文件名为 `cli.exe`
- `--icon icon/wjfkxz-cli.ico`：设置 exe 程序图标

#### 打包 main.exe（新版 GUI 应用）

```bash
pyinstaller --onefile --windowed --name main --icon icon/wjfkxz.ico --add-data "icon;icon" --add-data "app;app" app/main.py
```

- `--windowed`：窗口程序（不显示命令行窗口）
- `--icon icon/wjfkxz.ico`：设置 exe 程序图标
- `--add-data "app;app"`：将 app 模块打包进去
- 任务栏/窗口图标：`icon/wjfkxz.png`（通过 `--add-data` 打包，程序运行时自动加载）

#### 打包 file_splitter.exe（文件拆分器）

```bash
pyinstaller --onefile --windowed --name file_splitter --icon icon/wjfk.ico --add-data "icon;icon" file_splitter.py
```

- `--icon icon/wjfk.ico`：设置 exe 程序图标
- 任务栏/窗口图标：`icon/wjfk.png`（通过 `--add-data` 打包，程序运行时自动加载）

#### 打包 file_downloader.exe（文件下载/合并器）

```bash
pyinstaller --onefile --windowed --name file_downloader --icon icon/wjxz.ico --add-data "icon;icon" --hidden-import curl_cffi file_downloader.py
```

- `--icon icon/wjxz.ico`：设置 exe 程序图标
- `--hidden-import curl_cffi`：显式包含 curl_cffi 模块（增强模式依赖）
- 任务栏/窗口图标：`icon/wjxz.png`（通过 `--add-data` 打包，程序运行时自动加载）

### 打包说明

- 打包后的 exe 文件位于 `dist/` 目录下
- 如果增强模式打包失败或运行时不可用，程序会自动回退到标准 `requests` 模式
- 建议在打包前先执行 `pip install -r requirements.txt` 和 `pip install ".[enhanced]"` 确保所有依赖已安装
- 对于 `main.exe`，请确保 `app/` 目录及其子模块（`core/`、`ui/`、`utils/`）均被正确包含

## 问题反馈

如遇到问题或有功能建议，请通过以下方式反馈：

- **GitHub Issues**：[提交 Issue](https://github.com/zsh-cn/fkxz/issues)
- 提交时请尽量提供以下信息：
  - 使用的程序版本（`cli.exe` / `main.exe` / `file_splitter.exe` / `file_downloader.exe` 或源码运行）
  - 操作系统版本
  - 问题的详细描述和复现步骤
  - 相关的错误信息或截图

## 免责声明

本工具仅供学习、研究和个人合法用途。使用者应遵守所在国家/地区的法律法规，不得将本工具用于任何违法或侵权活动。

- 使用本工具下载文件时，请确保您拥有合法的下载权限，遵守目标网站的服务条款和 robots.txt 协议
- 增强模式（浏览器指纹模拟）功能仅用于研究和学习浏览器指纹技术，请勿用于绕过网站的安全防护措施进行未授权访问
- 本项目开发者不对使用者的任何不当行为承担责任，使用者需自行承担使用本工具所产生的一切后果和风险
- 本工具不提供任何形式的担保，使用过程中可能产生的数据丢失、文件损坏等问题，开发者不承担任何责任

## 许可证

本项目采用 [GNU General Public License v3.0](LICENSE) 许可证。