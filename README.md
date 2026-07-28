# 分块下载 - 大文件分片传输工具

将大文件拆分为多个小分片，支持本地合并与远程 HTTP 流式合并，可用于绕过文件上传大小限制。

## 项目结构

```
fkxz/
├── file_splitter.py      # 文件拆分器（GUI）
├── file_downloader.py    # 文件下载/合并器（GUI）
├── worker.js             # Cloudflare Workers 脚本
└── index.html            # 网页端文件下载器
```

## 组件说明

### file_splitter.py — 文件拆分器

Tkinter 图形界面，将大文件拆分为多个 `.fk` 分片，并生成 `.wjx` 信息文件。

- 支持自定义分片大小（1-1024 MB）
- 每个分片及原始文件均计算 MD5 校验值
- 支持取消拆分操作

### file_downloader.py — 文件下载/合并器

Tkinter 图形界面，读取 `.wjx` 信息文件，获取所有分片并合并还原。

- **本地模式**：从本地目录读取 `.wjx` 和 `.fk` 文件直接合并
- **远程模式**：从 URL 下载 `.wjx` 文件，逐个下载 `.fk` 分片后合并
- 实时进度显示（分片进度 / 总进度 / 下载速度）
- MD5 完整性校验
- 自动清理临时文件

### worker.js — Cloudflare Workers 后端

部署在 Cloudflare Workers 上的 HTTP 服务，接收 `?wjx=` 参数，流式合并分片并提供下载。

- 自动解析 `.wjx` 文件获取分片列表
- 使用 `FixedLengthStream` 流式合并
- 自动设置 `Content-Disposition` 触发浏览器下载
- 支持跨域（CORS）
- 注：此脚本不适用于 500MB 以上大文件

### index.html — 网页端文件下载器

轻量级的浏览器端文件下载器，支持通过 URL 参数直接解析 `.wjx` 文件并下载合并后的完整文件。

- 纯前端实现，无需后端支持
- 支持流式下载和实时进度显示
- 自动检测并使用 File System Access API（现代浏览器）
- 支持回退到传统下载方式

## 使用方式

### 拆分文件

```bash
python file_splitter.py
```

在 GUI 中选择要拆分的文件、输出目录和分片大小，点击"开始拆分"。

### 合并文件（本地）

```bash
python file_downloader.py
```

在输入框中填入 `.wjx` 文件的本地路径，选择输出目录，点击"开始合并"。

### 合并文件（远程）

#### 方式一：使用 Python 下载器

```bash
python file_downloader.py
```

在输入框中输入 `.wjx` 文件的完整 URL，选择输出目录，点击"开始下载"。

#### 方式二：使用 Cloudflare Workers

1. 将 `.fk` 分片和 `.wjx` 文件上传到 HTTP 服务器，保持相同目录结构
2. 部署 `worker.js` 到 Cloudflare Workers
3. 访问 `https://your-worker.workers.dev/?wjx=https://example.com/file.wjx`

#### 方式三：使用网页端下载器

1. 将 `index.html` 部署到任意静态文件服务器或直接在浏览器中打开
2. 通过 URL 参数提供 `.wjx` 文件地址：`https://your-domain.com/index.html?wjx=https://example.com/file.wjx`

## 环境要求

### Python 工具
- Python 3.6+
- requests 库（`pip install requests`）

### Cloudflare Workers（可选）
- Cloudflare Workers 账户

### 网页端
- 现代浏览器（推荐 Chrome 90+、Firefox 89+）

## 文件格式

### .wjx 信息文件

```
filename=原始文件名
total_size=文件总字节数
chunk_size=分片字节数
num_chunks=分片总数
chunk_0=分片文件名,分片大小,MD5
chunk_1=分片文件名,分片大小,MD5
...
md5=原始文件MD5值
```

### .fk 分片文件

命名格式：`{原文件名}-{索引}.fk`