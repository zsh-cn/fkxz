import ctypes
import hashlib
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import font as tkfont

import config


RESERVED_FILENAMES = {'CON', 'PRN', 'AUX', 'NUL'}
RESERVED_FILENAMES.update('COM%d' % i for i in range(1, 10))
RESERVED_FILENAMES.update('LPT%d' % i for i in range(1, 10))

INVALID_FILENAME_CHARS = '<>:"/\\|?*'

MAX_FILENAME_LENGTH = config.MAX_FILENAME_LENGTH


def safe_filename(name, default="未命名", max_length=MAX_FILENAME_LENGTH):
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
    return f"{path}.{os.getpid()}.part"


_REPLACE_RETRY_WINERRORS = (5, 32, 33)


def replace_with_retry(src, dst, attempts=6, delay=0.1):
    for attempt in range(1, attempts + 1):
        try:
            os.replace(src, dst)
            return True
        except OSError as exc:
            winerror = getattr(exc, 'winerror', None)
            if winerror not in _REPLACE_RETRY_WINERRORS or attempt >= attempts:
                raise
            time.sleep(delay * attempt)
    return False


def sha256_file(file_path, should_stop=None, on_progress=None,
                block_size=config.IO_BLOCK_SIZE, interval=0.2):
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


SPEED_PLACEHOLDER = "--"


def speed_text(speed):
    if speed is None:
        return SPEED_PLACEHOLDER
    return f"{format_size(int(speed))}/s"


def measured_speed(processed, started, now=None, min_interval=None):
    if started is None:
        return None
    if now is None:
        now = time.monotonic()
    if min_interval is None:
        min_interval = config.SPEED_MIN_INTERVAL
    elapsed = now - started
    if elapsed < min_interval:
        return None
    return max(0.0, processed / elapsed)


def calculate_sha256(file_path, cancel_check=None, progress_callback=None,
                     block_size=1024 * 1024, interval=0.2):
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


_GWL_EXSTYLE = -20
_GWLP_HWNDPARENT = -8
_WS_EX_TOPMOST = 0x00000008
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_NOACTIVATE = 0x08000000
_GA_ROOT = 2
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020
_HWND_TOP = 0


def _user32():
    if sys.platform != 'win32':
        return None
    try:
        return ctypes.windll.user32
    except (AttributeError, OSError):
        return None


def _long_procs(user32):
    get_long = user32.GetWindowLongW
    set_long = getattr(user32, 'SetWindowLongPtrW', None) or user32.SetWindowLongW
    get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_long.restype = ctypes.c_long
    set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    set_long.restype = ctypes.c_void_p
    return get_long, set_long


def widget_hwnd(widget):
    try:
        return int(widget.winfo_id())
    except (tk.TclError, AttributeError, TypeError, ValueError):
        return 0


def toplevel_hwnd(widget):
    hwnd = widget_hwnd(widget)
    if not hwnd:
        return 0
    user32 = _user32()
    if user32 is None:
        return hwnd
    try:
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        root = user32.GetAncestor(hwnd, _GA_ROOT)
    except Exception:
        return hwnd
    return int(root) if root else hwnd


def foreground_pid():
    user32 = _user32()
    if user32 is None:
        return None
    try:
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p,
                                                    ctypes.POINTER(ctypes.c_uint)]
        user32.GetWindowThreadProcessId.restype = ctypes.c_uint
        pid = ctypes.c_uint(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)
    except Exception:
        return None


def app_in_foreground():
    pid = foreground_pid()
    if pid is None:
        return True
    return pid == os.getpid()


def attach_popup_to_owner(window, owner):
    user32 = _user32()
    if user32 is None:
        return False
    try:
        window.update_idletasks()
    except tk.TclError:
        return False
    inner_hwnd = widget_hwnd(window)
    wrapper_hwnd = toplevel_hwnd(window)
    owner_hwnd = toplevel_hwnd(owner)
    if not wrapper_hwnd or not owner_hwnd or wrapper_hwnd == owner_hwnd:
        return False
    try:
        get_long, set_long = _long_procs(user32)
    except (AttributeError, OSError, TypeError):
        return False

    for target in {inner_hwnd, wrapper_hwnd}:
        if not target:
            continue
        try:
            style = int(get_long(target, _GWL_EXSTYLE) or 0)
            style = ((style | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE)
                     & ~_WS_EX_TOPMOST) & 0xFFFFFFFF
            set_long(target, _GWL_EXSTYLE, style)
        except Exception:
            pass

    try:
        set_long(wrapper_hwnd, _GWLP_HWNDPARENT, owner_hwnd)
    except Exception:
        return False

    try:
        user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                        ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        user32.SetWindowPos(wrapper_hwnd, _HWND_TOP, 0, 0, 0, 0,
                            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE
                            | _SWP_FRAMECHANGED)
    except Exception:
        pass
    return True


_active_popup = None


def close_open_popup(keep=None):
    popup = _active_popup
    if popup is not None and popup is not keep:
        popup._hide()


class PopupMenu:

    _BG = '#ffffff'
    _FG = config.TEXT_NORMAL
    _HOVER_BG = '#e9f0ff'
    _HOVER_FG = config.TEXT_PRIMARY
    _DISABLED_FG = '#b7b9bd'
    _SEP_BG = '#e8eaed'
    _BORDER = config.BORDER_COLOR
    _FONT = (config.FONT_FAMILY, config.FONT_SIZE)
    _MIN_TEXT_WIDTH = 76
    _WATCH_INTERVAL = 100

    def __init__(self, master):
        self._master = master
        self._owner = None
        self._items = []
        self._top = None
        self._ready = False
        self._font_obj = None
        self._focus_binds = []
        self._owner_binds = []
        self._focus_widget = None
        self._owner_geom = None
        self._watch_id = None

    def _font(self, master):
        if self._font_obj is None:
            self._font_obj = tkfont.Font(root=master, font=self._FONT)
        return self._font_obj

    def add_command(self, label='', command=None):
        self._items.append({'type': 'command', 'label': label,
                            'command': command, 'state': tk.NORMAL})
        return len(self._items) - 1

    def add_separator(self):
        self._items.append({'type': 'separator'})
        return len(self._items) - 1

    def entryconfig(self, index, **kwargs):
        item = self._items[index]
        for key in ('label', 'command', 'state'):
            if key in kwargs:
                item[key] = kwargs[key]

    def tk_popup(self, x_root, y_root):
        global _active_popup

        self._hide()
        close_open_popup(keep=self)

        owner = self._owner_window()
        prev_focus = self._current_focus()

        top = tk.Toplevel(owner)
        top.withdraw()
        top.overrideredirect(True)

        border = tk.Frame(top, bg=self._BORDER)
        border.pack()
        inner = tk.Frame(border, bg=self._BG)
        inner.pack(padx=1, pady=1)

        font = self._font(top)
        pad_x = max(10, font.measure('\u3000'))
        pad_y = max(4, font.metrics('linespace') // 4)

        labels = []
        row = 0
        for item in self._items:
            if item['type'] == 'separator':
                tk.Frame(inner, bg=self._SEP_BG, height=1).grid(
                    row=row, column=0, sticky=tk.EW,
                    padx=max(4, pad_x // 2), pady=max(3, pad_y // 2))
            else:
                disabled = item.get('state') != tk.NORMAL
                label = tk.Label(
                    inner, text=item.get('label') or '', font=self._FONT,
                    anchor=tk.W, bg=self._BG,
                    fg=self._DISABLED_FG if disabled else self._FG,
                    padx=pad_x, pady=pad_y,
                    cursor='arrow' if disabled else 'hand2',
                )
                label.grid(row=row, column=0, sticky=tk.EW)
                labels.append(label)
                if not disabled:
                    label.bind('<Enter>', lambda e, w=label: w.configure(
                        bg=self._HOVER_BG, fg=self._HOVER_FG))
                    label.bind('<Leave>', lambda e, w=label: w.configure(
                        bg=self._BG, fg=self._FG))
                label.bind('<Button-1>', lambda e, it=item: self._invoke(it))
            row += 1

        top.update_idletasks()
        content_width = max([self._MIN_TEXT_WIDTH] + [w.winfo_reqwidth() for w in labels])
        inner.columnconfigure(0, minsize=content_width)
        top.update_idletasks()

        width = top.winfo_reqwidth()
        height = top.winfo_reqheight()

        sw = top.winfo_screenwidth()
        sh = top.winfo_screenheight()
        x = max(0, min(x_root, sw - width - 4))
        y = max(0, min(y_root, sh - height - 4))
        top.geometry(f'+{x}+{y}')

        top.bind('<Button-3>', lambda e: 'break')
        top.bind('<Escape>', lambda e: self._hide())

        self._top = top
        self._owner = owner
        _active_popup = self

        top.deiconify()
        top.lift()
        attach_popup_to_owner(top, owner)
        self._bind_owner(owner)
        self._hold_focus(prev_focus, top)
        self._ready = False
        top.after(120, self._mark_ready)
        self._watch_id = top.after(self._WATCH_INTERVAL, self._watch)

    def _owner_window(self):
        try:
            return self._master.winfo_toplevel()
        except tk.TclError:
            return self._master

    def _owner_geometry(self, owner):
        try:
            return (owner.winfo_rootx(), owner.winfo_rooty(),
                    owner.winfo_width(), owner.winfo_height())
        except tk.TclError:
            return None

    def _bind_owner(self, owner):
        self._owner_geom = self._owner_geometry(owner)
        handlers = (
            ('<Configure>', self._on_owner_configure),
            ('<Unmap>', self._on_owner_unmap),
            ('<Button-1>', self._on_owner_press),
            ('<Button-2>', self._on_owner_press),
            ('<MouseWheel>', self._on_owner_press),
            ('<Destroy>', self._on_owner_destroy),
        )
        for seq, handler in handlers:
            try:
                funcid = owner.bind(seq, handler, add='+')
            except tk.TclError:
                continue
            if funcid:
                self._owner_binds.append((owner, seq, funcid))

        for seq, handler in (('<Unmap>', self._on_master_unmap),
                             ('<Destroy>', self._on_master_destroy)):
            try:
                funcid = self._master.bind(seq, handler, add='+')
            except tk.TclError:
                continue
            if funcid:
                self._owner_binds.append((self._master, seq, funcid))

    def _unbind_owner(self):
        binds, self._owner_binds = self._owner_binds, []
        self._owner_geom = None
        for widget, seq, funcid in binds:
            try:
                widget.unbind(seq, funcid)
            except tk.TclError:
                pass

    def _on_owner_configure(self, event):
        if self._owner is None or event.widget is not self._owner:
            return
        geom = self._owner_geometry(self._owner)
        if self._owner_geom is None:
            self._owner_geom = geom
            return
        if geom != self._owner_geom:
            self._hide()

    def _on_owner_unmap(self, event):
        if self._owner is None or event.widget is not self._owner:
            return
        self._hide()

    def _on_owner_press(self, event):
        self._hide()

    def _on_master_unmap(self, event):
        if event.widget is not self._master:
            return
        self._hide()

    def _on_master_destroy(self, event):
        if event.widget is not self._master:
            return
        self._hide()

    def _on_owner_destroy(self, event):
        if self._owner is None or event.widget is not self._owner:
            return
        self._owner = None
        self._hide()

    def _master_viewable(self):
        try:
            return bool(self._master.winfo_exists()) and bool(self._master.winfo_ismapped())
        except tk.TclError:
            return False

    def _watch(self):
        self._watch_id = None
        top = self._top
        if top is None:
            return
        if (not self._owner_alive() or not self._master_viewable()
                or not app_in_foreground()):
            self._hide()
            return
        geom = self._owner_geometry(self._owner)
        if self._owner_geom is not None and geom is not None and geom != self._owner_geom:
            self._hide()
            return
        try:
            self._watch_id = top.after(self._WATCH_INTERVAL, self._watch)
        except tk.TclError:
            self._watch_id = None

    def _owner_alive(self):
        owner = self._owner
        if owner is None:
            return False
        try:
            return bool(owner.winfo_exists())
        except tk.TclError:
            return False

    def _current_focus(self):
        try:
            widget = self._master.focus_get()
        except (tk.TclError, KeyError):
            return None
        try:
            if widget is not None and widget.winfo_exists():
                return widget
        except tk.TclError:
            return None
        return None

    def _hold_focus(self, widget, top):
        self._focus_binds = []
        if widget is not None:
            try:
                widget.focus_force()
            except tk.TclError:
                widget = None
        self._focus_widget = widget
        if widget is None:
            try:
                top.focus_force()
            except tk.TclError:
                pass
            return

        for seq, handler in (('<Escape>', self._on_key_escape),
                             ('<Key>', self._on_key_swallow),
                             ('<FocusOut>', self._on_focus_out)):
            try:
                funcid = widget.bind(seq, handler, add='+')
            except tk.TclError:
                continue
            if funcid:
                self._focus_binds.append((widget, seq, funcid))

    def _release_focus(self):
        binds, self._focus_binds = self._focus_binds, []
        for widget, seq, funcid in binds:
            try:
                widget.unbind(seq, funcid)
            except tk.TclError:
                pass

    def _on_key_escape(self, event):
        self._hide()
        return 'break'

    def _on_key_swallow(self, event):
        return 'break'

    def _mark_ready(self):
        if self._top is not None:
            self._ready = True

    def _on_focus_out(self, event):
        if not self._ready:
            return
        if self._focus_is_in_popup():
            return
        self._hide()

    def _focus_is_in_popup(self):
        top = self._top
        if top is None:
            return False
        try:
            current = self._master.focus_get()
        except (tk.TclError, KeyError):
            return False
        if current is None:
            return False
        try:
            name = str(current)
            top_name = str(top)
        except tk.TclError:
            return False
        return name == top_name or name.startswith(top_name + '.')

    def _invoke(self, item):
        if item.get('state') != tk.NORMAL:
            return
        command = item.get('command')
        self._hide()
        if callable(command):
            command()

    def _hide(self):
        global _active_popup

        top = self._top
        self._top = None
        if _active_popup is self:
            _active_popup = None
        if top is None:
            self._unbind_owner()
            return

        watch_id, self._watch_id = self._watch_id, None
        if watch_id is not None:
            try:
                top.after_cancel(watch_id)
            except (tk.TclError, ValueError):
                pass

        self._ready = False
        widget = self._focus_widget
        self._focus_widget = None
        self._release_focus()
        self._unbind_owner()
        try:
            top.destroy()
        except tk.TclError:
            pass
        if widget is not None:
            try:
                widget.focus_set()
            except tk.TclError:
                pass


def setup_context_menu(entry_widget, on_change=None):
    menu = PopupMenu(entry_widget)

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


def flush_ui(widget):
    try:
        widget.update_idletasks()
    except (tk.TclError, RuntimeError):
        pass


def scaled_geometry(window, width, height):
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
