import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from theme import (
    BG_PAGE, BG_CARD, FG_PRIMARY, FG_SECONDARY, FG_TERTIARY,
    ACCENT, ACCENT_DARK, BORDER, SUCCESS, ERROR,
)
from utils.helpers import format_size, setup_context_menu, RoundedButton, RoundedProgressBar, parse_wjxx
from core.merger import FileMerger


class MergerPage(ttk.Frame):
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
            text='读取本地 .wjx 信息文件和 .fk 分片，合并还原为原始文件',
            font=('Microsoft YaHei UI', 10),
            fg=FG_SECONDARY,
            bg=BG_PAGE,
        ).pack(side=tk.LEFT, padx=(16, 0), pady=(8, 0))

        card = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=1, column=0, sticky='ew', padx=32, pady=(0, 12))

        input_frame = tk.Frame(card, bg=BG_CARD, padx=24, pady=20)
        input_frame.pack(fill=tk.X)
        input_frame.columnconfigure(1, weight=1)

        self._build_field(input_frame, '信息文件 (.wjx)', '_wjxx_entry', self._browse_wjxx, 0, 0)
        self._build_field(input_frame, '输出目录', '_output_entry', self._browse_output, 2, 0)

        info_card = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        info_card.grid(row=2, column=0, sticky='ew', padx=32, pady=(0, 12))

        info_inner = tk.Frame(info_card, bg=BG_CARD, padx=24, pady=16)
        info_inner.pack(fill=tk.X)
        info_inner.columnconfigure(1, weight=1)

        tk.Label(info_inner, text='文件信息', font=('Microsoft YaHei UI', 12, 'bold'),
                 fg=FG_PRIMARY, bg=BG_CARD).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 12))

        info_grid = tk.Frame(info_inner, bg=BG_CARD)
        info_grid.grid(row=1, column=0, columnspan=2, sticky='ew')

        labels = [
            ('文件名:', 'filename'),
            ('文件大小:', 'filesize'),
            ('分块数:', 'chunks'),
        ]
        for i, (label_text, key) in enumerate(labels):
            col = i * 2
            tk.Label(info_grid, text=label_text, font=('Microsoft YaHei UI', 10),
                     fg=FG_SECONDARY, bg=BG_CARD).grid(row=0, column=col, sticky='w', padx=(0, 6))
            val_label = tk.Label(info_grid, text='-', font=('Microsoft YaHei UI', 10, 'bold'),
                                 fg=FG_PRIMARY, bg=BG_CARD)
            val_label.grid(row=0, column=col + 1, sticky='w', padx=(0, 32))
            setattr(self, f'_{key}_label', val_label)

        progress_card = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        progress_card.grid(row=3, column=0, sticky='nsew', padx=32, pady=(0, 12))

        progress_inner = tk.Frame(progress_card, bg=BG_CARD, padx=24, pady=20)
        progress_inner.pack(fill=tk.BOTH, expand=True)
        progress_inner.columnconfigure(0, weight=1)

        self._progress_row(progress_inner, '分块进度', '_chunk_progress', 0)
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

    def _build_field(self, parent, label, attr, browse_cb, row, col):
        tk.Label(parent, text=label, font=('Microsoft YaHei UI', 10),
                 fg=FG_PRIMARY, bg=BG_CARD, anchor='w').grid(row=row, column=col, sticky='w', pady=(0, 6))
        entry_row = tk.Frame(parent, bg=BG_CARD)
        entry_row.grid(row=row + 1, column=col, columnspan=3, sticky='ew', pady=(0, 16))
        entry_row.columnconfigure(0, weight=1)

        entry = ttk.Entry(entry_row, font=('Microsoft YaHei UI', 10))
        entry.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        entry.bind('<KeyRelease>', self._on_input_change)
        setup_context_menu(entry)
        setattr(self, attr, entry)

        RoundedButton(entry_row, text='浏览', command=browse_cb, width=80, height=34,
                      bg='#F3F4F6', fg=FG_PRIMARY).grid(row=0, column=1)

    def _progress_row(self, parent, label, attr, row):
        tk.Label(parent, text=label, font=('Microsoft YaHei UI', 10),
                 fg=FG_SECONDARY, bg=BG_CARD).grid(row=row, column=0, sticky='w', pady=(0, 6))
        pb = RoundedProgressBar(parent)
        pb.grid(row=row + 1, column=0, sticky='ew', pady=(0, 12))
        setattr(self, attr, pb)

    def _browse_wjxx(self):
        path = filedialog.askopenfilename(filetypes=[('文件信息文件', '*.wjx')])
        if path:
            self._wjxx_entry.delete(0, tk.END)
            self._wjxx_entry.insert(0, path)
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
        path = self._wjxx_entry.get().strip()
        if path and path.endswith('.wjx') and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                info = parse_wjxx(content)
                self._filename_label.config(text=info.get('filename', '-'))
                self._filesize_label.config(text=format_size(int(info.get('total_size', 0))))
                self._chunks_label.config(text=str(info.get('num_chunks', len(info.get('chunks', [])))))
            except Exception:
                self._filename_label.config(text='-')
                self._filesize_label.config(text='-')
                self._chunks_label.config(text='-')
        else:
            self._filename_label.config(text='-')
            self._filesize_label.config(text='-')
            self._chunks_label.config(text='-')

    def _validate_input(self):
        path = self._wjxx_entry.get().strip()
        output = self._output_entry.get().strip()
        if path and path.endswith('.wjx') and os.path.exists(path):
            if output:
                self._start_btn.config(state=tk.NORMAL)
                self._status_label.config(text='就绪 (本地模式)', fg=ACCENT)
            else:
                self._start_btn.config(state=tk.DISABLED)
                self._status_label.config(text='请选择输出目录', fg=ERROR)
        elif path:
            self._start_btn.config(state=tk.DISABLED)
            self._status_label.config(text='请输入有效的 .wjx 文件路径', fg=ERROR)
        else:
            self._start_btn.config(state=tk.DISABLED)
            self._status_label.config(text='就绪', fg=FG_SECONDARY)

    def _start(self):
        self._start_btn.config(state=tk.DISABLED)
        self._cancel_btn.config(state=tk.NORMAL)
        self._chunk_progress['value'] = 0
        self._total_progress['value'] = 0
        self._merger.merge_async(
            self._wjxx_entry.get().strip(),
            self._output_entry.get().strip(),
        )

    def _cancel(self):
        self._merger.cancel()

    def _on_progress(self, value, maximum):
        self.after(0, lambda: self._total_progress.configure(value=value, maximum=maximum))

    def _on_chunk_progress(self, value, maximum):
        self.after(0, lambda: self._chunk_progress.configure(value=value, maximum=maximum))

    def _on_status(self, text, color='#333333'):
        self.after(0, lambda: self._status_label.configure(text=text, fg=color))

    def _on_error(self, message):
        self.after(0, lambda: messagebox.showerror('错误', message))
        self.after(0, self._reset_ui)

    def _on_complete(self, result):
        self.after(0, self._reset_ui)
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