import ctypes
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
import uuid
import webbrowser
from collections import deque
from tkinter import filedialog, messagebox
from tkinter import font as tkfont
from tkinter import ttk

import config
import core


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


_SIZE_UNITS = ('B', 'KB', 'MB', 'GB', 'TB')


def format_size(size):
    value = float(max(0, size))
    unit = 0
    while unit < len(_SIZE_UNITS) - 1 and round(value, 2) >= 1024:
        value /= 1024.0
        unit += 1
    if unit == 0:
        return f"{int(round(value))} B"
    return f"{value:.2f} {_SIZE_UNITS[unit]}"


SPEED_PLACEHOLDER = "--"


def speed_text(speed):
    if speed is None:
        return SPEED_PLACEHOLDER
    return f"{format_size(int(round(speed)))}/s"


def progress_percent(done_bytes, total_bytes, finished=False):
    if finished:
        return 100.0
    if total_bytes <= 0:
        return 0.0
    percent = float(done_bytes) * 100.0 / float(total_bytes)
    return max(0.0, min(99.99, percent))


def format_percent(percent):
    try:
        value = float(percent)
    except (TypeError, ValueError):
        value = 0.0
    if value < 0:
        value = 0.0
    elif value > 100:
        value = 100.0
    return f"{value:.2f}"


class SpeedMeter:
    __slots__ = ('_window', '_min_interval', '_samples')

    def __init__(self, window=None, min_interval=None):
        self._window = float(config.SPEED_WINDOW if window is None else window)
        self._min_interval = float(
            config.SPEED_MIN_INTERVAL if min_interval is None else min_interval)
        self._samples = deque()

    def reset(self):
        self._samples.clear()

    def update(self, total_bytes, now=None):
        if now is None:
            now = time.monotonic()
        total_bytes = max(0, int(total_bytes))
        samples = self._samples
        if samples and samples[-1][1] == total_bytes and now - samples[-1][0] < 0.05:
            return
        samples.append((now, total_bytes))
        cutoff = now - self._window
        while len(samples) > 2 and samples[1][0] <= cutoff:
            samples.popleft()

    def speed(self):
        samples = self._samples
        if len(samples) < 2:
            return None
        start_time, start_bytes = samples[0]
        end_time, end_bytes = samples[-1]
        span = end_time - start_time
        if span < self._min_interval:
            return None
        return max(0.0, (end_bytes - start_bytes) / span)


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
        if callable(getattr(entry_widget, 'selection_present', None)) \
                and entry_widget.selection_present():
            entry_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
    except (tk.TclError, AttributeError):
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


_TASKBAR_NOPROGRESS = 0x0
_TASKBAR_INDETERMINATE = 0x1
_TASKBAR_NORMAL = 0x2
_TASKBAR_ERROR = 0x4
_TASKBAR_PAUSED = 0x8


class _GUID(ctypes.Structure):
    _fields_ = [
        ('Data1', ctypes.c_uint32),
        ('Data2', ctypes.c_uint16),
        ('Data3', ctypes.c_uint16),
        ('Data4', ctypes.c_ubyte * 8),
    ]


def _guid_from_text(text):
    value = uuid.UUID(text)
    guid = _GUID()
    guid.Data1 = value.time_low
    guid.Data2 = value.time_mid
    guid.Data3 = value.time_hi_version
    for index, byte in enumerate(value.bytes[8:]):
        guid.Data4[index] = byte
    return guid


class _TaskbarList3:
    _CLSID = "{56FDF344-FD6D-11D0-958A-006097C9A090}"
    _IID = "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}"
    _CLSCTX_INPROC_SERVER = 0x1
    _COINIT_APARTMENTTHREADED = 0x2
    _RPC_E_CHANGED_MODE = -2147417850

    _VTBL_RELEASE = 2
    _VTBL_HR_INIT = 3
    _VTBL_SET_PROGRESS_VALUE = 9
    _VTBL_SET_PROGRESS_STATE = 10
    _VTBL_SET_OVERLAY_ICON = 18

    def __init__(self):
        self._ptr = 0
        self._set_value = None
        self._set_state = None
        self._release = None
        self._com_initialized = False
        self._failed = False

    def open(self):
        if self._ptr:
            return True
        if self._failed:
            return False
        try:
            ole32 = ctypes.windll.ole32
            ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            ole32.CoInitializeEx.restype = ctypes.c_long
            ole32.CoCreateInstance.argtypes = [
                ctypes.POINTER(_GUID), ctypes.c_void_p, ctypes.c_uint,
                ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
            ole32.CoCreateInstance.restype = ctypes.c_long
            ole32.CoUninitialize.argtypes = []
            ole32.CoUninitialize.restype = None
        except (AttributeError, OSError):
            self._failed = True
            return False

        hr = ole32.CoInitializeEx(None, self._COINIT_APARTMENTTHREADED)
        self._com_initialized = hr >= 0
        if hr < 0 and hr != self._RPC_E_CHANGED_MODE:
            self._failed = True
            return False

        clsid = _guid_from_text(self._CLSID)
        iid = _guid_from_text(self._IID)
        ptr = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(clsid), None,
                                    self._CLSCTX_INPROC_SERVER,
                                    ctypes.byref(iid), ctypes.byref(ptr))
        if hr < 0 or not ptr.value:
            self._failed = True
            self._uninitialize()
            return False

        vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
            vtbl[self._VTBL_RELEASE])
        hr_init = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(
            vtbl[self._VTBL_HR_INIT])
        if hr_init(ptr.value) < 0:
            release(ptr.value)
            self._failed = True
            self._uninitialize()
            return False

        self._ptr = int(ptr.value)
        self._release = release
        self._set_value = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_ulonglong, ctypes.c_ulonglong)(vtbl[self._VTBL_SET_PROGRESS_VALUE])
        self._set_state = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)(
                vtbl[self._VTBL_SET_PROGRESS_STATE])
        return True

    def set_value(self, hwnd, completed, total):
        if not self._ptr:
            return False
        try:
            return self._set_value(self._ptr, int(hwnd),
                                   int(completed), int(total)) >= 0
        except Exception:
            return False

    def set_state(self, hwnd, state):
        if not self._ptr:
            return False
        try:
            return self._set_state(self._ptr, int(hwnd), int(state)) >= 0
        except Exception:
            return False

    def close(self):
        if self._ptr and self._release is not None:
            try:
                self._release(self._ptr)
            except Exception:
                pass
        self._ptr = 0
        self._set_value = None
        self._set_state = None
        self._release = None
        self._uninitialize()

    def _uninitialize(self):
        if not self._com_initialized:
            return
        self._com_initialized = False
        try:
            ctypes.windll.ole32.CoUninitialize()
        except Exception:
            pass


class _FLASHWINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.c_uint),
        ('hwnd', ctypes.c_void_p),
        ('dwFlags', ctypes.c_uint),
        ('uCount', ctypes.c_uint),
        ('dwTimeout', ctypes.c_uint),
    ]


def flash_taskbar(widget, count=4):
    if sys.platform != 'win32' or app_in_foreground():
        return False
    user32 = _user32()
    hwnd = toplevel_hwnd(widget)
    if user32 is None or not hwnd:
        return False
    try:
        info = _FLASHWINFO()
        info.cbSize = ctypes.sizeof(_FLASHWINFO)
        info.hwnd = hwnd
        info.dwFlags = 0x3
        info.uCount = max(1, int(count))
        info.dwTimeout = 0
        user32.FlashWindowEx.argtypes = [ctypes.POINTER(_FLASHWINFO)]
        user32.FlashWindowEx.restype = ctypes.c_bool
        user32.FlashWindowEx(ctypes.byref(info))
        return True
    except Exception:
        return False


class TaskbarProgress:
    SUCCESS_HOLD_MS = 2500
    ERROR_HOLD_MS = 6000

    def __init__(self, widget):
        self._widget = widget
        self._hwnd = 0
        self._api = _TaskbarList3() if sys.platform == 'win32' else None
        self._state = _TASKBAR_NOPROGRESS
        self._unit = -1
        self._timer = None

    @property
    def available(self):
        return self._api is not None

    def _window(self):
        if not self._hwnd:
            self._hwnd = toplevel_hwnd(self._widget)
        return self._hwnd

    def _ready(self):
        api = self._api
        if api is None:
            return 0
        hwnd = self._window()
        if not hwnd:
            return 0
        if not api.open():
            self._api = None
            return 0
        return hwnd

    def update(self, done, total):
        if self._api is None:
            return
        try:
            done = max(0, int(done))
            total = max(1, int(total))
        except (TypeError, ValueError):
            return
        hwnd = self._ready()
        if not hwnd:
            return
        self._cancel_timer()
        unit = min(10000, done * 10000 // total)
        if self._state != _TASKBAR_NORMAL:
            self._api.set_state(hwnd, _TASKBAR_NORMAL)
            self._state = _TASKBAR_NORMAL
            self._unit = -1
        if unit != self._unit:
            self._api.set_value(hwnd, done, total)
            self._unit = unit

    def indeterminate(self):
        self._set_state(_TASKBAR_INDETERMINATE)

    def pause(self):
        if self._state in (_TASKBAR_NORMAL, _TASKBAR_INDETERMINATE):
            self._set_state(_TASKBAR_PAUSED)

    wait = pause

    def complete(self, flash=True):
        if not self._ready():
            return
        self.update(100, 100)
        self._schedule_clear(self.SUCCESS_HOLD_MS)
        if flash:
            flash_taskbar(self._widget)

    def fail(self, flash=True):
        if not self._ready():
            return
        self._set_state(_TASKBAR_ERROR, reset_after=self.ERROR_HOLD_MS)
        if flash:
            flash_taskbar(self._widget)

    def clear(self):
        self._cancel_timer()
        self._unit = -1
        self._set_state(_TASKBAR_NOPROGRESS)

    def close(self):
        self.clear()
        api, self._api = self._api, None
        if api is not None:
            api.close()

    def _set_state(self, state, reset_after=None):
        hwnd = self._ready()
        if not hwnd:
            return
        self._cancel_timer()
        if state != self._state:
            self._api.set_state(hwnd, state)
            self._state = state
        if reset_after:
            self._schedule_clear(reset_after)

    def _schedule_clear(self, delay):
        try:
            self._timer = self._widget.after(delay, self._on_timer)
        except (tk.TclError, RuntimeError):
            self._timer = None

    def _on_timer(self):
        self._timer = None
        self.clear()

    def _cancel_timer(self):
        timer, self._timer = self._timer, None
        if timer is not None:
            try:
                self._widget.after_cancel(timer)
            except (tk.TclError, ValueError, RuntimeError):
                pass


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
                             ('<Key>', self._on_key_swallow)):
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
        if self._top is None:
            return None
        self._hide()
        return 'break'

    def _on_key_swallow(self, event):
        if self._top is None:
            return None
        return 'break'

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
    can_selection = callable(getattr(entry_widget, 'selection_present', None))
    can_select_range = callable(getattr(entry_widget, 'select_range', None))

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

    def _generate(sequence, notify=True):
        def _run():
            try:
                entry_widget.event_generate(sequence)
            except tk.TclError:
                return
            if notify:
                _after_action()
        return _run

    def _select_all():
        if can_select_range:
            try:
                entry_widget.select_range(0, tk.END)
            except tk.TclError:
                pass

    index = {
        'cut': menu.add_command(label="剪切", command=_generate('<<Cut>>')),
        'copy': menu.add_command(label="复制", command=_generate('<<Copy>>', notify=False)),
        'paste': menu.add_command(label="粘贴", command=_generate('<<Paste>>')),
    }
    menu.add_separator()
    index['delete'] = menu.add_command(
        label="删除", command=lambda: (delete_selected(entry_widget), _after_action()))
    menu.add_separator()
    index['select_all'] = menu.add_command(label="全选", command=_select_all)

    def _show_menu(event):
        try:
            if str(entry_widget['state']) == 'disabled':
                return
        except tk.TclError:
            return
        if entry_widget.focus_get() != entry_widget:
            entry_widget.focus_set()
            _select_all()

        has_selection = False
        saved_selection = None
        if can_selection:
            try:
                has_selection = bool(entry_widget.selection_present())
                if has_selection:
                    saved_selection = entry_widget.selection_get()
            except tk.TclError:
                has_selection = False

        state = tk.NORMAL if has_selection else tk.DISABLED
        menu.entryconfig(index['cut'], state=state)
        menu.entryconfig(index['copy'], state=state,
                         command=lambda: _copy_to_clipboard(saved_selection))
        menu.entryconfig(index['delete'], state=state)

        paste_state = tk.DISABLED
        try:
            if entry_widget.clipboard_get():
                paste_state = tk.NORMAL
        except Exception:
            paste_state = tk.DISABLED
        menu.entryconfig(index['paste'], state=paste_state)

        try:
            has_text = bool(entry_widget.get())
        except (tk.TclError, AttributeError):
            has_text = False
        menu.entryconfig(index['select_all'],
                         state=tk.NORMAL if (has_text and can_select_range) else tk.DISABLED)

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
    def __init__(self, widget, interval=None, idle_interval=None):
        self._widget = widget
        self._interval = max(10, int(config.UI_PUMP_INTERVAL if interval is None else interval))
        self._idle_interval = max(
            self._interval, int(config.UI_IDLE_PUMP_INTERVAL if idle_interval is None else idle_interval))
        self._queue = queue.Queue()
        self._latest = {}
        self._lock = threading.Lock()
        self._after_id = None
        self._stopped = False
        self._schedule(idle=True)

    def _schedule(self, idle=True):
        delay = self._idle_interval if idle else self._interval
        try:
            self._after_id = self._widget.after(delay, self._pump)
        except (tk.TclError, RuntimeError):
            self._stopped = True

    def _pump(self):
        self._after_id = None
        if self._stopped:
            return
        with self._lock:
            latest = self._latest
            self._latest = {}
        busy = bool(latest)
        for item in latest.values():
            self._invoke(item)
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            busy = True
            self._invoke(item)
        if not self._stopped:
            self._schedule(idle=not busy)

    @staticmethod
    def _invoke(item):
        func, args, kwargs = item
        try:
            func(*args, **kwargs)
        except (tk.TclError, RuntimeError):
            pass
        except Exception:
            if sys.stderr is not None:
                traceback.print_exc()

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


def open_external_url(url):
    if not url:
        return False
    try:
        if webbrowser.open(url, new=2):
            return True
    except Exception:
        pass
    if sys.platform == 'win32':
        try:
            os.startfile(url)
            return True
        except Exception:
            pass
    return False


def _dialog_font(size=None, bold=False, underline=False):
    try:
        font = tkfont.nametofont("TkDefaultFont").copy()
    except Exception:
        return (config.FONT_FAMILY, size or config.FONT_SIZE)
    if size:
        font.configure(size=size)
    if bold:
        font.configure(weight="bold")
    if underline:
        font.configure(underline=True)
    return font


def center_dialog(dialog, master, min_width=0):
    dialog.update_idletasks()
    try:
        width = max(dialog.winfo_width(), int(min_width))
        height = dialog.winfo_height()
        parent_x = master.winfo_rootx()
        parent_y = master.winfo_rooty()
        parent_w = master.winfo_width()
        parent_h = master.winfo_height()
    except tk.TclError:
        return
    x = parent_x + max(0, (parent_w - width) // 2)
    y = parent_y + max(0, (parent_h - height) // 3)
    dialog.geometry(f"{width}x{height}+{x}+{y}")


class AboutDialog(tk.Toplevel):

    def __init__(self, master, title=None):
        super().__init__(master)
        self.title(f"关于 {title or config.APP_NAME}")
        self.resizable(False, False)
        self.transient(master)

        self._link_fonts = []
        self._build_widgets(title or config.APP_NAME)
        self._center_on(master)

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda event: self.destroy())
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _build_widgets(self, title):
        outer = ttk.Frame(self, padding="18")
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X)
        tk.Label(header, text=title, font=_dialog_font(size=15, bold=True),
                 foreground=config.TEXT_PRIMARY).pack(anchor=tk.W)
        tk.Label(header, text=f"版本 {config.APP_VERSION}",
                 foreground=config.TEXT_SECONDARY).pack(anchor=tk.W, pady=(4, 0))

        info = ttk.LabelFrame(outer, text="应用信息", padding="12")
        info.pack(fill=tk.X, pady=(14, 0))
        info.columnconfigure(1, minsize=90)
        for row, (label, value) in enumerate((
                ("用途", "大文件分片传输工具"),
                ("许可证", config.APP_LICENSE),
        )):
            ttk.Label(info, text=f"{label}:").grid(
                row=row, column=0, sticky=tk.E, pady=4)
            ttk.Label(info, text=value).grid(
                row=row, column=1, sticky=tk.W, padx=(10, 0), pady=4)

        links = ttk.LabelFrame(outer, text="相关链接", padding="12")
        links.pack(fill=tk.X, pady=(12, 0))
        links.columnconfigure(1, minsize=90)
        link_specs = (
            ("官网", config.APP_HOMEPAGE, config.APP_HOMEPAGE),
            ("GitHub", config.APP_REPO_URL, config.APP_REPO_URL),
        )
        for row, (label, text, url) in enumerate(link_specs):
            ttk.Label(links, text=f"{label}:").grid(
                row=row, column=0, sticky=tk.E, pady=4)
            self._add_link(links, text, url).grid(
                row=row, column=1, sticky=tk.W, padx=(10, 0), pady=4)

        ttk.Label(outer, text="点击链接可在浏览器中打开。",
                  foreground=config.TEXT_SECONDARY).pack(anchor=tk.W, pady=(12, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill=tk.X, pady=(14, 0))
        ttk.Button(buttons, text="关闭", command=self.destroy,
                   width=10).pack(side=tk.RIGHT)

    def _add_link(self, parent, text, url):
        font = _dialog_font(underline=True)
        self._link_fonts.append(font)
        label = tk.Label(parent, text=text, font=font,
                         foreground=config.NAV_ACCENT, cursor="hand2")
        label.bind("<Button-1>", lambda event: open_external_url(url))
        label.bind("<Enter>", lambda event: label.configure(foreground=config.TEXT_PRIMARY))
        label.bind("<Leave>", lambda event: label.configure(foreground=config.NAV_ACCENT))
        return label

    def _center_on(self, master):
        center_dialog(self, master, min_width=420)


def show_about(window, title=None):
    title = title or config.APP_NAME
    existing = getattr(window, '_about_dialog', None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.lift()
                existing.focus_set()
                return existing
        except tk.TclError:
            pass
    dialog = AboutDialog(window, title)
    try:
        window._about_dialog = dialog
    except tk.TclError:
        pass
    return dialog


def install_about_menu(window, title=None, show_network=True):
    if not isinstance(window, (tk.Tk, tk.Toplevel)):
        return None
    if getattr(window, '_about_menu_installed', False):
        return None
    menubar = tk.Menu(window, tearoff=0)
    menubar.add_command(
        label="设置",
        command=lambda: open_settings_dialog(window, show_network=show_network))
    menubar.add_command(label="关于", command=lambda: show_about(window, title))
    window.config(menu=menubar)
    window._about_menu_installed = True
    return menubar


def run_gui_app(app_factory, app_id=None):
    if app_id:
        set_app_user_model_id(app_id)
    setup_dpi_awareness()

    root = tk.Tk()
    apply_default_font()

    app = app_factory(root)
    closer = getattr(app, 'on_close', None)
    if callable(closer):
        root.protocol("WM_DELETE_WINDOW", closer)

    root.mainloop()
    return app


def apply_default_font():
    try:
        from tkinter import font
        default_font = font.nametofont("TkDefaultFont")
        default_font.configure(size=config.FONT_SIZE)
    except Exception:
        pass


def nearest_existing_dir(path):
    current = os.path.abspath(path or '.')
    while True:
        if os.path.isdir(current):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    script = sys.argv[0] if sys.argv else ''
    if script:
        candidate = os.path.abspath(script)
        if os.path.isfile(candidate):
            return os.path.dirname(candidate)
    return os.path.dirname(os.path.abspath(__file__))


def check_free_space(directory, required_bytes, margin=None):
    if required_bytes <= 0:
        return True
    base = nearest_existing_dir(directory)
    if not base:
        return True
    try:
        usage = shutil.disk_usage(base)
    except OSError:
        return True
    margin = config.DISK_SPACE_MARGIN if margin is None else margin
    needed = int(required_bytes) + margin
    if usage.free >= needed:
        return True
    raise OSError(
        f"磁盘空间不足：需要 {format_size(needed)}，可用 {format_size(usage.free)}")


def open_folder(path):
    if not path:
        return False
    target = os.path.normpath(path)
    is_file = os.path.isfile(target)
    folder = os.path.dirname(target) if is_file else target
    if not folder or not os.path.isdir(folder):
        return False
    try:
        if sys.platform == 'win32':
            if is_file:
                subprocess.Popen(['explorer', f'/select,{target}'])
            else:
                os.startfile(folder)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', '-R', target] if is_file else ['open', folder])
        else:
            subprocess.Popen(['xdg-open', folder])
        return True
    except Exception:
        return False


def _hidden_process_kwargs():
    if sys.platform == 'win32':
        return {'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)}
    return {}


def shutdown_system(delay=None, comment="任务已完成，系统即将关机"):
    if delay is None:
        delay = getattr(config, 'SHUTDOWN_DELAY_SECONDS', 60)
    try:
        delay = max(0, int(delay))
    except (TypeError, ValueError):
        delay = 60
    try:
        if sys.platform == 'win32':
            command = ['shutdown', '/s', '/t', str(delay)]
            if comment:
                command.extend(['/c', comment])
            result = subprocess.run(command, timeout=10, **_hidden_process_kwargs())
        elif sys.platform == 'darwin':
            minutes = max(1, (delay + 59) // 60)
            result = subprocess.run(['shutdown', '-h', f'+{minutes}'], timeout=10)
        else:
            minutes = max(1, (delay + 59) // 60)
            result = subprocess.run(['shutdown', '-h', f'+{minutes}'], timeout=10)
        return result.returncode == 0
    except Exception:
        return False


def cancel_shutdown():
    try:
        if sys.platform == 'win32':
            result = subprocess.run(['shutdown', '/a'], timeout=10, **_hidden_process_kwargs())
        else:
            result = subprocess.run(['shutdown', '-c'], timeout=10)
        return result.returncode == 0
    except Exception:
        return False


def center_over(window, owner):
    try:
        window.update_idletasks()
        top = owner.winfo_toplevel()
        x = top.winfo_rootx() + max(0, (top.winfo_width() - window.winfo_width()) // 2)
        y = top.winfo_rooty() + max(0, (top.winfo_height() - window.winfo_height()) // 3)
        window.geometry(f"+{x}+{y}")
    except tk.TclError:
        pass


class ShutdownCountdown:
    def __init__(self, owner, delay=None, message="文件已处理完成，系统将在 {left} 秒后关机。",
                 on_status=None, comment="任务已完成，系统即将关机"):
        self.owner = owner
        default_delay = getattr(config, 'SHUTDOWN_DELAY_SECONDS', 60)
        self.delay = max(0, int(default_delay if delay is None else delay))
        self.message = message
        self.on_status = on_status
        self.comment = comment
        self.window = None
        self._text = None
        self._button = None
        self._after_id = None

    @property
    def active(self):
        return self.window is not None

    def start(self, comment=None):
        if self.window is not None:
            return True
        if not shutdown_system(self.delay, comment or self.comment):
            return False
        self._build()
        return True

    def _build(self):
        from tkinter import ttk

        window = tk.Toplevel(self.owner)
        self.window = window
        window.title("自动关机")
        window.resizable(False, False)

        body = ttk.Frame(window, padding="20")
        body.pack(fill=tk.BOTH, expand=True)

        self._text = tk.StringVar(master=window, value="")
        ttk.Label(body, textvariable=self._text, font=(config.FONT_FAMILY, 11),
                  foreground=config.TEXT_NORMAL).pack(anchor=tk.W)
        ttk.Label(body, text="关闭本窗口或点击「取消关机」可继续使用计算机。",
                  foreground=config.TEXT_SECONDARY).pack(anchor=tk.W, pady=(6, 14))

        self._button = ttk.Button(body, text="取消关机", command=self.cancel)
        self._button.pack(anchor=tk.E)

        window.protocol("WM_DELETE_WINDOW", self.cancel)
        center_over(window, self.owner)
        self._tick(self.delay)

    def _tick(self, left):
        window = self.window
        if window is None:
            return
        if left <= 0:
            self._text.set("系统正在关机...")
            self._button.config(state=tk.DISABLED)
            return
        self._text.set(self.message.format(left=left))
        try:
            self._after_id = window.after(1000, lambda: self._tick(left - 1))
        except tk.TclError:
            pass

    def _teardown(self):
        window = self.window
        self.window = None
        if window is None:
            return
        if self._after_id is not None:
            try:
                window.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        try:
            window.destroy()
        except tk.TclError:
            pass

    def cancel(self):
        if self.window is None:
            return
        cancel_shutdown()
        if self.on_status:
            self.on_status("状态: 已取消自动关机")
        self._teardown()

    def dispose(self):
        if self.window is None:
            return
        cancel_shutdown()
        self._teardown()


def legacy_config_dir():
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    elif sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    else:
        base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, config.CONFIG_DIR_NAME)


def _dir_writable(path):
    probe = os.path.join(path, '.fk_write_test')
    try:
        os.makedirs(path, exist_ok=True)
        with open(probe, 'w', encoding='utf-8') as handle:
            handle.write('')
        return True
    except OSError:
        return False
    finally:
        try:
            os.remove(probe)
        except OSError:
            pass


_CONFIG_DIR_CACHE = []


def config_dir():
    if _CONFIG_DIR_CACHE:
        return _CONFIG_DIR_CACHE[0]
    override = os.environ.get('FKXZ_CONFIG_DIR')
    if override:
        resolved = os.path.abspath(override)
    else:
        program_dir = app_dir()
        resolved = program_dir if _dir_writable(program_dir) else legacy_config_dir()
    _CONFIG_DIR_CACHE.append(resolved)
    return resolved


def _migrate_settings_file(target):
    if os.path.exists(target):
        return
    source = os.path.join(legacy_config_dir(), 'settings.json')
    try:
        if not os.path.isfile(source):
            return
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(source, target)
    except OSError:
        pass


LEGACY_OUTPUT_DIR_KEY = 'output_dir'
OUTPUT_DIR_KEYS = ('split_output_dir', 'download_output_dir')

_SETTINGS_CACHE = {}
_SETTINGS_LOCK = threading.Lock()


class Settings:

    def __new__(cls, path=None):
        resolved = os.path.abspath(
            path or os.path.join(config_dir(), 'settings.json'))
        if path is None:
            _migrate_settings_file(resolved)
        with _SETTINGS_LOCK:
            instance = _SETTINGS_CACHE.get(resolved)
            if instance is None:
                instance = super().__new__(cls)
                instance._path = resolved
                instance._lock = threading.RLock()
                instance._data = instance._load()
                _SETTINGS_CACHE[resolved] = instance
            return instance

    def __init__(self, path=None):
        pass

    def _load(self):
        try:
            with open(self._path, 'r', encoding='utf-8') as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def get(self, key, default=None):
        with self._lock:
            value = self._data.get(key, default)
        return default if value is None else value

    def set(self, key, value):
        with self._lock:
            if self._data.get(key) == value:
                return
            self._data[key] = value
            self._save()

    def discard(self, key):
        with self._lock:
            if key not in self._data:
                return
            del self._data[key]
            self._save()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            text = json.dumps(self._data, ensure_ascii=False, indent=2)
        except (OSError, TypeError, ValueError):
            return
        core.write_text_atomic(self._path, f"{text}\n")


def migrate_legacy_settings(settings):
    legacy = settings.get(LEGACY_OUTPUT_DIR_KEY, '')
    if legacy:
        for key in OUTPUT_DIR_KEYS:
            if not settings.get(key, ''):
                settings.set(key, legacy)
    settings.discard(LEGACY_OUTPUT_DIR_KEY)


def output_dir_setting(settings, key):
    saved = settings.get(key, '')
    if not saved:
        legacy = settings.get(LEGACY_OUTPUT_DIR_KEY, '')
        if legacy:
            settings.set(key, legacy)
            settings.discard(LEGACY_OUTPUT_DIR_KEY)
            saved = legacy
    return saved


def apply_network_settings(settings):
    for spec in config.NETWORK_SETTING_SPECS:
        try:
            value = int(settings.get(spec.key))
        except (TypeError, ValueError):
            continue
        setattr(config, spec.const, max(spec.low, min(spec.high, value)))


def available_themes(root=None):
    try:
        return list(ttk.Style(master=root).theme_names())
    except tk.TclError:
        return []


def apply_theme(root, name=None):
    try:
        style = ttk.Style(master=root)
    except tk.TclError:
        return ''
    names = list(style.theme_names())
    if name and name != config.THEME_AUTO and name in names:
        style.theme_use(name)
        return name
    for candidate in config.THEME_PREFERENCE:
        if candidate in names:
            style.theme_use(candidate)
            return candidate
    return style.theme_use()


_GEOMETRY_RE = re.compile(r'^(\d+)x(\d+)([+-]\d+)?([+-]\d+)?$')


def parse_geometry(text):
    match = _GEOMETRY_RE.match((text or '').strip())
    if not match:
        return None
    width = int(match.group(1))
    height = int(match.group(2))
    x = int(match.group(3)) if match.group(3) else None
    y = int(match.group(4)) if match.group(4) else None
    return width, height, x, y


def save_geometry(window, settings, key):
    try:
        geometry = window.winfo_geometry()
    except tk.TclError:
        return
    if geometry:
        settings.set(key, geometry)


def restore_geometry(window, settings, key, fallback_size):
    default_w, default_h = scaled_geometry(window, *fallback_size)
    saved = parse_geometry(settings.get(key, ''))
    if saved is None:
        return False

    width, height, x, y = saved
    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()
    width = max(default_w, min(width, screen_w))
    height = max(default_h, min(height, screen_h))

    if x is None or y is None:
        window.geometry(f"{width}x{height}")
        return True
    if (x > screen_w - 120 or y > screen_h - 80
            or x + width < 120 or y + height < 80):
        window.geometry(f"{width}x{height}")
        return True
    window.geometry(f"{width}x{height}{x:+d}{y:+d}")
    return True


class SettingsDialog(tk.Toplevel):

    def __init__(self, master, settings=None, show_network=True):
        super().__init__(master)
        self.title("设置")
        self.resizable(False, False)
        self.transient(master)
        self.settings = settings if settings is not None else Settings()
        self.show_network = show_network

        self._vars = {}
        self._theme_choices = []
        self._theme_var = tk.StringVar()

        self._build_widgets()
        self._load_values()
        self._center_on(master)

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda event: self.destroy())
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _build_network_frame(self, outer):
        net_frame = ttk.LabelFrame(outer, text="网络与重试", padding="12")
        net_frame.pack(fill=tk.X)
        net_frame.columnconfigure(1, minsize=90)

        for row, spec in enumerate(config.NETWORK_SETTING_SPECS):
            ttk.Label(net_frame, text=f"{spec.label}:").grid(
                row=row, column=0, sticky=tk.E, pady=4)
            var = tk.StringVar()
            self._vars[spec.key] = var
            spin = ttk.Spinbox(net_frame, from_=spec.low, to=spec.high,
                               textvariable=var, width=8)
            spin.grid(row=row, column=1, sticky=tk.W, padx=(10, 10), pady=4)
            setup_context_menu(spin)
            ttk.Label(net_frame,
                      text=f"{spec.hint}（{spec.low}-{spec.high}）",
                      foreground=config.TEXT_SECONDARY).grid(
                row=row, column=2, sticky=tk.W, pady=4)

    def _build_widgets(self):
        outer = ttk.Frame(self, padding="16")
        outer.pack(fill=tk.BOTH, expand=True)

        if self.show_network:
            self._build_network_frame(outer)

        ui_frame = ttk.LabelFrame(outer, text="界面", padding="12")
        ui_frame.pack(fill=tk.X, pady=(12, 0) if self.show_network else 0)
        ui_frame.columnconfigure(1, minsize=90)

        ttk.Label(ui_frame, text="界面主题:").grid(row=0, column=0, sticky=tk.E, pady=4)
        self._theme_choices = [config.THEME_AUTO]
        self._theme_choices.extend(available_themes(self))
        self.theme_combo = ttk.Combobox(
            ui_frame, state="readonly", width=14,
            values=self._theme_choices,
            textvariable=self._theme_var)
        self.theme_combo.grid(row=0, column=1, sticky=tk.W, padx=(10, 10), pady=4)
        ttk.Label(ui_frame, text="保存后立即生效",
                  foreground=config.TEXT_SECONDARY).grid(
            row=0, column=2, sticky=tk.W, pady=4)

        if self.show_network:
            ttk.Label(outer, text="网络参数在每次新建任务时生效，不影响正在进行的任务。",
                      foreground=config.TEXT_SECONDARY).pack(anchor=tk.W, pady=(12, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill=tk.X, pady=(14, 0))
        ttk.Button(buttons, text="恢复默认", command=self._restore_defaults,
                   width=10).pack(side=tk.LEFT)
        ttk.Button(buttons, text="保存", command=self._save,
                   width=10).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="取消", command=self.destroy,
                   width=10).pack(side=tk.RIGHT, padx=(0, 8))

    def _load_values(self):
        if self.show_network:
            for spec in config.NETWORK_SETTING_SPECS:
                try:
                    value = int(self.settings.get(spec.key))
                except (TypeError, ValueError):
                    value = spec.default
                value = max(spec.low, min(spec.high, value))
                self._vars[spec.key].set(str(value))

        saved_theme = self.settings.get('ttk_theme', config.THEME_AUTO)
        self._theme_var.set(self._theme_value(saved_theme))

    def _theme_value(self, value):
        return value if value in self._theme_choices else config.THEME_AUTO

    def _selected_theme(self):
        value = self._theme_var.get()
        return value if value in self._theme_choices else config.THEME_AUTO

    def _restore_defaults(self):
        if self.show_network:
            for spec in config.NETWORK_SETTING_SPECS:
                self._vars[spec.key].set(str(spec.default))
        self._theme_var.set(config.THEME_AUTO)

    def _collect_values(self):
        values = {}
        if not self.show_network:
            return values
        for spec in config.NETWORK_SETTING_SPECS:
            raw = (self._vars[spec.key].get() or "").strip()
            try:
                value = int(raw)
            except (TypeError, ValueError):
                self._warn(f"「{spec.label}」必须是整数。")
                return None
            if not spec.low <= value <= spec.high:
                self._warn(f"「{spec.label}」应在 {spec.low}-{spec.high} 之间。")
                return None
            values[spec.key] = value
        return values

    def _warn(self, message):
        messagebox.showerror("设置无效", message, parent=self)

    def _save(self):
        values = self._collect_values()
        if values is None:
            return

        for key, value in values.items():
            self.settings.set(key, value)
        theme = self._selected_theme()
        self.settings.set('ttk_theme', theme)

        if self.show_network:
            apply_network_settings(self.settings)
        apply_theme(self.master, theme)
        self.destroy()

    def _center_on(self, master):
        center_dialog(self, master)


def open_settings_dialog(window, settings=None, show_network=True):
    existing = getattr(window, '_settings_dialog', None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.lift()
                existing.focus_set()
                return existing
        except tk.TclError:
            pass
    dialog = SettingsDialog(window, settings, show_network=show_network)
    try:
        window._settings_dialog = dialog
    except tk.TclError:
        pass
    return dialog


WM_DROPFILES = 0x0233
_GWLP_WNDPROC = -4
_DROP_POLL_MS = 100
_drop_targets = {}
_drop_keepalive = []
_drop_pending = {}


def _wndproc_pointers(user32):
    get_ptr = getattr(user32, 'GetWindowLongPtrW', None) or user32.GetWindowLongW
    set_ptr = getattr(user32, 'SetWindowLongPtrW', None) or user32.SetWindowLongW
    get_ptr.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_ptr.restype = ctypes.c_void_p
    set_ptr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    set_ptr.restype = ctypes.c_void_p
    return get_ptr, set_ptr


def _dropped_paths(hdrop):
    shell32 = ctypes.windll.shell32
    shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                       ctypes.c_wchar_p, ctypes.c_uint]
    shell32.DragQueryFileW.restype = ctypes.c_uint
    total = int(shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0))
    paths = []
    for index in range(max(0, total)):
        length = int(shell32.DragQueryFileW(hdrop, index, None, 0))
        if length <= 0:
            continue
        buffer = ctypes.create_unicode_buffer(length + 1)
        shell32.DragQueryFileW(hdrop, index, buffer, length + 1)
        if buffer.value:
            paths.append(buffer.value)
    return paths


def _print_exc_safe():
    try:
        traceback.print_exc()
    except Exception:
        pass


def enable_file_drop(window, on_drop):
    if sys.platform != 'win32' or window is None:
        return False
    if getattr(window, '_drop_callback', None) is not None:
        return False
    user32 = _user32()
    if user32 is None:
        return False
    try:
        shell32 = ctypes.windll.shell32
        shell32.DragAcceptFiles.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        shell32.DragAcceptFiles.restype = None
        shell32.DragFinish.argtypes = [ctypes.c_void_p]
        shell32.DragFinish.restype = None

        get_ptr, set_ptr = _wndproc_pointers(user32)
        user32.CallWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_uint, ctypes.c_void_p,
                                           ctypes.c_void_p]
        user32.CallWindowProcW.restype = ctypes.c_void_p
        proc_type = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                                       ctypes.c_void_p, ctypes.c_void_p)

        pending = deque()
        ctx = {'hwnd': 0, 'old_proc': 0}

        def handler(hwnd_, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                try:
                    paths = _dropped_paths(wparam)
                except Exception:
                    paths = []
                try:
                    shell32.DragFinish(wparam)
                except Exception:
                    pass
                if paths:
                    pending.append(paths)
                return 0
            return user32.CallWindowProcW(ctypes.c_void_p(ctx['old_proc']),
                                          ctypes.c_void_p(hwnd_), msg, wparam, lparam)

        callback = proc_type(handler)
        callback_ptr = ctypes.cast(callback, ctypes.c_void_p)
        _drop_keepalive.append(callback)
        window._drop_callback = callback
        window._drop_pending = pending

        def install():
            hwnd = toplevel_hwnd(window)
            if not hwnd:
                return False
            if ctx['hwnd'] != hwnd:
                old_proc = get_ptr(hwnd, _GWLP_WNDPROC)
                if not old_proc:
                    return False
                if old_proc == callback_ptr.value:
                    ctx['hwnd'] = hwnd
                    return True
                if ctx['hwnd']:
                    _drop_targets.pop(ctx['hwnd'], None)
                    _drop_pending.pop(ctx['hwnd'], None)
                ctx['hwnd'] = hwnd
                ctx['old_proc'] = old_proc
                _drop_targets[hwnd] = (callback, old_proc)
                _drop_pending[hwnd] = pending
                shell32.DragAcceptFiles(hwnd, True)
            if get_ptr(hwnd, _GWLP_WNDPROC) == callback_ptr.value:
                return True
            set_ptr(hwnd, _GWLP_WNDPROC, callback_ptr)
            return bool(get_ptr(hwnd, _GWLP_WNDPROC) == callback_ptr.value)

        def pump():
            alive = True
            try:
                if window.winfo_exists() and window.winfo_viewable():
                    install()
                while pending:
                    batch = pending.popleft()
                    try:
                        on_drop(batch)
                    except Exception:
                        _print_exc_safe()
            except tk.TclError:
                alive = False
            finally:
                if alive:
                    try:
                        window.after(_DROP_POLL_MS, pump)
                    except tk.TclError:
                        pass

        def _on_destroy(event):
            if event.widget is window:
                _drop_targets.pop(ctx['hwnd'], None)
                _drop_pending.pop(ctx['hwnd'], None)

        try:
            window.bind('<Destroy>', _on_destroy, add='+')
            window.after(_DROP_POLL_MS, pump)
        except tk.TclError:
            return False
        return True
    except Exception:
        return False
