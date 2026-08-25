#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import hashlib
import argparse
import time
import shutil
from urllib.parse import urlparse, urljoin

import requests

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
    print(f"\r{prefix}[{bar}] {percent:.1f}% {suffix}", end='', flush=True)


def cmd_split(args):
    file_path = args.input
    output_dir = args.output
    chunk_size_mb = args.chunk_size

    if not os.path.exists(file_path):
        print(f"错误: 文件不存在 - {file_path}")
        sys.exit(1)
    if not os.path.isfile(file_path):
        print(f"错误: 路径不是文件 - {file_path}")
        sys.exit(1)
    if chunk_size_mb < 1 or chunk_size_mb > 1024:
        print(f"错误: 分片大小应在1-1024 MB之间")
        sys.exit(1)

    chunk_size = chunk_size_mb * 1024 * 1024

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    num_chunks = (file_size + chunk_size - 1) // chunk_size

    print(f"文件: {file_name}")
    print(f"大小: {format_size(file_size)}")
    print(f"分片大小: {chunk_size_mb} MB")
    print(f"分片数: {num_chunks}")
    print(f"输出目录: {output_dir}")
    print()

    wjxx_content = [
        f"filename={file_name}",
        f"total_size={file_size}",
        f"chunk_size={chunk_size}",
        f"num_chunks={num_chunks}"
    ]

    with open(file_path, 'rb') as f:
        for i in range(num_chunks):
            chunk_data = f.read(chunk_size)
            chunk_filename = f"{file_name}-{i+1}.fk"
            chunk_path = os.path.join(output_dir, chunk_filename)

            with open(chunk_path, 'wb') as chunk_file:
                chunk_file.write(chunk_data)

            wjxx_content.append(f"chunk_{i+1}={chunk_filename},{len(chunk_data)}")

            print_progress(i + 1, num_chunks,
                           prefix=f"拆分: ",
                           suffix=f"{i+1}/{num_chunks}")

    print()

    print("正在计算SHA-256...")
    file_sha256 = calculate_sha256(file_path)
    wjxx_content.append(f"sha256={file_sha256}")

    wjxx_filename = f"{file_name}.wjx"
    wjxx_path = os.path.join(output_dir, wjxx_filename)
    with open(wjxx_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(wjxx_content))

    print(f"\n拆分完成！")
    print(f"  分片数: {num_chunks}")
    print(f"  信息文件: {wjxx_filename}")
    print(f"  SHA-256: {file_sha256}")
    print(f"  保存位置: {output_dir}")


def parse_wjxx(content):
    info = {'chunks': []}
    lines = content.strip().split('\n')
    for line in lines:
        if '=' in line:
            key, value = line.split('=', 1)
            if key.startswith('chunk_'):
                parts = value.split(',')
                if len(parts) >= 2:
                    chunk_filename = os.path.basename(parts[0].strip())
                    info['chunks'].append({
                        'filename': chunk_filename,
                        'size': int(parts[1])
                    })
            else:
                info[key] = value.strip()
    return info


def read_local_wjxx(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def merge_chunks(wjxx_info, chunk_sources, output_path, num_chunks):
    with open(output_path, 'wb') as out_f:
        for i in range(num_chunks):
            chunk_path = chunk_sources[i]
            chunk_path = os.path.normpath(chunk_path)
            with open(chunk_path, 'rb') as chunk_f:
                for chunk in iter(lambda: chunk_f.read(65536), b""):
                    out_f.write(chunk)
            print_progress(i + 1, num_chunks,
                           prefix="合并: ",
                           suffix=f"{i+1}/{num_chunks}")
    print()


def cmd_merge(args):
    wjxx_path = args.input
    output_dir = args.output

    if not os.path.exists(wjxx_path):
        print(f"错误: .wjx文件不存在 - {wjxx_path}")
        sys.exit(1)
    if not wjxx_path.endswith('.wjx'):
        print(f"错误: 输入必须是.wjx文件")
        sys.exit(1)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    print(f"解析文件信息: {wjxx_path}")
    wjxx_content = read_local_wjxx(wjxx_path)
    wjxx_info = parse_wjxx(wjxx_content)

    if 'filename' not in wjxx_info or 'chunks' not in wjxx_info:
        print("错误: 文件信息格式不正确")
        sys.exit(1)

    num_chunks = len(wjxx_info['chunks'])
    total_size = sum(c['size'] for c in wjxx_info['chunks'])
    base_path = os.path.dirname(os.path.abspath(wjxx_path))

    print(f"文件名: {wjxx_info['filename']}")
    print(f"文件大小: {format_size(total_size)}")
    print(f"分块数: {num_chunks}")
    print()

    chunk_sources = {}
    for i, chunk_info in enumerate(wjxx_info['chunks']):
        chunk_path = os.path.join(base_path, chunk_info['filename'])
        chunk_path = os.path.normpath(chunk_path)
        if not os.path.exists(chunk_path):
            print(f"错误: 分片文件不存在 - {chunk_path}")
            sys.exit(1)
        chunk_sources[i] = chunk_path

    safe_filename = sanitize_filename(os.path.basename(wjxx_info['filename']))
    output_path = os.path.join(output_dir, safe_filename)
    output_path = os.path.normpath(output_path)

    print("正在合并文件...")
    merge_chunks(wjxx_info, chunk_sources, output_path, num_chunks)

    if 'sha256' in wjxx_info:
        print("正在校验SHA-256...")
        actual_sha256 = calculate_sha256(output_path)
        if actual_sha256 != wjxx_info['sha256']:
            print(f"错误: SHA-256校验失败!")
            print(f"  期望: {wjxx_info['sha256']}")
            print(f"  实际: {actual_sha256}")
            os.remove(output_path)
            sys.exit(1)
        print(f"  SHA-256校验通过: {actual_sha256}")

    print(f"\n合并完成！")
    print(f"  文件名: {safe_filename}")
    print(f"  保存位置: {output_path}")


def download_wjxx(url, session, enhanced):
    try:
        if enhanced and HAS_CURL_CFFI:
            response = session.get(url, timeout=120)
        else:
            response = session.get(url, timeout=120, stream=True)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"错误: 无法下载.wjx文件 - {e}")
        return None


def download_chunk_stream(url, chunk_path, chunk_size, session, enhanced, base_referer):
    headers = {}
    if enhanced:
        headers = dict(BROWSER_HEADERS)
        headers["Sec-Fetch-Dest"] = "empty"
        headers["Sec-Fetch-Mode"] = "cors"
        headers["Sec-Fetch-Site"] = "same-origin"
        headers["Sec-Fetch-User"] = "?1"
        headers["Upgrade-Insecure-Requests"] = "1"
        headers["Priority"] = "u=1, i"
        if base_referer:
            headers["Referer"] = base_referer

    try:
        if enhanced and HAS_CURL_CFFI:
            downloaded = [0]

            def content_callback(data):
                f.write(data)
                downloaded[0] += len(data)

            with open(chunk_path, 'wb') as f:
                response = session.get(url, timeout=120, headers=headers,
                                       content_callback=content_callback)
            response.raise_for_status()
        else:
            if enhanced:
                response = session.get(url, stream=True, timeout=120, headers=headers)
            else:
                response = session.get(url, stream=True, timeout=120)
            response.raise_for_status()

            downloaded = 0
            with open(chunk_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)

        return True
    except Exception as e:
        if os.path.exists(chunk_path):
            os.remove(chunk_path)
        print(f"\n错误: 分片下载失败 - {e}")
        return False


def download_chunk(base_url, chunk_info, chunk_index, output_dir, session, enhanced, base_referer):
    chunk_url = urljoin(base_url, chunk_info['filename'])
    chunk_size = chunk_info['size']
    chunk_path = os.path.join(output_dir, chunk_info['filename'])
    chunk_path = os.path.normpath(chunk_path)

    if chunk_size == 0:
        with open(chunk_path, 'wb') as f:
            pass
        return True, chunk_path

    print(f"  下载分片 {chunk_index + 1}: {chunk_info['filename']} ({format_size(chunk_size)})")
    success = download_chunk_stream(chunk_url, chunk_path, chunk_size, session, enhanced, base_referer)

    if success and os.path.exists(chunk_path) and os.path.getsize(chunk_path) == chunk_size:
        return True, chunk_path

    if os.path.exists(chunk_path):
        os.remove(chunk_path)
    return False, None


def cmd_download(args):
    url = args.url
    output_dir = args.output
    enhanced = args.enhanced

    if not url.endswith('.wjx'):
        print("错误: URL必须指向.wjx文件")
        sys.exit(1)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    if enhanced and HAS_CURL_CFFI:
        print("增强模式: 使用 curl_cffi (Chrome 131 指纹)")
        session = curl_requests.Session(impersonate="chrome131")
    elif enhanced:
        print("增强模式: curl_cffi 未安装，使用标准 requests + 浏览器头")
        session = requests.Session()
        session.mount('http://', requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32))
        session.mount('https://', requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32))
    else:
        print("标准模式: 使用 requests")
        session = requests.Session()
        session.mount('http://', requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32))
        session.mount('https://', requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32))

    if enhanced:
        session.headers.update(BROWSER_HEADERS)

    print(f"下载文件信息: {url}")
    wjxx_content = download_wjxx(url, session, enhanced)
    if not wjxx_content:
        print("错误: 无法获取文件信息")
        sys.exit(1)

    wjxx_info = parse_wjxx(wjxx_content)
    if 'filename' not in wjxx_info or 'chunks' not in wjxx_info:
        print("错误: 文件信息格式不正确")
        sys.exit(1)

    num_chunks = len(wjxx_info['chunks'])
    total_size = sum(c['size'] for c in wjxx_info['chunks'])

    parsed = urlparse(url)
    dir_path = parsed.path.rsplit('/', 1)[0] if '/' in parsed.path else ''
    base_url = f"{parsed.scheme}://{parsed.netloc}{dir_path}/"
    base_referer = base_url if enhanced else ""

    safe_filename = sanitize_filename(os.path.basename(wjxx_info['filename']))
    chunk_dir_name = f"{safe_filename}-fkxz"
    chunk_dir = os.path.join(output_dir, chunk_dir_name)
    if os.path.exists(chunk_dir):
        shutil.rmtree(chunk_dir)
    os.makedirs(chunk_dir, exist_ok=True)

    wjxx_save_path = os.path.join(chunk_dir, os.path.basename(urlparse(url).path))
    with open(wjxx_save_path, 'w', encoding='utf-8') as f:
        f.write(wjxx_content)

    print(f"文件名: {wjxx_info['filename']}")
    print(f"文件大小: {format_size(total_size)}")
    print(f"分块数: {num_chunks}")
    print(f"临时目录: {chunk_dir}")
    print()

    downloaded_chunks = {}
    download_start_time = time.time()
    total_downloaded = 0

    for i, chunk_info in enumerate(wjxx_info['chunks']):
        success, chunk_path = download_chunk(base_url, chunk_info, i, chunk_dir,
                                             session, enhanced, base_referer)
        if not success:
            print(f"\n错误: 分片 {i+1} 下载失败，已中止")
            shutil.rmtree(chunk_dir)
            sys.exit(1)

        downloaded_chunks[i] = chunk_path
        total_downloaded += chunk_info['size']

        elapsed = time.time() - download_start_time
        speed = total_downloaded / elapsed if elapsed > 0 else 0
        print_progress(i + 1, num_chunks,
                       prefix=f"总进度: ",
                       suffix=f"{i+1}/{num_chunks} | {format_size(int(speed))}/s")
    print()

    if len(downloaded_chunks) != num_chunks:
        print(f"错误: 下载不完整 - 期望{num_chunks}个，实际{len(downloaded_chunks)}个")
        shutil.rmtree(chunk_dir)
        sys.exit(1)

    print("正在合并文件...")
    output_path = os.path.join(output_dir, safe_filename)
    output_path = os.path.normpath(output_path)
    merge_chunks(wjxx_info, downloaded_chunks, output_path, num_chunks)

    if 'sha256' in wjxx_info:
        print("正在校验SHA-256...")
        actual_sha256 = calculate_sha256(output_path)
        if actual_sha256 != wjxx_info['sha256']:
            print(f"错误: SHA-256校验失败!")
            print(f"  期望: {wjxx_info['sha256']}")
            print(f"  实际: {actual_sha256}")
            os.remove(output_path)
            shutil.rmtree(chunk_dir)
            sys.exit(1)
        print(f"  SHA-256校验通过: {actual_sha256}")

    shutil.rmtree(chunk_dir)

    elapsed = time.time() - download_start_time
    print(f"\n下载完成！")
    print(f"  文件名: {safe_filename}")
    print(f"  大小: {format_size(total_size)}")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  平均速度: {format_size(int(total_size / elapsed)) if elapsed > 0 else 'N/A'}/s")
    print(f"  保存位置: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="分块下载",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python main.py split  -i ./video.mp4 -o ./chunks -c 10
  python main.py merge  -i ./chunks/video.mp4.wjx -o ./output
  python main.py download -u https://example.com/files/video.mp4.wjx -o ./output
  python main.py download -u https://example.com/files/video.mp4.wjx -o ./output --enhanced
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    parser_split = subparsers.add_parser('split', help='拆分文件为分块')
    parser_split.add_argument('-i', '--input', required=True, help='要拆分的文件路径')
    parser_split.add_argument('-o', '--output', required=True, help='输出目录')
    parser_split.add_argument('-c', '--chunk-size', type=int, default=10,
                              help='每个分片大小(MB), 范围1-1024, 默认10')

    parser_merge = subparsers.add_parser('merge', help='本地合并分块文件')
    parser_merge.add_argument('-i', '--input', required=True, help='.wjx信息文件路径')
    parser_merge.add_argument('-o', '--output', required=True, help='输出目录')

    parser_download = subparsers.add_parser('download', help='远程下载并合并文件')
    parser_download.add_argument('-u', '--url', required=True, help='.wjx信息文件的URL')
    parser_download.add_argument('-o', '--output', required=True, help='输出目录')
    parser_download.add_argument('-e', '--enhanced', action='store_true',
                                 help='启用增强模式 (浏览器指纹伪装 + curl_cffi)')

    args = parser.parse_args()

    if args.command == 'split':
        cmd_split(args)
    elif args.command == 'merge':
        cmd_merge(args)
    elif args.command == 'download':
        cmd_download(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()