# 文件分块下载 - 大文件分片传输工具

将大文件分块为多个小分片，支持本地合并与远程下载合并分片，可用于绕过文件上传大小限制或便于文件传输。

## 项目功能

- **文件分块**：将大文件按指定大小分块为多个 `.fk` 分片，并生成 `.fkx` 信息文件（单遍读写，同时产出分片哈希与文件哈希）
- **文件下载**：支持本地 `.fkx` 合并还原与远程 URL 下载分片合并，支持 SHA-256 完整性校验
- **并发下载**：远程模式可设 1-16 个并发分片，弱网/高延迟链路上吞吐显著提升；单分片失败自动指数退避重试
- **断点续传**：远程下载中断后已下载的分片自动保留，重新下载时按大小 + SHA-256 跳过完整分片，残缺分片用 `Range` 从断点续传
- **增强模式**：集成 `curl_cffi` 浏览器模拟，可模拟 Chrome 浏览器请求头，绕过 Cloudflare 验证、EdgeOne Pages、防盗链等反爬虫保护
- **多端支持**：提供聚合 GUI 程序、独立 GUI 程序、网页端工具等多种使用方式
- **跨平台**：Python 工具支持 Windows / Linux / macOS；网页端下载页面支持所有现代浏览器

## 项目官网

项目官网提供了项目介绍、下载页面、在线体验和文档页面，欢迎访问：

- **主站**：[https://fkxz.zhshh.cn](https://fkxz.zhshh.cn)
- **备用站**：[https://zsh-cn.github.io/fkxz/](https://zsh-cn.github.io/fkxz/)

## 项目结构

```
fkxz/
├── icon/                          # 图标资源
│   ├── wjfk.ico                   # 文件分块图标（打包图标）
│   ├── wjfk.png                   # 文件分块图标（窗口、任务栏图标）
│   ├── wjfkxz.ico                 # 应用主图标（打包图标）
│   ├── wjfkxz.png                 # 应用主图标（窗口、任务栏图标）
│   ├── wjxz.ico                   # 文件下载图标（打包图标）
│   └── wjxz.png                   # 文件下载图标（窗口、任务栏图标）
│
├── web/                           # 网页端下载页面
│   ├── favicon.png                # 网站图标
│   ├── index.html                 # 文件下载页面
│   └── sw.js                      # Service Worker 脚本
│
├── main.py                        # 聚合程序，集成文件分块与文件下载 (GUI)
├── wjfk.py                        # 独立文件分块程序 (GUI)
├── wjxz.py                        # 独立文件合并/下载程序 (GUI, 支持增强模式)
├── core.py                        # 分块/合并内核（仅 .fkx 格式与分片读写，无界面依赖）
├── utils.py                       # 公共工具（文件名/路径/哈希、DPI 适配、UI 线程桥、图标/对话框/右键菜单、节流器）
├── config.py                      # 全局常量与版本号（网络/IO/并发/配色/窗口尺寸）
├── requirements.txt               # Python 依赖
└── LICENSE                        # MPL 2.0 许可证
```

## 下载已打包程序

如果您不想安装 Python 环境，可以直接下载已打包的 Windows 可执行程序（`.exe`），开箱即用。

前往 [Releases 页面](https://github.com/zsh-cn/fkxz/releases) 下载最新版本，或访问 [项目官网](https://fkxz.zhshh.cn) 通过备用源下载程序和在线使用网页版下载fkx文件。提供以下可执行程序：

| 类型 | 文件名 | 说明 |
|------|--------|------|
| GUI（聚合） | `wjfkxz.exe` | 聚合程序，集成文件分块与文件下载，侧边栏一键切换 |
| GUI（独立） | `wjfk.exe` | 独立程序，功能为文件分块 |
| GUI（独立） | `wjxz.exe` | 独立程序，支持本地合并与远程下载 |


## Releases 程序说明

### 聚合 GUI 程序

#### wjfkxz.exe — 文件分块下载

`wjfkxz.exe` 是聚合程序，集成文件分块与文件下载两大功能，通过侧边栏一键切换。

##### 启动

双击 `wjfkxz.exe` 即可启动。

##### 使用步骤

1. 启动后左侧边栏显示"文件分块"和"文件下载"两个功能入口
2. 点击"文件分块"进入分块界面，操作同 `wjfk.exe`
3. 点击"文件下载"进入下载界面，操作同 `wjxz.exe`
4. 无需开启多个窗口，在侧边栏即可随时切换

各功能的详细操作请参考下方 `wjfk.exe` 和 `wjxz.exe` 的使用说明。

---

### 独立 GUI 程序

#### wjfk.exe — 文件分块

`wjfk.exe` 是独立的文件分块 GUI 工具，将大文件分块为多个小分片。

##### 启动

双击 `wjfk.exe` 即可启动。

##### 使用步骤

1. 点击"浏览"选择要分块的文件
2. 点击"浏览"选择输出目录
3. 设置输出文件名
4. 设置每个分片的大小（1-1024 MB，默认 10 MB）
5. 点击"开始分块"

分块完成后会在输出目录生成：
- `{文件名}-1.fk`、`{文件名}-2.fk`、... — 分片文件
- `{文件名}.fkx` — 信息文件

将 `.fk` 分片和 `.fkx` 文件上传到服务器（保持相同目录结构），即可通过 `.fkx` 文件的 URL 分享给他人下载。

---

#### wjxz.exe — 文件下载

`wjxz.exe` 是独立的文件下载 GUI 工具，支持本地合并和远程下载两种模式。

##### 启动

双击 `wjxz.exe` 即可启动。

##### 本地模式

1. 点击"浏览"选择本地 `.fkx` 信息文件
2. 点击"浏览"选择输出目录
3. 点击"开始合并"

程序会自动读取同目录下的 `.fk` 分片并合并还原。

##### 远程模式

1. 在输入框中填入 `.fkx` 文件的完整 URL（如 `https://example.com/files/video.mp4.fkx`）
2. 点击"浏览"选择输出目录
3. 勾选或取消"启用增强模式/启用SHA-256检验"（默认勾选）
4. 设置"并发分片数"（1-16，默认 3；仅远程模式可调，本地模式下该控件自动禁用）
5. 点击"开始下载"

程序会自动下载 `.fkx` 信息文件、并发下载 `.fk` 分片、合并还原并校验 SHA-256。

**断点续传**：下载中断（网络错误、手动取消等）后，已下载的分片会保留在 `{输出目录}/{文件名}-fkxz/` 分片目录中。再次点击"开始下载"时，程序会自动跳过已完整下载的分片（大小 + SHA-256 校验），残缺分片用 `Range: bytes=<已有长度>-` 从断点续传，全部下载完成后自动清理分片目录。

##### 增强模式

- **默认启用**：勾选后使用 `curl_cffi` 模拟 Chrome 浏览器，自动模拟浏览器请求头，可绕过 Cloudflare 验证、EdgeOne Pages、防盗链等反爬虫保护
- **取消勾选**：使用标准 `requests` 库进行下载

## 快速开始

### 方式一：源码运行

```bash
git clone https://github.com/zsh-cn/fkxz.git
cd fkxz
python -m venv .venv        # 创建虚拟环境（可选）
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux / macOS
pip install -r requirements.txt
python wjfk.py                 # 启动分块 GUI
python wjxz.py                 # 启动下载 GUI
python main.py                 # 启动聚合 GUI
```

### 方式二：直接下载 exe（无需 Python 环境）

前往 [Releases](https://github.com/zsh-cn/fkxz/releases) 下载已打包的 `.exe` 程序，解压后直接双击运行即可。详见上方 [Releases 已打包程序使用说明](#releases-已打包程序使用说明)。

## 组件说明

### 聚合 GUI 工具

#### main.py — 聚合程序

Tkinter 图形界面，集成文件分块与文件下载两大功能，通过侧边栏实现功能切换。

- 左侧边栏持久化显示"文件分块"和"文件下载"两个功能入口
- 点击侧边栏按钮即可在两项功能之间切换，无需开启多个窗口

### 独立 GUI 工具

#### wjfk.py — 文件分块

Tkinter 图形界面，将大文件分块为多个 `.fk` 分片，并生成 `.fkx` 信息文件。

- 支持自定义分片大小（1-1024 MB）
- 单遍读写：边读边写分片，同时算出分片与整个文件的 SHA-256（不再回读源文件，内存占用约 1 MB）
- 每个分片及原始文件均计算 SHA-256 校验值
- 状态栏实时进度（`正在分块 i/n | 已处理 / 总大小 | 速度`），速度按 `utils.measured_speed` 口径：不足 0.5 秒显示 `--`
- 支持取消分块操作

#### wjxz.py — 文件下载

Tkinter 图形界面，读取 `.fkx` 信息文件，获取所有分片并合并还原。

- **本地模式**：从本地目录读取 `.fkx` 和 `.fk` 文件直接合并（只核对分片是否齐备，没有传输过程，进度只显示字节量与分片计数，不显示速度）
- **远程模式**：从 URL 下载 `.fkx` 文件，并发下载 `.fk` 分片后合并（并发数 1-16 可调，本地模式下该控件自动禁用）
- 实时进度显示（单条字节进度条 + 百分比 / 已下载量 / 速度 / 分片计数，进度回调按时间节流）
- 速度统计只算真实网络字节：复用已有分片、断点续传的偏移量都划入基准不计速；计时从首块数据到达才开始，不足 0.5 秒先显示 `--`，避免首帧出现几 GB/s 的瞬时虚高（分块、合并两处进度共用同一口径）
- SHA-256 完整性校验：分片边下边校验，合并时同步算出成品哈希直接比对，不再二次整读
- 断点续传：已下载分片按大小 + SHA-256 跳过，残缺分片用 `Range` 续传；单分片失败按指数退避重试 3 次
- 续传可靠性：`.part` 文件名带「进程号 + 本轮运行序号」，上一轮还没退出的线程不会和新一轮抢同一个文件；历史遗留的 `.part` 会被新一轮认领（跨进程/重启也能续）；已经下完但改名失败的 `.part` 只复算哈希、不再重下一遍；`os.replace` 遇到 Windows 临时占用（WinError 5/32/33）自动退避重试
- 每轮下载有独立的运行序号与停止信号：上一轮遗留线程既改不动本轮进度（不会出现进度反复回退），也不会被新一轮的"重新开始"唤醒
- 自动清理临时文件
- **增强模式**（默认启用）：界面提供复选框，勾选后使用 `curl_cffi` 模拟 Chrome 浏览器，自动模拟浏览器请求头（User-Agent、Sec-Ch-Ua、Sec-Fetch-\* 等），支持 Referer 头信息传递，可绕过反爬虫保护（如 Cloudflare 验证、EdgeOne Pages、防盗链等）。取消勾选则使用标准请求模式

### 版本与关于

版本号只在 `config.py` 的 `APP_VERSION` 维护一处，三个程序启动后都可通过菜单栏一级「关于」查看。

### 公共模块

#### core.py — 分块/合并内核

只做「`.fkx` 格式 + 分片读写」的最小内核（纯标准库，不依赖 Tkinter），可脱离界面单独调用或测试：

- `.fkx` 格式：后缀与分片命名、文本编解码（UTF-8 BOM / GB18030 兼容）、解析与原子写入
- `split_file()` 单遍读源文件产出 `.fk` 分片与清单，同时算出分片与整文件 SHA-256
- `merge_chunks()` 按序把分片字节写进调用方指定的成品路径，边写边算 SHA-256
- 进度与取消以回调注入（`on_progress` / `should_stop`），取消时自动清理半成品

刻意不含校验逻辑：哈希比对、已有分片复用、字节数核对、文件名净化、路径越界、重名避让
一律由调用方（`utils.py` / `wjfk.py` / `wjxz.py`）负责，内核只按格式读写字节。

#### utils.py — 界面公共工具

各 GUI 程序共享的工具函数：

- DPI 感知设置与高分屏自适应窗口尺寸
- 工作线程 → 主线程的 UI 调用桥（队列 + 定时泵，高频刷新自动合帧）与时间节流器
- 图标路径解析（兼容 PyInstaller 打包环境）与 Tkinter 图标加载
- 目录/文件选择对话框封装、输入框右键菜单（剪切/复制/粘贴/删除/全选）
- 文件名净化 `safe_filename`、重名避让 `unique_path`、路径越界校验 `ensure_within_dir`、
  临时文件 `part_path_for` / 删除 `safe_remove`、带占用重试的改名 `replace_with_retry`、流式 SHA-256 `sha256_file`
- 速度显示统一口径：`measured_speed(processed, started)` 不足 `SPEED_MIN_INTERVAL`（0.5s）返回 `None`，
  `speed_text()` 把 `None` 翻译成 `--`；下载、分块、合并三处进度都走这两个函数
- 统一 GUI 启动入口 `run_gui_app`

### 网页端工具 — `web/`

#### sw.js + index.html — Service Worker 下载器

基于 Service Worker 的浏览器端文件下载器，通过 SW 拦截请求并在浏览器端流式合并分片后返回完整文件。

- **sw.js**：Service Worker 脚本，拦截 `/fkxz` 路径的请求，解析 `.fkx` 文件获取分片列表，逐个抓取 `.fk` 分片并通过 `ReadableStream` 流式合并，最终以单个文件形式返回给浏览器下载。
- **index.html**：配套前端页面，自动注册 Service Worker，解析 `.fkx` 文件并展示文件信息，点击下载按钮后通过 SW 代理完成流式合并下载。
  响应带 `Accept-Ranges: bytes`，暂停/继续完全交给浏览器下载管理器：它续传时会带 `Range` 头发起新请求，
  SW 按字节偏移定位到对应分片，返回 `206 + Content-Range` 从断点继续拼接，页面侧不保存任何进度状态。

Service Worker 方案的优势在于：
- 无需 File System Access API，兼容性更好
- 合并过程在 SW 后台线程完成，不阻塞主线程
- 直接触发浏览器原生下载行为，用户体验更流畅
- 页面侧始终同源，不涉及 CORS；但分片服务器仍需允许跨域（响应带 `Access-Control-Allow-Origin`），
  SW 里的 `fetch` 默认就是 `cors` 模式，**并不能绕过跨域限制**

## 使用方式

### 聚合 GUI 工具

#### 聚合程序（分块 + 下载）

```bash
python main.py
```

启动后左侧边栏显示"文件分块"和"文件下载"两个功能入口，点击侧边栏按钮即可切换。无需开启多个窗口。

### 独立 GUI 工具

#### 分块文件

```bash
python wjfk.py
```

在 GUI 中选择要分块的文件、输出目录和分片大小，点击"开始分块"。

分块完成后可将 `.fk` 分片和 `.fkx` 文件上传到服务器，保持相同目录结构，使用 `.fkx` 文件信息 URL 以供分享、下载。

#### 合并文件（本地/远程）

```bash
python wjxz.py
```

在输入框中填入 `.fkx` 文件的本地路径或完整 URL，选择输出目录。界面默认勾选**增强模式**（使用 curl_cffi 浏览器模拟以绕过反爬虫），和**启用SHA-256检验**。可根据需要取消勾选切换为标准模式/跳过SHA-256检验。点击"开始合并"（本地）或"开始下载"（远程）。

### 网页端方式

1. 将 `web/index.html` 和 `web/sw.js` 部署到同一目录下的静态文件服务器
2. 通过 URL 参数提供 `.fkx` 文件地址：
   `https://your-domain.com/index.html?fkx=https://example.com/file.fkx`
3. 页面自动解析文件信息，点击"下载"按钮即可触发 SW 流式合并下载
- 要求站点必须使用 HTTPS 或 localhost（Service Worker 安全策略要求）
- `sw.js` 必须与 `index.html` 同源部署

## 环境要求

### Python 工具

| 组件 | 最低版本 | 依赖 |
|------|---------|------|
| 聚合 GUI | Python 3.8+ | `requests`、`tkinter`（Linux 需 `apt install python3-tk`） |
| 独立 GUI | Python 3.8+ | `requests`、`tkinter`（Linux 需 `apt install python3-tk`） |
| 增强模式 | Python 3.8+ | `requests` + `curl_cffi` |

安装依赖：

```bash
pip install -r requirements.txt
```

- `requests`：HTTP 请求库（必需）
- `curl_cffi`：浏览器模拟库（可选，用于增强模式绕过反爬虫）

### 网页端

- 现代浏览器（推荐 Chrome 90+、Firefox 89+）
- 需浏览器支持 Service Worker API（Chrome 45+、Firefox 44+）

## 文件格式

### .fkx 信息文件

命名格式：`{原文件名}.fkx`（如 `video.mp4.fkx`），内容格式如下：

```
filename=原始文件名
total_size=文件总字节数
chunk_size=分片字节数
num_chunks=分片总数
chunk_1=分片文件名,分片大小,分片SHA-256
chunk_2=分片文件名,分片大小,分片SHA-256
...
sha256=原始文件SHA-256
```

> `chunk_N` 从 1 开始且必须连续；`total_size` 会在合并时与累计写入字节数比对。

### .fk 分片文件

命名格式：`{原文件名}-{索引}.fk`

## PyInstaller 打包说明

如果你想自行从源码打包为 `.exe` 可执行程序，可以使用 PyInstaller。

### 安装 PyInstaller

```bash
pip install pyinstaller
```

### 打包命令

在项目根目录下执行以下命令，打包产物输出至 `docs/dist/` 目录：

#### 打包 wjfk.exe（文件分块）

```bash
pyinstaller --onefile --windowed --name wjfk --distpath docs/dist --icon icon/wjfk.ico --add-data "icon;icon" wjfk.py
```

- `--icon icon/wjfk.ico`：设置 exe 程序图标
- 任务栏/窗口图标：`icon/wjfk.png`（通过 `--add-data` 打包，程序运行时自动加载）

#### 打包 wjfkxz.exe（聚合程序）

```bash
pyinstaller --onefile --windowed --name wjfkxz --distpath docs/dist --icon icon/wjfkxz.ico --add-data "icon;icon" main.py
```

- `--icon icon/wjfkxz.ico`：设置 exe 程序图标
- `--add-data "icon;icon"`：打包图标资源（窗口/任务栏图标 `icon/wjfkxz.png`）

#### 打包 wjxz.exe（文件下载）

```bash
pyinstaller --onefile --windowed --name wjxz --distpath docs/dist --icon icon/wjxz.ico --add-data "icon;icon" --hidden-import curl_cffi wjxz.py
```

- `--icon icon/wjxz.ico`：设置 exe 程序图标
- `--hidden-import curl_cffi`：显式包含 curl_cffi 模块（增强模式依赖）
- 任务栏/窗口图标：`icon/wjxz.png`（通过 `--add-data` 打包，程序运行时自动加载）

### 打包说明

- 打包后的 exe 文件位于 `docs/dist/` 目录下
- 建议在打包前先执行 `pip install -r requirements.txt` 确保所有依赖已安装
- 打包产生的 `build/` 目录与 `.spec` 文件可手动删除

## 问题反馈

如遇到问题或有功能建议，请通过以下方式反馈：

- **GitHub Issues**：[提交 Issue](https://github.com/zsh-cn/fkxz/issues)
- 提交时请尽量提供以下信息：
  - 使用的程序版本（`wjfkxz.exe` / `wjfk.exe` / `wjxz.exe` /源码运行或网页端下载页面）
  - 操作系统/浏览器版本
  - 问题的详细描述和复现步骤
  - 相关的错误信息或截图

## 免责声明

本工具仅供学习、研究和个人合法用途。使用者应遵守所在国家/地区的法律法规及平台的服务条款，不得将本工具用于任何违法或侵权、违反平台规定的活动。

- 本项目开发者不对使用者的任何不当行为承担责任，使用者需自行承担使用本工具所产生的一切后果和风险

## 许可证

本项目采用 [Mozilla Public License Version 2.0 (MPL-2.0)](LICENSE) 许可证。