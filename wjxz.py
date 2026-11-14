import hashlib
import os
import queue
import re
import shutil
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from urllib.parse import quote, unquote, urljoin, urlparse

import requests

import config
import core
import utils

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    curl_requests = None
    HAS_CURL_CFFI = False

_DRIVE_PATH_RE = re.compile(r'^/[A-Za-z]:')


def _new_pooled_session():
    session = requests.Session()
    size = config.HTTP_POOL_SIZE
    adapter = requests.adapters.HTTPAdapter(pool_connections=size, pool_maxsize=size)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def _new_enhanced_session():
    if HAS_CURL_CFFI:
        for target in config.IMPERSONATE_TARGETS:
            try:
                return curl_requests.Session(impersonate=target), True
            except Exception:
                continue
        try:
            return curl_requests.Session(), True
        except Exception:
            pass
    return _new_pooled_session(), False


VERIFY_STATUS_THRESHOLD = 8 * 1024 * 1024


def _validate_chunk_name(filename):
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        raise ValueError(f"非法的分片文件名: {filename}")
    return os.path.basename(filename)


def chunk_path_in(directory, filename):
    return utils.ensure_within_dir(directory, _validate_chunk_name(filename))


def same_chunk_layout(left_info, right_info):
    left = left_info.get('chunks') or []
    right = right_info.get('chunks') or []
    if not left or len(left) != len(right):
        return False
    return all(lc['filename'] == rc['filename'] and lc['size'] == rc['size']
               for lc, rc in zip(left, right))


def find_existing_chunk(chunk_dir, chunk_info, verified_cache=None,
                        should_stop=None, on_verify_start=None, on_verify_end=None):
    try:
        chunk_path = chunk_path_in(chunk_dir, chunk_info['filename'])
    except ValueError:
        return None
    if not os.path.exists(chunk_path):
        return None
    if os.path.getsize(chunk_path) != chunk_info['size']:
        return None

    expected_sha256 = chunk_info.get('sha256')
    if not expected_sha256:
        return chunk_path

    verify_key = (chunk_info['filename'], chunk_info['size'], expected_sha256)
    if verified_cache is not None and verify_key in verified_cache:
        return chunk_path

    notify_verify = chunk_info['size'] > VERIFY_STATUS_THRESHOLD
    if notify_verify and on_verify_start:
        on_verify_start(chunk_info['filename'])
    try:
        actual_sha256 = utils.sha256_file(chunk_path, should_stop=should_stop)
    finally:
        if notify_verify and on_verify_end:
            on_verify_end(chunk_info['filename'])
    if actual_sha256 is None:
        return None
    if actual_sha256 == expected_sha256:
        if verified_cache is not None:
            verified_cache.add(verify_key)
        return chunk_path

    utils.safe_remove(chunk_path)
    return None


class FileDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("文件下载")
        utils.scaled_geometry(self.root, *config.DOWNLOADER_WINDOW_SIZE)
        self.root.resizable(True, True)

        self._icon = utils.apply_window_icon(self.root, 'wjxz.png')

        self.style = ttk.Style()
        available_themes = self.style.theme_names()
        if 'vista' in available_themes:
            self.style.theme_use('vista')
        elif 'xpnative' in available_themes:
            self.style.theme_use('xpnative')
        elif 'clam' in available_themes:
            self.style.theme_use('clam')

        self.fkx_path = ""
        self.output_dir = ""
        self.download_thread = None
        self.is_cancelled = False
        self.is_local = False
        self._closed = False

        self.session = _new_pooled_session()
        self.session_enhanced, self._curl_session = _new_enhanced_session()
        self.session_enhanced.headers.update(config.BROWSER_HEADERS)

        self.downloaded_chunks = {}
        self.file_info = {}
        self.total_download_size = 0
        self.downloaded_size = 0
        self.download_start_time = 0
        self.chunk_dir = ""
        self.safe_filename = ""
        self.base_referer = ""
        self.enhanced_mode = tk.BooleanVar(value=self._curl_session)
        self.verify_sha256_var = tk.BooleanVar(value=True)
        self.workers_var = tk.IntVar(value=config.DEFAULT_WORKERS)
        self._use_enhanced = self._curl_session
        self._last_chunk_error = ""
        self._verified_chunks = set()

        self._progress_lock = threading.Lock()
        self._chunk_bytes = {}
        self._chunk_bytes_total = 0
        self._speed_base_bytes = 0
        self._speed_start_time = None
        self._run_token = 0
        self._run_part_token = None
        self._run_part_names_cache = []
        self._abort_download = False
        self._file_info_source = None

        self._status_lock = threading.Lock()
        self._status_base = None
        self._verifying_names = set()

        self.create_widgets()
        utils.install_about_menu(self.root, "文件下载")

        self.ui = utils.UiDispatcher(self.root)


    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        url_frame = ttk.LabelFrame(main_frame, text="文件信息来源", padding="10")
        url_frame.pack(fill=tk.X, pady=5)
        url_frame.columnconfigure(0, weight=1)
        url_frame.columnconfigure(1, weight=1)
        url_frame.columnconfigure(2, minsize=130)

        ttk.Label(url_frame, text="文件信息URL或本地路径 (.fkx):").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 5), sticky=tk.EW, ipady=2)
        self.url_entry.bind('<KeyRelease>', self.validate_input)
        utils.setup_context_menu(self.url_entry, on_change=self.validate_input)
        self.browse_fkx_btn = ttk.Button(url_frame, text="浏览", command=self.browse_fkx_file)
        self.browse_fkx_btn.grid(row=1, column=2, pady=(0, 5))

        ttk.Label(url_frame, text="输出目录:").grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        self.output_entry = ttk.Entry(url_frame)
        self.output_entry.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 5), sticky=tk.EW, ipady=2)
        self.browse_output_btn = ttk.Button(url_frame, text="浏览", command=self.browse_output_dir)
        self.browse_output_btn.grid(row=3, column=2, pady=(0, 5))
        utils.setup_context_menu(self.output_entry)

        self.enhanced_checkbox = ttk.Checkbutton(url_frame, text="启用增强模式 (curl_cffi浏览器模拟)", variable=self.enhanced_mode)
        self.enhanced_checkbox.grid(row=4, column=0, sticky=tk.W, pady=5)

        self.verify_sha256_checkbox = ttk.Checkbutton(url_frame, text="启用SHA-256检验", variable=self.verify_sha256_var)
        self.verify_sha256_checkbox.grid(row=4, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        if not self._curl_session:
            self.enhanced_mode.set(False)
            self.enhanced_checkbox.config(state=tk.DISABLED, text="增强模式不可用 (未安装 curl_cffi)")

        ttk.Label(url_frame, text="并发分片数:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.workers_spinbox = ttk.Spinbox(url_frame, from_=config.MIN_WORKERS,
                                           to=config.MAX_WORKERS, width=6,
                                           textvariable=self.workers_var)
        self.workers_spinbox.grid(row=5, column=1, sticky=tk.W, padx=(10, 0), pady=5)
        ttk.Label(url_frame, text=f"({config.MIN_WORKERS}-{config.MAX_WORKERS}，仅远程模式可调)").grid(
            row=5, column=2, sticky=tk.W, pady=5)

        control_frame = ttk.LabelFrame(main_frame, text="文件信息", padding="10")
        control_frame.pack(fill=tk.X, pady=5)
        control_frame.columnconfigure(1, weight=1)

        ttk.Label(control_frame, text="文件名:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.filename_label = ttk.Label(control_frame, text="-", foreground=config.TEXT_SECONDARY)
        self.filename_label.grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)

        ttk.Label(control_frame, text="文件大小:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.filesize_label = ttk.Label(control_frame, text="-", foreground=config.TEXT_SECONDARY)
        self.filesize_label.grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)

        ttk.Label(control_frame, text="分片数:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.chunks_label = ttk.Label(control_frame, text="-", foreground=config.TEXT_SECONDARY)
        self.chunks_label.grid(row=2, column=1, sticky=tk.W, padx=10, pady=5)

        control_frame2 = ttk.LabelFrame(main_frame, text="处理状态", padding="10")
        control_frame2.pack(fill=tk.X, pady=5)
        control_frame2.columnconfigure(0, weight=1)

        self.progress_bar = ttk.Progressbar(control_frame2, orient=tk.HORIZONTAL,
                                            mode='determinate', maximum=100)
        self.progress_bar.grid(row=0, column=0, pady=5, sticky=tk.EW)

        self.status_label = ttk.Label(control_frame2, text="状态: 就绪", foreground=config.TEXT_NORMAL)
        self.status_label.grid(row=1, column=0, sticky=tk.W, pady=5)

        self.download_detail_label = ttk.Label(control_frame2, text="", foreground=config.TEXT_SECONDARY)
        self.download_detail_label.grid(row=2, column=0, sticky=tk.W, pady=5)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)

        self.start_button = ttk.Button(button_frame, text="开始合并", command=self.start_download, width=20, state=tk.NORMAL)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.cancel_button = ttk.Button(button_frame, text="取消", command=self.cancel_download, width=15, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=5)


    def _run_on_ui(self, func, *args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            func(*args, **kwargs)
        else:
            self.ui.call(func, *args, **kwargs)

    def _run_on_ui_latest(self, key, func, *args, **kwargs):
        self.ui.call_latest(key, func, *args, **kwargs)


    @staticmethod
    def _is_remote_url(path):
        lowered = (path or '').lower()
        return lowered.startswith('http://') or lowered.startswith('https://')

    @staticmethod
    def _has_drive_letter(path):
        return len(path) >= 2 and path[1] == ':'

    @staticmethod
    def _strip_query(path):
        return path.split('?', 1)[0].split('#', 1)[0]

    @classmethod
    def _url_path_of(cls, path):
        if not path:
            return ''
        if cls._is_remote_url(path):
            try:
                return urlparse(path).path or ''
            except ValueError:
                return cls._strip_query(path)
        return path

    @classmethod
    def _looks_like_fkx(cls, path):
        return cls._url_path_of(path).lower().endswith('.fkx')

    @classmethod
    def _is_domain_like(cls, path):
        if not path:
            return False
        if cls._is_remote_url(path):
            return False
        if len(path) >= 2 and path[1] == ':':
            return False
        if path.startswith('.') or path.startswith('/') or path.startswith('\\'):
            return False
        bare = cls._strip_query(path)
        slash_pos = bare.find('/')
        if slash_pos == -1:
            slash_pos = len(bare)
        dot_pos = bare.find('.')
        return dot_pos != -1 and dot_pos < slash_pos

    def _resolve_local_path(self, path):
        if path.lower().startswith('file://'):
            parsed = urlparse(path)
            local = unquote(parsed.path or '')
            netloc = parsed.netloc
            if netloc and netloc.lower() != 'localhost':
                local = f"//{netloc}{local}"
            elif _DRIVE_PATH_RE.match(local):
                local = local[1:]
            path = local.replace('/', os.sep) if os.sep != '/' else local
        if not self._is_remote_url(path) and not self._has_drive_letter(path):
            return os.path.abspath(path)
        return path

    def _update_path_type_ui(self, path, is_local=False):
        if not path:
            if self._curl_session:
                self.enhanced_checkbox.config(state=tk.NORMAL)
            self.workers_spinbox.config(state=tk.NORMAL)
            return
        if not is_local and (self._is_remote_url(path) or self._is_domain_like(path)):
            if self._curl_session:
                self.enhanced_checkbox.config(state=tk.NORMAL)
            self.workers_spinbox.config(state=tk.NORMAL)
            self.start_button.config(text="开始下载")
        else:
            self.enhanced_checkbox.config(state=tk.DISABLED)
            self.workers_spinbox.config(state=tk.DISABLED)
            self.start_button.config(text="开始合并")


    def validate_input(self, event=None):
        path = self.url_entry.get().strip()
        if path:
            if self._looks_like_fkx(path) and self._is_domain_like(path):
                if not getattr(self, '_auto_prepending', False):
                    local_path = os.path.join(os.getcwd(), self._url_path_of(path))
                    if os.path.exists(local_path):
                        self._update_path_type_ui(path, is_local=True)
                    else:
                        self._auto_prepending = True
                        self.url_entry.delete(0, tk.END)
                        self.url_entry.insert(0, 'https://' + path)
                        self._auto_prepending = False
                        path = 'https://' + path
                        self._update_path_type_ui(path)
            else:
                self._update_path_type_ui(path)

            if self._looks_like_fkx(path):
                self.schedule_parse()
            else:
                self.status_label.config(text="状态: 就绪", foreground=config.TEXT_NORMAL)
        else:
            self._update_path_type_ui("")
            self.status_label.config(text="状态: 就绪", foreground=config.TEXT_NORMAL)
            self.clear_file_info()

    def schedule_parse(self):
        if getattr(self, '_parse_after_id', None):
            self.root.after_cancel(self._parse_after_id)
        self._parse_after_id = self.root.after(500, self.parse_file)

    def clear_file_info(self):
        self.file_info = None
        self.total_download_size = 0
        self.filename_label.config(text="-")
        self.filesize_label.config(text="-")
        self.chunks_label.config(text="-")
        self.download_detail_label.config(text="")
        self.progress_bar['value'] = 0

    def _download_in_progress(self):
        return bool(self.download_thread and self.download_thread.is_alive())

    def _apply_parse_result(self, fkx_info, total_size, num_chunks):
        in_progress = self._download_in_progress()
        self.filename_label.config(text=str(fkx_info.get('filename', '-')))
        self.filesize_label.config(text=utils.format_size(total_size))
        self.chunks_label.config(text=str(num_chunks))
        self.is_local = not self._is_remote_url(self.fkx_path)
        self.file_info = fkx_info
        self._file_info_source = self.fkx_path
        self.total_download_size = total_size
        if in_progress:
            self.enhanced_checkbox.config(state=tk.DISABLED)
            self.workers_spinbox.config(state=tk.DISABLED)
        else:
            self._update_path_type_ui(self.fkx_path)
        if not in_progress:
            mode_text = "本地模式" if self.is_local else "远程模式"
            self.update_status(f"状态: 就绪 ({mode_text})", foreground=config.TEXT_SUCCESS)
            self.download_detail_label.config(text="")

    def _apply_parse_error(self, error_msg):
        if not self._download_in_progress():
            self.status_label.config(text="状态: 就绪", foreground=config.TEXT_NORMAL)

    def parse_file(self):
        path = self.url_entry.get().strip()
        if not path:
            return
        if self._download_in_progress():
            return
        if not self._looks_like_fkx(path):
            return

        path = self._resolve_local_path(path)
        self.fkx_path = path
        self._use_enhanced = bool(self.enhanced_mode.get() and self._curl_session)
        self.progress_bar['value'] = 0

        is_remote = self._is_remote_url(path)
        use_enhanced = self._use_enhanced

        def parse_thread():
            try:
                if is_remote:
                    content = self.download_fkx(path)
                    if not content:
                        self._run_on_ui(self._apply_parse_error, "无法下载文件信息")
                        return
                else:
                    if not os.path.exists(path) or not os.path.isfile(path):
                        self._run_on_ui(self._apply_parse_error, f"本地文件不存在: {path}")
                        return
                    content = self.read_local_fkx(path)
                    if not content:
                        self._run_on_ui(self._apply_parse_error, "无法获取文件信息")
                        return

                fkx_info = self.parse_fkx(content)
                if 'filename' not in fkx_info or 'chunks' not in fkx_info:
                    self._run_on_ui(self._apply_parse_error, "文件信息格式不正确")
                    return

                total_size = sum(chunk['size'] for chunk in fkx_info['chunks'])
                num_chunks = len(fkx_info['chunks'])
                self._run_on_ui(self._apply_parse_result, fkx_info, total_size, num_chunks)
            except Exception as exc:
                message = f"解析失败: {exc}"
                self._run_on_ui(self._apply_parse_error, message)

        self._use_enhanced = use_enhanced
        threading.Thread(target=parse_thread, daemon=True, name="parse-worker").start()


    def _idle_button_text(self):
        return "开始合并" if self.is_local else "开始下载"

    def _apply_ui_state(self, state, button_text=None):
        running = state == "running"
        editing = tk.DISABLED if running else tk.NORMAL
        for widget in (self.url_entry, self.output_entry, self.browse_fkx_btn,
                       self.browse_output_btn, self.verify_sha256_checkbox):
            widget.config(state=editing)

        enhanced_enabled = (not running) and (not self.is_local) and self._curl_session
        self.enhanced_checkbox.config(state=tk.NORMAL if enhanced_enabled else tk.DISABLED)

        workers_enabled = (not running) and (not self.is_local)
        self.workers_spinbox.config(state=tk.NORMAL if workers_enabled else tk.DISABLED)

        if running:
            self.start_button.config(state=tk.DISABLED, text=self._idle_button_text())
            self.cancel_button.config(state=tk.NORMAL, text="取消")
            return

        if button_text is None:
            button_text = "重试" if state == "retry" else self._idle_button_text()
        self.start_button.config(state=tk.NORMAL, text=button_text)
        self.cancel_button.config(state=tk.DISABLED, text="取消")

    def browse_fkx_file(self):
        file_path = utils.browse_file_dialog(self.url_entry, filetypes=[("文件信息文件", "*.fkx")])
        if file_path:
            self.fkx_path = file_path
            self.validate_input()

    def browse_output_dir(self):
        dir_path = utils.browse_directory(self.output_entry)
        if dir_path:
            self.output_dir = dir_path


    def _get_request_headers(self, referer=None, is_chunk=False):
        headers = dict(config.BROWSER_HEADERS)
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

    def download_single(self, url, timeout=config.CONNECT_TIMEOUT):
        try:
            if self._use_enhanced and self._curl_session:
                response = self.session_enhanced.get(
                    url, timeout=timeout, headers=self._get_request_headers()
                )
            elif self._use_enhanced:
                response = self.session_enhanced.get(
                    url, timeout=timeout, stream=True, headers=self._get_request_headers()
                )
            else:
                response = self.session.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            return response
        except Exception as exc:
            self.update_status(f"状态: 网络错误 - {str(exc)[:50]}", foreground=config.TEXT_ERROR)
            return None

    def read_local_fkx(self, file_path):
        try:
            return core.read_fkx_text(file_path)
        except OSError as exc:
            self.show_error(f"无法读取文件信息: {exc}")
            return None

    def parse_fkx(self, content):
        return core.parse_fkx(content)


    def _should_stop(self, stop_event=None):
        if self.is_cancelled:
            return True
        if stop_event is not None:
            return stop_event.is_set()
        return self._abort_download

    def _set_chunk_bytes(self, index, written, token=None):
        with self._progress_lock:
            if token is not None and token != self._run_token:
                return
            previous = self._chunk_bytes.get(index, 0)
            delta = written - previous
            self._chunk_bytes[index] = written
            if delta:
                self._chunk_bytes_total += delta
                if self._speed_start_time is None:
                    self._speed_base_bytes = self._chunk_bytes_total - delta
                    self._speed_start_time = time.monotonic()

    def _reset_progress_counters(self, num_chunks=0):
        with self._progress_lock:
            self._run_token += 1
            token = self._run_token
            self._chunk_bytes = {i: 0 for i in range(num_chunks)}
            self._chunk_bytes_total = 0
            self._speed_base_bytes = 0
            self._speed_start_time = None
        return token

    def _record_chunk_error(self, message):
        with self._progress_lock:
            self._last_chunk_error = message

    def _transfer_to_part(self, url, part_path, chunk_size, expected_sha256, index,
                          token, stop_event):
        def should_stop():
            return self._should_stop(stop_event)

        offset = 0
        hasher = hashlib.sha256()

        if os.path.exists(part_path):
            existing = os.path.getsize(part_path)
            if existing > chunk_size:
                utils.safe_remove(part_path)
                self._set_chunk_bytes(index, 0, token)
            elif existing == chunk_size:
                with open(part_path, 'rb') as handle:
                    while True:
                        block = handle.read(config.IO_BLOCK_SIZE)
                        if not block:
                            break
                        hasher.update(block)
                        if should_stop():
                            raise _ChunkCancelled()
                self._set_chunk_bytes(index, chunk_size, token)
                if expected_sha256 and hasher.hexdigest() != expected_sha256:
                    return False, "sha-mismatch"
                return True, ""
            elif existing > 0:
                offset = existing
                with open(part_path, 'rb') as handle:
                    while True:
                        block = handle.read(config.IO_BLOCK_SIZE)
                        if not block:
                            break
                        hasher.update(block)
                        if should_stop():
                            raise _ChunkCancelled()

        headers = self._get_request_headers(referer=self.base_referer, is_chunk=True)
        if offset:
            headers['Range'] = f'bytes={offset}-'

        if offset == 0 and self._use_enhanced and self._curl_session:
            written = 0
            with open(part_path, 'wb') as handle:
                def content_callback(data):
                    nonlocal written
                    if should_stop():
                        return -1
                    handle.write(data)
                    hasher.update(data)
                    written += len(data)
                    self._set_chunk_bytes(index, written, token)
                    return None

                try:
                    response = self.session_enhanced.get(
                        url, timeout=config.CHUNK_TIMEOUT, headers=headers,
                        content_callback=content_callback,
                    )
                except Exception:
                    if should_stop():
                        raise _ChunkCancelled()
                    raise
            response.raise_for_status()
        else:
            if self._use_enhanced:
                response = self.session_enhanced.get(
                    url, stream=True, timeout=config.CHUNK_TIMEOUT, headers=headers)
            elif offset:
                response = self.session.get(
                    url, stream=True, timeout=config.CHUNK_TIMEOUT,
                    headers={'Range': headers['Range']})
            else:
                response = self.session.get(url, stream=True, timeout=config.CHUNK_TIMEOUT)
            response.raise_for_status()

            if offset and getattr(response, 'status_code', 0) != 206:
                offset = 0
                hasher = hashlib.sha256()

            written = offset
            with open(part_path, 'ab' if offset else 'wb') as handle:
                for block in response.iter_content(chunk_size=config.CHUNK_BUFFER):
                    if should_stop():
                        raise _ChunkCancelled()
                    if not block:
                        continue
                    handle.write(block)
                    hasher.update(block)
                    written += len(block)
                    self._set_chunk_bytes(index, written, token)
                handle.flush()

        if written != chunk_size:
            return False, f"大小不匹配 (期望 {chunk_size}, 实际 {written})"
        if expected_sha256 and hasher.hexdigest() != expected_sha256:
            return False, "sha-mismatch"
        return True, ""

    def _check_existing_chunk(self, chunk_dir, chunk_info, stop_event=None):
        return find_existing_chunk(
            chunk_dir, chunk_info,
            verified_cache=self._verified_chunks,
            should_stop=lambda: self._should_stop(stop_event),
            on_verify_start=self._begin_verify,
            on_verify_end=self._end_verify,
        )

    def _mark_chunk_done(self, index, size, path, reused=False, token=None):
        with self._progress_lock:
            if token is not None and token != self._run_token:
                return
            previous = self._chunk_bytes.get(index, 0)
            delta = size - previous
            self.downloaded_chunks[index] = path
            self._chunk_bytes[index] = size
            if delta:
                self._chunk_bytes_total += delta
                if reused:
                    self._speed_base_bytes += delta

    def _sleep_backoff(self, attempt, stop_event=None):
        deadline = time.monotonic() + config.RETRY_BASE_DELAY * (2 ** (attempt - 1))
        while time.monotonic() < deadline:
            if self._should_stop(stop_event):
                return
            time.sleep(0.05)

    def _fetch_chunk(self, base_url, index, chunk_info, chunk_dir, token, stop_event):
        if self._should_stop(stop_event):
            return False

        filename = chunk_info['filename']
        chunk_size = chunk_info['size']
        expected_sha256 = chunk_info.get('sha256')

        existing = self._check_existing_chunk(chunk_dir, chunk_info, stop_event)
        if existing:
            self._mark_chunk_done(index, chunk_size, existing, reused=True, token=token)
            return True

        try:
            chunk_path = chunk_path_in(chunk_dir, filename)
        except ValueError as exc:
            self._record_chunk_error(f"{filename}: {exc}")
            return False

        if chunk_size == 0:
            try:
                with open(chunk_path, 'wb'):
                    pass
            except OSError as exc:
                self._record_chunk_error(f"{filename}: {exc}")
                return False
            self._mark_chunk_done(index, 0, chunk_path, token=token)
            return True

        url = urljoin(base_url, self._quote_segment(filename))
        part_path = self._part_path_for(chunk_path, token)
        self._adopt_previous_part(chunk_path, part_path, token)
        last_error = "未知错误"

        for attempt in range(1, config.RETRY_ATTEMPTS + 1):
            if self._should_stop(stop_event):
                return False
            try:
                ok, err = self._transfer_to_part(
                    url, part_path, chunk_size, expected_sha256, index, token, stop_event)
            except _ChunkCancelled:
                return False
            except Exception as exc:
                ok, err = False, (str(exc)[:120] or exc.__class__.__name__)

            if ok:
                try:
                    utils.replace_with_retry(part_path, chunk_path)
                except OSError as exc:
                    self._record_chunk_error(f"{filename}: {exc}")
                    return False
                self._mark_chunk_done(index, chunk_size, chunk_path, token=token)
                return True

            last_error = err
            if err == "sha-mismatch":
                utils.safe_remove(part_path)
                self._set_chunk_bytes(index, 0, token)
            if attempt < config.RETRY_ATTEMPTS:
                self._sleep_backoff(attempt, stop_event)

        self._record_chunk_error(f"{filename}: {last_error}")
        return False

    def _part_path_for(self, chunk_path, token):
        return f"{chunk_path}.{os.getpid()}.r{token}.part"

    def _adopt_previous_part(self, chunk_path, part_path, token):
        if os.path.exists(part_path):
            return
        prefix = os.path.basename(chunk_path) + '.'
        candidates = []
        for name in self._run_part_names(token):
            if not name.startswith(prefix):
                continue
            path = os.path.join(self.chunk_dir, name)
            if path == part_path:
                continue
            try:
                candidates.append((os.path.getsize(path), path))
            except OSError:
                continue
        if not candidates:
            return
        candidates.sort(reverse=True)
        try:
            utils.replace_with_retry(candidates[0][1], part_path, attempts=2, delay=0.05)
        except OSError:
            pass

    def _run_part_names(self, token):
        with self._progress_lock:
            if self._run_part_token == token:
                return self._run_part_names_cache
            try:
                names = [n for n in os.listdir(self.chunk_dir) if n.endswith('.part')]
            except OSError:
                names = []
            self._run_part_token = token
            self._run_part_names_cache = names
            return names

    @staticmethod
    def _quote_segment(name):
        if '%' in name:
            return name
        return quote(name)


    def sanitize_filename(self, filename):
        return utils.safe_filename(filename, default="未命名")

    def _get_chunk_dir_name(self):
        return f"{self.safe_filename}-fkxz" if self.safe_filename else "fkwj"

    def get_chunk_dir(self, output_dir):
        chunk_dir = utils.ensure_within_dir(output_dir, self._get_chunk_dir_name())
        os.makedirs(chunk_dir, exist_ok=True)
        return chunk_dir

    def cleanup_chunk_dir(self, output_dir):
        try:
            chunk_dir = utils.ensure_within_dir(output_dir, self._get_chunk_dir_name())
        except ValueError:
            return
        if os.path.isdir(chunk_dir):
            shutil.rmtree(chunk_dir, ignore_errors=True)


    def update_status(self, text, foreground=config.TEXT_NORMAL):
        with self._status_lock:
            self._status_base = (text, foreground)
        self._push_status()

    def _status_payload_locked(self):
        text, foreground = self._status_base or ("状态: 就绪", config.TEXT_NORMAL)
        count = len(self._verifying_names)
        if count == 1:
            return f"状态: 正在校验已有分片 {next(iter(self._verifying_names))}", config.TEXT_NORMAL
        if count > 1:
            return f"状态: 正在校验已有分片 (并发 {count} 个)", config.TEXT_NORMAL
        return text, foreground

    def _refresh_status(self):
        with self._status_lock:
            text, foreground = self._status_payload_locked()
        self._set_status(text, foreground)

    def _push_status(self):
        self._run_on_ui_latest('status', self._refresh_status)

    def _enter_status_phase(self, text, foreground=config.TEXT_NORMAL):
        with self._status_lock:
            self._status_base = (text, foreground)
            self._verifying_names.clear()
        self._push_status()

    def _leave_status_phase(self):
        with self._status_lock:
            self._verifying_names.clear()
        self._push_status()

    def _begin_verify(self, name):
        with self._status_lock:
            self._verifying_names.add(name)
        self._push_status()

    def _end_verify(self, name):
        with self._status_lock:
            self._verifying_names.discard(name)
        self._push_status()

    def _set_status(self, text, foreground=config.TEXT_NORMAL):
        self.status_label.config(text=text, foreground=foreground)

    def show_error(self, message):
        self.update_status(f"状态: {message}", foreground=config.TEXT_ERROR)

    def _set_progress_value(self, value):
        self.progress_bar['value'] = max(0.0, min(100.0, value))

    def _set_detail(self, text):
        self.download_detail_label.config(text=text)

    def _push_overall(self, completed, count, bytes_done, total_bytes, speed,
                      show_speed=True):
        percent = 0.0
        if total_bytes > 0:
            percent = min(100.0, bytes_done / total_bytes * 100)
            self.progress_bar['value'] = percent
        text = (f"已下载: {utils.format_size(bytes_done)} / {utils.format_size(total_bytes)}"
                f" ({percent:.0f}%)")
        if show_speed:
            text += f" | 速度: {utils.speed_text(speed)}"
        text += f" | 分片: {completed}/{count}"
        self.download_detail_label.config(text=text)

    def _report_download_progress(self, num_chunks, throttle, token=None, force=False):
        if not throttle.ready(force=force):
            return
        with self._progress_lock:
            if token is not None and token != self._run_token:
                return
            bytes_done = self._chunk_bytes_total
            completed = len(self.downloaded_chunks)
            base_bytes = self._speed_base_bytes
            started = self._speed_start_time
        speed = utils.measured_speed(bytes_done - base_bytes, started)
        self._run_on_ui_latest('overall', self._push_overall,
                               completed, num_chunks, bytes_done,
                               self.total_download_size, speed)


    def _action_name(self):
        return "合并" if self.is_local else "下载"

    def _interrupted_prefix(self):
        return "合并失败" if self.is_local else "下载已中断"

    def _fail(self, prefix, detail=""):
        text = f"状态: {prefix}"
        if detail:
            text += f" - {detail}"
        self._set_retry_ui(text)

    def _cancel(self):
        self._set_retry_ui(f"状态: 已取消{self._action_name()}", is_cancel=True)

    def _fail_input(self, message):
        self._last_chunk_error = message
        self.show_error(message)
        return False

    def _validate_download_inputs(self):
        raw_path = self.url_entry.get().strip()
        raw_output = self.output_entry.get().strip()

        self.fkx_path = self._resolve_local_path(raw_path) if raw_path else ""
        self.output_dir = os.path.abspath(raw_output) if raw_output else ""

        if not raw_path:
            return self._fail_input("请输入文件信息URL或本地路径")
        if not self._looks_like_fkx(raw_path):
            return self._fail_input("输入必须是.fkx文件")
        if not self.output_dir:
            return self._fail_input("请选择输出目录")

        self.is_local = not self._is_remote_url(self.fkx_path)
        if self.fkx_path != self._file_info_source:
            self.file_info = None
        return True

    def _set_busy_ui(self):
        self._apply_ui_state("running")


    def _get_or_fetch_fkx_info(self):
        fkx_local_path = self.fkx_path

        if self.file_info and 'chunks' in self.file_info and self._file_info_source == self.fkx_path:
            self.total_download_size = sum(chunk['size'] for chunk in self.file_info['chunks'])
            return self.file_info, fkx_local_path, None

        fkx_content = None

        if self.is_local:
            if not os.path.exists(fkx_local_path):
                self.show_error(f"本地文件不存在: {fkx_local_path}")
                self._last_chunk_error = f"本地文件不存在: {fkx_local_path}"
                return None, None, None
            if not os.path.isfile(fkx_local_path):
                self.show_error(f"路径不是文件: {fkx_local_path}")
                self._last_chunk_error = f"路径不是文件: {fkx_local_path}"
                return None, None, None
            fkx_content = self.read_local_fkx(fkx_local_path)
        else:
            fkx_content = self.download_fkx(self.fkx_path)

        if self.is_cancelled or not fkx_content:
            if not fkx_content and not self.is_cancelled:
                self.show_error("无法获取文件信息")
                self._last_chunk_error = "无法获取文件信息"
            return None, None, None

        self.update_status("状态: 正在解析文件信息...")
        fkx_info = self.parse_fkx(fkx_content)

        if 'filename' not in fkx_info or 'chunks' not in fkx_info:
            self.show_error("文件信息格式不正确")
            self._last_chunk_error = "文件信息格式不正确"
            return None, None, None

        self.file_info = fkx_info
        self._file_info_source = self.fkx_path
        return fkx_info, fkx_local_path, fkx_content

    def _apply_download_state_ui(self, fkx_info, total_size, num_chunks):
        self.filename_label.config(text=str(fkx_info.get('filename', '-')))
        self.filesize_label.config(text=utils.format_size(total_size))
        self.chunks_label.config(text=str(num_chunks))
        self.progress_bar['maximum'] = 100
        self.progress_bar['value'] = 0

    def _setup_download_state(self, fkx_info, fkx_content, fkx_local_path):
        total_size = sum(chunk['size'] for chunk in fkx_info['chunks'])
        num_chunks = len(fkx_info['chunks'])

        self.file_info = fkx_info
        self.safe_filename = self.sanitize_filename(os.path.basename(str(fkx_info.get('filename', ''))))
        self.total_download_size = total_size
        self.downloaded_chunks = {}
        self.downloaded_size = 0
        self.download_start_time = time.time()
        self.chunk_dir = ""
        self._reset_progress_counters()

        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir, exist_ok=True)
            except OSError as exc:
                self.show_error(f"无法创建输出目录: {exc}")
                self._last_chunk_error = f"无法创建输出目录: {exc}"
                return None, None

        if self.is_local:
            base_path = os.path.dirname(fkx_local_path)
            self.base_referer = ""
        else:
            parsed = urlparse(self.fkx_path)
            dir_path = parsed.path.rsplit('/', 1)[0] if '/' in parsed.path else ''
            base_path = f"{parsed.scheme}://{parsed.netloc}{dir_path}/"
            self.base_referer = base_path
            try:
                self.chunk_dir = self.get_chunk_dir(self.output_dir)
            except (ValueError, OSError) as exc:
                self.show_error(f"无法创建临时目录: {exc}")
                self._last_chunk_error = f"无法创建临时目录: {exc}"
                return None, None

            remote_name = unquote(parsed.path.rsplit('/', 1)[-1]) if parsed.path else ""
            cache_name = utils.safe_filename(remote_name, default="remote.fkx")
            try:
                local_fkx_path = utils.ensure_within_dir(self.chunk_dir, cache_name)
            except ValueError:
                local_fkx_path = os.path.join(self.chunk_dir, "remote.fkx")

            if fkx_content is not None:
                if os.path.exists(local_fkx_path):
                    try:
                        local_info = self.parse_fkx(core.read_fkx_text(local_fkx_path))
                        remote_info = self.parse_fkx(fkx_content)
                        local_chunks = local_info.get('chunks', [])
                        remote_chunks = remote_info.get('chunks', [])
                        if same_chunk_layout(local_info, remote_info):
                            if any('sha256' not in lc for lc in local_chunks) and \
                                    any('sha256' in rc for rc in remote_chunks):
                                fkx_info = remote_info
                            else:
                                fkx_info = local_info
                            num_chunks = len(fkx_info['chunks'])
                            total_size = sum(chunk['size'] for chunk in fkx_info['chunks'])
                            self.file_info = fkx_info
                            self.total_download_size = total_size
                    except Exception:
                        pass
                else:
                    core.write_fkx_text(local_fkx_path, fkx_content)

        self._run_on_ui(self._apply_download_state_ui, fkx_info, total_size, num_chunks)
        return base_path, num_chunks

    def _collect_chunks(self, fkx_info, base_path, num_chunks, workers=1):
        if self.is_local:
            throttle = utils.Throttle(config.PROGRESS_INTERVAL)
            for i, chunk_info in enumerate(fkx_info['chunks']):
                if self.is_cancelled:
                    return False
                try:
                    chunk_path = chunk_path_in(base_path, chunk_info['filename'])
                except ValueError as exc:
                    self._last_chunk_error = str(exc)
                    return False
                if not os.path.exists(chunk_path):
                    self._last_chunk_error = f"分片文件不存在: {chunk_info['filename']}"
                    return False
                self.downloaded_chunks[i] = chunk_path
                self.downloaded_size += chunk_info['size']
                self._set_chunk_bytes(i, chunk_info['size'])
                if throttle.ready() or i == num_chunks - 1:
                    self._run_on_ui_latest('overall', self._push_overall,
                                           i + 1, num_chunks, self.downloaded_size,
                                           self.total_download_size, None, False)
            self.update_status(f"状态: 分片就绪，准备合并 (共{num_chunks}个)", foreground=config.TEXT_NORMAL)
            return True

        workers = max(1, min(config.MAX_WORKERS, workers, num_chunks))
        self._enter_status_phase(f"状态: 正在下载分片 (共{num_chunks}个, {workers} 线程)")
        self._run_on_ui(self._set_detail, "")
        with self._progress_lock:
            self.downloaded_chunks = {}
        token = self._reset_progress_counters(num_chunks)
        self._abort_download = False
        self.download_start_time = time.time()

        throttle = utils.Throttle(config.PROGRESS_INTERVAL)

        index_queue = queue.Queue()
        for i in range(num_chunks):
            index_queue.put(i)
        stop_event = threading.Event()

        def chunk_worker():
            try:
                while not stop_event.is_set() and not self._should_stop(stop_event):
                    try:
                        index = index_queue.get_nowait()
                    except queue.Empty:
                        return
                    if not self._fetch_chunk(base_path, index,
                                             fkx_info['chunks'][index], self.chunk_dir,
                                             token, stop_event):
                        stop_event.set()
                        return
            except Exception as exc:
                self._record_chunk_error(str(exc)[:120] or exc.__class__.__name__)
                stop_event.set()

        threads = [threading.Thread(target=chunk_worker, name=f"fkxz-chunk-{n}", daemon=True)
                   for n in range(workers)]
        for thread in threads:
            thread.start()

        stopped_early = False
        try:
            while any(thread.is_alive() for thread in threads):
                if self._should_stop(stop_event):
                    stopped_early = True
                    break
                self._report_download_progress(num_chunks, throttle, token)
                time.sleep(0.05)
        finally:
            stop_event.set()
            for thread in threads:
                thread.join(timeout=0.2)

        try:
            self._report_download_progress(num_chunks, throttle, token, force=True)

            if stopped_early or self.is_cancelled:
                return False

            with self._progress_lock:
                completed = len(self.downloaded_chunks)
            self.downloaded_size = sum(fkx_info['chunks'][i]['size'] for i in self.downloaded_chunks)
            return completed == num_chunks
        finally:
            self._leave_status_phase()

    def _merge_chunks(self, fkx_info, num_chunks, compute_sha256=True):
        safe_name = self.sanitize_filename(os.path.basename(str(fkx_info.get('filename', ''))))
        try:
            target_path = utils.unique_path(utils.ensure_within_dir(self.output_dir, safe_name))
        except ValueError as exc:
            self._last_chunk_error = str(exc)
            return None, None

        self.update_status("状态: 正在合并文件...")
        merge_start = time.monotonic()
        throttle = utils.Throttle(config.PROGRESS_INTERVAL)

        def on_progress(merged_bytes):
            if throttle.ready():
                self._report_merge_progress(
                    merged_bytes, utils.measured_speed(merged_bytes, merge_start))

        try:
            result = core.merge_chunks(
                [self.downloaded_chunks.get(i) for i in range(num_chunks)],
                target_path,
                compute_sha256=compute_sha256,
                on_progress=on_progress,
                should_stop=self._should_stop,
            )
        except core.Cancelled:
            return None, None

        self._report_merge_progress(result.size, utils.measured_speed(result.size, merge_start))

        expected_total = int(fkx_info.get('total_size') or 0)
        if expected_total and result.size != expected_total:
            utils.safe_remove(result.path)
            self._last_chunk_error = (
                f"合并字节数与文件信息不一致 (期望 {expected_total}, 实际 {result.size})")
            return None, None
        return result.path, result.sha256

    def _report_merge_progress(self, merged_bytes, speed):
        percentage = merged_bytes / self.total_download_size * 100 if self.total_download_size else 0
        text = (f"合并: {utils.format_size(merged_bytes)} / {utils.format_size(self.total_download_size)}"
                f" ({percentage:.0f}%)"
                f" | 速度: {utils.speed_text(speed)}")
        self._run_on_ui_latest('merge-progress', self._set_progress_value, percentage)
        self._run_on_ui_latest('detail', self._set_detail, text)

    def download_and_merge(self, verify_sha256=True, use_enhanced=True, workers=1):
        output_path = None
        try:
            self._use_enhanced = bool(use_enhanced and self._curl_session)
            self._last_chunk_error = ""
            self._abort_download = False
            self._run_on_ui(self._set_busy_ui)

            fkx_info, fkx_local_path, fkx_content = self._get_or_fetch_fkx_info()
            if fkx_info is None:
                if self.is_cancelled:
                    self._cancel()
                else:
                    self._fail(f"{self._action_name()}失败", self._last_chunk_error)
                return

            base_path, num_chunks = self._setup_download_state(fkx_info, fkx_content, fkx_local_path)
            if base_path is None:
                self._fail(f"{self._action_name()}失败", self._last_chunk_error)
                return

            if not self._collect_chunks(fkx_info, base_path, num_chunks, workers):
                if self.is_cancelled:
                    self._cancel()
                else:
                    self._fail(self._interrupted_prefix(), self._last_chunk_error)
                return

            if len(self.downloaded_chunks) != num_chunks:
                error_msg = f"下载不完整: 期望{num_chunks}个分片，实际下载{len(self.downloaded_chunks)}个"
                self.show_error(error_msg)
                self._last_chunk_error = error_msg
                self._fail(self._interrupted_prefix(), error_msg)
                return

            need_sha = bool(verify_sha256 and fkx_info.get('sha256'))
            output_path, digest = self._merge_chunks(fkx_info, num_chunks, compute_sha256=need_sha)
            if output_path is None:
                if self.is_cancelled:
                    self._cancel()
                else:
                    self._fail(f"{self._action_name()}失败", self._last_chunk_error)
                return

            if need_sha:
                self.update_status("状态: 正在比对SHA-256...")
                if digest != fkx_info['sha256']:
                    utils.safe_remove(output_path)
                    self._fail(f"{self._action_name()}失败", "SHA-256校验失败")
                    return

            if not self.is_local:
                self.cleanup_chunk_dir(self.output_dir)

            verified = "sha" if need_sha else ("size" if fkx_info.get('total_size') else "none")
            self._run_on_ui(self._on_success, num_chunks, verified, output_path)
        except Exception as exc:
            error_msg = str(exc) or exc.__class__.__name__
            self.show_error(f"{self._action_name()}失败 - {error_msg}")
            self._last_chunk_error = error_msg
            utils.safe_remove(output_path)
            self._fail(f"{self._action_name()}失败", error_msg)


    def _on_success(self, num_chunks, verified, output_path):
        self.progress_bar['value'] = 100
        action = "合并" if self.is_local else "下载"
        suffix = {"sha": "（SHA-256 已校验）", "size": "（已校验字节数）", "none": ""}.get(verified, "")
        self.update_status(f"状态: {action}成功{suffix}", foreground=config.TEXT_SUCCESS)
        self.download_detail_label.config(text="")
        self._apply_ui_state("idle")

        mode_text = "本地" if self.is_local else "远程"
        enhanced_text = " (增强模式)" if self._use_enhanced and not self.is_local else ""
        safe_filename = utils.safe_filename(
            os.path.basename(str((self.file_info or {}).get('filename', ''))), default="文件")
        messagebox.showinfo(
            "完成",
            f"文件{action}完成！\n模式: {mode_text}{enhanced_text}\n"
            f"文件名: {safe_filename}\n保存位置: {output_path}",
            parent=self.root,
        )

    def _set_retry_ui(self, status_text, is_cancel=False):
        def _apply():
            self.progress_bar['value'] = 0
            self.download_detail_label.config(text="")
            self._apply_ui_state("idle" if is_cancel else "retry")
            self.update_status(status_text,
                               foreground=config.TEXT_NORMAL if is_cancel else config.TEXT_ERROR)
        self._run_on_ui(_apply)

    def download_fkx(self, url):
        response = self.download_single(url)
        if response is None:
            return None
        try:
            return core.decode_fkx(response.content)
        except Exception as exc:
            self.show_error(f"无法解析文件信息: {exc}")
            return None

    def start_download(self):
        if self.download_thread and self.download_thread.is_alive():
            return

        if not self._validate_download_inputs():
            self.clear_file_info()
            self._apply_ui_state("idle")
            return

        verify_sha256 = bool(self.verify_sha256_var.get())
        use_enhanced = bool(self.enhanced_mode.get() and self._curl_session)
        try:
            workers = int(self.workers_var.get())
        except (ValueError, tk.TclError):
            workers = 1
        workers = max(1, min(config.MAX_WORKERS, workers))

        self.is_cancelled = False

        self.download_thread = threading.Thread(
            target=self.download_and_merge,
            args=(verify_sha256, use_enhanced, workers),
            name="download-worker",
            daemon=True,
        )
        self.download_thread.start()

    def cancel_download(self):
        self.is_cancelled = True
        self.cancel_button.config(state=tk.DISABLED)
        self.update_status("状态: 正在取消...")


    def close(self, timeout=2.0):
        if self._closed:
            return
        self._closed = True
        self.is_cancelled = True
        thread = self.download_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self.ui.stop()
        try:
            self.session.close()
        except Exception:
            pass
        if self.session_enhanced is not self.session:
            try:
                self.session_enhanced.close()
            except Exception:
                pass


class _ChunkCancelled(Exception):
    pass


if __name__ == "__main__":
    utils.set_app_user_model_id(config.APP_ID_DOWNLOADER)
    utils.run_gui_app(FileDownloaderApp)
