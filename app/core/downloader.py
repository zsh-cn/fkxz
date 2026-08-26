import os
import hashlib
import shutil
import tempfile
import threading
import time
from urllib.parse import urlparse, urljoin

import requests as req_lib
from requests.adapters import HTTPAdapter

from core.base_worker import BaseWorker
from utils.helpers import parse_fkx, sanitize_filename, format_size

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

    def cancel(self):
        self._is_cancelled = True
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass

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
            session = curl_requests.Session(impersonate="chrome131")
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
            headers["Upgrade-Insecure-Requests"] = "1"
            headers["Priority"] = "u=1, i"
        if referer:
            headers["Referer"] = referer
        return headers

    def _download_text(self, url):
        assert self._session is not None
        while True:
            try:
                if self._is_cancelled:
                    return None
                headers = self._get_request_headers()
                resp = self._session.get(url, timeout=120, headers=headers)
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                if self._is_cancelled:
                    return None
                if not self._ask_retry("下载失败", f"无法下载文件信息: {str(e)[:100]}\n是否重试？"):
                    return None

    def _download_chunk(self, url, chunk_path, chunk_size, referer):
        assert self._session is not None
        while True:
            try:
                headers = self._get_request_headers(referer=referer, is_chunk=True)
                downloaded_bytes = 0

                resp = self._session.get(url, stream=True, timeout=120, headers=headers)
                resp.raise_for_status()

                with open(chunk_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if self._is_cancelled:
                            try:
                                os.remove(chunk_path)
                            except FileNotFoundError:
                                pass
                            return False
                        f.write(chunk)
                        downloaded_bytes += len(chunk)
                        if self._progress_callback:
                            self._progress_callback(downloaded_bytes, chunk_size, len(chunk))

                if self._is_cancelled:
                    try:
                        os.remove(chunk_path)
                    except FileNotFoundError:
                        pass
                    return False

                return True
            except Exception as e:
                try:
                    os.remove(chunk_path)
                except FileNotFoundError:
                    pass
                if self._is_cancelled:
                    return False
                if not self._ask_retry("下载失败", f"分片下载失败: {str(e)[:100]}\n是否重试？"):
                    return False

    def _get_chunk_dir(self, output_dir, safe_name):
        prefix = f"{safe_name}-fkxz-" if safe_name else "fkwj-"
        chunk_dir = tempfile.mkdtemp(prefix=prefix, dir=output_dir)
        return chunk_dir

    def _cleanup_chunk_dir(self, chunk_dir):
        if os.path.exists(chunk_dir):
            shutil.rmtree(chunk_dir)

    def _fetch_and_parse_fkx(self, fkx_url, enhanced, emit_status=True):
        if not fkx_url:
            return None, "请输入文件信息URL"

        if not fkx_url.startswith('http://') and not fkx_url.startswith('https://'):
            return None, "请输入有效的URL"

        self._enhanced = enhanced and HAS_CURL_CFFI
        self._session = self._create_session(enhanced)

        if emit_status:
            self._emit_status("正在获取文件信息...")
        fkx_content = self._download_text(fkx_url)

        if self._is_cancelled:
            return None, None

        if not fkx_content:
            return None, "无法下载文件信息"

        fkx_info = parse_fkx(fkx_content)

        if 'filename' not in fkx_info or 'chunks' not in fkx_info:
            return None, "文件信息格式不正确"

        num_chunks = len(fkx_info['chunks'])
        total_size = sum(chunk['size'] for chunk in fkx_info['chunks'])

        self._emit_file_info({
            'filename': fkx_info.get('filename', '-'),
            'total_size': total_size,
            'num_chunks': num_chunks,
        })

        if emit_status:
            self._emit_status("文件信息已获取", '#006600')

        return fkx_info, None

    def fetch_fkx_info_async(self, fkx_url, enhanced=True):
        self._is_cancelled = False
        self._thread = threading.Thread(
            target=self._fetch_fkx_info,
            args=(fkx_url, enhanced),
            daemon=True
        )
        self._thread.start()

    def download_async(self, fkx_url, output_dir, enhanced=True):
        self._is_cancelled = False
        self._thread = threading.Thread(
            target=self._download,
            args=(fkx_url, output_dir, enhanced),
            daemon=True
        )
        self._thread.start()

    def _fetch_fkx_info(self, fkx_url, enhanced):
        try:
            fkx_info, error = self._fetch_and_parse_fkx(fkx_url, enhanced, emit_status=True)
            if self._is_cancelled:
                self._emit_status("已取消获取", '#cc0000')
                return
            if error:
                self._emit_status(error, '#cc0000')
                return
        except Exception as e:
            self._emit_status(f"获取文件信息失败: {str(e)[:100]}", '#cc0000')

    def _download(self, fkx_url, output_dir, enhanced):
        try:
            fkx_info, error = self._fetch_and_parse_fkx(fkx_url, enhanced, emit_status=False)

            if self._is_cancelled:
                self._emit_status("已取消下载", '#cc0000')
                self._emit_complete({'cancelled': True})
                return

            if error:
                self._emit_error(error)
                return

            if fkx_info is None:
                self._emit_error("无法解析文件信息")
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

            parsed = urlparse(fkx_url)
            dir_path = parsed.path.rsplit('/', 1)[0] if '/' in parsed.path else ''
            base_url = f"{parsed.scheme}://{parsed.netloc}{dir_path}/"

            chunk_dir = self._get_chunk_dir(output_dir, safe_filename)
            fkx_save_path = os.path.join(chunk_dir, os.path.basename(fkx_url))
            with open(fkx_save_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join([
                    f"filename={fkx_info.get('filename', '')}",
                    f"total_size={total_size}",
                    f"num_chunks={num_chunks}",
                ] + [
                    f"chunk_{i+1}={chunk['filename']},{chunk['size']}"
                    for i, chunk in enumerate(fkx_info['chunks'])
                ]))

            downloaded_chunks = {}
            downloaded_size = 0
            download_start_time = time.time()

            self._emit_status(f"正在顺序下载分片 (共{num_chunks}个)")

            for i, chunk_info in enumerate(fkx_info['chunks']):
                if self._is_cancelled:
                    self._cleanup_chunk_dir(chunk_dir)
                    self._emit_status("已取消下载", '#cc0000')
                    self._emit_complete({'cancelled': True})
                    return

                self._emit_status(f"正在下载分片 {i+1}/{num_chunks}: {chunk_info['filename']}")

                chunk_url = urljoin(base_url, chunk_info['filename'])
                chunk_size = chunk_info['size']
                chunk_path = os.path.join(chunk_dir, chunk_info['filename'])
                chunk_path = os.path.normpath(chunk_path)

                if chunk_size == 0:
                    with open(chunk_path, 'wb') as f:
                        pass
                    downloaded_chunks[i] = chunk_path
                else:
                    before_download = downloaded_size
                    self._progress_callback = lambda d, cs, cb, db=before_download: self._on_chunk_progress(d, cs, db, download_start_time)

                    success = self._download_chunk(chunk_url, chunk_path, chunk_size, base_url)

                    if not success:
                        if self._is_cancelled:
                            self._cleanup_chunk_dir(chunk_dir)
                            self._emit_status("已取消下载", '#cc0000')
                            self._emit_complete({'cancelled': True})
                            return
                        self._cleanup_chunk_dir(chunk_dir)
                        self._emit_error(f"分片 {i+1} 下载失败")
                        return

                    if os.path.exists(chunk_path) and os.path.getsize(chunk_path) == chunk_size:
                        downloaded_chunks[i] = chunk_path
                        downloaded_size += chunk_size
                    else:
                        self._emit_error(f"分片 {i+1} 下载不完整")
                        self._cleanup_chunk_dir(chunk_dir)
                        return

                self._emit_progress(i + 1, num_chunks)
                self._emit_chunk_progress(100, 100)

            if self._is_cancelled:
                self._cleanup_chunk_dir(chunk_dir)
                self._emit_status("已取消下载", '#cc0000')
                self._emit_complete({'cancelled': True})
                return

            if len(downloaded_chunks) != num_chunks:
                self._emit_error(f"下载不完整: 期望{num_chunks}个分片，实际下载{len(downloaded_chunks)}个")
                self._cleanup_chunk_dir(chunk_dir)
                return

            self._emit_status("正在合并文件...")
            output_path = os.path.join(output_dir, safe_filename)
            output_path = os.path.normpath(output_path)

            merged_bytes = [0]
            with open(output_path, 'wb') as f:
                for i in range(num_chunks):
                    if self._is_cancelled:
                        try:
                            os.remove(output_path)
                        except FileNotFoundError:
                            pass
                        self._cleanup_chunk_dir(chunk_dir)
                        self._emit_status("已取消下载", '#cc0000')
                        self._emit_complete({'cancelled': True})
                        return

                    chunk_path = downloaded_chunks[i]
                    with open(chunk_path, 'rb') as chunk_file:
                        for chunk in iter(lambda: chunk_file.read(65536), b""):
                            f.write(chunk)
                            merged_bytes[0] += len(chunk)
                            if total_size > 0:
                                percentage = merged_bytes[0] / total_size
                                self._emit_chunk_progress(percentage * 100, 100)

            if 'sha256' in fkx_info:
                self._emit_status("正在校验SHA-256...")
                actual_sha256 = hashlib.sha256()
                with open(output_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        if self._is_cancelled:
                            try:
                                os.remove(output_path)
                            except FileNotFoundError:
                                pass
                            self._cleanup_chunk_dir(chunk_dir)
                            self._emit_status("已取消下载", '#cc0000')
                            self._emit_complete({'cancelled': True})
                            return
                        actual_sha256.update(chunk)

                if actual_sha256.hexdigest() != fkx_info['sha256']:
                    self._emit_error("文件SHA-256校验失败")
                    try:
                        os.remove(output_path)
                    except FileNotFoundError:
                        pass
                    self._cleanup_chunk_dir(chunk_dir)
                    return

            self._cleanup_chunk_dir(chunk_dir)

            self._emit_progress(num_chunks, num_chunks)
            self._emit_chunk_progress(100, 100)
            self._emit_status("下载成功", '#006600')
            self._emit_complete({
                'mode': '远程',
                'file_name': safe_filename,
                'output_path': output_path,
            })

        except Exception as e:
            self._emit_error(f"下载过程发生错误: {str(e)}")

    def _on_chunk_progress(self, downloaded, chunk_size, downloaded_before, start_time):
        total_downloaded = downloaded_before + downloaded
        elapsed = time.time() - start_time
        speed = total_downloaded / elapsed if elapsed > 0 else 0

        if chunk_size > 0:
            percentage = downloaded / chunk_size
            self._emit_chunk_progress(percentage * 100, 100)

        self._emit_download_status(total_downloaded, self._total_size, speed)