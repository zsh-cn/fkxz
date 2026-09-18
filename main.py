import os
import sys
import ctypes

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('fkxz.main')
except Exception:
    pass

import tkinter as tk
from tkinter import ttk

import wjfk
import wjxz


class ModuleHost(tk.Frame):

    def title(self, *args, **kwargs):
        pass

    def geometry(self, *args, **kwargs):
        pass

    def minsize(self, *args, **kwargs):
        pass

    def resizable(self, *args, **kwargs):
        pass

    def iconphoto(self, *args, **kwargs):
        pass

    def iconbitmap(self, *args, **kwargs):
        pass

    def protocol(self, *args, **kwargs):
        pass

    def mainloop(self, *args, **kwargs):
        pass

    def quit(self, *args, **kwargs):
        pass


class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("文件分块下载")
        self.root.geometry("950x700")
        self.root.minsize(950, 650)

        self._set_icon()

        self.current_host = None
        self.current_app = None
        self.module_cache = {}

        self._create_sidebar()
        self._create_content()

        self.show_splitter()

    def _set_icon(self):
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(getattr(sys, '_MEIPASS', ''), 'icon', 'wjfkxz.png')
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon', 'wjfkxz.png')
        if os.path.exists(icon_path):
            self._icon = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, self._icon)

    def _load_nav_icon(self, filename, size=22):
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(getattr(sys, '_MEIPASS', ''), 'icon', filename)
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon', filename)
        if os.path.exists(icon_path):
            img = tk.PhotoImage(file=icon_path)
            w, h = img.width(), img.height()
            if w > size or h > size:
                factor = max(1, max(w, h) // size)
                img = img.subsample(factor, factor)
            return img
        return None

    def _create_sidebar(self):
        self.sidebar_bg = "#f4f5f7"
        self.sidebar_width = 200
        self.nav_active_bg = "#e0e4eb"
        self.nav_hover_bg = "#eaecf0"
        self.nav_fg = "#333333"
        self.nav_font = ('Microsoft YaHei UI', 10)

        sidebar = tk.Frame(self.root, width=self.sidebar_width, bg=self.sidebar_bg,
                           highlightbackground="#d5d8dc", highlightthickness=1)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        title_frame = tk.Frame(sidebar, bg=self.sidebar_bg)
        title_frame.pack(fill=tk.X, pady=(20, 10), padx=16)
        tk.Label(title_frame, text="文件分块下载", font=('Microsoft YaHei UI', 13, 'bold'),
                 fg="#1a1a1a", bg=self.sidebar_bg).pack(anchor=tk.W)

        tk.Frame(sidebar, bg="#d5d8dc", height=1).pack(fill=tk.X, padx=12, pady=(0, 12))

        self.nav_items = {}
        self._nav_icon_refs = []
        self.icon_fk = self._load_nav_icon("wjfk.png")
        self.icon_xz = self._load_nav_icon("wjxz.png")
        self._create_nav_item(sidebar, "文件分块", "split", self.show_splitter, icon=self.icon_fk)
        self._create_nav_item(sidebar, "文件下载", "download", self.show_downloader, icon=self.icon_xz)

        tk.Frame(sidebar, bg=self.sidebar_bg, height=1).pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 8))

        self._active_nav = None

    def _create_nav_item(self, parent, text, key, command, icon=None):
        frame = tk.Frame(parent, bg=self.sidebar_bg, cursor="hand2")

        indicator = tk.Frame(frame, bg=self.sidebar_bg, width=3)
        indicator.pack(side=tk.LEFT, fill=tk.Y)

        if icon:
            icon_label = tk.Label(frame, image=icon, bg=self.sidebar_bg, padx=8, pady=4)
            self._nav_icon_refs.append(icon)
        else:
            icon_label = tk.Label(frame, text="", bg=self.sidebar_bg, padx=4, pady=4)
        icon_label.pack(side=tk.LEFT)

        label = tk.Label(frame, text=text, font=self.nav_font,
                         fg=self.nav_fg, bg=self.sidebar_bg,
                         anchor=tk.W, padx=4, pady=8)

        def _on_enter(event):
            if self._active_nav != key:
                frame.configure(bg=self.nav_hover_bg)
                icon_label.configure(bg=self.nav_hover_bg)
                label.configure(bg=self.nav_hover_bg)
                indicator.configure(bg=self.nav_hover_bg)

        def _on_leave(event):
            if self._active_nav != key:
                frame.configure(bg=self.sidebar_bg)
                icon_label.configure(bg=self.sidebar_bg)
                label.configure(bg=self.sidebar_bg)
                indicator.configure(bg=self.sidebar_bg)

        def _on_click(event):
            self._set_active_nav(key)
            command()

        frame.bind("<Enter>", _on_enter)
        frame.bind("<Leave>", _on_leave)
        icon_label.bind("<Enter>", _on_enter)
        icon_label.bind("<Leave>", _on_leave)
        icon_label.bind("<Button-1>", _on_click)
        label.bind("<Enter>", _on_enter)
        label.bind("<Leave>", _on_leave)
        label.bind("<Button-1>", _on_click)
        indicator.bind("<Button-1>", _on_click)

        label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        frame.pack(fill=tk.X, padx=8, pady=1)

        self.nav_items[key] = (frame, icon_label, label, indicator)

    def _set_active_nav(self, key):
        for k, (frame, icon_label, label, indicator) in self.nav_items.items():
            if k == key:
                frame.configure(bg=self.nav_active_bg)
                icon_label.configure(bg=self.nav_active_bg)
                label.configure(bg=self.nav_active_bg, fg="#1a1a1a")
                indicator.configure(bg="#3b71fe")
            else:
                frame.configure(bg=self.sidebar_bg)
                icon_label.configure(bg=self.sidebar_bg)
                label.configure(bg=self.sidebar_bg, fg=self.nav_fg)
                indicator.configure(bg=self.sidebar_bg)
        self._active_nav = key

    def _create_content(self):
        self.content_frame = tk.Frame(self.root, bg="#ffffff")
        self.content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _hide_current_module(self):
        if self.current_host is not None:
            self.current_host.pack_forget()

    def _get_or_create_module(self, key):
        if key in self.module_cache:
            return self.module_cache[key]

        host = ModuleHost(self.content_frame)
        if key == "split":
            app = wjfk.FileSplitterApp(host)
        elif key == "download":
            app = wjxz.FileDownloaderApp(host)
        else:
            raise ValueError(f"Unknown module key: {key}")

        self.module_cache[key] = (host, app)
        return host, app

    def show_splitter(self):
        self._hide_current_module()

        host, app = self._get_or_create_module("split")
        host.pack(fill=tk.BOTH, expand=True)
        self.current_host = host
        self.current_app = app

        self._set_active_nav("split")

    def show_downloader(self):
        self._hide_current_module()

        host, app = self._get_or_create_module("download")
        host.pack(fill=tk.BOTH, expand=True)
        self.current_host = host
        self.current_app = app

        self._set_active_nav("download")


if __name__ == "__main__":
    root = tk.Tk()

    try:
        from tkinter import font
        default_font = font.nametofont("TkDefaultFont")
        default_font.configure(size=10)
    except Exception:
        pass

    try:
        scale_factor = root.tk.call('tk', 'scaling')
    except Exception:
        scale_factor = 1.0

    if scale_factor > 1.5:
        root.update_idletasks()
        req_width = max(950, int(950 * scale_factor / 1.25))
        req_height = max(700, int(700 * scale_factor / 1.25))
    else:
        req_width, req_height = 950, 700

    root.geometry(f"{req_width}x{req_height}")
    root.minsize(req_width, req_height - 50)

    app = MainApp(root)
    root.mainloop()