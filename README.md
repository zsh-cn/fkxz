# 分块下载 - 大文件分片传输工具

将大文件拆分为多个小分片，支持本地合并与远程 HTTP 流式合并，可用于绕过文件上传大小限制。

## 项目结构

```
fkxz/
├── file_splitter.py      # 文件拆分器（GUI）
├── file_downloader.py    # 文件下载/合并器（GUI）
└── worker.js             # Cloudflare Workers脚本
```

## 工作流程

```
大文件 → file_splitter.py → .fk 分片 + .wjx 信息文件
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
              本地模式                    远程模式
          file_downloader.py         上传到云端获得直链
          （直接读取本地分片）              │
                                    worker.js / file_downloader.py
                                          │
                                    合并后的原始文件
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
注：此脚本不适用于500MB以上大文件

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

在输入框中填入 `.wjx` 文件的本地路径，选择输出目录，点击"开始下载"。

### 合并文件（远程）

1. 将 `.fk` 分片和 `.wjx` 文件上传到 HTTP 服务器，保持相同目录结构
2. 在 `file_downloader.py` 中输入 `.wjx` 文件的完整 URL
3. 或通过 Cloudflare Workers 部署 `worker.js`，访问 `https://your-worker.workers.dev/?wjx=https://example.com/file.wjx`

## 环境要求

- Python 3.6+
- requests 库（`pip install requests`）
- Cloudflare Workers 账户（可选，用于脚本部署）

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