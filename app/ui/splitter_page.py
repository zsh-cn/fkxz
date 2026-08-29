import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from theme import (
    BG_PAGE, BG_CARD, FG_PRIMARY, FG_SECONDARY, FG_TERTIARY,
    BORDER, ERROR,
)
from utils.helpers import format_size, RoundedButton, RoundedProgressBar, setup_context_menu
from ui.base_page import BasePage
from core.splitter import FileSplitter


class SplitterPage(BasePage):
    _splitter: FileSplitter
    _file_entry: ttk.Entry
    _output_entry: ttk.Entry
    _chunk_var: tk.StringVar
    _filesize_label: tk.Label
    _chunkcount_label: tk.Label
    _progress: RoundedProgressBar
    _start_btn: RoundedButton
    _cancel_btn: RoundedButton
    _status_label: tk.Label
    _update_after_id: str | None

    def __init__(self, parent):
        super().__init__(parent)
        self._update_after_id = None
        self._splitter = FileSplitter(callbacks={
            'on_progress': self._on_progress,
            'on_chunk_progress': self._on_chunk_progress,
            'on_status': self._on_status,
            'on_error': self._on_error,
            'on_complete': self._on_complete,
        })
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        header = tk.Frame(self, bg=BG_PAGE)
        header.grid(row=0, column=0, sticky='ew', padx=32, pady=(28, 16))

        tk.Label(
            header,
            text='文件分块',
            font=('Microsoft YaHei UI', 20, 'bold'),
            fg=FG_PRIMARY,
            bg=BG_PAGE,
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            text='将大文件拆分为多个分片，生成 .fk 分片文件和 .fkx 信息文件',
            font=('Microsoft YaHei UI', 10),
            fg=FG_SECONDARY,
            bg=BG_PAGE,
        ).pack(side=tk.LEFT, padx=(16, 0), pady=(8, 0))

        card = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=1, column=0, sticky='ew', padx=32, pady=(0, 12))

        input_frame = tk.Frame(card, bg=BG_CARD, padx=24, pady=20)
        input_frame.pack(fill=tk.X)
        input_frame.columnconfigure(1, weight=1)

        self._build_field(input_frame, '选择文件', '_file_entry', self._browse_file, 0, 0)
        self._build_field(input_frame, '输出目录', '_output_entry', self._browse_output, 2, 0)

        size_frame = tk.Frame(input_frame, bg=BG_CARD)
        size_frame.grid(row=4, column=0, columnspan=3, sticky='ew', pady=(4, 0))

        tk.Label(size_frame, text='分片大小 (MB)', font=('Microsoft YaHei UI', 10),
                 fg=FG_PRIMARY, bg=BG_CARD).pack(side=tk.LEFT)

        self._chunk_var = tk.StringVar(value='10')
        vcmd = (self.register(self._validate_chunk), '%P')
        chunk_entry = ttk.Entry(size_frame, textvariable=self._chunk_var, width=10,
                                font=('Microsoft YaHei UI', 10),
                                validate='key', validatecommand=vcmd)
        chunk_entry.pack(side=tk.LEFT, padx=(12, 8))
        setup_context_menu(chunk_entry)

        tk.Label(size_frame, text='范围 1 - 1024 MB', font=('Microsoft YaHei UI', 9),
                 fg=FG_TERTIARY, bg=BG_CARD).pack(side=tk.LEFT)

        info_card = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        info_card.grid(row=2, column=0, sticky='ew', padx=32, pady=(0, 12))

        info_inner = tk.Frame(info_card, bg=BG_CARD, padx=24, pady=16)
        info_inner.pack(fill=tk.X)
        info_inner.columnconfigure(1, weight=1)

        tk.Label(info_inner, text='分块信息', font=('Microsoft YaHei UI', 12, 'bold'),
                 fg=FG_PRIMARY, bg=BG_CARD).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 12))

        info_grid = tk.Frame(info_inner, bg=BG_CARD)
        info_grid.grid(row=1, column=0, columnspan=2, sticky='ew')
        info_grid.columnconfigure(1, weight=1)

        labels = [
            ('文件大小:', 'filesize'),
            ('分片数:', 'chunkcount'),
        ]
        for i, (label_text, key) in enumerate(labels):
            tk.Label(info_grid, text=label_text, font=('Microsoft YaHei UI', 10),
                     fg=FG_SECONDARY, bg=BG_CARD).grid(row=i, column=0, sticky='e', padx=(0, 8), pady=(0, 6))
            val_label = tk.Label(info_grid, text='-', font=('Microsoft YaHei UI', 10, 'bold'),
                                 fg=FG_PRIMARY, bg=BG_CARD, wraplength=500, justify='left', anchor='w')
            val_label.grid(row=i, column=1, sticky='w', pady=(0, 6))
            setattr(self, f'_{key}_label', val_label)

        self._chunk_var.trace_add('write', lambda *args: self._schedule_file_info_update())

        progress_card = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        progress_card.grid(row=3, column=0, sticky='ew', padx=32, pady=(0, 12))

        progress_inner = tk.Frame(progress_card, bg=BG_CARD, padx=24, pady=16)
        progress_inner.pack(fill=tk.X)
        progress_inner.columnconfigure(0, weight=1)

        tk.Label(progress_inner, text='拆分进度', font=('Microsoft YaHei UI', 10),
                 fg=FG_SECONDARY, bg=BG_CARD).grid(row=0, column=0, sticky='w', pady=(0, 6))
        self._progress = RoundedProgressBar(progress_inner)
        self._progress.grid(row=1, column=0, sticky='ew', pady=(0, 12))

        self._status_label = tk.Label(progress_inner, text='就绪', font=('Microsoft YaHei UI', 10),
                                      fg=FG_SECONDARY, bg=BG_CARD, anchor='w')
        self._status_label.grid(row=2, column=0, sticky='w')

        btn_frame = tk.Frame(self, bg=BG_PAGE)
        btn_frame.grid(row=4, column=0, sticky='ew', padx=32, pady=(0, 28))

        self._start_btn = RoundedButton(btn_frame, text='开始拆分', command=self._start, width=120, height=38,
                                        state='disabled')
        self._start_btn.pack(side=tk.LEFT, padx=(0, 12))

        self._cancel_btn = RoundedButton(btn_frame, text='取消', command=self._cancel, width=80, height=38,
                                         state='disabled', bg='#E5E7EB', fg=FG_PRIMARY)
        self._cancel_btn.pack(side=tk.LEFT)

    def _validate_chunk(self, value):
        if value == '':
            return True
        try:
            v = int(value)
            return 1 <= v <= 1024
        except ValueError:
            return False

    def _update_file_info(self):
        self._update_after_id = None
        if not hasattr(self, '_filesize_label'):
            return
        file_path = self._file_entry.get().strip()
        if not file_path or not os.path.exists(file_path):
            self._progress['value'] = 0
            self._filesize_label.config(text='-')
            self._chunkcount_label.config(text='-')
            return
        try:
            chunk_size_mb = int(self._chunk_var.get())
            if chunk_size_mb < 1 or chunk_size_mb > 1024:
                chunk_size_mb = None
        except ValueError:
            chunk_size_mb = None

        file_size = os.path.getsize(file_path)
        self._filesize_label.config(text=format_size(file_size))

        if chunk_size_mb is not None:
            chunk_size = chunk_size_mb * 1024 * 1024
            num_chunks = (file_size + chunk_size - 1) // chunk_size
            self._chunkcount_label.config(text=str(num_chunks))
        else:
            self._chunkcount_label.config(text='-')

    def _schedule_file_info_update(self):
        if self._update_after_id is not None:
            self.after_cancel(self._update_after_id)
        self._update_after_id = self.after(300, self._update_file_info)

    def _browse_file(self):
        path = filedialog.askopenfilename()
        if path:
            self._file_entry.delete(0, tk.END)
            self._file_entry.insert(0, path)
            self._progress['value'] = 0
            self._status_label.config(text='就绪', fg=FG_SECONDARY)
            self._update_file_info()
            self._validate_input()

    def _browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self._output_entry.delete(0, tk.END)
            self._output_entry.insert(0, path)
            self._validate_input()

    def _on_input_change(self, event=None):
        self._progress['value'] = 0
        self._status_label.config(text='就绪', fg=FG_SECONDARY)
        self._schedule_file_info_update()
        self._validate_input()

    def _validate_input(self):
        file_path = self._file_entry.get().strip()
        output = self._output_entry.get().strip()

        if not file_path:
            self._apply_validation(False, '就绪')
            return

        if not os.path.isfile(file_path):
            self._apply_validation(False, '就绪')
            return

        if not output:
            self._apply_validation(False, '就绪')
            return

        self._apply_validation(True, '就绪')

    def _start(self):
        self._start_btn.config(state=tk.DISABLED)
        self._cancel_btn.config(state=tk.NORMAL)
        self._progress['value'] = 0
        self._splitter.split_async(
            self._file_entry.get().strip(),
            self._output_entry.get().strip(),
            self._chunk_var.get(),
        )

    def _cancel(self):
        self._splitter.cancel()
        self._cancel_btn.config(state=tk.DISABLED)
        self._on_status('正在取消...', ERROR)
        self._progress['value'] = 0

    def _on_progress(self, value, maximum):
        self.after(0, lambda: self._progress.configure(value=value, maximum=maximum))

    def _on_chunk_progress(self, value, maximum):
        self.after(0, lambda: self._progress.configure(value=value, maximum=maximum))

    def _on_status(self, text, color='#333333'):
        self.after(0, lambda: self._status_label.configure(text=text, fg=color))

    def _on_error(self, message):
        self.after(0, lambda: self._status_label.configure(text=message, fg=ERROR))
        self.after(0, self._reset_ui)

    def _on_complete(self, result):
        cancelled = result.get('cancelled', False) if result else False
        self.after(0, lambda: self._finalize_ui(cancelled=cancelled))
        if not cancelled:
            self.after(0, lambda: messagebox.showinfo(
                '完成',
                f"文件拆分完成！\n\n文件名: {result['file_name']}\n"
                f"文件大小: {format_size(result['file_size'])}\n"
                f"分片数: {result['num_chunks']}\n"
                f"信息文件: {result['fkx_filename']}\n"
                f"保存位置: {result['output_dir']}"
            ))

    def _reset_ui(self):
        if self._update_after_id is not None:
            self.after_cancel(self._update_after_id)
            self._update_after_id = None
        self._validate_input()
        self._cancel_btn.config(state=tk.DISABLED)
        self._progress['value'] = 0

    def _finalize_ui(self, cancelled=False):
        self._cancel_btn.config(state=tk.DISABLED)
        self._validate_input()
        if cancelled:
            self._progress['value'] = 0
            self._status_label.config(text='拆分已取消', fg=ERROR)