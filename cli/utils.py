import os
import sys
import hashlib
from typing import Any

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    curl_requests = None
    HAS_CURL_CFFI = False

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


def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def sanitize_filename(filename):
    filename = os.path.basename(filename)
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename


def calculate_sha256(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def print_progress(current, total, prefix="", suffix=""):
    bar_len = 40
    filled = int(bar_len * current / total) if total > 0 else 0
    bar = '#' * filled + '-' * (bar_len - filled)
    percent = (current / total * 100) if total > 0 else 0
    sys.stdout.write(f"\r{prefix}[{bar}] {percent:.1f}% {suffix}" + " " * 60)
    sys.stdout.flush()


def parse_fkx(content):
    info: dict[str, Any] = {'chunks': []}
    lines = content.strip().split('\n')
    raw_chunks = {}

    for line in lines:
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key.startswith('chunk_'):
            try:
                index = int(key.split('_', 1)[1])
            except ValueError:
                continue
            parts = value.split(',')
            if len(parts) >= 2:
                chunk_filename = os.path.basename(parts[0].strip())
                if index in raw_chunks:
                    raise ValueError(f"chunk 索引重复: chunk_{index}")
                raw_chunks[index] = {
                    'filename': chunk_filename,
                    'size': int(parts[1])
                }
        else:
            info[key] = value.strip()

    if not raw_chunks:
        raise ValueError("未找到任何 chunk 条目")

    sorted_indices = sorted(raw_chunks.keys())
    expected_start = 1
    for i, idx in enumerate(sorted_indices):
        if idx != expected_start + i:
            raise ValueError(
                f"chunk 索引不连续: 期望 chunk_{expected_start + i}, 实际 chunk_{idx}"
            )

    info['chunks'] = [raw_chunks[idx] for idx in sorted_indices]
    return info