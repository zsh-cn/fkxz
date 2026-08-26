import tkinter as tk
from tkinter import ttk

from theme import (
    BG_SIDEBAR, BG_SIDEBAR_HOVER,
    FG_SIDEBAR_TEXT, FG_SIDEBAR_TEXT_ACTIVE,
    ACCENT,
)


class Sidebar(ttk.Frame):
    def __init__(self, parent, on_select=None):
        super().__init__(parent, width=220)
        self.pack_propagate(False)
        self.on_select = on_select
        self._buttons = []
        self._selected = 0

        self._build()

    def _build(self):
        self.configure(style='Sidebar.TFrame')

        header_frame = tk.Frame(self, bg=BG_SIDEBAR, height=72)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)

        tk.Label(
            header_frame,
            text="文件分块下载",
            font=('Microsoft YaHei UI', 13, 'bold'),
            fg='#FFFFFF',
            bg=BG_SIDEBAR,
        ).pack(anchor='w', padx=24, pady=(22, 0))

        inner = tk.Frame(self, bg=BG_SIDEBAR)
        inner.pack(fill=tk.BOTH, expand=True, pady=(8, 8))

        items = [
            ('文件分块', '将大文件拆分为多个分片'),
            ('本地合并', '合并本地分片还原文件'),
            ('远程下载', '从远程URL下载并合并'),
        ]

        for i, (label, tip) in enumerate(items):
            btn_frame = tk.Frame(inner, bg=BG_SIDEBAR, cursor='hand2')
            btn_frame.pack(fill=tk.X, padx=12, pady=2)

            text_frame = tk.Frame(btn_frame, bg=BG_SIDEBAR)
            text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

            title_label = tk.Label(
                text_frame,
                text=label,
                font=('Microsoft YaHei UI', 10),
                fg=FG_SIDEBAR_TEXT,
                bg=BG_SIDEBAR,
                anchor='w',
            )
            title_label.pack(fill=tk.X)
            setattr(self, f'_title_{i}', title_label)

            tip_label = tk.Label(
                text_frame,
                text=tip,
                font=('Microsoft YaHei UI', 8),
                fg='#6B7280',
                bg=BG_SIDEBAR,
                anchor='w',
            )
            tip_label.pack(fill=tk.X, pady=(2, 0))
            setattr(self, f'_tip_{i}', tip_label)

            right_indicator = tk.Frame(btn_frame, bg=BG_SIDEBAR, width=3)
            right_indicator.pack(side=tk.RIGHT, fill=tk.Y)
            setattr(self, f'_indicator_{i}', right_indicator)

            for widget in (btn_frame, text_frame, title_label, tip_label):
                widget.bind('<Button-1>', lambda e, idx=i: self.select(idx))
                widget.bind('<Enter>', lambda e, idx=i: self._on_hover(idx, True))
                widget.bind('<Leave>', lambda e, idx=i: self._on_hover(idx, False))

            self._buttons.append({
                'frame': btn_frame,
                'indicator': right_indicator,
                'title': title_label,
                'tip': tip_label,
            })

        self.select(0)

    def select(self, index):
        self._selected = index
        for i, btn in enumerate(self._buttons):
            if i == index:
                btn['indicator'].configure(bg=ACCENT)
                btn['title'].configure(fg=FG_SIDEBAR_TEXT_ACTIVE)
                btn['tip'].configure(fg='#C7D2FE')
                btn['frame'].configure(bg='#2A2D32')
                btn['title'].configure(bg='#2A2D32')
                btn['tip'].configure(bg='#2A2D32')
            else:
                btn['indicator'].configure(bg=BG_SIDEBAR)
                btn['title'].configure(fg=FG_SIDEBAR_TEXT)
                btn['tip'].configure(fg='#6B7280')
                btn['frame'].configure(bg=BG_SIDEBAR)
                btn['title'].configure(bg=BG_SIDEBAR)
                btn['tip'].configure(bg=BG_SIDEBAR)

        if self.on_select:
            self.on_select(index)

    def _on_hover(self, index, entering):
        if index == self._selected:
            return
        btn = self._buttons[index]
        if entering:
            btn['frame'].configure(bg=BG_SIDEBAR_HOVER)
            btn['title'].configure(fg='#E5E7EB', bg=BG_SIDEBAR_HOVER)
            btn['tip'].configure(fg='#9CA3AF', bg=BG_SIDEBAR_HOVER)
        else:
            btn['frame'].configure(bg=BG_SIDEBAR)
            btn['title'].configure(fg=FG_SIDEBAR_TEXT, bg=BG_SIDEBAR)
            btn['tip'].configure(fg='#6B7280', bg=BG_SIDEBAR)