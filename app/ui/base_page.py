import tkinter as tk
from tkinter import ttk
from typing import Callable, Any

from theme import FG_PRIMARY, FG_SECONDARY, BG_CARD
from utils.helpers import setup_context_menu, RoundedButton, RoundedProgressBar


class BasePage(ttk.Frame):
    _on_input_change: Callable[[tk.Event], Any]
    _start_btn: RoundedButton
    _status_label: tk.Label

    def _build_field(self, parent, label, attr, browse_cb, row, col, show_browse=True):
        tk.Label(parent, text=label, font=('Microsoft YaHei UI', 10),
                 fg=FG_PRIMARY, bg=BG_CARD, anchor='w').grid(row=row, column=col, sticky='w', pady=(0, 6))
        entry_row = tk.Frame(parent, bg=BG_CARD)
        entry_row.grid(row=row + 1, column=col, columnspan=3, sticky='ew', pady=(0, 16))
        entry_row.columnconfigure(0, weight=1)

        entry = ttk.Entry(entry_row, font=('Microsoft YaHei UI', 10))
        entry.grid(row=0, column=0, sticky='ew', padx=(0, 10), ipady=2)
        entry.bind('<KeyRelease>', self._on_input_change)
        entry.bind('<<Paste>>', lambda e: entry.after(10, self._on_input_change))  # type: ignore[arg-type]
        entry.bind('<<Cut>>', lambda e: entry.after(10, self._on_input_change))  # type: ignore[arg-type]
        setup_context_menu(entry, on_change=self._on_input_change)
        setattr(self, attr, entry)

        if show_browse:
            RoundedButton(entry_row, text='浏览', command=browse_cb, width=80, height=36,
                          bg='#F3F4F6', fg=FG_PRIMARY).grid(row=0, column=1)

    def _progress_row(self, parent, label, attr, row):
        tk.Label(parent, text=label, font=('Microsoft YaHei UI', 10),
                 fg=FG_SECONDARY, bg=BG_CARD).grid(row=row, column=0, sticky='w', pady=(0, 6))
        pb = RoundedProgressBar(parent)
        pb.grid(row=row + 1, column=0, sticky='ew', pady=(0, 12))
        setattr(self, attr, pb)

    def _apply_validation(self, valid, status_text, status_color=None):
        if status_color is None:
            status_color = FG_SECONDARY
        if valid:
            self._start_btn.config(state=tk.NORMAL)
        else:
            self._start_btn.config(state=tk.DISABLED)
        self._status_label.config(text=status_text, fg=status_color)