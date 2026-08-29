import os
import hashlib
import tkinter as tk
from typing import Any


def format_size(size_bytes):
    if size_bytes <= 0:
        return "0 B"
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(size_bytes)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} B"
    return f"{size:.2f} {units[unit_index]}"


def parse_fkx(content):
    info: dict[str, Any] = {'chunks': []}
    lines = content.strip().split('\n')
    raw_chunks = {}

    for line in lines:
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key.startswith('chunk_'):
            try:
                index = int(key.split('_', 1)[1])
            except ValueError:
                continue
            parts = value.split(',')
            if len(parts) >= 2:
                chunk_filename = os.path.basename(parts[0].strip())
                if index in raw_chunks:
                    raise ValueError(f"chunk 索引重复: chunk_{index}")
                chunk_info = {
                    'filename': chunk_filename,
                    'size': int(parts[1])
                }
                if len(parts) >= 3:
                    chunk_info['sha256'] = parts[2].strip()
                raw_chunks[index] = chunk_info
        else:
            info[key] = value.strip()

    if not raw_chunks:
        raise ValueError("未找到任何 chunk 条目")

    sorted_indices = sorted(raw_chunks.keys())
    expected_start = 1
    for i, idx in enumerate(sorted_indices):
        if idx != expected_start + i:
            raise ValueError(
                f"chunk 索引不连续: 期望 chunk_{expected_start + i}, 实际 chunk_{idx}"
            )

    info['chunks'] = [raw_chunks[idx] for idx in sorted_indices]
    return info


def fkx_chunk_to_line(index, chunk_info):
    sha256_part = f",{chunk_info['sha256']}" if 'sha256' in chunk_info else ""
    return f"chunk_{index}={chunk_info['filename']},{chunk_info['size']}{sha256_part}"


def sanitize_filename(filename):
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename


def is_remote_url(path):
    return path.startswith('http://') or path.startswith('https://')


def has_drive_letter(path):
    return len(path) >= 2 and path[1] == ':'


def is_domain_like(path):
    if not path:
        return False
    if path.startswith('http://') or path.startswith('https://'):
        return False
    if len(path) >= 2 and path[1] == ':':
        return False
    if path.startswith('.') or path.startswith('/') or path.startswith('\\'):
        return False
    slash_pos = path.find('/')
    if slash_pos == -1:
        slash_pos = len(path)
    dot_pos = path.find('.')
    return dot_pos != -1 and dot_pos < slash_pos


def resolve_local_path(path):
    if path.startswith('file://'):
        path = path[7:]
    if not is_remote_url(path) and not has_drive_letter(path):
        return os.path.abspath(path)
    return path


def calculate_sha256(file_path, cancel_check=None, progress_callback=None):
    file_size = os.path.getsize(file_path)
    sha256_hash = hashlib.sha256()
    processed = 0
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b""):
            if cancel_check and cancel_check():
                return None
            sha256_hash.update(chunk)
            processed += len(chunk)
            if progress_callback:
                progress_callback(processed, file_size)
    return sha256_hash.hexdigest()


def _delete_selected(entry_widget):
    try:
        if entry_widget.selection_present():
            entry_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
    except tk.TclError:
        pass


def setup_context_menu(entry_widget, on_change=None):
    def _after_action():
        if on_change is not None:
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

    menu = tk.Menu(entry_widget, tearoff=0)
    menu.add_command(label="剪切", command=lambda: (entry_widget.event_generate('<<Cut>>'), _after_action()))
    menu.add_command(label="复制", command=lambda: entry_widget.event_generate('<<Copy>>'))
    menu.add_command(label="粘贴", command=lambda: (entry_widget.event_generate('<<Paste>>'), _after_action()))
    menu.add_separator()
    menu.add_command(label="删除", command=lambda: (_delete_selected(entry_widget), _after_action()))
    menu.add_separator()
    menu.add_command(label="全选", command=lambda: entry_widget.select_range(0, tk.END))

    def _show_menu(event):
        if str(entry_widget['state']) == 'disabled':
            return
        try:
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
        except tk.TclError:
            pass

    entry_widget.bind('<Button-3>', _show_menu)


def _draw_rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1 + r,
        x1, y1,
        x1 + r, y1,
    ]
    canvas.create_polygon(points, smooth=True, **kwargs)


class RoundedProgressBar(tk.Canvas):
    def __init__(self, parent, maximum=100, value=0, height=8,
                 bg='#E5E7EB', fill='#3B82F6', **kwargs):
        self._maximum = maximum
        self._value = value
        self._track_color = bg
        self._fill_color = fill
        self._bar_height = height
        self._radius = height // 2

        super().__init__(parent, height=height, highlightthickness=0,
                         bd=0, bg=parent.cget('bg'), **kwargs)
        self.bind('<Configure>', self._on_resize)
        self._draw()

    def _draw(self):
        self.delete('all')
        w = self.winfo_width()
        if w < 2:
            return
        h = self._bar_height
        r = self._radius

        _draw_rounded_rect(self, 0, 0, w, h, r, fill=self._track_color, outline='')

        if self._maximum > 0 and self._value > 0:
            pct = self._value / self._maximum
            fill_w = max(r * 2, int(pct * w))
            fill_w = min(fill_w, w)

            if fill_w <= r * 2:
                self.create_oval(0, 0, r * 2, h, fill=self._fill_color, outline='')
            else:
                _draw_rounded_rect(self, 0, 0, fill_w, h, r, fill=self._fill_color, outline='')

    def _on_resize(self, event):
        self._draw()

    def configure(self, *args, **kwargs):
        if 'value' in kwargs:
            self._value = kwargs.pop('value')
        if 'maximum' in kwargs:
            self._maximum = kwargs.pop('maximum')
        self._draw()
        super().configure(*args, **kwargs)

    def config(self, **kwargs):
        self.configure(**kwargs)

    def __getitem__(self, key):
        if key == 'value':
            return self._value
        if key == 'maximum':
            return self._maximum
        raise KeyError(key)

    def __setitem__(self, key, value):
        if key == 'value':
            self._value = value
            self._draw()
        elif key == 'maximum':
            self._maximum = value
            self._draw()
        else:
            raise KeyError(key)


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text='', command=None, width=100, height=34,
                 bg='#3B82F6', fg='#FFFFFF', radius=8, font=None,
                 state='normal', **kwargs):
        self._btn_width = width
        self._btn_height = height
        self._radius = radius
        self._bg = bg
        self._fg = fg
        self._bg_normal = bg
        self._calc_hover_colors(bg)
        self._bg_disabled = '#E5E7EB'
        self._fg_disabled = '#9CA3AF'
        self._command = command
        self._state = state
        self._font = font or ('Microsoft YaHei UI', 10)
        self._text = text

        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, bd=0, **kwargs)
        self._draw()
        self._bind_events()

    def _bind_events(self):
        if self._state == 'normal':
            self.bind('<Enter>', self._on_enter)
            self.bind('<Leave>', self._on_leave)
            self.bind('<Button-1>', self._on_press)
            self.bind('<ButtonRelease-1>', self._on_release)

    def _unbind_events(self):
        self.unbind('<Enter>')
        self.unbind('<Leave>')
        self.unbind('<Button-1>')
        self.unbind('<ButtonRelease-1>')

    def _luminance(self, hex_color):
        c = hex_color.lstrip('#')
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        return (r * 299 + g * 587 + b * 114) / 1000

    def _calc_hover_colors(self, bg):
        lum = self._luminance(bg)
        if lum > 128:
            self._bg_hover = self._darken(bg, 0.10)
            self._bg_active = self._darken(bg, 0.18)
        else:
            self._bg_hover = self._lighten(bg, 0.12)
            self._bg_active = self._darken(bg, 0.08)

    def _lighten(self, hex_color, factor):
        c = hex_color.lstrip('#')
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f'#{r:02x}{g:02x}{b:02x}'

    def _darken(self, hex_color, factor):
        c = hex_color.lstrip('#')
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        r = int(r * (1 - factor))
        g = int(g * (1 - factor))
        b = int(b * (1 - factor))
        return f'#{r:02x}{g:02x}{b:02x}'

    def _draw(self, bg=None):
        self.delete('all')
        if bg is None:
            bg = self._bg_disabled if self._state == 'disabled' else self._bg
        fg = self._fg_disabled if self._state == 'disabled' else self._fg

        r = self._radius
        w = self._btn_width
        h = self._btn_height
        _draw_rounded_rect(self, 0, 0, w, h, r, fill=bg)

        self.create_text(w / 2, h / 2, text=self._text, fill=fg,
                         font=self._font, anchor='center')

    def _on_enter(self, event):
        if self._state == 'normal':
            self._draw(bg=self._bg_hover)

    def _on_leave(self, event):
        if self._state == 'normal':
            self._draw(bg=self._bg_normal)

    def _on_press(self, event):
        if self._state == 'normal':
            self._draw(bg=self._bg_active)

    def _on_release(self, event):
        if self._state == 'normal':
            self._draw(bg=self._bg_hover)
            if self._command:
                self._command()

    def config(self, **kwargs):
        if 'text' in kwargs:
            self._text = kwargs.pop('text')
        if 'state' in kwargs:
            old_state = self._state
            self._state = kwargs.pop('state')
            if self._state != old_state:
                self._unbind_events()
                self._bind_events()
        if 'command' in kwargs:
            self._command = kwargs.pop('command')
        if 'bg' in kwargs:
            self._bg_normal = kwargs.pop('bg')
            self._bg = self._bg_normal
            self._calc_hover_colors(self._bg_normal)
        super().config(**kwargs)
        self._draw()

    def configure(self, *args, **kwargs):
        self.config(**kwargs)

    def cget(self, key):
        if key == 'text':
            return self._text
        if key == 'state':
            return self._state
        return super().cget(key)

    def pack(self, **kwargs):
        super().pack(**kwargs)

    def grid(self, **kwargs):
        super().grid(**kwargs)