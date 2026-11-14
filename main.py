import tkinter as tk

import config
import utils
import wjfk
import wjxz


def _make_window_noop(name):

    def _noop(self, *args, **kwargs):
        self.swallowed_calls.append(name)
        return None

    _noop.__name__ = name
    return _noop


class ModuleHost(tk.Frame):

    _WINDOW_METHODS = (
        'title', 'geometry', 'minsize', 'maxsize', 'resizable',
        'iconphoto', 'iconbitmap', 'protocol', 'mainloop', 'quit',
    )

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.swallowed_calls = []

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)

        def _noop(*args, **kwargs):
            self.swallowed_calls.append(name)
            return None

        return _noop


for _method_name in ModuleHost._WINDOW_METHODS:
    setattr(ModuleHost, _method_name, _make_window_noop(_method_name))


class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title(config.APP_NAME)
        utils.scaled_geometry(self.root, *config.MAIN_WINDOW_SIZE)

        self._set_icon()
        utils.install_about_menu(self.root, config.APP_NAME)

        self.current_host = None
        self.current_app = None
        self.module_cache = {}

        self._create_sidebar()
        self._create_content()

        self.show_splitter()

    def _set_icon(self):
        self._icon = utils.apply_window_icon(self.root, 'wjfkxz.png')

    def _load_nav_icon(self, filename, size=22):
        return utils.load_icon(filename, size=size, master=self.root)

    def _create_sidebar(self):
        self.sidebar_bg = config.SIDEBAR_BG
        self.sidebar_width = config.SIDEBAR_WIDTH
        self.nav_active_bg = config.NAV_ACTIVE_BG
        self.nav_hover_bg = config.NAV_HOVER_BG
        self.nav_fg = config.NAV_FG
        self.nav_font = (config.FONT_FAMILY, config.FONT_SIZE)

        sidebar = tk.Frame(self.root, width=self.sidebar_width, bg=self.sidebar_bg,
                           highlightbackground=config.BORDER_COLOR, highlightthickness=1)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        title_frame = tk.Frame(sidebar, bg=self.sidebar_bg)
        title_frame.pack(fill=tk.X, pady=(20, 10), padx=16)
        tk.Label(title_frame, text=config.APP_NAME, font=(config.FONT_FAMILY, 13, 'bold'),
                 fg=config.TEXT_PRIMARY, bg=self.sidebar_bg).pack(anchor=tk.W)

        tk.Frame(sidebar, bg=config.BORDER_COLOR, height=1).pack(fill=tk.X, padx=12, pady=(0, 12))

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
                label.configure(bg=self.nav_active_bg, fg=config.TEXT_PRIMARY)
                indicator.configure(bg=config.NAV_ACCENT)
            else:
                frame.configure(bg=self.sidebar_bg)
                icon_label.configure(bg=self.sidebar_bg)
                label.configure(bg=self.sidebar_bg, fg=self.nav_fg)
                indicator.configure(bg=self.sidebar_bg)
        self._active_nav = key

    def _create_content(self):
        self.content_frame = tk.Frame(self.root, bg=config.CONTENT_BG)
        self.content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def on_close(self):
        if getattr(self, "_closing", False):
            return
        self._closing = True
        for _host, app in self.module_cache.values():
            closer = getattr(app, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

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

    def _switch_to(self, key):
        self._hide_current_module()
        host, app = self._get_or_create_module(key)
        host.pack(fill=tk.BOTH, expand=True)
        self.current_host = host
        self.current_app = app
        self._set_active_nav(key)

    def show_splitter(self):
        self._switch_to("split")

    def show_downloader(self):
        self._switch_to("download")


if __name__ == "__main__":
    utils.setup_dpi_awareness()
    utils.set_app_user_model_id(config.APP_ID_MAIN)

    root = tk.Tk()

    try:
        from tkinter import font
        font.nametofont("TkDefaultFont").configure(size=config.FONT_SIZE)
    except Exception:
        pass

    app = MainApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
