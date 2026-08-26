import os
import sys
import ctypes
import tkinter as tk
from tkinter import ttk

try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('fkxz.app')
except Exception:
    pass

from ui.sidebar import Sidebar
from ui.splitter_page import SplitterPage
from ui.merger_page import MergerPage
from ui.downloader_page import DownloaderPage
from theme import (
    BG_PAGE, BG_CARD, BG_SIDEBAR,
    FG_PRIMARY, ACCENT, BORDER,
)


def _get_icon_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(getattr(sys, '_MEIPASS', ''), 'icon', 'wjfkxz.png')
    return os.path.join(os.path.dirname(__file__), '..', 'icon', 'wjfkxz.png')


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("文件分块下载")
        self.root.geometry("1100x800")
        self.root.minsize(960, 600)
        self.root.configure(bg=BG_PAGE)

        icon_path = _get_icon_path()
        if os.path.exists(icon_path):
            self._icon = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, self._icon)

        self._setup_styles()
        self._build()

    def _setup_styles(self):
        style = ttk.Style()

        available_themes = style.theme_names()
        if 'vista' in available_themes:
            style.theme_use('vista')
        elif 'xpnative' in available_themes:
            style.theme_use('xpnative')
        elif 'clam' in available_themes:
            style.theme_use('clam')

        style.configure('Sidebar.TFrame', background=BG_SIDEBAR)

        style.configure(
            'TEntry',
            font=('Microsoft YaHei UI', 10),
            fieldbackground=BG_CARD,
            foreground=FG_PRIMARY,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(12, 8),
        )

        style.map('TEntry', bordercolor=[
            ('focus', ACCENT),
        ])

        style.configure(
            'TCheckbutton',
            font=('Microsoft YaHei UI', 10),
            background=BG_CARD,
            foreground=FG_PRIMARY,
        )

        style.map('TCheckbutton', background=[
            ('active', BG_CARD),
        ])

        style.configure(
            'TLabel',
            font=('Microsoft YaHei UI', 10),
            background=BG_PAGE,
            foreground=FG_PRIMARY,
        )

        style.configure(
            'Card.TFrame',
            background=BG_CARD,
        )

    def _build(self):
        main_container = tk.Frame(self.root, bg=BG_PAGE)
        main_container.pack(fill=tk.BOTH, expand=True)

        self._content_area = tk.Frame(main_container, bg=BG_PAGE)
        self._pages = []
        self._pages.append(SplitterPage(self._content_area))
        self._pages.append(MergerPage(self._content_area))
        self._pages.append(DownloaderPage(self._content_area))

        self._sidebar = Sidebar(main_container, on_select=self._on_nav_select)
        self._sidebar.pack(side=tk.LEFT, fill=tk.Y)

        self._content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._show_page(0)

    def _on_nav_select(self, index):
        self._show_page(index)

    def _show_page(self, index):
        for page in self._pages:
            page.grid_forget()
        self._pages[index].grid(row=0, column=0, sticky='nsew')
        self._content_area.grid_rowconfigure(0, weight=1)
        self._content_area.grid_columnconfigure(0, weight=1)

    def run(self):
        self.root.mainloop()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    dpi = 96
    try:
        user32 = ctypes.windll.user32
        root = tk.Tk()
        root.withdraw()
        dpi = user32.GetDpiForWindow(root.winfo_id())
        root.destroy()
    except Exception:
        pass

    app = App()

    if dpi > 96:
        try:
            app.root.tk.call('tk', 'scaling', dpi / 72.0)
        except Exception:
            pass

    app.run()


if __name__ == '__main__':
    main()