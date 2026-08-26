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
    
    def _setup_context_menu(self, entry_widget):
        menu = tk.Menu(entry_widget, tearoff=0)
        menu.add_command(label="剪切", command=lambda: entry_widget.event_generate('<<Cut>>'))
        menu.add_command(label="复制", command=lambda: entry_widget.event_generate('<<Copy>>'))
        menu.add_command(label="粘贴", command=lambda: entry_widget.event_generate('<<Paste>>'))
        menu.add_separator()
        menu.add_command(label="删除", command=lambda: entry_widget.delete(0, tk.END))
        menu.add_separator()
        menu.add_command(label="全选", command=lambda: entry_widget.select_range(0, tk.END))
        entry_widget.bind('<Button-3>', lambda e: menu.tk_popup(e.x_root, e.y_root))
    
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
        self._setup_context_menu(self.url_entry)
        
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
        
        ttk.Label(control_frame, text="分块数:").grid(row=2, column=0, sticky=tk.W, pady=5)
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
        
        self.start_button = ttk.Button(button_frame, text="开始合并", command=self.start_download, width=20, state=tk.DISABLED)
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
    
    def validate_input(self, event=None):
        path = self.url_entry.get().strip()
        if path:
            if path.startswith('http://') or path.startswith('https://'):
                if not path.endswith('.fkx'):
                    self.status_label.config(text="状态: URL必须指向.fkx文件", foreground="#cc0000")
                    self.clear_file_info()
                else:
                    self.status_label.config(text="状态: 就绪 (远程模式)", foreground="#006600")
                    self.is_local = False
                    self.start_button.config(state=tk.DISABLED, text="开始下载")
                    self.schedule_parse()
            elif path.endswith('.fkx'):
                self.status_label.config(text="状态: 就绪 (本地模式)", foreground="#006600")
                self.is_local = True
                self.start_button.config(state=tk.DISABLED, text="开始合并")
                self.schedule_parse()
            else:
                self.status_label.config(text="状态: 输入必须是.fkx文件", foreground="#cc0000")
                self.clear_file_info()
        else:
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
        self.start_button.config(state=tk.DISABLED)
    
    def show_parse_error(self, title, message):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("350x150")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        
        dialog.update_idletasks()
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()
        dialog_width = dialog.winfo_width()
        dialog_height = dialog.winfo_height()
        x = root_x + (root_width - dialog_width) // 2
        y = root_y + (root_height - dialog_height) // 2
        dialog.geometry(f"+{x}+{y}")
        
        ttk.Label(dialog, text=message, wraplength=300, justify=tk.CENTER).pack(pady=20)
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="重试", command=lambda: [dialog.destroy(), self.parse_file()]).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="确定", command=dialog.destroy).pack(side=tk.LEFT, padx=10)
    
    def _apply_parse_result(self, fkx_info, total_size, num_chunks, is_local):
        self.filename_label.config(text=fkx_info.get('filename', '-'))
        self.filesize_label.config(text=self.format_size(total_size))
        self.chunks_label.config(text=str(num_chunks))
        self.is_local = is_local
        self.file_info = fkx_info
        self.total_download_size = total_size
        button_text = "开始合并" if is_local else "开始下载"
        self.start_button.config(state=tk.NORMAL, text=button_text)
        self.update_status("状态: 解析成功", foreground="#006600")
        self.download_detail_label.config(text="")

    def _apply_parse_error(self, error_msg):
        self.show_parse_error("错误", error_msg)
        self.update_status("状态: 解析失败")
        self.clear_file_info()

    def parse_file(self):
        path = self.url_entry.get().strip()
        if not path:
            return
        
        if not path.endswith('.fkx'):
            return
        
        self._use_enhanced = self.enhanced_mode.get()
        self.progress_chunk['value'] = 0
        self.progress_total['value'] = 0
        self.update_status("状态: 正在解析文件信息...")
        
        def parse_thread():
            try:
                fkx_content = None
                if path.startswith('http://') or path.startswith('https://'):
                    fkx_content = self.download_fkx(path)
                    if not fkx_content:
                        self.root.after(0, lambda: self._apply_parse_error("无法下载文件信息"))
                        return
                else:
                    if not os.path.exists(path):
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
                is_local = not (path.startswith('http://') or path.startswith('https://'))
                
                self.root.after(0, lambda: self._apply_parse_result(fkx_info, total_size, num_chunks, is_local))
                
            except Exception as e:
                self.root.after(0, lambda: self._apply_parse_error(f"解析失败: {str(e)}"))
        
        threading.Thread(target=parse_thread, daemon=True).start()
    
    def disable_all_widgets(self):
        self.url_entry.config(state=tk.DISABLED)
        self.output_entry.config(state=tk.DISABLED)
        self.browse_fkx_btn.config(state=tk.DISABLED)
        self.browse_output_btn.config(state=tk.DISABLED)
        self.enhanced_checkbox.config(state=tk.DISABLED)
        self.start_button.config(state=tk.DISABLED)
    
    def enable_all_widgets(self):
        self.url_entry.config(state=tk.NORMAL)
        self.output_entry.config(state=tk.NORMAL)
        self.browse_fkx_btn.config(state=tk.NORMAL)
        self.browse_output_btn.config(state=tk.NORMAL)
        self.enhanced_checkbox.config(state=tk.NORMAL)
        if self.file_info and 'chunks' in self.file_info:
            button_text = "开始合并" if self.is_local else "开始下载"
            self.start_button.config(state=tk.NORMAL, text=button_text)
        self.cancel_button.config(state=tk.DISABLED)
    
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
            self.update_status(f"状态: 网络错误 - {str(e)[:50]}")
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
        def show():
            messagebox.showerror("错误", message)
        self.root.after(0, show)
    
    def update_chunk_progress(self, downloaded, chunk_size):
        def update():
            if chunk_size > 0:
                percentage = downloaded / chunk_size
                self.progress_chunk['value'] = percentage * 100
            self.root.update_idletasks()
        self.root.after(0, update)
    
    def chunk_progress_callback(self, downloaded, chunk_size):
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
            return None
        if not self.output_dir:
            self.show_error("请选择输出目录")
            return None
        if not self.fkx_path.endswith('.fkx'):
            self.show_error("输入必须是.fkx文件")
            return None
        
        self.is_local = not (self.fkx_path.startswith('http://') or self.fkx_path.startswith('https://'))
        return (self.fkx_path, self.output_dir, self.is_local)

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
                return None, None
            if not os.path.isfile(fkx_local_path):
                self.show_error(f"路径不是文件: {fkx_local_path}")
                return None, None
            fkx_content = self.read_local_fkx(fkx_local_path)
        else:
            fkx_content = self.download_fkx(self.fkx_path)
        
        if self.is_cancelled or not fkx_content:
            if not fkx_content:
                self.show_error("无法获取文件信息")
            return None, None
        
        self.update_status("状态: 正在解析文件信息...")
        fkx_info = self.parse_fkx(fkx_content)
        
        if 'filename' not in fkx_info or 'chunks' not in fkx_info:
            self.show_error("文件信息格式不正确")
            return None, None
        
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
        with open(output_path, 'wb') as f:
            for i in range(num_chunks):
                if self.is_cancelled:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    return None
                chunk_path = self.downloaded_chunks[i]
                chunk_path = os.path.normpath(chunk_path)
                with open(chunk_path, 'rb') as chunk_file:
                    for chunk in iter(lambda: chunk_file.read(65536), b""):
                        f.write(chunk)
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
        try:
            self._use_enhanced = self.enhanced_mode.get()
            
            inputs = self._validate_download_inputs()
            if inputs is None:
                self.reset_ui("状态: 下载失败")
                return
            fkx_path, output_dir, is_local = inputs  # type: ignore[reportAssignmentType]
            
            self.is_cancelled = False
            self.disable_all_widgets()
            self.cancel_button.config(state=tk.NORMAL)
            
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
            
            self.start_button.config(state=tk.DISABLED)
            self.cancel_button.config(state=tk.NORMAL)
            
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
                    self.reset_ui("状态: 下载失败")
                    return
            
            if not self.is_local:
                self.cleanup_chunk_dir(self.output_dir)
            
            self.progress_total['value'] = num_chunks
            self.progress_chunk['value'] = 100
            self.update_status("状态: 下载成功", foreground="#006600")
            self.download_detail_label.config(text="")
            self.enable_all_widgets()
            
            safe_filename = self.sanitize_filename(os.path.basename(fkx_info['filename']))  # type: ignore[reportArgumentType]
            mode_text = "本地" if self.is_local else "远程"
            enhanced_text = " (增强模式)" if self._use_enhanced and not self.is_local else ""
            def show_completion():
                messagebox.showinfo("完成", f"文件合并完成！\n模式: {mode_text}{enhanced_text}\n文件名: {safe_filename}\n保存位置: {output_path}")
            self.root.after(0, show_completion)
        except Exception as e:
            self.show_error(f"下载线程异常: {str(e)}")
            if 'output_path' in dir() and output_path is not None and os.path.exists(output_path):  # type: ignore[reportPossiblyUnboundVariable]
                os.remove(output_path)  # type: ignore[reportPossiblyUnboundVariable]
            if not self.is_local:
                self.cleanup_chunk_dir(self.output_dir)
            self.reset_ui()
    
    def download_fkx(self, url):
        while True:
            response = self.download_single(url)
            if response:
                try:
                    return response.text
                except Exception as e:
                    self.show_error(f"无法解析文件信息: {str(e)}")
                    return None
            if self.is_cancelled:
                return None
            if not self.ask_retry("下载失败", "无法下载文件信息，是否重试？"):
                return None
    
    def start_download(self):
        self.download_thread = threading.Thread(target=self.download_and_merge)
        self.download_thread.start()
    
    def cancel_download(self):
        self.is_cancelled = True
    
    def reset_ui(self, status_text=None):
        self.progress_chunk['value'] = 0
        self.progress_total['value'] = 0
        self.download_detail_label.config(text="")
        if status_text is not None:
            self.update_status(status_text)
        else:
            self.update_status("状态: 就绪")
        self.enable_all_widgets()

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