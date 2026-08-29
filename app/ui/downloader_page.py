import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading

from theme import (
    BG_PAGE, BG_CARD, FG_PRIMARY, FG_SECONDARY, FG_TERTIARY,
    ACCENT, BORDER, ERROR, SUCCESS,
)
from utils.helpers import (
    format_size, RoundedButton, RoundedProgressBar, parse_fkx,
    is_remote_url, has_drive_letter, is_domain_like, resolve_local_path,
)
from ui.base_page import BasePage
from core.downloader import FileDownloader, FileMerger, HAS_CURL_CFFI


class DownloaderPage(BasePage):
    _downloader: FileDownloader
    _info_after_id: str | None
    _url_entry: ttk.Entry
    _output_entry: ttk.Entry
    _url_entry_browse_btn: RoundedButton
    _output_entry_browse_btn: RoundedButton
    _filename_label: tk.Label
    _filesize_label: tk.Label
    _chunks_label: tk.Label
    _chunk_progress: RoundedProgressBar
    _total_progress: RoundedProgressBar
    _start_btn: RoundedButton
    _cancel_btn: RoundedButton
    _status_label: tk.Label
    _download_detail: tk.Label
    _enhanced_var: tk.BooleanVar
    _enhanced_cb: ttk.Checkbutton
    _verify_sha256_var: tk.BooleanVar
    _verify_sha256_cb: ttk.Checkbutton

    def __init__(self, parent):
        super().__init__(parent)
        self._downloader = FileDownloader(callbacks={
            'on_progress': self._on_progress,
            'on_chunk_progress': self._on_chunk_progress,
            'on_status': self._on_status,
            'on_error': self._on_error,
            'on_complete': self._on_complete,
            'on_file_info': self._on_file_info,
            'on_download_status': self._on_download_status,
            'on_ask_retry': self._on_ask_retry,
        })
        self._info_after_id = None
        self._auto_prepending = False
        self._retry_queue = []
        self._running = False
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        header = tk.Frame(self, bg=BG_PAGE)
        header.grid(row=0, column=0, sticky='ew', padx=32, pady=(28, 16))

        tk.Label(
            header,
            text='文件下载',
            font=('Microsoft YaHei UI', 20, 'bold'),
            fg=FG_PRIMARY,
            bg=BG_PAGE,
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            text='支持本地 .fkx 合并与远程 URL 下载分片，自动合并还原为原始文件',
            font=('Microsoft YaHei UI', 10),
            fg=FG_SECONDARY,
            bg=BG_PAGE,
        ).pack(side=tk.LEFT, padx=(16, 0), pady=(8, 0))

        card = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=1, column=0, sticky='ew', padx=32, pady=(0, 12))

        input_frame = tk.Frame(card, bg=BG_CARD, padx=24, pady=20)
        input_frame.pack(fill=tk.X)
        input_frame.columnconfigure(1, weight=1)

        self._build_field(input_frame, '文件信息 URL (.fkx)', '_url_entry', self._browse_local_fkx, 0, 0, show_browse=True)
        self._build_field(input_frame, '输出目录', '_output_entry', self._browse_output, 2, 0)

        enhanced_frame = tk.Frame(input_frame, bg=BG_CARD)
        enhanced_frame.grid(row=4, column=0, columnspan=3, sticky='ew', pady=(4, 0))

        self._enhanced_var = tk.BooleanVar(value=True)
        self._enhanced_cb = ttk.Checkbutton(
            enhanced_frame,
            text='启用增强模式 (curl_cffi 浏览器指纹模拟)',
            variable=self._enhanced_var,
        )
        self._enhanced_cb.pack(side=tk.LEFT)

        if not HAS_CURL_CFFI:
            self._enhanced_var.set(False)
            self._enhanced_cb.config(state=tk.DISABLED)
            tk.Label(
                enhanced_frame,
                text='增强模式不可用 (未安装 curl_cffi)',
                font=('Microsoft YaHei UI', 9),
                fg=ERROR,
                bg=BG_CARD,
            ).pack(side=tk.LEFT, padx=(12, 0))

        verify_frame = tk.Frame(input_frame, bg=BG_CARD)
        verify_frame.grid(row=5, column=0, columnspan=3, sticky='ew', pady=(4, 0))

        self._verify_sha256_var = tk.BooleanVar(value=True)
        self._verify_sha256_cb = ttk.Checkbutton(
            verify_frame,
            text='启用SHA-256校验',
            variable=self._verify_sha256_var,
        )
        self._verify_sha256_cb.pack(side=tk.LEFT)

        info_card = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        info_card.grid(row=2, column=0, sticky='ew', padx=32, pady=(0, 12))

        info_inner = tk.Frame(info_card, bg=BG_CARD, padx=24, pady=16)
        info_inner.pack(fill=tk.X)
        info_inner.columnconfigure(1, weight=1)

        tk.Label(info_inner, text='文件信息', font=('Microsoft YaHei UI', 12, 'bold'),
                 fg=FG_PRIMARY, bg=BG_CARD).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 12))

        info_grid = tk.Frame(info_inner, bg=BG_CARD)
        info_grid.grid(row=1, column=0, columnspan=2, sticky='ew')
        info_grid.columnconfigure(1, weight=1)

        labels = [
            ('文件名:', 'filename'),
            ('文件大小:', 'filesize'),
            ('分片数:', 'chunks'),
        ]
        for i, (label_text, key) in enumerate(labels):
            tk.Label(info_grid, text=label_text, font=('Microsoft YaHei UI', 10),
                     fg=FG_SECONDARY, bg=BG_CARD).grid(row=i, column=0, sticky='e', padx=(0, 8), pady=(0, 6))
            val_label = tk.Label(info_grid, text='-', font=('Microsoft YaHei UI', 10, 'bold'),
                                 fg=FG_PRIMARY, bg=BG_CARD, wraplength=500, justify='left', anchor='w')
            val_label.grid(row=i, column=1, sticky='w', pady=(0, 6))
            setattr(self, f'_{key}_label', val_label)

        progress_card = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        progress_card.grid(row=3, column=0, sticky='ew', padx=32, pady=(0, 12))

        progress_inner = tk.Frame(progress_card, bg=BG_CARD, padx=24, pady=16)
        progress_inner.pack(fill=tk.X)
        progress_inner.columnconfigure(0, weight=1)

        self._progress_row(progress_inner, '分片进度', '_chunk_progress', 0)
        self._progress_row(progress_inner, '总进度', '_total_progress', 2)

        self._status_label = tk.Label(progress_inner, text='就绪', font=('Microsoft YaHei UI', 10),
                                      fg=FG_SECONDARY, bg=BG_CARD, anchor='w')
        self._status_label.grid(row=4, column=0, sticky='w', pady=(8, 0))

        self._download_detail = tk.Label(progress_inner, text='', font=('Microsoft YaHei UI', 9),
                                         fg=FG_TERTIARY, bg=BG_CARD, anchor='w')
        self._download_detail.grid(row=5, column=0, sticky='w', pady=(4, 0))

        btn_frame = tk.Frame(self, bg=BG_PAGE)
        btn_frame.grid(row=4, column=0, sticky='ew', padx=32, pady=(0, 28))

        self._start_btn = RoundedButton(btn_frame, text='开始下载', command=self._start, width=120, height=38,
                                        state='normal')
        self._start_btn.pack(side=tk.LEFT, padx=(0, 12))

        self._cancel_btn = RoundedButton(btn_frame, text='取消', command=self._cancel, width=80, height=38,
                                         state='disabled', bg='#E5E7EB', fg=FG_PRIMARY)
        self._cancel_btn.pack(side=tk.LEFT)

    def _browse_local_fkx(self):
        path = filedialog.askopenfilename(filetypes=[('文件信息文件', '*.fkx')])
        if path:
            self._url_entry.delete(0, tk.END)
            self._url_entry.insert(0, path)
            self._chunk_progress['value'] = 0
            self._total_progress['value'] = 0
            self._on_input_change()

    def _browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self._output_entry.delete(0, tk.END)
            self._output_entry.insert(0, path)
            self._validate_input()

    def _on_input_change(self, event=None):
        path = self._url_entry.get().strip()
        if path and path.endswith('.fkx') and is_domain_like(path):
            if not self._auto_prepending:
                local_path = os.path.join(os.getcwd(), path)
                if os.path.exists(local_path):
                    self._update_path_type_ui(path, is_local=True)
                else:
                    self._auto_prepending = True
                    self._url_entry.delete(0, tk.END)
                    self._url_entry.insert(0, 'https://' + path)
                    self._auto_prepending = False
                    path = 'https://' + path
                    self._update_path_type_ui(path)
        else:
            self._update_path_type_ui(path)

        self._validate_input()
        if self._info_after_id:
            self.after_cancel(self._info_after_id)
            self._info_after_id = None
        if self._cancel_btn.cget('state') != 'normal':
            self._chunk_progress['value'] = 0
            self._total_progress['value'] = 0
            self._download_detail.config(text='')
            self._info_after_id = self.after(500, self._parse_and_display_info)

    def _reset_info_labels(self):
        self._filename_label.config(text='-')
        self._filesize_label.config(text='-')
        self._chunks_label.config(text='-')
        self._chunk_progress['value'] = 0
        self._total_progress['value'] = 0

    def _parse_and_display_info(self):
        self._info_after_id = None
        if self._cancel_btn.cget('state') == 'normal':
            return
        path = self._url_entry.get().strip()
        if path and is_remote_url(path):
            if path.endswith('.fkx'):
                self._downloader.fetch_fkx_info_async(path, enhanced=self._enhanced_var.get())
        elif path and path.endswith('.fkx'):
            try:
                resolved = resolve_local_path(path)
                if os.path.exists(resolved) and os.path.isfile(resolved):
                    with open(resolved, 'r', encoding='utf-8') as f:
                        content = f.read()
                    info = parse_fkx(content)
                    self._filename_label.config(text=info.get('filename', '-'))
                    self._filesize_label.config(text=format_size(int(str(info.get('total_size', 0)))))
                    self._chunks_label.config(text=str(info.get('num_chunks', len(info.get('chunks', [])))))
            except Exception:
                pass

    def _update_path_type_ui(self, path, is_local=False):
        if not path:
            if HAS_CURL_CFFI:
                self._enhanced_cb.config(state=tk.NORMAL)
            return
        if not is_local and (is_remote_url(path) or is_domain_like(path)):
            if HAS_CURL_CFFI:
                self._enhanced_cb.config(state=tk.NORMAL)
            self._start_btn.config(text='开始下载')
        else:
            self._enhanced_cb.config(state=tk.DISABLED)
            self._start_btn.config(text='开始合并')

    def _apply_validation(self, valid, status_text, status_color=None):
        if status_color is None:
            status_color = FG_SECONDARY
        self._start_btn.config(state=tk.NORMAL)
        self._status_label.config(text=status_text, fg=status_color)

    def _validate_input(self):
        text = self._url_entry.get().strip()
        output = self._output_entry.get().strip()

        if not text:
            self._apply_validation(False, '就绪')
            self._reset_info_labels()
            return

        if not text.endswith('.fkx'):
            self._apply_validation(False, '就绪')
            return

        if not output:
            self._apply_validation(False, '就绪')
            return

        if is_remote_url(text):
            self._apply_validation(True, '就绪 (远程模式)', ACCENT)
        else:
            self._apply_validation(True, '就绪 (本地模式)', ACCENT)

    def _start(self):
        self._running = True
        if self._info_after_id:
            self.after_cancel(self._info_after_id)
            self._info_after_id = None

        text = self._url_entry.get().strip()
        output = self._output_entry.get().strip()

        if not text:
            self._on_status('请输入文件信息的URL或本地路径', ERROR)
            self._reset_info_labels()
            self._running = False
            return
        if not text.endswith('.fkx'):
            self._on_status('输入必须是.fkx文件', ERROR)
            self._reset_info_labels()
            self._running = False
            return
        if not output:
            self._on_status('请选择输出目录', ERROR)
            self._running = False
            return

        text = resolve_local_path(text)

        self._start_btn.config(state=tk.DISABLED)
        self._cancel_btn.config(state=tk.NORMAL)
        self._chunk_progress['value'] = 0
        self._total_progress['value'] = 0
        self._download_detail.config(text='')
        self._url_entry.config(state=tk.DISABLED)
        self._output_entry.config(state=tk.DISABLED)
        self._url_entry_browse_btn.config(state=tk.DISABLED)
        self._output_entry_browse_btn.config(state=tk.DISABLED)
        self._enhanced_cb.config(state=tk.DISABLED)
        self._verify_sha256_cb.config(state=tk.DISABLED)
        self._downloader.download_async(
            text,
            output,
            enhanced=self._enhanced_var.get(),
            verify_sha256=self._verify_sha256_var.get(),
        )

    def _cancel(self):
        self._downloader.cancel()
        self._cancel_btn.config(state=tk.DISABLED)
        self._on_status('正在取消...', ERROR)
        self._chunk_progress['value'] = 0
        self._total_progress['value'] = 0

    def _on_progress(self, value, maximum):
        self.after(0, lambda: self._total_progress.configure(value=value, maximum=maximum))

    def _on_chunk_progress(self, value, maximum):
        self.after(0, lambda: self._chunk_progress.configure(value=value, maximum=maximum))

    def _on_status(self, text, color='#333333'):
        if not self._running and color == ERROR:
            color = FG_SECONDARY
        if text == "正在校验SHA-256...":
            self.after(0, lambda: self._cancel_btn.config(text='跳过'))
        self.after(0, lambda: self._status_label.configure(text=text, fg=color))

    def _on_error(self, message):
        self.after(0, lambda: self._status_label.configure(text=message, fg=ERROR))
        self.after(0, lambda: (
            self._cancel_btn.config(state=tk.DISABLED, text='取消'),
            self._start_btn.config(state=tk.NORMAL),
            self._chunk_progress.config(value=0),
            self._total_progress.config(value=0),
            self._download_detail.config(text=''),
            self._url_entry.config(state=tk.NORMAL),
            self._output_entry.config(state=tk.NORMAL),
            self._url_entry_browse_btn.config(state=tk.NORMAL),
            self._output_entry_browse_btn.config(state=tk.NORMAL),
            self._verify_sha256_cb.config(state=tk.NORMAL),
        ))
        self.after(0, lambda: self._update_path_type_ui(self._url_entry.get().strip()))

    def _on_complete(self, result):
        cancelled = result.get('cancelled', False) if result else False
        self.after(0, lambda: self._finalize_ui(cancelled=cancelled, result=result))
        if not cancelled:
            self.after(0, lambda: messagebox.showinfo(
                '完成',
                f"文件下载完成！\n\n模式: {result['mode']}\n"
                f"文件名: {result['file_name']}\n"
                f"保存位置: {result['output_path']}"
            ))

    def _on_file_info(self, info):
        self.after(0, lambda: self._filename_label.config(text=info.get('filename', '-')))
        self.after(0, lambda: self._filesize_label.config(text=format_size(info.get('total_size', 0))))
        self.after(0, lambda: self._chunks_label.config(text=str(info.get('num_chunks', 0))))

    def _on_download_status(self, downloaded, total, speed):
        text = ''
        if total > 0 and downloaded > 0:
            text = f"已下载: {format_size(downloaded)} / {format_size(total)}  |  速度: {format_size(int(speed))}/s"
        self.after(0, lambda t=text: self._download_detail.config(text=t))

    def _on_ask_retry(self, title, message):
        flag = [False]

        def do_ask():
            if messagebox.askretrycancel(title, message):
                flag[0] = True

        self.after(0, do_ask)

        deadline = time.time() + 120
        while not flag[0] and not self._downloader.is_cancelled and time.time() < deadline:
            self.after(200, lambda: None)
            try:
                self.winfo_toplevel().update_idletasks()
                self.winfo_toplevel().update()
            except Exception:
                break

        return flag[0]

    def _reset_ui(self):
        self._running = False
        self._on_input_change()
        self._cancel_btn.config(state=tk.DISABLED, text='取消')
        self._download_detail.config(text='')
        self._chunk_progress['value'] = 0
        self._total_progress['value'] = 0

    def _finalize_ui(self, cancelled=False, result=None):
        self._running = False
        self._cancel_btn.config(state=tk.DISABLED, text='取消')
        self._url_entry.config(state=tk.NORMAL)
        self._output_entry.config(state=tk.NORMAL)
        self._url_entry_browse_btn.config(state=tk.NORMAL)
        self._output_entry_browse_btn.config(state=tk.NORMAL)
        self._verify_sha256_cb.config(state=tk.NORMAL)
        if cancelled:
            self._download_detail.config(text='')
            self._chunk_progress['value'] = 0
            self._total_progress['value'] = 0
            self._start_btn.config(state=tk.NORMAL)
        else:
            self._start_btn.config(state=tk.NORMAL)
            mode = result.get('mode', '') if result else ''
            if mode == 'remote':
                status_text = '下载完成'
            else:
                status_text = '合并完成'
            self._status_label.config(text=status_text, fg=SUCCESS)
            self._download_detail.config(text='')
        self._update_path_type_ui(self._url_entry.get().strip())


class MergerPage(BasePage):
    _merger: FileMerger
    _fkx_entry: ttk.Entry
    _output_entry: ttk.Entry
    _fkx_entry_browse_btn: RoundedButton
    _output_entry_browse_btn: RoundedButton
    _filename_label: tk.Label
    _filesize_label: tk.Label
    _chunks_label: tk.Label
    _chunk_progress: RoundedProgressBar
    _total_progress: RoundedProgressBar
    _start_btn: RoundedButton
    _cancel_btn: RoundedButton
    _status_label: tk.Label
    _verify_sha256_var: tk.BooleanVar
    _verify_sha256_cb: ttk.Checkbutton

    def __init__(self, parent):
        super().__init__(parent)
        self._merger = FileMerger(callbacks={
            'on_progress': self._on_progress,
            'on_chunk_progress': self._on_chunk_progress,
            'on_status': self._on_status,
            'on_error': self._on_error,
            'on_complete': self._on_complete,
            'on_file_info': self._on_file_info,
        })
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        header = tk.Frame(self, bg=BG_PAGE)
        header.grid(row=0, column=0, sticky='ew', padx=32, pady=(28, 16))

        tk.Label(
            header,
            text='本地合并',
            font=('Microsoft YaHei UI', 20, 'bold'),
            fg=FG_PRIMARY,
            bg=BG_PAGE,
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            text='读取本地 .fkx 信息文件和 .fk 分片，合并还原为原始文件',
            font=('Microsoft YaHei UI', 10),
            fg=FG_SECONDARY,
            bg=BG_PAGE,
        ).pack(side=tk.LEFT, padx=(16, 0), pady=(8, 0))

        card = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=1, column=0, sticky='ew', padx=32, pady=(0, 12))

        input_frame = tk.Frame(card, bg=BG_CARD, padx=24, pady=20)
        input_frame.pack(fill=tk.X)
        input_frame.columnconfigure(1, weight=1)

        self._build_field(input_frame, '信息文件 (.fkx)', '_fkx_entry', self._browse_fkx, 0, 0)
        self._build_field(input_frame, '输出目录', '_output_entry', self._browse_output, 2, 0)

        verify_frame = tk.Frame(input_frame, bg=BG_CARD)
        verify_frame.grid(row=4, column=0, columnspan=3, sticky='ew', pady=(4, 0))

        self._verify_sha256_var = tk.BooleanVar(value=True)
        self._verify_sha256_cb = ttk.Checkbutton(
            verify_frame,
            text='启用SHA-256校验',
            variable=self._verify_sha256_var,
        )
        self._verify_sha256_cb.pack(side=tk.LEFT)

        info_card = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        info_card.grid(row=2, column=0, sticky='ew', padx=32, pady=(0, 12))

        info_inner = tk.Frame(info_card, bg=BG_CARD, padx=24, pady=16)
        info_inner.pack(fill=tk.X)
        info_inner.columnconfigure(1, weight=1)

        tk.Label(info_inner, text='文件信息', font=('Microsoft YaHei UI', 12, 'bold'),
                 fg=FG_PRIMARY, bg=BG_CARD).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 12))

        info_grid = tk.Frame(info_inner, bg=BG_CARD)
        info_grid.grid(row=1, column=0, columnspan=2, sticky='ew')
        info_grid.columnconfigure(1, weight=1)

        labels = [
            ('文件名:', 'filename'),
            ('文件大小:', 'filesize'),
            ('分片数:', 'chunks'),
        ]
        for i, (label_text, key) in enumerate(labels):
            tk.Label(info_grid, text=label_text, font=('Microsoft YaHei UI', 10),
                     fg=FG_SECONDARY, bg=BG_CARD).grid(row=i, column=0, sticky='e', padx=(0, 8), pady=(0, 6))
            val_label = tk.Label(info_grid, text='-', font=('Microsoft YaHei UI', 10, 'bold'),
                                 fg=FG_PRIMARY, bg=BG_CARD, wraplength=500, justify='left', anchor='w')
            val_label.grid(row=i, column=1, sticky='w', pady=(0, 6))
            setattr(self, f'_{key}_label', val_label)

        progress_card = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        progress_card.grid(row=3, column=0, sticky='ew', padx=32, pady=(0, 12))

        progress_inner = tk.Frame(progress_card, bg=BG_CARD, padx=24, pady=16)
        progress_inner.pack(fill=tk.X)
        progress_inner.columnconfigure(0, weight=1)

        self._progress_row(progress_inner, '分片进度', '_chunk_progress', 0)
        self._progress_row(progress_inner, '总进度', '_total_progress', 2)

        self._status_label = tk.Label(progress_inner, text='就绪', font=('Microsoft YaHei UI', 10),
                                      fg=FG_SECONDARY, bg=BG_CARD, anchor='w')
        self._status_label.grid(row=4, column=0, sticky='w', pady=(8, 0))

        btn_frame = tk.Frame(self, bg=BG_PAGE)
        btn_frame.grid(row=4, column=0, sticky='ew', padx=32, pady=(0, 28))

        self._start_btn = RoundedButton(btn_frame, text='开始合并', command=self._start, width=120, height=38,
                                        state='disabled')
        self._start_btn.pack(side=tk.LEFT, padx=(0, 12))

        self._cancel_btn = RoundedButton(btn_frame, text='取消', command=self._cancel, width=80, height=38,
                                         state='disabled', bg='#E5E7EB', fg=FG_PRIMARY)
        self._cancel_btn.pack(side=tk.LEFT)

    def _browse_fkx(self):
        path = filedialog.askopenfilename(filetypes=[('文件信息文件', '*.fkx')])
        if path:
            self._fkx_entry.delete(0, tk.END)
            self._fkx_entry.insert(0, path)
            self._chunk_progress['value'] = 0
            self._total_progress['value'] = 0
            self._validate_input()
            self._parse_and_display_info()

    def _browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self._output_entry.delete(0, tk.END)
            self._output_entry.insert(0, path)
            self._validate_input()

    def _on_input_change(self, event=None):
        self._chunk_progress['value'] = 0
        self._total_progress['value'] = 0
        self._validate_input()
        self._parse_and_display_info()

    def _parse_and_display_info(self):
        path = self._fkx_entry.get().strip()
        if path and path.endswith('.fkx') and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                info = parse_fkx(content)
                self._filename_label.config(text=info.get('filename', '-'))
                self._filesize_label.config(text=format_size(int(str(info.get('total_size', 0)))))
                self._chunks_label.config(text=str(len(info.get('chunks', []))))
            except Exception:
                pass

    def _validate_input(self):
        path = self._fkx_entry.get().strip()
        output = self._output_entry.get().strip()

        if not path:
            self._apply_validation(False, '就绪')
            return

        if not path.endswith('.fkx') or not os.path.exists(path):
            self._apply_validation(False, '就绪')
            return

        if not output:
            self._apply_validation(False, '就绪')
            return

        self._apply_validation(True, '就绪 (本地模式)', ACCENT)

    def _start(self):
        self._start_btn.config(state=tk.DISABLED)
        self._cancel_btn.config(state=tk.NORMAL)
        self._chunk_progress['value'] = 0
        self._total_progress['value'] = 0
        self._fkx_entry.config(state=tk.DISABLED)
        self._output_entry.config(state=tk.DISABLED)
        self._fkx_entry_browse_btn.config(state=tk.DISABLED)
        self._output_entry_browse_btn.config(state=tk.DISABLED)
        self._verify_sha256_cb.config(state=tk.DISABLED)
        self._merger.merge_async(
            self._fkx_entry.get().strip(),
            self._output_entry.get().strip(),
            verify_sha256=self._verify_sha256_var.get(),
        )

    def _cancel(self):
        self._merger.cancel()
        self._cancel_btn.config(state=tk.DISABLED)
        self._on_status('正在取消...', ERROR)
        self._chunk_progress['value'] = 0
        self._total_progress['value'] = 0

    def _on_progress(self, value, maximum):
        self.after(0, lambda: self._total_progress.configure(value=value, maximum=maximum))

    def _on_chunk_progress(self, value, maximum):
        self.after(0, lambda: self._chunk_progress.configure(value=value, maximum=maximum))

    def _on_status(self, text, color='#333333'):
        if text == "正在校验SHA-256...":
            self.after(0, lambda: self._cancel_btn.config(text='跳过'))
        self.after(0, lambda: self._status_label.configure(text=text, fg=color))

    def _on_error(self, message):
        self.after(0, lambda: self._status_label.configure(text=message, fg=ERROR))
        self.after(0, lambda: (
            self._cancel_btn.config(state=tk.DISABLED, text='取消'),
            self._start_btn.config(state=tk.NORMAL),
            self._chunk_progress.config(value=0),
            self._total_progress.config(value=0),
            self._fkx_entry.config(state=tk.NORMAL),
            self._output_entry.config(state=tk.NORMAL),
            self._fkx_entry_browse_btn.config(state=tk.NORMAL),
            self._output_entry_browse_btn.config(state=tk.NORMAL),
            self._verify_sha256_cb.config(state=tk.NORMAL),
        ))

    def _on_complete(self, result):
        cancelled = result.get('cancelled', False) if result else False
        self.after(0, lambda: self._finalize_ui(cancelled=cancelled))
        if not cancelled:
            self.after(0, lambda: messagebox.showinfo(
                '完成',
                f"文件合并完成！\n\n模式: {result['mode']}\n"
                f"文件名: {result['file_name']}\n"
                f"保存位置: {result['output_path']}"
            ))

    def _on_file_info(self, info):
        self.after(0, lambda: self._filename_label.config(text=info.get('filename', '-')))
        self.after(0, lambda: self._filesize_label.config(text=format_size(info.get('total_size', 0))))
        self.after(0, lambda: self._chunks_label.config(text=str(info.get('num_chunks', 0))))

    def _reset_ui(self):
        self._validate_input()
        self._cancel_btn.config(state=tk.DISABLED, text='取消')
        self._chunk_progress['value'] = 0
        self._total_progress['value'] = 0

    def _finalize_ui(self, cancelled=False):
        self._cancel_btn.config(state=tk.DISABLED, text='取消')
        self._fkx_entry.config(state=tk.NORMAL)
        self._output_entry.config(state=tk.NORMAL)
        self._fkx_entry_browse_btn.config(state=tk.NORMAL)
        self._output_entry_browse_btn.config(state=tk.NORMAL)
        self._verify_sha256_cb.config(state=tk.NORMAL)
        if cancelled:
            self._chunk_progress['value'] = 0
            self._total_progress['value'] = 0
            self._validate_input()
        else:
            self._start_btn.config(state=tk.NORMAL)
            self._status_label.config(text='合并完成', fg=SUCCESS)