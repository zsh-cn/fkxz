import ctypes
import hashlib
import os
import sys
import tkinter as tk
from tkinter import filedialog


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


def resolve_icon_path(icon_filename):
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', '')
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, 'icon', icon_filename)


def load_icon(filename, size=None):
    icon_path = resolve_icon_path(filename)
    if not os.path.exists(icon_path):
        return None
    img = tk.PhotoImage(file=icon_path)
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
    icon = tk.PhotoImage(file=icon_path)
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


def run_gui_app(app_factory, min_width, min_height):
    setup_dpi_awareness()

    root = tk.Tk()

    try:
        from tkinter import font
        default_font = font.nametofont("TkDefaultFont")
        default_font.configure(size=10)
    except Exception:
        pass

    app = app_factory(root)

    try:
        if hasattr(root, 'tk') and hasattr(root.tk, 'call'):
            scale_factor = root.tk.call('tk', 'scaling')
        else:
            scale_factor = 1.0
    except Exception:
        scale_factor = 1.0

    if scale_factor > 1.5:
        root.update_idletasks()
        req_width = max(min_width, root.winfo_reqwidth())
        req_height = max(min_height, root.winfo_reqheight())
        root.geometry(f"{req_width}x{req_height}")

    root.mainloop()
