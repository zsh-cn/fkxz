import os
import sys
import requests
import hashlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
from urllib.parse import urlparse, urljoin
import time
import shutil
import ctypes

try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('fkxz.downloader')
except Exception:
    pass

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
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

class FileDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("文件下载")
        self.root.geometry("650x600")
        self.root.minsize(650, 600)
        self.root.resizable(True, True)

        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(getattr(sys, '_MEIPASS', ''), 'icon', 'wjxz.png')
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon', 'wjxz.png')
        if os.path.exists(icon_path):
            self._icon = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, self._icon)
        
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
        self.session = requests.Session()
        if HAS_CURL_CFFI:
            self.session_enhanced = curl_requests.Session(impersonate="chrome131")  # type: ignore[reportPossiblyUnboundVariable]
        else:
            self.session_enhanced = requests.Session()
            self.session_enhanced.mount('http://', requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32))  # type: ignore[reportAttributeAccessIssue]
            self.session_enhanced.mount('https://', requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32))  # type: ignore[reportAttributeAccessIssue]
        self.session_enhanced.headers.update(BROWSER_HEADERS)
        self.session.mount('http://', requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32))  # type: ignore[reportAttributeAccessIssue]
        self.session.mount('https://', requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32))  # type: ignore[reportAttributeAccessIssue]
        self.downloaded_chunks = {}
        self.chunk_errors = []
        self.file_info = {}
        self.total_download_size = 0
        self.downloaded_size = 0
        self.download_start_time = 0
        self.chunk_dir = ""
        self.safe_filename = ""
        self.base_referer = ""
        self.enhanced_mode = tk.BooleanVar(value=True)
        self._use_enhanced = True
        
        self.create_widgets()
    
    def _delete_selected(self, entry_widget):
        try:
            if entry_widget.selection_present():
                entry_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass

    def _setup_context_menu(self, entry_widget, on_change=None):
        menu = tk.Menu(entry_widget, tearoff=0)

        def _after_action():
            if on_change:
                entry_widget.after_idle(on_change)

        def _copy_to_clipboard(saved_selection=None):
            try:
                entry_widget.clipboard_clear()
                if saved_selection:
                    entry_widget.clipboard_append(saved_selection)
                else:
                    entry_widget.event_generate('<<Copy>>')
            except tk.TclError:
                pass

        menu.add_command(label="剪切", command=lambda: (entry_widget.event_generate('<<Cut>>'), _after_action()))
        menu.add_command(label="复制", command=lambda: entry_widget.event_generate('<<Copy>>'))
        menu.add_command(label="粘贴", command=lambda: (entry_widget.event_generate('<<Paste>>'), _after_action()))
        menu.add_separator()
        menu.add_command(label="删除", command=lambda: (self._delete_selected(entry_widget), _after_action()))
        menu.add_separator()
        menu.add_command(label="全选", command=lambda: entry_widget.select_range(0, tk.END))

        def _show_menu(event):
            if entry_widget.focus_get() != entry_widget:
                entry_widget.focus_set()
                entry_widget.select_range(0, tk.END)
            has_selection = False
            saved_selection = None
            try:
                has_selection = entry_widget.selection_present()
                if has_selection:
                    saved_selection = entry_widget.selection_get()
            except tk.TclError:
                pass
            state = tk.NORMAL if has_selection else tk.DISABLED
            menu.entryconfig(0, state=state)
            menu.entryconfig(1, state=state, command=lambda: _copy_to_clipboard(saved_selection))
            menu.entryconfig(4, state=state)

            paste_state = tk.DISABLED
            try:
                if entry_widget.clipboard_get():
                    paste_state = tk.NORMAL
            except (tk.TclError, Exception):
                pass
            menu.entryconfig(2, state=paste_state)

            select_all_state = tk.NORMAL if entry_widget.get() else tk.DISABLED
            menu.entryconfig(6, state=select_all_state)

            menu.tk_popup(event.x_root, event.y_root)

        entry_widget.bind('<Button-3>', _show_menu)
    
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        url_frame = ttk.LabelFrame(main_frame, text="文件信息来源", padding="10")
        url_frame.pack(fill=tk.X, pady=5)
        url_frame.columnconfigure(1, weight=1)
        
        ttk.Label(url_frame, text="文件信息URL或本地路径 (.fkx):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.grid(row=0, column=1, padx=10, pady=5, sticky=tk.EW)
        self.url_entry.bind('<KeyRelease>', self.validate_input)
        self._setup_context_menu(self.url_entry, on_change=self.validate_input)
        
        ttk.Label(url_frame, text="输出目录:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.output_entry = ttk.Entry(url_frame)
        self.output_entry.grid(row=1, column=1, padx=10, pady=5, sticky=tk.EW)
        self.browse_output_btn = ttk.Button(url_frame, text="浏览", command=self.browse_output_dir)
        self.browse_output_btn.grid(row=1, column=2, pady=5)
        self._setup_context_menu(self.output_entry)
        
        self.browse_fkx_btn = ttk.Button(url_frame, text="浏览", command=self.browse_fkx_file)
        self.browse_fkx_btn.grid(row=0, column=2, pady=5)
        
        self.enhanced_checkbox = ttk.Checkbutton(url_frame, text="启用增强模式 (curl_cffi浏览器指纹模拟)", variable=self.enhanced_mode)
        self.enhanced_checkbox.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=5)

        if not HAS_CURL_CFFI:
            self.enhanced_mode.set(False)
            self.enhanced_checkbox.config(state=tk.DISABLED)
            ttk.Label(url_frame, text="增强模式不可用 (未安装 curl_cffi)", foreground='#E74C3C').grid(row=2, column=2, sticky=tk.W, pady=5)
        
        control_frame = ttk.LabelFrame(main_frame, text="文件信息", padding="10")
        control_frame.pack(fill=tk.X, pady=5)
        control_frame.columnconfigure(1, weight=1)
        
        ttk.Label(control_frame, text="文件名:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.filename_label = ttk.Label(control_frame, text="-", foreground="#666666")
        self.filename_label.grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)
        
        ttk.Label(control_frame, text="文件大小:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.filesize_label = ttk.Label(control_frame, text="-", foreground="#666666")
        self.filesize_label.grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
        
        ttk.Label(control_frame, text="分片数:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.chunks_label = ttk.Label(control_frame, text="-", foreground="#666666")
        self.chunks_label.grid(row=2, column=1, sticky=tk.W, padx=10, pady=5)
        
        control_frame2 = ttk.LabelFrame(main_frame, text="处理状态", padding="10")
        control_frame2.pack(fill=tk.X, pady=5)
        control_frame2.columnconfigure(0, weight=1)
        
        self.progress_chunk = ttk.Progressbar(control_frame2, orient=tk.HORIZONTAL, mode='determinate')
        self.progress_chunk.grid(row=0, column=0, pady=5, sticky=tk.EW)
        
        self.progress_total = ttk.Progressbar(control_frame2, orient=tk.HORIZONTAL, mode='determinate')
        self.progress_total.grid(row=1, column=0, pady=5, sticky=tk.EW)
        
        self.status_label = ttk.Label(control_frame2, text="状态: 就绪", foreground="#333333")
        self.status_label.grid(row=2, column=0, sticky=tk.W, pady=5)
        
        self.download_detail_label = ttk.Label(control_frame2, text="", foreground="#666666")
        self.download_detail_label.grid(row=3, column=0, sticky=tk.W, pady=5)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        self.start_button = ttk.Button(button_frame, text="开始合并", command=self.start_download, width=20, state=tk.NORMAL)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.cancel_button = ttk.Button(button_frame, text="取消", command=self.cancel_download, width=15, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=5)
    
    def format_size(self, size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    @staticmethod
    def _is_remote_url(path):
        return path.startswith('http://') or path.startswith('https://')

    @staticmethod
    def _has_drive_letter(path):
        return len(path) >= 2 and path[1] == ':'

    @staticmethod
    def _is_domain_like(path):
        if not path:
            return False
        if path.startswith('http://') or path.startswith('https://'):
            return False
        if len(path) >= 2 and path[1] == ':':
            return False
        if path.startswith('.') or path.startswith('/') or path.startswith('\\'):
            return False
        slash_pos = path.find('/')
        if slash_pos == -1:
            slash_pos = len(path)
        dot_pos = path.find('.')
        return dot_pos != -1 and dot_pos < slash_pos

    def _resolve_local_path(self, path):
        if not self._is_remote_url(path) and not self._has_drive_letter(path):
            return os.path.abspath(path)
        return path

    def _update_path_type_ui(self, path, is_local=False):
        if not path:
            if HAS_CURL_CFFI:
                self.enhanced_checkbox.config(state=tk.NORMAL)
            return
        if not is_local and (self._is_remote_url(path) or self._is_domain_like(path)):
            if HAS_CURL_CFFI:
                self.enhanced_checkbox.config(state=tk.NORMAL)
            self.start_button.config(text="开始下载")
        else:
            self.enhanced_checkbox.config(state=tk.DISABLED)
            self.start_button.config(text="开始合并")

    def validate_input(self, event=None):
        path = self.url_entry.get().strip()
        if path:
            if path.endswith('.fkx') and self._is_domain_like(path):
                if not getattr(self, '_auto_prepending', False):
                    local_path = os.path.join(os.getcwd(), path)
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

            if path.endswith('.fkx'):
                self.schedule_parse()
            else:
                self.status_label.config(text="状态: 就绪", foreground="#333333")
        else:
            self._update_path_type_ui("")
            self.status_label.config(text="状态: 就绪", foreground="#333333")
            self.clear_file_info()
    
    def schedule_parse(self):
        if hasattr(self, '_parse_after_id'):
            self.root.after_cancel(self._parse_after_id)
        self._parse_after_id = self.root.after(500, self.parse_file)
    
    def clear_file_info(self):
        self.file_info = None
        self.total_download_size = 0
        self.filename_label.config(text="-")
        self.filesize_label.config(text="-")
        self.chunks_label.config(text="-")
        self.download_detail_label.config(text="")
        self.progress_chunk['value'] = 0
        self.progress_total['value'] = 0
    
    def show_parse_error(self, title, message):
        self.update_status(f"状态: {title} - {message}", foreground="#cc0000")
    
    def _apply_parse_result(self, fkx_info, total_size, num_chunks):
        self.filename_label.config(text=fkx_info.get('filename', '-'))
        self.filesize_label.config(text=self.format_size(total_size))
        self.chunks_label.config(text=str(num_chunks))
        self.is_local = not self._is_remote_url(self.fkx_path)
        self.file_info = fkx_info
        self.total_download_size = total_size
        self._update_path_type_ui(self.fkx_path)
        mode_text = "本地模式" if self.is_local else "远程模式"
        self.update_status(f"状态: 就绪 ({mode_text})", foreground="#006600")
        self.download_detail_label.config(text="")

    def _apply_parse_error(self, error_msg):
        self.status_label.config(text="状态: 就绪", foreground="#333333")

    def parse_file(self):
        path = self.url_entry.get().strip()
        if not path:
            return
        
        if not path.endswith('.fkx'):
            return
        
        path = self._resolve_local_path(path)
        self.fkx_path = path
        self._use_enhanced = self.enhanced_mode.get()
        self.progress_chunk['value'] = 0
        self.progress_total['value'] = 0
        
        def parse_thread():
            try:
                fkx_content = None
                if self._is_remote_url(path):
                    fkx_content = self.download_fkx(path)
                    if not fkx_content:
                        self.root.after(0, lambda: self._apply_parse_error("无法下载文件信息"))
                        return
                else:
                    if not os.path.exists(path) or not os.path.isfile(path):
                        self.root.after(0, lambda: self._apply_parse_error(f"本地文件不存在: {path}"))
                        return
                    fkx_content = self.read_local_fkx(path)
                
                if not fkx_content:
                    self.root.after(0, lambda: self._apply_parse_error("无法获取文件信息"))
                    return
                
                fkx_info = self.parse_fkx(fkx_content)
                
                if 'filename' not in fkx_info or 'chunks' not in fkx_info:
                    self.root.after(0, lambda: self._apply_parse_error("文件信息格式不正确"))
                    return
                
                total_size = sum(chunk['size'] for chunk in fkx_info['chunks'])
                num_chunks = len(fkx_info['chunks'])

                self.root.after(0, lambda: self._apply_parse_result(fkx_info, total_size, num_chunks))
                
            except Exception as e:
                self.root.after(0, lambda: self._apply_parse_error(f"解析失败: {str(e)}"))
        
        threading.Thread(target=parse_thread, daemon=True).start()
    
    def disable_all_widgets(self):
        def _disable():
            self.url_entry.config(state=tk.DISABLED)
            self.output_entry.config(state=tk.DISABLED)
            self.browse_fkx_btn.config(state=tk.DISABLED)
            self.browse_output_btn.config(state=tk.DISABLED)
            self.enhanced_checkbox.config(state=tk.DISABLED)
            self.start_button.config(state=tk.DISABLED)
        self.root.after(0, _disable)
    
    def enable_all_widgets(self):
        def _enable():
            self.url_entry.config(state=tk.NORMAL)
            self.output_entry.config(state=tk.NORMAL)
            self.browse_fkx_btn.config(state=tk.NORMAL)
            self.browse_output_btn.config(state=tk.NORMAL)
            if self.is_local:
                self.enhanced_checkbox.config(state=tk.DISABLED)
            elif HAS_CURL_CFFI:
                self.enhanced_checkbox.config(state=tk.NORMAL)
            else:
                self.enhanced_checkbox.config(state=tk.DISABLED)
            if self.file_info and 'chunks' in self.file_info:
                button_text = "开始合并" if self.is_local else "开始下载"
                self.start_button.config(state=tk.NORMAL, text=button_text)
            else:
                self.start_button.config(state=tk.NORMAL, text="开始下载")
            self.cancel_button.config(state=tk.DISABLED)
        self.root.after(0, _enable)
    
    def browse_fkx_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("文件信息文件", "*.fkx")])
        if file_path:
            self.fkx_path = file_path
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, file_path)
            self.validate_input()
    
    def browse_output_dir(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.output_dir = dir_path
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, dir_path)
    
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

    def download_single(self, url, timeout=120):
        try:
            if self._use_enhanced:
                session = self.session_enhanced
                headers = self._get_request_headers()
                if HAS_CURL_CFFI:
                    response = session.get(url, timeout=timeout, headers=headers)
                else:
                    response = session.get(url, timeout=timeout, stream=True, headers=headers)
            else:
                response = self.session.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            return response
        except Exception as e:
            self.update_status(f"状态: 网络错误 - {str(e)[:50]}", foreground="#cc0000")
            return None

    def ask_retry(self, title, message):
        result = [False]
        event = threading.Event()

        def show_dialog():
            if messagebox.askretrycancel(title, message):
                result[0] = True
            event.set()

        self.root.after(0, show_dialog)
        event.wait()
        return result[0]
    
    def read_local_fkx(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            self.show_error(f"无法读取文件信息: {str(e)}")
            return None
    
    def parse_fkx(self, content):
        info = {'chunks': []}
        
        lines = content.strip().split('\n')
        for line in lines:
            if '=' in line:
                key, value = line.split('=', 1)
                if key.startswith('chunk_'):
                    parts = value.split(',')
                    if len(parts) >= 2:
                        chunk_filename = parts[0].strip()
                        chunk_filename = os.path.basename(chunk_filename)
                        chunk_info = {
                            'filename': chunk_filename,
                            'size': int(parts[1])
                        }
                        info['chunks'].append(chunk_info)
                else:
                    info[key] = value.strip()
        
        return info
    
    def _download_stream_to_file(self, response, chunk_path, chunk_size, progress_callback):
        downloaded = 0
        with open(chunk_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=65536):
                if self.is_cancelled:
                    if os.path.exists(chunk_path):
                        os.remove(chunk_path)
                    return False
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, chunk_size, len(chunk))
        return True

    def download_chunk_stream(self, url, chunk_path, chunk_size, progress_callback=None):
        while True:
            try:
                if self._use_enhanced:
                    session = self.session_enhanced
                    headers = self._get_request_headers(referer=self.base_referer, is_chunk=True)
                    if HAS_CURL_CFFI:
                        fh_ref: list = [None]
                        downloaded_bytes = [0]
                        last_reported = [0]

                        def content_callback(data):
                            if self.is_cancelled:
                                return -1
                            fh_ref[0].write(data)  # type: ignore[reportOptionalMemberAccess]
                            downloaded_bytes[0] += len(data)
                            d = downloaded_bytes[0]
                            if d - last_reported[0] >= 65536 or d >= chunk_size:
                                last_reported[0] = d
                                if progress_callback:
                                    progress_callback(d, chunk_size, len(data))

                        with open(chunk_path, 'wb') as f:
                            fh_ref[0] = f
                            response = session.get(url, timeout=120, headers=headers, content_callback=content_callback)  # type: ignore[reportCallIssue]
                        response.raise_for_status()
                    else:
                        response = session.get(url, stream=True, timeout=120, headers=headers)
                        response.raise_for_status()
                        if not self._download_stream_to_file(response, chunk_path, chunk_size, progress_callback):
                            return False
                else:
                    response = self.session.get(url, stream=True, timeout=120)
                    response.raise_for_status()
                    if not self._download_stream_to_file(response, chunk_path, chunk_size, progress_callback):
                        return False
                
                if self.is_cancelled:
                    if os.path.exists(chunk_path):
                        os.remove(chunk_path)
                    return False
                
                return True
            except Exception as e:
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)
                if self.is_cancelled:
                    return False
                if not self.ask_retry("下载失败", f"分片下载失败: {str(e)[:100]}\n是否重试？"):
                    self.chunk_errors.append(f"下载失败: {str(e)}")
                    return False
    
    def download_chunk(self, base_url, chunk_info, chunk_index, output_dir, progress_callback=None):
        chunk_url = urljoin(base_url, chunk_info['filename'])
        
        chunk_size = chunk_info['size']
        chunk_path = os.path.join(output_dir, chunk_info['filename'])
        chunk_path = os.path.normpath(chunk_path)
        
        if chunk_size == 0:
            with open(chunk_path, 'wb') as f:
                pass
            self.downloaded_chunks[chunk_index] = chunk_path  # type: ignore[reportCallIssue]
            return chunk_index
        
        self.update_status(f"状态: 正在下载 {chunk_info['filename']}")
        success = self.download_chunk_stream(chunk_url, chunk_path, chunk_size, progress_callback)
        
        if success and os.path.exists(chunk_path) and os.path.getsize(chunk_path) == chunk_size:
            self.downloaded_chunks[chunk_index] = chunk_path  # type: ignore[reportCallIssue]
            self.downloaded_size += chunk_size
            return chunk_index
        
        if os.path.exists(chunk_path):
            os.remove(chunk_path)
        return None
    
    def read_local_chunk(self, base_path, chunk_info):
        chunk_path = os.path.join(base_path, chunk_info['filename'])
        chunk_path = os.path.normpath(chunk_path)
        try:
            with open(chunk_path, 'rb') as f:
                return f.read()
        except Exception as e:
            self.show_error(f"无法读取分片文件 {chunk_info['filename']}: {str(e)}")
            return None
    
    def sanitize_filename(self, filename):
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename
    
    def _get_chunk_dir_name(self):
        return f"{self.safe_filename}-fkxz" if self.safe_filename else "fkwj"

    def get_chunk_dir(self, output_dir):
        chunk_dir = os.path.join(output_dir, self._get_chunk_dir_name())
        if os.path.exists(chunk_dir):
            shutil.rmtree(chunk_dir)
        os.makedirs(chunk_dir, exist_ok=True)
        return chunk_dir
    
    def cleanup_chunk_dir(self, output_dir):
        chunk_dir = os.path.join(output_dir, self._get_chunk_dir_name())
        if os.path.exists(chunk_dir):
            shutil.rmtree(chunk_dir)
    
    def update_status(self, text, foreground="#333333"):
        def update():
            self.status_label.config(text=text, foreground=foreground)
            self.root.update_idletasks()
        self.root.after(0, update)
    
    def show_error(self, message):
        self.update_status(f"状态: {message}", foreground="#cc0000")
    
    def update_chunk_progress(self, downloaded, chunk_size):
        def update():
            if chunk_size > 0:
                percentage = downloaded / chunk_size
                self.progress_chunk['value'] = percentage * 100
            self.root.update_idletasks()
        self.root.after(0, update)
    
    def chunk_progress_callback(self, downloaded, chunk_size, chunk_len=0):
        total_downloaded = self._downloaded_before_chunk + downloaded
        
        elapsed = time.time() - self.download_start_time
        if elapsed > 0:
            speed = total_downloaded / elapsed
        else:
            speed = 0
        
        self.update_chunk_progress(downloaded, chunk_size)
        self.update_download_status(total_downloaded, self.total_download_size, speed)
    
    def update_download_status(self, downloaded, total, speed):
        def update():
            if total > 0 and downloaded > 0:
                text = f"已下载: {self.format_size(downloaded)} / {self.format_size(total)} | 速度: {self.format_size(int(speed))}/s"
                self.download_detail_label.config(text=text)
            self.root.update_idletasks()
        self.root.after(0, update)
    
    def _validate_download_inputs(self):
        self.fkx_path = self.url_entry.get().strip()
        self.output_dir = self.output_entry.get().strip()
        
        if not self.fkx_path:
            self.show_error("请输入文件信息的URL或本地路径")
            self.clear_file_info()
            return None
        if not self.fkx_path.endswith('.fkx'):
            self.show_error("输入必须是.fkx文件")
            self.clear_file_info()
            return None
        if not self.output_dir:
            self.show_error("请选择输出目录")
            return None
        
        self.fkx_path = self._resolve_local_path(self.fkx_path)
        self.output_dir = os.path.abspath(self.output_dir)
        self.is_local = not self._is_remote_url(self.fkx_path)
        return (self.fkx_path, self.output_dir)

    def _get_or_fetch_fkx_info(self):
        fkx_local_path = self.fkx_path
        fkx_content = None
        
        if self.file_info and 'chunks' in self.file_info:
            if self.is_local:
                fkx_content = self.read_local_fkx(fkx_local_path)
            else:
                fkx_content = self.download_fkx(self.fkx_path)
        elif self.is_local:
            if self.fkx_path.startswith('file://'):
                fkx_local_path = self.fkx_path[7:]
            if not os.path.exists(fkx_local_path):
                self.show_error(f"本地文件不存在: {fkx_local_path}")
                return None, None, None
            if not os.path.isfile(fkx_local_path):
                self.show_error(f"路径不是文件: {fkx_local_path}")
                return None, None, None
            fkx_content = self.read_local_fkx(fkx_local_path)
        else:
            fkx_content = self.download_fkx(self.fkx_path)
        
        if self.is_cancelled or not fkx_content:
            if not fkx_content:
                self.show_error("无法获取文件信息")
            return None, None, None

        self.update_status("状态: 正在解析文件信息...")
        fkx_info = self.parse_fkx(fkx_content)

        if 'filename' not in fkx_info or 'chunks' not in fkx_info:
            self.show_error("文件信息格式不正确")
            return None, None, None
        
        return fkx_info, fkx_local_path, fkx_content

    def _setup_download_state(self, fkx_info, fkx_content, fkx_local_path):
        num_chunks = len(fkx_info['chunks'])
        total_size = sum(chunk['size'] for chunk in fkx_info['chunks'])
        
        self.filename_label.config(text=fkx_info.get('filename', '-'))
        self.filesize_label.config(text=self.format_size(total_size))
        self.chunks_label.config(text=str(num_chunks))
        self.file_info = fkx_info
        self.safe_filename = self.sanitize_filename(os.path.basename(fkx_info['filename']))
        self.total_download_size = total_size
        
        self.progress_total['maximum'] = num_chunks
        self.progress_total['value'] = 0
        self.progress_chunk['maximum'] = 100
        self.progress_chunk['value'] = 0
        
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
            except Exception as e:
                self.show_error(f"无法创建输出目录: {str(e)}")
                return None, None
        
        self.downloaded_chunks = {}
        self.chunk_errors = []
        self.downloaded_size = 0
        self.download_start_time = time.time()
        self.chunk_dir = ""
        
        if self.is_local:
            base_path = os.path.dirname(fkx_local_path)
            self.base_referer = ""
        else:
            parsed = urlparse(self.fkx_path)
            dir_path = parsed.path.rsplit('/', 1)[0] if '/' in parsed.path else ''
            base_path = f"{parsed.scheme}://{parsed.netloc}{dir_path}/"
            self.base_referer = base_path
            self.chunk_dir = self.get_chunk_dir(self.output_dir)
            fkx_save_path = os.path.join(self.chunk_dir, os.path.basename(self.fkx_path))
            with open(fkx_save_path, 'w', encoding='utf-8') as f:
                f.write(fkx_content)
        
        return base_path, num_chunks

    def _collect_chunks(self, fkx_info, base_path, num_chunks):
        if self.is_local:
            for i, chunk_info in enumerate(fkx_info['chunks']):
                if self.is_cancelled:
                    return False
                self.update_status(f"状态: 正在读取分片 {i+1}/{num_chunks}")
                chunk_path = os.path.join(base_path, chunk_info['filename'])
                chunk_path = os.path.normpath(chunk_path)
                self.downloaded_chunks[i] = chunk_path
                self.downloaded_size += chunk_info['size']
                self.progress_total['value'] = i + 1
                self.progress_chunk['value'] = 100
                self.update_download_status(self.downloaded_size, self.total_download_size, 0)
        else:
            self.update_status(f"状态: 正在顺序下载分片 (共{num_chunks}个)")
            self.download_detail_label.config(text="")
            for i, chunk_info in enumerate(fkx_info['chunks']):
                if self.is_cancelled:
                    return False
                self.update_status(f"状态: 正在下载分片 {i+1}/{num_chunks}: {chunk_info['filename']}")
                self._downloaded_before_chunk = self.downloaded_size
                result = self.download_chunk(base_path, chunk_info, i, self.chunk_dir,
                                            self.chunk_progress_callback)
                if result is None:
                    self.update_status(f"状态: 分片 {i+1} 下载失败")
                    return False
                self.progress_total['value'] = i + 1
                self.progress_chunk['value'] = 100
                self.root.update_idletasks()
        return True

    def _merge_chunks(self, fkx_info, num_chunks):
        safe_filename = self.sanitize_filename(os.path.basename(fkx_info['filename']))
        output_path = os.path.join(self.output_dir, safe_filename)
        output_path = os.path.normpath(output_path)
        
        self.update_status("状态: 正在合并文件...")
        merged_bytes = [0]
        cancelled = False
        with open(output_path, 'wb') as f:
            for i in range(num_chunks):
                if self.is_cancelled:
                    cancelled = True
                    break
                chunk_path = self.downloaded_chunks[i]
                chunk_path = os.path.normpath(chunk_path)
                with open(chunk_path, 'rb') as chunk_file:
                    for chunk in iter(lambda: chunk_file.read(65536), b""):
                        f.write(chunk)
                        merged_bytes[0] += len(chunk)
                        if self.total_download_size > 0:
                            def update_progress():
                                percentage = merged_bytes[0] / self.total_download_size
                                self.progress_chunk['value'] = percentage * 100
                                self.download_detail_label.config(
                                    text=f"合并中: {self.format_size(merged_bytes[0])} / {self.format_size(self.total_download_size)}"
                                )
                                self.root.update_idletasks()
                            self.root.after(0, update_progress)
        if cancelled:
            if os.path.exists(output_path):
                os.remove(output_path)
            return None
        return output_path

    def _verify_sha256(self, output_path, expected_sha256):
        self.update_status("状态: 正在校验SHA-256...")
        actual_sha256 = hashlib.sha256()
        with open(output_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b""):
                if self.is_cancelled:
                    return False
                actual_sha256.update(chunk)
        if actual_sha256.hexdigest() != expected_sha256:
            self.show_error("文件SHA-256校验失败")
            return False
        return True

    def download_and_merge(self):
        output_path = None
        try:
            self._use_enhanced = self.enhanced_mode.get()
            
            inputs = self._validate_download_inputs()
            if inputs is None:
                self.reset_ui("状态: 下载失败")
                return
            fkx_path, output_dir = inputs  # type: ignore[reportAssignmentType]
            
            self.is_cancelled = False
            def _disable_widgets():
                self.disable_all_widgets()
                self.cancel_button.config(state=tk.NORMAL)
            self.root.after(0, _disable_widgets)
            
            fkx_info, fkx_local_path, fkx_content = self._get_or_fetch_fkx_info()
            if fkx_info is None:
                if not self.is_local:
                    self.cleanup_chunk_dir(self.output_dir)
                self.reset_ui("状态: 下载失败" if not self.is_cancelled else "状态: 已取消下载")
                return
            
            base_path, num_chunks = self._setup_download_state(fkx_info, fkx_content, fkx_local_path)
            
            if base_path is None:
                self.reset_ui("状态: 下载失败")
                return
            
            def _set_buttons():
                self.start_button.config(state=tk.DISABLED)
                self.cancel_button.config(state=tk.NORMAL)
            self.root.after(0, _set_buttons)
            
            if not self._collect_chunks(fkx_info, base_path, num_chunks):
                if self.is_cancelled:
                    if not self.is_local:
                        self.cleanup_chunk_dir(self.output_dir)
                    self.reset_ui("状态: 已取消下载")
                    return
                if self.chunk_errors:
                    self.show_error("\n".join(self.chunk_errors))
                if not self.is_local:
                    self.cleanup_chunk_dir(self.output_dir)
                self.reset_ui("状态: 下载失败")
                return
            
            if len(self.downloaded_chunks) != num_chunks:
                self.show_error(f"下载不完整: 期望{num_chunks}个分片，实际下载{len(self.downloaded_chunks)}个")
                if not self.is_local:
                    self.cleanup_chunk_dir(self.output_dir)
                self.reset_ui("状态: 下载失败")
                return
            
            output_path = self._merge_chunks(fkx_info, num_chunks)
            if output_path is None:
                if not self.is_local:
                    self.cleanup_chunk_dir(self.output_dir)
                self.reset_ui("状态: 已取消下载")
                return
            
            if 'sha256' in fkx_info:
                if not self._verify_sha256(output_path, fkx_info['sha256']):
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    if not self.is_local:
                        self.cleanup_chunk_dir(self.output_dir)
                    if self.is_cancelled:
                        self.reset_ui("状态: 已取消下载")
                    else:
                        self.reset_ui("状态: 下载失败")
                    return
            
            if not self.is_local:
                self.cleanup_chunk_dir(self.output_dir)
            
            def _on_success():
                self.progress_total['value'] = num_chunks
                self.progress_chunk['value'] = 100
                self.update_status("状态: 下载成功", foreground="#006600")
                self.download_detail_label.config(text="")
                self.enable_all_widgets()
            self.root.after(0, _on_success)
            
            safe_filename = self.sanitize_filename(os.path.basename(fkx_info['filename']))  # type: ignore[reportArgumentType]
            mode_text = "本地" if self.is_local else "远程"
            enhanced_text = " (增强模式)" if self._use_enhanced and not self.is_local else ""
            def show_completion():
                messagebox.showinfo("完成", f"文件合并完成！\n模式: {mode_text}{enhanced_text}\n文件名: {safe_filename}\n保存位置: {output_path}")
            self.root.after(0, show_completion)
        except Exception as e:
            self.show_error(f"下载线程异常: {str(e)}")
            if output_path is not None and os.path.exists(output_path):
                os.remove(output_path)
            if not self.is_local:
                self.cleanup_chunk_dir(self.output_dir)
            self.reset_ui("状态: 下载失败")
    
    def download_fkx(self, url):
        response = self.download_single(url)
        if response:
            try:
                return response.text
            except Exception as e:
                self.show_error(f"无法解析文件信息: {str(e)}")
                return None
        if self.is_cancelled:
            return None
        return None
    
    def start_download(self):
        self.download_thread = threading.Thread(target=self.download_and_merge)
        self.download_thread.start()
    
    def cancel_download(self):
        self.is_cancelled = True
    
    def reset_ui(self, status_text=None):
        def _reset():
            self.progress_chunk['value'] = 0
            self.progress_total['value'] = 0
            self.download_detail_label.config(text="")
            if status_text is not None:
                self.update_status(status_text)
            else:
                self.update_status("状态: 就绪")
            self.enable_all_widgets()
        self.root.after(0, _reset)

if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    
    root = tk.Tk()
    
    try:
        from tkinter import font
        default_font = font.nametofont("TkDefaultFont")
        default_font.configure(size=10)
    except Exception:
        pass
    
    app = FileDownloaderApp(root)
    root.mainloop()