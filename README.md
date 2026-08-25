# 分块下载 - 大文件分片传输工具

将大文件拆分为多个小分片，支持本地合并与远程下载合并分块，可用于绕过文件上传大小限制。

## 项目结构

```
fkxz/
├── cil/                           # 命令行工具 (CLI)
│   └── main.py                    # 统一 CLI 入口，支持 split/merge/download 命令
│
├── py/                            # 新版 GUI 应用 (Tkinter, 带侧边栏导航)
│   ├── main.py                    # GUI 入口，集成三大功能页面
│   ├── theme.py                   # 主题配色常量
│   ├── core/                      # 核心业务逻辑
│   │   ├── __init__.py
│   │   ├── splitter.py            # 文件拆分核心逻辑
│   │   ├── downloader.py          # 远程下载核心逻辑
│   │   └── merger.py              # 本地合并核心逻辑
│   ├── ui/                        # 图形界面组件
│   │   ├── __init__.py
│   │   ├── sidebar.py             # 侧边栏导航
│   │   ├── splitter_page.py       # 文件分块页面
│   │   ├── merger_page.py         # 本地合并页面
│   │   └── downloader_page.py     # 远程下载页面
│   └── utils/                     # 工具函数
│       ├── __init__.py
│       └── helpers.py             # 文件格式化、校验、WJX 解析、自定义组件
│
├── web/                           # 网页端工具
│   ├── index.html                 # 网页端文件下载器
│   ├── sw.html                    # Service Worker 下载器页面
│   ├── sw.js                      # Service Worker 脚本
│   └── worker.js                  # Cloudflare Workers 脚本
│
├── file_splitter.py               # 旧版独立拆分器 (GUI)
├── file_downloader.py             # 旧版独立下载/合并器 (GUI)
├── file_downloader_Enhanced.py    # 旧版增强独立下载/合并器 (GUI, curl_cffi)
├── requirements.txt               # Python 依赖
├── LICENSE                        # GPL v3 许可证
└── .gitignore
```

## 组件说明

### 命令行工具 — `cil/main.py`

基于 `argparse` 的统一命令行入口，提供三大命令：

| 命令 | 说明 |
|------|------|
| `split` | 将大文件拆分为 `.fk` 分片和 `.wjx` 信息文件 |
| `merge` | 读取本地 `.wjx` 和 `.fk` 文件合并还原 |
| `download` | 从远程 URL 下载 `.wjx` 和 `.fk` 分片后合并 |

- 支持 SHA-256 完整性校验
- 支持 `--enhanced` 增强模式（curl_cffi 浏览器指纹模拟）
- 终端实时进度条显示
- 下载完成后自动清理临时文件

### 新版 GUI 应用 — `py/main.py`

Tkinter 现代化图形界面，采用侧边栏导航设计，集成三大功能于一体：

- **文件分块**：选择文件 → 设置分片大小 → 一键拆分，生成 `.fk` 分片和 `.wjx` 信息文件
- **本地合并**：选择 `.wjx` 信息文件 → 自动读取同目录分片 → 合并还原
- **远程下载**：输入 `.wjx` 文件 URL → 可选增强模式 → 下载分片并合并

**特性：**
- 侧边栏导航，三页无缝切换
- 自定义圆角进度条和按钮组件，现代化视觉风格
- HiDPI 高 DPI 自适应（Windows）
- 多线程异步处理，界面不阻塞
- 实时分块进度 + 总进度 + 下载速度显示
- 远程模式支持 curl_cffi 浏览器指纹模拟（绕过反爬虫）
- 文件信息预览（文件名、大小、分块数）
- 支持取消操作
- 右键上下文菜单（剪切/复制/粘贴/全选）

### 旧版独立 GUI 工具

#### file_splitter.py — 文件拆分器

Tkinter 图形界面，将大文件拆分为多个 `.fk` 分片，并生成 `.wjx` 信息文件。

- 支持自定义分片大小（1-1024 MB）
- 每个分片及原始文件均计算 SHA-256 校验值
- 支持取消拆分操作

#### file_downloader.py — 文件下载/合并器

Tkinter 图形界面，读取 `.wjx` 信息文件，获取所有分片并合并还原。

- **本地模式**：从本地目录读取 `.wjx` 和 `.fk` 文件直接合并
- **远程模式**：从 URL 下载 `.wjx` 文件，逐个下载 `.fk` 分片后合并
- 实时进度显示（分片进度 / 总进度 / 下载速度）
- SHA-256 完整性校验
- 自动清理临时文件

#### file_downloader_Enhanced.py — 增强版文件下载/合并器

基于 `file_downloader.py` 的增强版本，提供更强的反反爬虫能力。

- 使用 `curl_cffi` 库模拟 Chrome 浏览器（版本 131）进行请求
- 自动伪装浏览器请求头（User-Agent、Sec-Ch-Ua、Sec-Fetch-* 等）
- 支持 Referer 头信息传递，部分网站必需
- 其余功能与 `file_downloader.py` 相同（本地/远程模式、SHA-256 校验等）

### 网页端工具 — `web/`

#### worker.js — Cloudflare Workers 后端

部署在 Cloudflare Workers 上的 HTTP 服务，接收 `?wjx=` 参数，流式合并分片并提供直链下载。

- 自动解析 `.wjx` 文件获取分片列表
- 使用 `FixedLengthStream` 流式合并
- 自动设置 `Content-Disposition` 触发浏览器下载
- 支持跨域（CORS）
- 注：此脚本不适用于大文件

#### index.html — 网页端文件下载器

轻量级的浏览器端文件下载器，支持通过 URL 参数直接解析 `.wjx` 文件并下载合并后的完整文件。

- 纯前端实现，无需后端支持
- 支持流式下载和实时进度显示
- 自动检测并使用 File System Access API（现代浏览器）
- 支持回退到传统下载方式

#### sw.js + sw.html — Service Worker 下载器

基于 Service Worker 的浏览器端文件下载器，通过 SW 拦截请求并在浏览器端流式合并分片后返回完整文件。

- **sw.js**：Service Worker 脚本，拦截 `/fkxz` 路径的请求，解析 `.wjx` 文件获取分片列表，逐个抓取 `.fk` 分片并通过 `ReadableStream` 流式合并，最终以单个文件形式返回给浏览器下载。
- **sw.html**：配套前端页面，自动注册 Service Worker，解析 `.wjx` 文件并展示文件信息，点击下载按钮后通过 SW 代理完成流式合并下载。

相比 `index.html`，Service Worker 方案的优势在于：
- 无需 File System Access API，兼容性更好
- 合并过程在 SW 后台线程完成，不阻塞主线程
- 直接触发浏览器原生下载行为，用户体验更流畅
- 同样支持跨域资源（通过 SW 代理绕过 CORS 限制）

## 使用方式

### 命令行工具 (CLI)

#### 拆分文件

```bash
python cil/main.py split -i ./video.mp4 -o ./chunks -c 10
```

参数说明：
- `-i, --input`：要拆分的文件路径（必填）
- `-o, --output`：输出目录（必填）
- `-c, --chunk-size`：分片大小（MB），范围 1-1024，默认 10

#### 本地合并

```bash
python cil/main.py merge -i ./chunks/video.mp4.wjx -o ./output
```

参数说明：
- `-i, --input`：`.wjx` 信息文件路径（必填）
- `-o, --output`：输出目录（必填）

#### 远程下载

```bash
# 标准模式
python cil/main.py download -u https://example.com/files/video.mp4.wjx -o ./output

# 增强模式（浏览器指纹伪装）
python cil/main.py download -u https://example.com/files/video.mp4.wjx -o ./output --enhanced
```

参数说明：
- `-u, --url`：`.wjx` 信息文件的 URL（必填）
- `-o, --output`：输出目录（必填）
- `-e, --enhanced`：启用增强模式（可选，需安装 curl_cffi）

### 新版 GUI 应用

```bash
python py/main.py
```

启动后通过左侧导航栏切换功能：
- **文件分块**：选择文件、输出目录和分片大小，点击"开始拆分"
- **本地合并**：选择 `.wjx` 信息文件、输出目录，点击"开始合并"
- **远程下载**：输入 `.wjx` 文件 URL、选择输出目录，可选启用增强模式，点击"开始下载"

### 旧版 GUI 工具

#### 拆分文件

```bash
python file_splitter.py
```

在 GUI 中选择要拆分的文件、输出目录和分片大小，点击"开始拆分"。

拆分完成后可将 `.fk` 分片和 `.wjx` 文件上传到服务器，保持相同目录结构，使用 `.wjx` 文件信息 URL 以供分享、下载。

#### 合并文件（本地）

```bash
python file_downloader.py
```

在输入框中填入 `.wjx` 文件的本地路径，选择输出目录，点击"开始合并"。增强版下载器 `file_downloader_Enhanced.py` 同样支持本地模式。

#### 合并文件（远程）

```bash
python file_downloader.py
```

在输入框中输入 `.wjx` 文件的完整 URL，选择输出目录，点击"开始下载"。

#### 增强版远程下载

```bash
python file_downloader_Enhanced.py
```

适用于启用了反爬虫保护的网站（如 Cloudflare 验证、EdgeOne Pages、防盗链等），自动模拟 Chrome 浏览器请求以绕过检测，使用方式与标准版相同。

### 网页端方式

#### 方式一：使用 Cloudflare Workers

1. 部署 `web/worker.js` 到 Cloudflare Workers
2. 访问 `https://your-worker.workers.dev/?wjx=https://example.com/file.wjx`

#### 方式二：使用网页端下载器

1. 将 `web/index.html` 部署到任意静态文件服务器
2. 通过 URL 参数提供 `.wjx` 文件地址：
   `https://your-domain.com/index.html?wjx=https://example.com/file.wjx`
- 使用时应注意浏览器跨域限制

#### 方式三：使用 Service Worker 下载器

1. 将 `web/sw.html` 和 `web/sw.js` 部署到同一目录下的静态文件服务器
2. 通过 URL 参数提供 `.wjx` 文件地址：
   `https://your-domain.com/sw.html?wjx=https://example.com/file.wjx`
3. 页面自动解析文件信息，点击"下载"按钮即可触发 SW 流式合并下载
- 要求站点必须使用 HTTPS 或 localhost（Service Worker 安全策略要求）
- `sw.js` 必须与 `sw.html` 同源部署

## 环境要求

### Python 工具

| 组件 | 最低版本 | 依赖 |
|------|---------|------|
| CLI 工具 (`cil/`) | Python 3.6+ | `requests` |
| 新版 GUI (`py/`) | Python 3.6+ | `requests` |
| 旧版 GUI | Python 3.6+ | `requests` |
| 增强版 / 增强模式 | Python 3.6+ | `requests` + `curl_cffi` |

安装依赖：

```bash
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

### .wjx 信息文件

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

## 许可证

本项目采用 [GNU General Public License v3.0](LICENSE) 许可证。