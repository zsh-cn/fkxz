import os
import sys
import hashlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import ctypes

try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('fkxz.splitter')
except Exception:
    pass

class FileSplitterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("文件分块")
        self.root.geometry("650x380")
        self.root.minsize(650, 380)
        self.root.resizable(True, True)

        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(getattr(sys, '_MEIPASS', ''), 'icon', 'wjfk.png')
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon', 'wjfk.png')
        if os.path.exists(icon_path):
            self._icon = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, self._icon)
        
        self.file_path = ""
        self.output_dir = ""
        self.chunk_size = 10 * 1024 * 1024
        self.split_thread = None
        self.is_cancelled = False
        
        self.create_widgets()
    
    def _delete_selected(self, entry_widget):
        try:
            if entry_widget.selection_present():
                entry_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass

    def _setup_context_menu(self, entry_widget, on_change=None):
        menu = tk.Menu(entry_widget, tearoff=0)

        def _copy_to_clipboard(saved_selection=None):
            try:
                entry_widget.clipboard_clear()
                if saved_selection:
                    entry_widget.clipboard_append(saved_selection)
                else:
                    entry_widget.event_generate('<<Copy>>')
            except tk.TclError:
                pass

        menu.add_command(label="剪切", command=lambda: entry_widget.event_generate('<<Cut>>'))
        menu.add_command(label="复制", command=lambda: entry_widget.event_generate('<<Copy>>'))
        menu.add_command(label="粘贴", command=lambda: entry_widget.event_generate('<<Paste>>'))
        menu.add_separator()
        menu.add_command(label="删除", command=lambda: [self._delete_selected(entry_widget), entry_widget.after(10, on_change) if on_change else None])
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
    
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        input_frame = ttk.LabelFrame(main_frame, text="分块配置", padding="10")
        input_frame.pack(fill=tk.X, pady=5)
        input_frame.columnconfigure(1, weight=1)
        input_frame.columnconfigure(2, minsize=130)
        
        ttk.Label(input_frame, text="选择要分块的文件:").grid(row=0, column=0, sticky=tk.E, pady=5)
        self.file_entry = ttk.Entry(input_frame)
        self.file_entry.grid(row=0, column=1, padx=10, pady=5, sticky=tk.EW, ipady=2)
        self.file_entry.bind('<KeyRelease>', self._on_file_entry_change)
        self.file_entry.bind('<<Paste>>', lambda e: self.file_entry.after(10, self._on_file_entry_change))
        self.file_entry.bind('<<Cut>>', lambda e: self.file_entry.after(10, self._on_file_entry_change))
        self.file_browse_btn = ttk.Button(input_frame, text="浏览", command=self.browse_file)
        self.file_browse_btn.grid(row=0, column=2, pady=5)
        self._setup_context_menu(self.file_entry, self._on_file_entry_change)
        
        ttk.Label(input_frame, text="输出目录:").grid(row=1, column=0, sticky=tk.E, pady=5)
        self.output_entry = ttk.Entry(input_frame)
        self.output_entry.grid(row=1, column=1, padx=10, pady=5, sticky=tk.EW, ipady=2)
        self.output_browse_btn = ttk.Button(input_frame, text="浏览", command=self.browse_output_dir)
        self.output_browse_btn.grid(row=1, column=2, pady=5)
        self._setup_context_menu(self.output_entry)
        
        ttk.Label(input_frame, text="分片大小(MB):").grid(row=2, column=0, sticky=tk.E, pady=5)
        self.chunk_size_var = tk.IntVar(value=10)
        self.chunk_spinbox = ttk.Spinbox(input_frame, from_=1, to=1024, textvariable=self.chunk_size_var, width=10)
        self.chunk_spinbox.grid(row=2, column=1, padx=10, pady=5, sticky=tk.W)
        self._setup_context_menu(self.chunk_spinbox)
        self.chunk_spinbox.bind('<KeyRelease>', self._schedule_file_info_update)
        self.chunk_spinbox.bind('<<Increment>>', self._schedule_file_info_update)
        self.chunk_spinbox.bind('<<Decrement>>', self._schedule_file_info_update)
        
        ttk.Label(input_frame, text="(范围: 1-1024 MB)").grid(row=2, column=2, sticky=tk.W, pady=5)
        
        control_frame = ttk.LabelFrame(main_frame, text="分块状态", padding="10")
        control_frame.pack(fill=tk.X, pady=5)
        control_frame.columnconfigure(0, weight=1)
        
        self.progress = ttk.Progressbar(control_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.grid(row=0, column=0, pady=10, sticky=tk.EW)
        
        self.status_label = ttk.Label(control_frame, text="状态: 就绪", foreground="#333333")
        self.status_label.grid(row=1, column=0, sticky=tk.W, pady=5)
        
        self.file_info_label = ttk.Label(control_frame, text="", foreground="#666666")
        self.file_info_label.grid(row=1, column=0, sticky=tk.E)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        self.start_button = ttk.Button(button_frame, text="开始分块", command=self.start_split, width=20)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.cancel_button = ttk.Button(button_frame, text="取消分块", command=self.cancel_split, width=15, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=5)
    
    def _on_file_entry_change(self, event=None):
        self.file_path = self.file_entry.get().strip()
        if self.file_path and os.path.isfile(self.file_path):
            self.progress['value'] = 0
            self.status_label.config(text="状态: 就绪", foreground="#333333")
            self._schedule_file_info_update()
        elif not self.file_path:
            self.progress['value'] = 0
            self.status_label.config(text="状态: 就绪", foreground="#333333")
            self.file_info_label.config(text="")

    def _schedule_file_info_update(self, event=None):
        if hasattr(self, '_update_after_id'):
            self.root.after_cancel(self._update_after_id)
        self._update_after_id = self.root.after(300, self._update_file_info)

    def _update_file_info(self):
        if not self.file_path or not os.path.exists(self.file_path):
            self.file_info_label.config(text="")
            return
        try:
            chunk_size_mb = self.chunk_size_var.get()
            if chunk_size_mb < 1 or chunk_size_mb > 1024:
                chunk_size_mb = None
        except (ValueError, tk.TclError):
            chunk_size_mb = None
        
        file_size = os.path.getsize(self.file_path)
        size_text = f"文件大小: {self.format_size(file_size)}"
        
        if chunk_size_mb is not None:
            chunk_size = chunk_size_mb * 1024 * 1024
            num_chunks = (file_size + chunk_size - 1) // chunk_size
            size_text += f" | 分片数: {num_chunks}"
        
        self.file_info_label.config(text=size_text)
    
    def browse_file(self):
        file_path = filedialog.askopenfilename()
        if file_path:
            self.file_path = file_path
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, file_path)
            
            self.progress['value'] = 0
            self.status_label.config(text="状态: 就绪", foreground="#333333")
            
            if os.path.exists(file_path):
                self._update_file_info()
            else:
                self.file_info_label.config(text="")
    
    def browse_output_dir(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.output_dir = dir_path
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, dir_path)
    
    def format_size(self, size):
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.2f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"

    def calculate_sha256(self, file_path, cancel_check=None, progress_callback=None):
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
    
    def _on_split_sha256_progress(self, processed, total):
        def update():
            if total > 0:
                self.progress['value'] = processed / total * 100
            self.status_label.config(
                text=f"状态: 正在计算文件SHA-256... {self.format_size(processed)} / {self.format_size(total)}"
            )
            self.root.update_idletasks()
        self.root.after(0, update)

    def update_status(self, text, foreground="#333333"):
        self.status_label.config(text=text, foreground=foreground)
        self.root.update_idletasks()
    
    def _validate_split_inputs(self):
        entry_file = self.file_entry.get().strip()
        if entry_file:
            self.file_path = os.path.abspath(entry_file)
        entry_output = self.output_entry.get().strip()
        if entry_output:
            self.output_dir = os.path.abspath(entry_output)

        if not self.file_path:
            self.update_status("状态: 请选择要分块的文件", foreground="#cc0000")
            return None
        if not os.path.exists(self.file_path):
            self.update_status("状态: 所选文件不存在", foreground="#cc0000")
            return None
        if not os.path.isfile(self.file_path):
            self.update_status("状态: 所选路径不是文件", foreground="#cc0000")
            return None
        if not self.output_dir:
            self.update_status("状态: 请选择输出目录", foreground="#cc0000")
            return None
        
        try:
            chunk_size_mb = self.chunk_size_var.get()
            if chunk_size_mb < 1 or chunk_size_mb > 1024:
                self.update_status("状态: 分片大小应在1-1024 MB之间", foreground="#cc0000")
                return None
            self.chunk_size = chunk_size_mb * 1024 * 1024
        except (ValueError, tk.TclError):
            self.update_status("状态: 分片大小必须是数字", foreground="#cc0000")
            return None
        
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
            except Exception as e:
                self.update_status(f"状态: 无法创建输出目录: {str(e)}", foreground="#cc0000")
                return None
        
        file_name = os.path.basename(self.file_path)
        file_size = os.path.getsize(self.file_path)
        num_chunks = (file_size + self.chunk_size - 1) // self.chunk_size
        return (file_name, file_size, num_chunks)

    def _do_split_chunks(self, file_name, num_chunks, fkx_path):
        chunk_paths = []
        try:
            with open(fkx_path, 'w', encoding='utf-8') as fkx_file:
                fkx_file.write(f"filename={file_name}\n")
                fkx_file.write(f"total_size={os.path.getsize(self.file_path)}\n")
                fkx_file.write(f"chunk_size={self.chunk_size}\n")
                fkx_file.write(f"num_chunks={num_chunks}\n")
                fkx_file.flush()

                with open(self.file_path, 'rb') as f:
                    for i in range(num_chunks):
                        if self.is_cancelled:
                            self.update_status("状态: 分块已取消", foreground="#cc0000")
                            return False, chunk_paths

                        chunk_data = f.read(self.chunk_size)
                        chunk_filename = f"{file_name}-{i+1}.fk"
                        chunk_path = os.path.join(self.output_dir, chunk_filename)

                        with open(chunk_path, 'wb') as chunk_file:
                            chunk_file.write(chunk_data)

                        chunk_paths.append(chunk_path)

                        chunk_sha256 = self.calculate_sha256(
                            chunk_path,
                            cancel_check=lambda: self.is_cancelled
                        )
                        if self.is_cancelled or chunk_sha256 is None:
                            self.update_status("状态: 分块已取消", foreground="#cc0000")
                            return False, chunk_paths

                        fkx_file.write(f"chunk_{i+1}={chunk_filename},{len(chunk_data)},{chunk_sha256}\n")
                        fkx_file.flush()

                        self.progress['value'] = i + 1
                        self.update_status(f"状态: 正在分块 {i+1}/{num_chunks}")
            return True, chunk_paths
        except Exception as e:
            self.update_status(f"状态: 分块过程发生错误: {str(e)}", foreground="#cc0000")
            return False, chunk_paths

    def _finalize_split(self, file_name, file_size, num_chunks, fkx_path, chunk_paths):
        self.update_status("状态: 正在计算文件SHA-256...")
        self.progress['maximum'] = 100

        file_sha256 = self.calculate_sha256(
            self.file_path,
            cancel_check=lambda: self.is_cancelled,
            progress_callback=lambda p, t: self._on_split_sha256_progress(p, t)
        )

        if self.is_cancelled or file_sha256 is None:
            self._cleanup(fkx_path, chunk_paths)
            self.update_status("状态: 分块已取消", foreground="#cc0000")
            self.progress['value'] = 0
            self.reset_ui()
            return

        with open(fkx_path, 'a', encoding='utf-8') as f:
            f.write(f"sha256={file_sha256}\n")

        self.progress['maximum'] = num_chunks
        self.progress['value'] = num_chunks
        self.update_status(f"状态: 分块完成！已生成 {num_chunks} 个分片", foreground="#006600")
        self.reset_ui()
        fkx_filename = os.path.basename(fkx_path)
        messagebox.showinfo("完成", f"文件分块完成！\n文件名: {file_name}\n文件大小: {self.format_size(file_size)}\n分片数: {num_chunks}\n信息文件: {fkx_filename}\n保存位置: {self.output_dir}")

    def split_file(self):
        inputs = self._validate_split_inputs()
        if inputs is None:
            self.reset_ui()
            return

        file_name, file_size, num_chunks = inputs

        self.start_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.NORMAL)
        self.file_entry.config(state=tk.DISABLED)
        self.file_browse_btn.config(state=tk.DISABLED)
        self.output_entry.config(state=tk.DISABLED)
        self.output_browse_btn.config(state=tk.DISABLED)
        self.chunk_spinbox.config(state=tk.DISABLED)
        self.is_cancelled = False

        self.progress['maximum'] = num_chunks
        self.progress['value'] = 0

        fkx_filename = f"{file_name}.fkx"
        fkx_path = os.path.join(self.output_dir, fkx_filename)

        success, chunk_paths = self._do_split_chunks(file_name, num_chunks, fkx_path)
        if not success:
            self._cleanup(fkx_path, chunk_paths)
            self.progress['value'] = 0
            self.reset_ui()
            return

        self._finalize_split(file_name, file_size, num_chunks, fkx_path, chunk_paths)

    def _cleanup(self, fkx_path, chunk_paths):
        for path in chunk_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        try:
            if os.path.exists(fkx_path):
                os.remove(fkx_path)
        except Exception:
            pass

    def start_split(self):
        self.progress['value'] = 0
        self.split_thread = threading.Thread(target=self.split_file)
        self.split_thread.start()

    def cancel_split(self):
        self.is_cancelled = True

    def reset_ui(self):
        self.start_button.config(state=tk.NORMAL)
        self.cancel_button.config(state=tk.DISABLED)
        self.file_entry.config(state=tk.NORMAL)
        self.file_browse_btn.config(state=tk.NORMAL)
        self.output_entry.config(state=tk.NORMAL)
        self.output_browse_btn.config(state=tk.NORMAL)
        self.chunk_spinbox.config(state=tk.NORMAL)

if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    
    root = tk.Tk()
    
    try:
        from tkinter import font
        default_font = font.nametofont("TkDefaultFont")
        default_font.configure(size=10)
    except Exception:
        pass
    
    app = FileSplitterApp(root)
    root.mainloop()