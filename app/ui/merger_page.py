import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from theme import (
    BG_PAGE, BG_CARD, FG_PRIMARY, FG_SECONDARY, FG_TERTIARY,
    ACCENT, BORDER, ERROR,
)
from utils.helpers import format_size, RoundedButton, RoundedProgressBar, parse_fkx
from ui.base_page import BasePage
from core.merger import FileMerger


class MergerPage(BasePage):
    _merger: FileMerger
    _fkx_entry: ttk.Entry
    _output_entry: ttk.Entry
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
            self._validate_input()
            self._parse_and_display_info()

    def _browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self._output_entry.delete(0, tk.END)
            self._output_entry.insert(0, path)
            self._validate_input()

    def _on_input_change(self, event=None):
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
        self._cancel_btn.config(state=tk.DISABLED)
        self._chunk_progress['value'] = 0
        self._total_progress['value'] = 0

    def _finalize_ui(self, cancelled=False):
        self._cancel_btn.config(state=tk.DISABLED)
        self._validate_input()
        if cancelled:
            self._chunk_progress['value'] = 0
            self._total_progress['value'] = 0