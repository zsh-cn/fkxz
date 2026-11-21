import tkinter as tk

import config
import core
import utils
import wjfk
import wjxz


class ModuleHost(tk.Frame):
    _WINDOW_METHODS = (
        'title', 'geometry', 'minsize', 'maxsize', 'resizable',
        'iconphoto', 'iconbitmap', 'protocol', 'mainloop', 'quit',
        'wm_title', 'wm_geometry', 'wm_minsize', 'wm_maxsize',
        'wm_resizable', 'wm_iconbitmap', 'wm_protocol',
    )

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.swallowed_calls = []

    def __getattr__(self, name):
        if name.startswith('_') or name not in self._WINDOW_METHODS:
            raise AttributeError(
                f"{type(self).__name__!r} object has no attribute {name!r}")

        def _noop(*args, **kwargs):
            self.swallowed_calls.append(name)
            return None

        return _noop


class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title(config.APP_NAME)

        self.settings = utils.Settings()
        utils.migrate_legacy_settings(self.settings)
        utils.apply_network_settings(self.settings)
        utils.apply_theme(self.root, self.settings.get('ttk_theme', config.THEME_AUTO))

        utils.restore_geometry(self.root, self.settings, 'main_geometry',
                               config.MAIN_WINDOW_SIZE)

        self._set_icon()
        utils.install_about_menu(self.root, config.APP_NAME)

        self.current_host = None
        self.current_app = None
        self.module_cache = {}

        self._create_sidebar()
        self._create_content()
        utils.enable_file_drop(self.root, self.handle_drop)

        if self.settings.get('last_module', 'split') == 'download':
            self.show_downloader()
        else:
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

    def handle_drop(self, paths):
        fkx_paths = [p for p in paths if p.lower().endswith(core.MANIFEST_SUFFIX)]
        if fkx_paths:
            self.show_downloader()
            target, payload = self.current_app, fkx_paths
        else:
            self.show_splitter()
            target, payload = self.current_app, paths
        handler = getattr(target, 'handle_drop', None)
        if callable(handler):
            handler(payload)

    def on_close(self):
        if getattr(self, "_closing", False):
            return
        self._closing = True
        utils.save_geometry(self.root, self.settings, 'main_geometry')
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
        self.settings.set('last_module', key)

    def show_splitter(self):
        self._switch_to("split")

    def show_downloader(self):
        self._switch_to("download")


if __name__ == "__main__":
    utils.run_gui_app(MainApp, config.APP_ID_MAIN)
