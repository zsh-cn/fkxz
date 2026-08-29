import os
import hashlib
import shutil
import threading
import time
from urllib.parse import urlparse, urljoin

import requests as req_lib
from requests.adapters import HTTPAdapter

from core.base_worker import BaseWorker
from utils.helpers import parse_fkx, sanitize_filename, format_size, is_remote_url, resolve_local_path, calculate_sha256

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


class FileDownloader(BaseWorker):
    def __init__(self, callbacks=None):
        super().__init__(callbacks=callbacks)
        self._session = None
        self._enhanced = False
        self._total_size = 0
        self._progress_callback = None
        self._progress_lock = threading.Lock()
        self._last_chunk_error = ""

    def cancel(self):
        self._is_cancelled = True
        self._close_session()

    def _emit_download_status(self, downloaded, total, speed):
        cb = self.callbacks.get('on_download_status')
        if cb:
            cb(downloaded, total, speed)

    def _ask_retry(self, title, message):
        cb = self.callbacks.get('on_ask_retry')
        if cb:
            return cb(title, message)
        return False

    def _create_session(self, enhanced):
        if enhanced and HAS_CURL_CFFI:
            session = curl_requests.Session(impersonate="chrome131")  # type: ignore[union-attr]
        else:
            session = req_lib.Session()
            session.mount('http://', HTTPAdapter(pool_connections=32, pool_maxsize=32))
            session.mount('https://', HTTPAdapter(pool_connections=32, pool_maxsize=32))
        session.headers.update(BROWSER_HEADERS)
        return session

    def _get_request_headers(self, referer=None, is_chunk=False):
        headers = dict(BROWSER_HEADERS)
        if is_chunk:
            headers["Sec-Fetch-Dest"] = "empty"
            headers["Sec-Fetch-Mode"] = "cors"
            headers["Sec-Fetch-Site"] = "same-origin"
            headers["Sec-Fetch-User"] = "?1"
            headers["Upgrade-Insecure-Requests"] = "1"
            headers["Priority"] = "u=1, i"
        if referer:
            headers["Referer"] = referer
        return headers

    def _download_text(self, url):
        if self._session is None:
            return None
        try:
            if self._is_cancelled:
                return None
            headers = self._get_request_headers()
            resp = self._session.get(url, timeout=120, headers=headers)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            self._emit_status(f"网络错误 - {str(e)[:50]}", '#cc0000')
            return None

    def _download_chunk(self, url, chunk_path, chunk_size, referer):
        if self._session is None:
            self._last_chunk_error = "网络会话未初始化"
            return False
        try:
            headers = self._get_request_headers(referer=referer, is_chunk=True)
            downloaded_bytes = [0]
            last_reported = [0]

            if self._enhanced and HAS_CURL_CFFI:
                fh_ref: list = [None]

                def content_callback(data):
                    if self._is_cancelled:
                        return -1
                    fh_ref[0].write(data)
                    downloaded_bytes[0] += len(data)
                    d = downloaded_bytes[0]
                    if d - last_reported[0] >= 65536 or d >= chunk_size:
                        last_reported[0] = d
                        with self._progress_lock:
                            cb = self._progress_callback
                        if cb:
                            cb(d, chunk_size, len(data))

                with open(chunk_path, 'wb') as f:
                    fh_ref[0] = f
                    resp = self._session.get(url, timeout=120, headers=headers, content_callback=content_callback)  # type: ignore[call-arg]
                resp.raise_for_status()
            else:
                resp = self._session.get(url, stream=True, timeout=120, headers=headers)
                resp.raise_for_status()

                with open(chunk_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if self._is_cancelled:
                            return False
                        f.write(chunk)
                        downloaded_bytes[0] += len(chunk)
                        with self._progress_lock:
                            cb = self._progress_callback
                        if cb:
                            cb(downloaded_bytes[0], chunk_size, len(chunk))

            if self._is_cancelled:
                return False

            if os.path.exists(chunk_path) and os.path.getsize(chunk_path) == chunk_size:
                return True

            self._last_chunk_error = (
                f"下载大小不匹配 (期望 {chunk_size}, 实际 {os.path.getsize(chunk_path)})"
            )
            return False
        except Exception as e:
            self._last_chunk_error = str(e)[:100]
            return False

    def _get_chunk_dir(self, output_dir, safe_name):
        chunk_dir_name = f"{safe_name}-fkxz" if safe_name else "fkwj"
        chunk_dir = os.path.join(output_dir, chunk_dir_name)
        if not os.path.exists(chunk_dir):
            os.makedirs(chunk_dir)
        return chunk_dir

    def _cleanup_chunk_dir(self, chunk_dir):
        if chunk_dir and os.path.exists(chunk_dir):
            shutil.rmtree(chunk_dir, ignore_errors=True)

    def _close_session(self):
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    def _fetch_and_parse_fkx(self, fkx_url, enhanced, emit_status=True):
        if not fkx_url:
            return None, "请输入文件信息URL", None

        if not fkx_url.endswith('.fkx'):
            return None, "输入必须是.fkx文件", None

        if is_remote_url(fkx_url):
            self._enhanced = enhanced and HAS_CURL_CFFI
            self._session = self._create_session(enhanced)

            if emit_status:
                self._emit_status("正在获取文件信息...")
            fkx_content = self._download_text(fkx_url)

            if self._is_cancelled:
                return None, None, None

            if not fkx_content:
                return None, "无法下载文件信息", None
        else:
            fkx_path = resolve_local_path(fkx_url)
            if not os.path.exists(fkx_path):
                return None, f"本地文件不存在: {fkx_path}", None
            if not os.path.isfile(fkx_path):
                return None, f"路径不是文件: {fkx_path}", None
            if emit_status:
                self._emit_status("正在读取文件信息...")
            try:
                with open(fkx_path, 'r', encoding='utf-8') as f:
                    fkx_content = f.read()
            except Exception as e:
                return None, f"无法读取文件信息: {str(e)}", None

        fkx_info = parse_fkx(fkx_content)

        if 'filename' not in fkx_info or 'chunks' not in fkx_info:
            return None, "文件信息格式不正确", None

        num_chunks = len(fkx_info['chunks'])
        total_size = sum(chunk['size'] for chunk in fkx_info['chunks'])

        self._emit_file_info({
            'filename': fkx_info.get('filename', '-'),
            'total_size': total_size,
            'num_chunks': num_chunks,
        })

        if emit_status:
            self._emit_status("文件信息已获取", '#006600')

        return fkx_info, None, fkx_content

    def fetch_fkx_info_async(self, fkx_url, enhanced=True):
        self._is_cancelled = False
        self._thread = threading.Thread(
            target=self._fetch_fkx_info,
            args=(fkx_url, enhanced),
            daemon=True
        )
        self._thread.start()

    def download_async(self, fkx_url, output_dir, enhanced=True, verify_sha256=True):
        self._is_cancelled = False
        self._thread = threading.Thread(
            target=self._download,
            args=(fkx_url, output_dir, enhanced, verify_sha256),
            daemon=True
        )
        self._thread.start()

    def _fetch_fkx_info(self, fkx_url, enhanced):
        try:
            fkx_info, error, _ = self._fetch_and_parse_fkx(fkx_url, enhanced, emit_status=True)
            if self._is_cancelled:
                self._emit_status("已取消获取", '#cc0000')
                return
            if error:
                self._emit_status(error, '#cc0000')
                return
        except Exception as e:
            self._emit_status(f"获取文件信息失败: {str(e)[:100]}", '#cc0000')

    @staticmethod
    def _validate_chunk_filename(filename):
        if '..' in filename or '/' in filename or '\\' in filename:
            raise ValueError(f"非法的分片文件名: {filename}")
        return os.path.basename(filename)

    def _check_existing_chunk(self, chunk_dir, chunk_info):
        chunk_path = os.path.join(chunk_dir, chunk_info['filename'])
        chunk_path = os.path.normpath(chunk_path)
        if not os.path.exists(chunk_path):
            return None
        if os.path.getsize(chunk_path) != chunk_info['size']:
            return None
        if 'sha256' in chunk_info:
            self._emit_status(f"正在校验分片: {chunk_info['filename']}")
            actual_sha256 = calculate_sha256(
                chunk_path,
                cancel_check=lambda: self._is_cancelled,
                progress_callback=lambda p, t: self._on_chunk_sha256_progress(p, t, chunk_info['filename'])
            )
            if self._is_cancelled:
                return None
            if actual_sha256 == chunk_info['sha256']:
                self._emit_chunk_progress(100, 100)
                return chunk_path
            return None
        return chunk_path

    def _sync_local_fkx(self, chunk_dir, remote_fkx_content, fkx_filename):
        local_fkx_path = os.path.join(chunk_dir, fkx_filename)
        if os.path.exists(local_fkx_path):
            try:
                with open(local_fkx_path, 'r', encoding='utf-8') as f:
                    local_fkx_content = f.read()
                local_info = parse_fkx(local_fkx_content)
                remote_info = parse_fkx(remote_fkx_content)

                local_num = len(local_info.get('chunks', []))
                remote_num = len(remote_info.get('chunks', []))
                if local_num == remote_num:
                    match = True
                    for i in range(local_num):
                        lc = local_info['chunks'][i]
                        rc = remote_info['chunks'][i]
                        if lc['filename'] != rc['filename'] or lc['size'] != rc['size']:
                            match = False
                            break
                    if match:
                        if any('sha256' not in lc for lc in local_info['chunks']) and \
                           any('sha256' in rc for rc in remote_info['chunks']):
                            return remote_info
                        return local_info
            except Exception:
                pass

        with open(local_fkx_path, 'w', encoding='utf-8') as f:
            f.write(remote_fkx_content)
        return parse_fkx(remote_fkx_content)

    def _download(self, fkx_url, output_dir, enhanced, verify_sha256=True):
        chunk_dir = ""
        output_path = None
        try:
            output_dir = os.path.abspath(output_dir)
            fkx_info, error, fkx_content = self._fetch_and_parse_fkx(fkx_url, enhanced, emit_status=False)

            if self._is_cancelled:
                self._emit_status("已取消下载", '#cc0000')
                self._emit_complete({'cancelled': True})
                self._close_session()
                return

            if error:
                self._close_session()
                if not self._ask_retry("下载失败", f"{error}\n是否重试？"):
                    self._emit_error(error)
                    return
                fkx_info, error, fkx_content = self._fetch_and_parse_fkx(fkx_url, enhanced, emit_status=False)
                if error:
                    self._close_session()
                    self._emit_error(error)
                    return

            if fkx_info is None:
                self._emit_error("无法解析文件信息")
                self._close_session()
                return

            num_chunks = len(fkx_info['chunks'])
            total_size = sum(chunk['size'] for chunk in fkx_info['chunks'])
            self._total_size = total_size

            filename = fkx_info['filename']
            assert isinstance(filename, str)
            safe_filename = sanitize_filename(os.path.basename(filename))

            self._emit_progress(0, num_chunks)
            self._emit_chunk_progress(0, 100)

            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            is_local = not is_remote_url(fkx_url)

            if is_local:
                fkx_path = resolve_local_path(fkx_url)
                base_path = os.path.dirname(fkx_path)
                chunk_dir = ""
                downloaded_chunks = {}
                downloaded_size = 0

                self._emit_status(f"正在读取分片 (共{num_chunks}个)")

                for i, chunk_info in enumerate(fkx_info['chunks']):
                    if self._is_cancelled:
                        self._emit_status("已取消合并", '#cc0000')
                        self._emit_complete({'cancelled': True})
                        return

                    self._emit_status(f"正在读取分片 {i+1}/{num_chunks}")

                    chunk_path = os.path.join(base_path, chunk_info['filename'])
                    chunk_path = os.path.normpath(chunk_path)

                    if not os.path.exists(chunk_path):
                        if not self._ask_retry("合并失败", f"分片文件不存在: {chunk_info['filename']}\n是否重试？"):
                            self._emit_error(f"分片文件不存在: {chunk_info['filename']}")
                            return
                        continue

                    downloaded_chunks[i] = chunk_path
                    downloaded_size += chunk_info['size']
                    self._emit_progress(i + 1, num_chunks)
                    self._emit_chunk_progress(100, 100)
            else:
                parsed = urlparse(fkx_url)
                dir_path = parsed.path.rsplit('/', 1)[0] if '/' in parsed.path else ''
                base_url = f"{parsed.scheme}://{parsed.netloc}{dir_path}/"

                chunk_dir = self._get_chunk_dir(output_dir, safe_filename)
                fkx_filename = os.path.basename(fkx_url)

                fkx_info = self._sync_local_fkx(chunk_dir, fkx_content, fkx_filename)
                num_chunks = len(fkx_info['chunks'])
                total_size = sum(chunk['size'] for chunk in fkx_info['chunks'])
                self._total_size = total_size
                self._emit_progress(0, num_chunks)

                download_start_time = time.time()
                downloaded_chunks = {}
                downloaded_size = 0

                self._emit_status(f"正在顺序下载分片 (共{num_chunks}个)")

                i = 0
                while i < num_chunks:
                    if self._is_cancelled:
                        self._close_session()
                        self._emit_status("已取消下载（分片已保留）", '#cc0000')
                        self._emit_complete({'cancelled': True})
                        return

                    chunk_info = fkx_info['chunks'][i]

                    existing = self._check_existing_chunk(chunk_dir, chunk_info)
                    if existing:
                        self._emit_status(f"分片 {i+1}/{num_chunks} 已存在，跳过")
                        downloaded_chunks[i] = existing
                        downloaded_size += chunk_info['size']
                        self._emit_progress(i + 1, num_chunks)
                        self._emit_chunk_progress(100, 100)
                        i += 1
                        continue

                    self._emit_status(f"正在下载分片 {i+1}/{num_chunks}: {chunk_info['filename']}")
                    self._emit_chunk_progress(0, 100)

                    chunk_filename = self._validate_chunk_filename(chunk_info['filename'])
                    chunk_url = urljoin(base_url, chunk_filename)
                    chunk_size = chunk_info['size']
                    chunk_path = os.path.join(chunk_dir, chunk_filename)
                    chunk_path = os.path.normpath(chunk_path)

                    if chunk_size == 0:
                        with open(chunk_path, 'wb') as f:
                            pass
                        downloaded_chunks[i] = chunk_path
                    else:
                        before_download = downloaded_size
                        self._progress_callback = lambda d, cs, cb, db=before_download: self._on_chunk_progress(d, cs, db, download_start_time)

                        while True:
                            success = self._download_chunk(chunk_url, chunk_path, chunk_size, base_url)

                            if success and os.path.exists(chunk_path) and os.path.getsize(chunk_path) == chunk_size:
                                break

                            if self._is_cancelled:
                                self._close_session()
                                self._emit_status("已取消下载（分片已保留）", '#cc0000')
                                self._emit_complete({'cancelled': True})
                                return

                            if not self._ask_retry("下载失败", f"分片 {i+1}/{num_chunks} 下载失败\n原因: {self._last_chunk_error}\n是否重试？"):
                                self._close_session()
                                self._emit_status(f"下载已中断（分片已保留） - {self._last_chunk_error}", '#cc6600')
                                self._emit_complete({'cancelled': True})
                                return

                        downloaded_chunks[i] = chunk_path
                        downloaded_size += chunk_size

                    self._emit_progress(i + 1, num_chunks)
                    self._emit_chunk_progress(100, 100)
                    i += 1

            if self._is_cancelled:
                if is_local:
                    self._emit_status("已取消合并", '#cc0000')
                else:
                    self._emit_status("已取消下载（分片已保留）", '#cc0000')
                self._emit_complete({'cancelled': True})
                return

            if len(downloaded_chunks) != num_chunks:
                if not is_local:
                    self._close_session()
                    error_msg = f"下载不完整: 期望{num_chunks}个分片，实际下载{len(downloaded_chunks)}个"
                    if not self._ask_retry("下载失败", f"{error_msg}\n是否重试？"):
                        self._emit_status(f"下载已中断（分片已保留） - {error_msg}", '#cc6600')
                        self._emit_complete({'cancelled': True})
                        return
                    self._download(fkx_url, output_dir, enhanced, verify_sha256)
                    return
                self._emit_error(f"下载不完整: 期望{num_chunks}个分片，实际下载{len(downloaded_chunks)}个")
                self._close_session()
                return

            self._emit_status("正在合并文件...")
            output_path = os.path.join(output_dir, safe_filename)
            output_path = os.path.normpath(output_path)

            merged_bytes = [0]
            cancelled = False
            with open(output_path, 'wb') as f:
                for i in range(num_chunks):
                    if self._is_cancelled:
                        cancelled = True
                        break

                    chunk_path = downloaded_chunks[i]
                    with open(chunk_path, 'rb') as chunk_file:
                        for chunk in iter(lambda: chunk_file.read(65536), b""):
                            f.write(chunk)
                            merged_bytes[0] += len(chunk)
                            if total_size > 0:
                                percentage = merged_bytes[0] / total_size
                                self._emit_chunk_progress(percentage * 100, 100)
                                self._emit_status(
                                    f"正在合并文件... {format_size(merged_bytes[0])} / {format_size(total_size)}"
                                )

            if cancelled:
                try:
                    os.remove(output_path)
                except FileNotFoundError:
                    pass
                self._close_session()
                if is_local:
                    self._emit_status("已取消合并", '#cc0000')
                else:
                    self._emit_status("已取消下载（分片已保留）", '#cc0000')
                self._emit_complete({'cancelled': True})
                return

            if 'sha256' in fkx_info and verify_sha256:
                self._emit_status("正在校验SHA-256...")
                actual_sha256 = hashlib.sha256()
                sha256_cancelled = False
                sha256_bytes = [0]
                with open(output_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        if self._is_cancelled:
                            sha256_cancelled = True
                            break
                        actual_sha256.update(chunk)
                        sha256_bytes[0] += len(chunk)
                        if total_size > 0:
                            percentage = sha256_bytes[0] / total_size
                            self._emit_chunk_progress(percentage * 100, 100)
                            self._emit_status(
                                f"正在校验SHA-256... {format_size(sha256_bytes[0])} / {format_size(total_size)}"
                            )

                if sha256_cancelled:
                    self._close_session()
                    if not is_local:
                        self._cleanup_chunk_dir(chunk_dir)
                    self._emit_progress(num_chunks, num_chunks)
                    self._emit_chunk_progress(100, 100)
                    if is_local:
                        self._emit_status("合并成功（已跳过SHA-256检验）", '#006600')
                    else:
                        self._emit_status("下载成功（已跳过SHA-256检验）", '#006600')
                    self._emit_complete({
                        'mode': '本地' if is_local else '远程',
                        'file_name': safe_filename,
                        'output_path': output_path,
                    })
                    return

                if actual_sha256.hexdigest() != fkx_info['sha256']:
                    try:
                        os.remove(output_path)
                    except FileNotFoundError:
                        pass
                    self._close_session()
                    if not is_local:
                        self._emit_status("SHA-256校验失败（分片已保留）", '#cc0000')
                        self._emit_complete({'cancelled': True, 'sha256_failed': True})
                    else:
                        self._emit_error("文件SHA-256校验失败")
                    return

            if not is_local:
                self._cleanup_chunk_dir(chunk_dir)

            self._close_session()

            self._emit_progress(num_chunks, num_chunks)
            self._emit_chunk_progress(100, 100)
            mode_text = "本地" if is_local else "远程"
            if is_local:
                self._emit_status("合并成功", '#006600')
            else:
                self._emit_status("下载成功", '#006600')
            self._emit_complete({
                'mode': mode_text,
                'file_name': safe_filename,
                'output_path': output_path,
            })

        except Exception as e:
            self._close_session()
            error_msg = f"下载过程发生错误: {str(e)}"
            if not self._ask_retry("下载失败", f"{error_msg}\n是否重试？"):
                self._emit_error(error_msg)
            else:
                self._download(fkx_url, output_dir, enhanced, verify_sha256)

    def _on_chunk_progress(self, downloaded, chunk_size, downloaded_before, start_time):
        total_downloaded = downloaded_before + downloaded
        elapsed = time.time() - start_time
        speed = total_downloaded / elapsed if elapsed > 0 else 0

        if chunk_size > 0:
            percentage = downloaded / chunk_size
            self._emit_chunk_progress(percentage * 100, 100)

        self._emit_download_status(total_downloaded, self._total_size, speed)

    def _on_chunk_sha256_progress(self, processed, total, filename):
        if total > 0:
            self._emit_chunk_progress(processed / total * 100, 100)
        self._emit_status(
            f"正在校验分片: {filename}  {format_size(processed)} / {format_size(total)}"
        )


class FileMerger(BaseWorker):
    def merge_async(self, fkx_path, output_dir, verify_sha256=True):
        self._is_cancelled = False
        self._thread = threading.Thread(
            target=self._merge,
            args=(fkx_path, output_dir, verify_sha256),
            daemon=True
        )
        self._thread.start()

    def _merge(self, fkx_path, output_dir, verify_sha256=True):
        try:
            fkx_path = os.path.abspath(fkx_path)
            output_dir = os.path.abspath(output_dir)

            if not fkx_path:
                self._emit_error("请输入.fkx文件路径")
                return

            if not os.path.exists(fkx_path):
                self._emit_error(f"本地文件不存在: {fkx_path}")
                return

            if not fkx_path.endswith('.fkx'):
                self._emit_error("输入必须是.fkx文件")
                return

            if not output_dir:
                self._emit_error("请选择输出目录")
                return

            self._emit_status("正在解析文件信息...")

            try:
                with open(fkx_path, 'r', encoding='utf-8') as f:
                    fkx_content = f.read()
            except Exception as e:
                self._emit_error(f"无法读取文件信息: {str(e)}")
                return

            fkx_info = parse_fkx(fkx_content)

            if 'filename' not in fkx_info or 'chunks' not in fkx_info:
                self._emit_error("文件信息格式不正确")
                return

            num_chunks = len(fkx_info['chunks'])
            total_size = sum(chunk['size'] for chunk in fkx_info['chunks'])

            self._emit_file_info({
                'filename': fkx_info.get('filename', '-'),
                'total_size': total_size,
                'num_chunks': num_chunks,
            })

            base_path = os.path.dirname(fkx_path)

            self._emit_progress(0, num_chunks)
            self._emit_chunk_progress(0, 100)

            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            downloaded_chunks = {}

            for i, chunk_info in enumerate(fkx_info['chunks']):
                if self._is_cancelled:
                    self._emit_status("已取消合并", '#cc0000')
                    self._emit_complete({'cancelled': True})
                    return

                self._emit_status(f"正在读取分片 {i+1}/{num_chunks}")

                chunk_path = os.path.join(base_path, chunk_info['filename'])
                chunk_path = os.path.normpath(chunk_path)

                if not os.path.exists(chunk_path):
                    self._emit_error(f"分片文件不存在: {chunk_info['filename']}")
                    return

                downloaded_chunks[i] = chunk_path
                self._emit_progress(i + 1, num_chunks)
                self._emit_chunk_progress(100, 100)

            self._emit_status("正在合并文件...")
            filename = fkx_info['filename']
            assert isinstance(filename, str)
            safe_filename = sanitize_filename(os.path.basename(filename))
            output_path = os.path.join(output_dir, safe_filename)
            output_path = os.path.normpath(output_path)

            merged_bytes = [0]
            cancelled = False
            with open(output_path, 'wb') as f:
                for i in range(num_chunks):
                    if self._is_cancelled:
                        cancelled = True
                        break

                    chunk_path = downloaded_chunks[i]
                    with open(chunk_path, 'rb') as chunk_file:
                        for chunk in iter(lambda: chunk_file.read(65536), b""):
                            f.write(chunk)
                            merged_bytes[0] += len(chunk)
                            if total_size > 0:
                                percentage = merged_bytes[0] / total_size
                                self._emit_chunk_progress(percentage * 100, 100)
                                self._emit_status(
                                    f"正在合并文件... {format_size(merged_bytes[0])} / {format_size(total_size)}"
                                )

            if cancelled:
                try:
                    os.remove(output_path)
                except FileNotFoundError:
                    pass
                self._emit_status("已取消合并", '#cc0000')
                self._emit_complete({'cancelled': True})
                return

            if 'sha256' in fkx_info and verify_sha256:
                self._emit_status("正在校验SHA-256...")
                actual_sha256 = hashlib.sha256()
                sha256_cancelled = False
                sha256_bytes = [0]
                with open(output_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        if self._is_cancelled:
                            sha256_cancelled = True
                            break
                        actual_sha256.update(chunk)
                        sha256_bytes[0] += len(chunk)
                        if total_size > 0:
                            percentage = sha256_bytes[0] / total_size
                            self._emit_chunk_progress(percentage * 100, 100)
                            self._emit_status(
                                f"正在校验SHA-256... {format_size(sha256_bytes[0])} / {format_size(total_size)}"
                            )

                if sha256_cancelled:
                    self._emit_progress(num_chunks, num_chunks)
                    self._emit_chunk_progress(100, 100)
                    self._emit_status("合并成功（已跳过SHA-256检验）", '#006600')
                    self._emit_complete({
                        'mode': '本地',
                        'file_name': safe_filename,
                        'output_path': output_path,
                    })
                    return

                if actual_sha256.hexdigest() != fkx_info['sha256']:
                    self._emit_error("文件SHA-256校验失败")
                    try:
                        os.remove(output_path)
                    except FileNotFoundError:
                        pass
                    return

            self._emit_progress(num_chunks, num_chunks)
            self._emit_chunk_progress(100, 100)
            self._emit_status("合并成功", '#006600')
            self._emit_complete({
                'mode': '本地',
                'file_name': safe_filename,
                'output_path': output_path,
            })

        except Exception as e:
            self._emit_error(f"合并过程发生错误: {str(e)}")