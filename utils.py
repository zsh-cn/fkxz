import ctypes
import hashlib
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import config


RESERVED_FILENAMES = {'CON', 'PRN', 'AUX', 'NUL'}
RESERVED_FILENAMES.update('COM%d' % i for i in range(1, 10))
RESERVED_FILENAMES.update('LPT%d' % i for i in range(1, 10))

INVALID_FILENAME_CHARS = '<>:"/\\|?*'

MAX_FILENAME_LENGTH = config.MAX_FILENAME_LENGTH


def safe_filename(name, default="未命名", max_length=MAX_FILENAME_LENGTH):
    """把任意字符串净化成合法、可安全落盘的文件名。

    处理：路径分隔符、Windows 非法字符、控制字符、首尾空白、
    结尾的点/空格、保留设备名（CON/PRN/AUX/NUL/COM1..LPT9）、超长截断、空结果。
    """
    if name is None:
        return default
    text = str(name)
    text = text.replace('\\', '/').split('/')[-1]
    text = ''.join('_' if (ord(ch) < 32 or ch in INVALID_FILENAME_CHARS) else ch for ch in text)
    text = text.strip().strip('. ')
    if not text or text in ('.', '..'):
        return default

    stem, ext = os.path.splitext(text)
    if stem.upper() in RESERVED_FILENAMES:
        stem = f"{stem}_"
        text = stem + ext

    if len(ext) > 16:
        stem, ext = text, ''
    if len(stem) + len(ext) > max_length:
        stem = stem[:max(1, max_length - len(ext))]
        text = (stem + ext).rstrip('. ')
    return text or default


def unique_path(path):
    """若目标已存在，依次尝试 "名称 (1).后缀"、"名称 (2).后缀"……"""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    index = 1
    while True:
        candidate = f"{base} ({index}){ext}"
        if not os.path.exists(candidate):
            return candidate
        index += 1


def ensure_within_dir(base_dir, name):
    """拼出 base_dir/name 并校验结果仍在 base_dir 内，越界则抛 ValueError。"""
    base = os.path.abspath(base_dir)
    target = os.path.abspath(os.path.join(base, name))
    try:
        common = os.path.commonpath([base, target])
    except ValueError:
        raise ValueError(f"路径越界: {name}")
    if os.path.normcase(common) != os.path.normcase(base):
        raise ValueError(f"路径越界: {name}")
    if os.path.normcase(target) == os.path.normcase(base):
        raise ValueError(f"目标路径退化为目录: {name}")
    return target


def safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def part_path_for(path):
    """生成同目录下的临时文件名，避免多实例互相覆盖。"""
    return f"{path}.{os.getpid()}.part"


def sha256_file(file_path, should_stop=None, on_progress=None,
                block_size=config.IO_BLOCK_SIZE, interval=0.2):
    """计算文件 SHA-256。大块读取 + 时间节流回调，避免刷爆调用方。

    返回 None 表示中途被 should_stop() 取消。
    """
    file_size = os.path.getsize(file_path)
    sha256_hash = hashlib.sha256()
    processed = 0
    last_push = 0.0
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(block_size)
            if not chunk:
                break
            if should_stop and should_stop():
                return None
            sha256_hash.update(chunk)
            processed += len(chunk)
            if on_progress:
                now = time.monotonic()
                if processed >= file_size or now - last_push >= interval:
                    last_push = now
                    on_progress(processed, file_size)
    return sha256_hash.hexdigest()


def setup_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def format_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.2f} GB"


def calculate_sha256(file_path, cancel_check=None, progress_callback=None,
                     block_size=1024 * 1024, interval=0.2):
    """兼容入口（历史 API）：转发到 sha256_file。"""
    return sha256_file(file_path, should_stop=cancel_check,
                       on_progress=progress_callback,
                       block_size=block_size, interval=interval)


def resolve_icon_path(icon_filename):
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', '')
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, 'icon', icon_filename)


def load_icon(filename, size=None, master=None):
    """加载图标；master 用于把图片绑定到指定解释器（多窗口/宿主场景更稳）。"""
    icon_path = resolve_icon_path(filename)
    if not os.path.exists(icon_path):
        return None
    img = tk.PhotoImage(master=master, file=icon_path)
    if size is not None:
        w, h = img.width(), img.height()
        if w > size or h > size:
            factor = max(1, max(w, h) // size)
            img = img.subsample(factor, factor)
    return img


def apply_window_icon(root, icon_filename):
    icon_path = resolve_icon_path(icon_filename)
    if not os.path.exists(icon_path):
        return None
    icon = tk.PhotoImage(master=root, file=icon_path)
    root.iconphoto(True, icon)
    return icon


def browse_directory(entry_widget):
    dir_path = filedialog.askdirectory()
    if dir_path:
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, dir_path)
        return dir_path
    return None


def browse_file_dialog(entry_widget, filetypes=None):
    if filetypes:
        file_path = filedialog.askopenfilename(filetypes=filetypes)
    else:
        file_path = filedialog.askopenfilename()
    if file_path:
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, file_path)
        return file_path
    return None


def set_app_user_model_id(app_id):
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def delete_selected(entry_widget):
    try:
        if entry_widget.selection_present():
            entry_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
    except tk.TclError:
        pass


def setup_context_menu(entry_widget, on_change=None):
    menu = tk.Menu(entry_widget, tearoff=0)

    def _after_action():
        if on_change:
            entry_widget.after_idle(on_change)

    def _copy_to_clipboard(saved_selection=None):
        try:
            entry_widget.clipboard_clear()
            if saved_selection:
                entry_widget.clipboard_append(saved_selection)
            else:
                entry_widget.event_generate('<<Copy>>')
        except tk.TclError:
            pass

    menu.add_command(label="剪切", command=lambda: (entry_widget.event_generate('<<Cut>>'), _after_action()))
    menu.add_command(label="复制", command=lambda: entry_widget.event_generate('<<Copy>>'))
    menu.add_command(label="粘贴", command=lambda: (entry_widget.event_generate('<<Paste>>'), _after_action()))
    menu.add_separator()
    menu.add_command(label="删除", command=lambda: (delete_selected(entry_widget), _after_action()))
    menu.add_separator()
    menu.add_command(label="全选", command=lambda: entry_widget.select_range(0, tk.END))

    def _show_menu(event):
        if str(entry_widget['state']) == 'disabled':
            return
        if entry_widget.focus_get() != entry_widget:
            entry_widget.focus_set()
            entry_widget.select_range(0, tk.END)
        has_selection = False
        saved_selection = None
        try:
            has_selection = entry_widget.selection_present()
            if has_selection:
                saved_selection = entry_widget.selection_get()
        except tk.TclError:
            pass
        state = tk.NORMAL if has_selection else tk.DISABLED
        menu.entryconfig(0, state=state)
        menu.entryconfig(1, state=state, command=lambda: _copy_to_clipboard(saved_selection))
        menu.entryconfig(4, state=state)

        paste_state = tk.DISABLED
        try:
            if entry_widget.clipboard_get():
                paste_state = tk.NORMAL
        except (tk.TclError, Exception):
            pass
        menu.entryconfig(2, state=paste_state)

        select_all_state = tk.NORMAL if entry_widget.get() else tk.DISABLED
        menu.entryconfig(6, state=select_all_state)

        menu.tk_popup(event.x_root, event.y_root)

    entry_widget.bind('<Button-3>', _show_menu)


class Throttle:
    """时间戳节流器：间隔内只放行一次，用于进度回调降频。"""

    __slots__ = ('_interval', '_last')

    def __init__(self, interval=0.15):
        self._interval = max(0.0, float(interval))
        self._last = 0.0

    def ready(self, force=False):
        now = time.monotonic()
        if force or now - self._last >= self._interval:
            self._last = now
            return True
        return False


class UiDispatcher:
    """工作线程 → Tk 主线程的调用桥。

    Tk/Tcl 不是线程安全的：任何控件操作都必须回到主线程执行。
    工作线程只往队列里放任务，由主线程定时泵出执行。

    - call()        离散事件（状态文字、错误、完成），按顺序全部执行
    - call_latest() 高频刷新（进度条、速度），同 key 只保留最后一次
    """

    def __init__(self, widget, interval=40):
        self._widget = widget
        self._interval = max(10, int(interval))
        self._queue = queue.Queue()
        self._latest = {}
        self._lock = threading.Lock()
        self._after_id = None
        self._stopped = False
        self._schedule()

    def _schedule(self):
        try:
            self._after_id = self._widget.after(self._interval, self._pump)
        except (tk.TclError, RuntimeError):
            self._stopped = True

    def _pump(self):
        self._after_id = None
        if self._stopped:
            return
        with self._lock:
            latest = self._latest
            self._latest = {}
        for item in latest.values():
            self._invoke(item)
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            self._invoke(item)
        if not self._stopped:
            self._schedule()

    @staticmethod
    def _invoke(item):
        func, args, kwargs = item
        try:
            func(*args, **kwargs)
        except (tk.TclError, RuntimeError):
            pass
        except Exception:
            pass

    def call(self, func, *args, **kwargs):
        if self._stopped:
            return
        self._queue.put((func, args, kwargs))

    def call_latest(self, key, func, *args, **kwargs):
        if self._stopped:
            return
        with self._lock:
            self._latest[key] = (func, args, kwargs)

    def stop(self):
        self._stopped = True
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


def scaled_geometry(window, width, height):
    """按 DPI 缩放系数设置窗口尺寸与最小尺寸。

    宿主模式（子模块拿到的是 Frame）下 geometry/minsize 会被宿主吸收，不影响布局。
    """
    try:
        scale = float(window.tk.call('tk', 'scaling'))
    except Exception:
        scale = 1.0
    if scale > 1.5:
        width = int(width * scale / 1.25)
        height = int(height * scale / 1.25)
    window.geometry(f"{width}x{height}")
    window.minsize(width, height)
    return width, height


def show_about(window, title=None):
    title = title or config.APP_NAME
    messagebox.showinfo(
        f"关于 {title}",
        f"{title}\n版本 {config.APP_VERSION}\n\n"
        f"大文件分片传输工具\n"
        f"许可证: {config.APP_LICENSE}\n"
        f"{config.APP_HOMEPAGE}",
        parent=window,
    )


def install_about_menu(window, title=None):
    """给顶层窗口挂一个一级"关于"菜单项；宿主 Frame 上自动跳过。"""
    if not isinstance(window, (tk.Tk, tk.Toplevel)):
        return None
    if getattr(window, '_about_menu_installed', False):
        return None
    menubar = tk.Menu(window)
    menubar.add_command(label="关于", command=lambda: show_about(window, title))
    window.config(menu=menubar)
    window._about_menu_installed = True
    return menubar


def run_gui_app(app_factory):
    setup_dpi_awareness()

    root = tk.Tk()

    try:
        from tkinter import font
        default_font = font.nametofont("TkDefaultFont")
        default_font.configure(size=config.FONT_SIZE)
    except Exception:
        pass

    app_factory(root)

    root.mainloop()
