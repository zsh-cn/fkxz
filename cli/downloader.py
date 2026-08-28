import os
import sys
import time
import shutil
import random
from urllib.parse import urlparse, urljoin

import requests
from requests.adapters import HTTPAdapter

from cli.utils import (
    BROWSER_HEADERS, HAS_CURL_CFFI, curl_requests,
    format_size, sanitize_filename, calculate_sha256, parse_fkx, print_progress
)

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1


def _validate_chunk_filename(filename):
    if '..' in filename or '/' in filename or '\\' in filename:
        raise ValueError(f"非法的分片文件名: {filename}")
    return os.path.basename(filename)


def download_fkx(url, session, enhanced, timeout=120):
    headers = {}
    if enhanced:
        headers = dict(BROWSER_HEADERS)
    try:
        if enhanced and HAS_CURL_CFFI:
            response = session.get(url, timeout=timeout, headers=headers)
        else:
            response = session.get(url, timeout=timeout, stream=True, headers=headers)
        response.raise_for_status()
        return response.text
    except Exception as e:
        sys.stdout.write(f"错误: 无法下载.fkx文件 - {e}\n")
        sys.stdout.flush()
        return None


def _report_download_progress(downloaded, chunk_size):
    pct = min(downloaded / chunk_size * 100, 100)
    sys.stdout.write(
        f"\r    下载中... {format_size(downloaded)}/{format_size(chunk_size)} ({pct:.1f}%)" + " " * 20
    )
    sys.stdout.flush()


def _validate_download_size(downloaded, chunk_size, chunk_path):
    if chunk_size > 0 and downloaded != chunk_size:
        sys.stdout.write(
            f"\r    警告: 下载大小不匹配 "
            f"(期望 {format_size(chunk_size)}, 实际 {format_size(downloaded)})\n"
        )
        sys.stdout.flush()
        if os.path.exists(chunk_path):
            os.remove(chunk_path)
        return False
    return True


def download_chunk_stream(url, chunk_path, chunk_size, session, enhanced, base_referer, timeout=120):
    headers = {}
    if enhanced:
        headers = dict(BROWSER_HEADERS)
        headers["Sec-Fetch-Dest"] = "empty"
        headers["Sec-Fetch-Mode"] = "cors"
        headers["Sec-Fetch-Site"] = "same-origin"
        if base_referer:
            headers["Referer"] = base_referer

    try:
        downloaded = [0]
        last_report = [0]

        if enhanced and HAS_CURL_CFFI:
            def content_callback(data):
                f.write(data)
                downloaded[0] += len(data)
                if chunk_size > 0 and downloaded[0] - last_report[0] >= 65536:
                    _report_download_progress(downloaded[0], chunk_size)
                    last_report[0] = downloaded[0]

            with open(chunk_path, 'wb') as f:
                response = session.get(url, timeout=timeout, headers=headers,
                                       content_callback=content_callback)
            response.raise_for_status()
        else:
            response = session.get(url, stream=True, timeout=timeout, headers=headers)
            response.raise_for_status()

            with open(chunk_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=65536):
                    f.write(chunk)
                    downloaded[0] += len(chunk)
                    if chunk_size > 0 and downloaded[0] - last_report[0] >= 65536:
                        _report_download_progress(downloaded[0], chunk_size)
                        last_report[0] = downloaded[0]

        if not _validate_download_size(downloaded[0], chunk_size, chunk_path):
            return False

        sys.stdout.write(f"\r    下载完成: {format_size(chunk_size)}" + " " * 20 + "\n")
        sys.stdout.flush()
        return True
    except Exception as e:
        if os.path.exists(chunk_path):
            os.remove(chunk_path)
        sys.stdout.write(f"\n    错误: 分片下载失败 - {e}\n")
        sys.stdout.flush()
        return False


def download_chunk(base_url, chunk_info, chunk_index, output_dir, session, enhanced, base_referer, timeout=120):
    chunk_filename = _validate_chunk_filename(chunk_info['filename'])
    chunk_url = urljoin(base_url, chunk_filename)
    chunk_size = chunk_info['size']
    chunk_path = os.path.join(output_dir, chunk_filename)
    chunk_path = os.path.normpath(chunk_path)

    if chunk_size == 0:
        with open(chunk_path, 'wb') as f:
            pass
        sys.stdout.write(f"  [{chunk_index + 1}] {chunk_filename} (空文件, 跳过)\n")
        sys.stdout.flush()
        return True, chunk_path

    sys.stdout.write(f"  [{chunk_index + 1}] {chunk_filename} ({format_size(chunk_size)})\n")
    sys.stdout.flush()

    for attempt in range(1, MAX_RETRIES + 1):
        success = download_chunk_stream(chunk_url, chunk_path, chunk_size, session, enhanced, base_referer, timeout)
        if success and os.path.exists(chunk_path) and os.path.getsize(chunk_path) == chunk_size:
            return True, chunk_path

        if os.path.exists(chunk_path):
            os.remove(chunk_path)

        if attempt < MAX_RETRIES:
            delay = RETRY_BASE_DELAY * attempt + random.uniform(0, 0.5)
            sys.stdout.write(f"    重试 {attempt}/{MAX_RETRIES - 1}，{delay:.1f}s 后重试...\n")
            sys.stdout.flush()
            time.sleep(delay)

    sys.stdout.write(f"    错误: 分片 {chunk_index + 1} 下载失败（已重试 {MAX_RETRIES} 次）\n")
    sys.stdout.flush()
    return False, None


def cmd_download(args):
    url = args.url
    output_dir = args.output
    enhanced = args.enhanced
    timeout = args.timeout

    if not url.endswith('.fkx'):
        sys.stdout.write("错误: URL必须指向.fkx文件\n")
        sys.stdout.flush()
        sys.exit(1)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    if enhanced and HAS_CURL_CFFI:
        sys.stdout.write("增强模式: 使用 curl_cffi (Chrome 131 指纹)\n")
        session = curl_requests.Session(impersonate="chrome131")
    elif enhanced:
        sys.stdout.write("增强模式: curl_cffi 未安装，使用标准 requests + 浏览器头\n")
        session = requests.Session()
        session.mount('http://', HTTPAdapter(pool_connections=32, pool_maxsize=32))
        session.mount('https://', HTTPAdapter(pool_connections=32, pool_maxsize=32))
    else:
        sys.stdout.write("标准模式: 使用 requests\n")
        session = requests.Session()
        session.mount('http://', HTTPAdapter(pool_connections=32, pool_maxsize=32))
        session.mount('https://', HTTPAdapter(pool_connections=32, pool_maxsize=32))
    sys.stdout.flush()

    if enhanced:
        session.headers.update(BROWSER_HEADERS)

    sys.stdout.write(f"下载文件信息: {url}\n")
    sys.stdout.flush()
    fkx_content = download_fkx(url, session, enhanced, timeout)
    if not fkx_content:
        sys.stdout.write("错误: 无法获取文件信息\n")
        sys.stdout.flush()
        sys.exit(1)

    fkx_info = parse_fkx(fkx_content)
    if 'filename' not in fkx_info or 'chunks' not in fkx_info:
        sys.stdout.write("错误: 文件信息格式不正确\n")
        sys.stdout.flush()
        sys.exit(1)

    num_chunks = len(fkx_info['chunks'])
    total_size = sum(c['size'] for c in fkx_info['chunks'])

    parsed = urlparse(url)
    dir_path = parsed.path.rsplit('/', 1)[0] if '/' in parsed.path else ''
    base_url = f"{parsed.scheme}://{parsed.netloc}{dir_path}/"
    base_referer = base_url if enhanced else ""

    safe_filename = sanitize_filename(os.path.basename(fkx_info['filename']))
    chunk_dir_name = f"{safe_filename}-fkxz"
    chunk_dir = os.path.join(output_dir, chunk_dir_name)
    if os.path.exists(chunk_dir):
        shutil.rmtree(chunk_dir)
    os.makedirs(chunk_dir, exist_ok=True)

    fkx_save_path = os.path.join(chunk_dir, os.path.basename(urlparse(url).path))
    with open(fkx_save_path, 'w', encoding='utf-8') as f:
        f.write(fkx_content)

    sys.stdout.write(f"文件名: {fkx_info['filename']}\n")
    sys.stdout.write(f"文件大小: {format_size(total_size)}\n")
    sys.stdout.write(f"分片数: {num_chunks}\n")
    sys.stdout.write(f"临时目录: {chunk_dir}\n")
    sys.stdout.write("\n")
    sys.stdout.flush()

    downloaded_chunks = {}
    download_start_time = time.time()
    total_downloaded = 0

    for i, chunk_info in enumerate(fkx_info['chunks']):
        success, chunk_path = download_chunk(base_url, chunk_info, i, chunk_dir,
                                             session, enhanced, base_referer, timeout)
        if not success:
            sys.stdout.write(f"\n错误: 分片 {i+1} 下载失败，已中止\n")
            sys.stdout.flush()
            shutil.rmtree(chunk_dir)
            sys.exit(1)

        downloaded_chunks[i] = chunk_path
        total_downloaded += chunk_info['size']

        elapsed = time.time() - download_start_time
        speed = total_downloaded / elapsed if elapsed > 0 else 0
        print_progress(i + 1, num_chunks,
                       prefix=f"总进度: ",
                       suffix=f"{i+1}/{num_chunks} | {format_size(int(speed))}/s")
        sys.stdout.write("\n")
    sys.stdout.write("\n")
    sys.stdout.flush()

    if len(downloaded_chunks) != num_chunks:
        sys.stdout.write(f"错误: 下载不完整 - 期望{num_chunks}个，实际{len(downloaded_chunks)}个\n")
        sys.stdout.flush()
        shutil.rmtree(chunk_dir)
        sys.exit(1)

    sys.stdout.write("正在合并文件...\n")
    sys.stdout.flush()
    output_path = os.path.join(output_dir, safe_filename)
    output_path = os.path.normpath(output_path)

    from cli.merger import merge_chunks
    merge_chunks(downloaded_chunks, output_path, num_chunks, total_size)

    if 'sha256' in fkx_info:
        sys.stdout.write("正在校验SHA-256...\n")
        sys.stdout.flush()
        actual_sha256 = calculate_sha256(output_path)
        if actual_sha256 != fkx_info['sha256']:
            sys.stdout.write(f"错误: SHA-256校验失败!\n")
            sys.stdout.write(f"  期望: {fkx_info['sha256']}\n")
            sys.stdout.write(f"  实际: {actual_sha256}\n")
            sys.stdout.flush()
            os.remove(output_path)
            shutil.rmtree(chunk_dir)
            sys.exit(1)
        sys.stdout.write(f"  SHA-256校验通过: {actual_sha256}\n")
        sys.stdout.flush()

    shutil.rmtree(chunk_dir)

    elapsed = time.time() - download_start_time
    sys.stdout.write(f"\n下载完成！\n")
    sys.stdout.write(f"  文件名: {safe_filename}\n")
    sys.stdout.write(f"  大小: {format_size(total_size)}\n")
    sys.stdout.write(f"  耗时: {elapsed:.1f}s\n")
    sys.stdout.write(f"  平均速度: {format_size(int(total_size / elapsed)) if elapsed > 0 else 'N/A'}/s\n")
    sys.stdout.write(f"  保存位置: {output_path}\n")
    sys.stdout.flush()
