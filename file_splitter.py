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
    
    def _setup_context_menu(self, entry_widget):
        menu = tk.Menu(entry_widget, tearoff=0)
        menu.add_command(label="剪切", command=lambda: entry_widget.event_generate('<<Cut>>'))
        menu.add_command(label="复制", command=lambda: entry_widget.event_generate('<<Copy>>'))
        menu.add_command(label="粘贴", command=lambda: entry_widget.event_generate('<<Paste>>'))
        menu.add_separator()
        menu.add_command(label="删除", command=lambda: entry_widget.delete(0, tk.END))
        menu.add_separator()
        menu.add_command(label="全选", command=lambda: entry_widget.select_range(0, tk.END))

        def _show_menu(event):
            if entry_widget.focus_get() != entry_widget:
                entry_widget.focus_set()
                entry_widget.select_range(0, tk.END)
            menu.tk_popup(event.x_root, event.y_root)

        entry_widget.bind('<Button-3>', _show_menu)
    
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        input_frame = ttk.LabelFrame(main_frame, text="输入配置", padding="10")
        input_frame.pack(fill=tk.X, pady=5)
        input_frame.columnconfigure(1, weight=1)
        input_frame.columnconfigure(2, minsize=130)
        
        ttk.Label(input_frame, text="选择要拆分的文件:").grid(row=0, column=0, sticky=tk.E, pady=5)
        self.file_entry = ttk.Entry(input_frame)
        self.file_entry.grid(row=0, column=1, padx=10, pady=5, sticky=tk.EW)
        ttk.Button(input_frame, text="浏览", command=self.browse_file).grid(row=0, column=2, pady=5)
        self._setup_context_menu(self.file_entry)
        
        ttk.Label(input_frame, text="输出目录:").grid(row=1, column=0, sticky=tk.E, pady=5)
        self.output_entry = ttk.Entry(input_frame)
        self.output_entry.grid(row=1, column=1, padx=10, pady=5, sticky=tk.EW)
        ttk.Button(input_frame, text="浏览", command=self.browse_output_dir).grid(row=1, column=2, pady=5)
        self._setup_context_menu(self.output_entry)
        
        ttk.Label(input_frame, text="每个分片大小(MB):").grid(row=2, column=0, sticky=tk.E, pady=5)
        self.chunk_size_var = tk.IntVar(value=10)
        chunk_spinbox = ttk.Spinbox(input_frame, from_=1, to=1024, textvariable=self.chunk_size_var, width=10)
        chunk_spinbox.grid(row=2, column=1, padx=10, pady=5, sticky=tk.W)
        chunk_spinbox.bind('<KeyRelease>', self._schedule_file_info_update)
        chunk_spinbox.bind('<<Increment>>', self._schedule_file_info_update)
        chunk_spinbox.bind('<<Decrement>>', self._schedule_file_info_update)
        
        ttk.Label(input_frame, text="(范围: 1-1024 MB)").grid(row=2, column=2, sticky=tk.W, pady=5)
        
        control_frame = ttk.LabelFrame(main_frame, text="拆分状态", padding="10")
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
        
        self.start_button = ttk.Button(button_frame, text="开始拆分", command=self.start_split, width=20)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.cancel_button = ttk.Button(button_frame, text="取消拆分", command=self.cancel_split, width=15, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=5)
    
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
    
    def calculate_sha256(self, file_path, cancel_check=None):
        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b""):
                if cancel_check and cancel_check():
                    return None
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    def update_status(self, text):
        self.status_label.config(text=text)
        self.root.update_idletasks()
    
    def show_error(self, message):
        messagebox.showerror("错误", message)
    
    def _validate_split_inputs(self):
        if not self.file_path:
            self.show_error("请选择要拆分的文件")
            return None
        if not os.path.exists(self.file_path):
            self.show_error("所选文件不存在")
            return None
        if not os.path.isfile(self.file_path):
            self.show_error("所选路径不是文件")
            return None
        if not self.output_dir:
            self.show_error("请选择输出目录")
            return None
        
        try:
            chunk_size_mb = self.chunk_size_var.get()
            if chunk_size_mb < 1 or chunk_size_mb > 1024:
                self.show_error("分片大小应在1-1024 MB之间")
                return None
            self.chunk_size = chunk_size_mb * 1024 * 1024
        except (ValueError, tk.TclError):
            self.show_error("分片大小必须是数字")
            return None
        
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
            except Exception as e:
                self.show_error(f"无法创建输出目录: {str(e)}")
                return None
        
        file_name = os.path.basename(self.file_path)
        file_size = os.path.getsize(self.file_path)
        num_chunks = (file_size + self.chunk_size - 1) // self.chunk_size
        return (file_name, file_size, num_chunks)

    def _do_split_chunks(self, file_name, num_chunks):
        fkx_content = []
        try:
            with open(self.file_path, 'rb') as f:
                for i in range(num_chunks):
                    if self.is_cancelled:
                        self.update_status("状态: 拆分已取消")
                        self.cleanup_chunks(self.output_dir, file_name, i)
                        return None
                    
                    chunk_data = f.read(self.chunk_size)
                    chunk_filename = f"{file_name}-{i+1}.fk"
                    chunk_path = os.path.join(self.output_dir, chunk_filename)
                    
                    with open(chunk_path, 'wb') as chunk_file:
                        chunk_file.write(chunk_data)
                    
                    fkx_content.append(f"chunk_{i+1}={chunk_filename},{len(chunk_data)}")
                    
                    self.progress['value'] = i + 1
                    self.update_status(f"状态: 正在拆分 {i+1}/{num_chunks}")
            return fkx_content
        except Exception as e:
            self.show_error(f"拆分过程发生错误: {str(e)}")
            return None

    def _finalize_split(self, file_name, file_size, num_chunks, fkx_content):
        self.update_status("状态: 正在计算文件SHA-256...")
        
        file_sha256 = self.calculate_sha256(
            self.file_path,
            cancel_check=lambda: self.is_cancelled
        )
        
        if self.is_cancelled or file_sha256 is None:
            self.update_status("状态: 拆分已取消")
            self.progress['value'] = 0
            self.reset_ui()
            return
        
        fkx_content.append(f"sha256={file_sha256}")
        
        fkx_filename = f"{file_name}.fkx"
        fkx_path = os.path.join(self.output_dir, fkx_filename)
        with open(fkx_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(fkx_content))
        
        self.progress['value'] = num_chunks
        self.update_status(f"状态: 拆分完成！已生成 {num_chunks} 个分片")
        self.reset_ui()
        messagebox.showinfo("完成", f"文件拆分完成！\n文件名: {file_name}\n文件大小: {self.format_size(file_size)}\n分片数: {num_chunks}\n信息文件: {fkx_filename}\n保存位置: {self.output_dir}")

    def split_file(self):
        inputs = self._validate_split_inputs()
        if inputs is None:
            self.reset_ui()
            return
        
        file_name, file_size, num_chunks = inputs
        
        self.start_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.NORMAL)
        self.is_cancelled = False
        
        self.progress['maximum'] = num_chunks
        self.progress['value'] = 0
        
        fkx_content = [
            f"filename={file_name}",
            f"total_size={file_size}",
            f"chunk_size={self.chunk_size}",
            f"num_chunks={num_chunks}"
        ]
        
        chunk_results = self._do_split_chunks(file_name, num_chunks)
        if chunk_results is None:
            self.progress['value'] = 0
            self.reset_ui()
            return
        
        fkx_content.extend(chunk_results)
        self._finalize_split(file_name, file_size, num_chunks, fkx_content)
    
    def cleanup_chunks(self, output_dir, file_name, count):
        for i in range(1, count + 1):
            chunk_path = os.path.join(output_dir, f"{file_name}-{i}.fk")
            if os.path.exists(chunk_path):
                try:
                    os.remove(chunk_path)
                except:
                    pass
    
    def start_split(self):
        self.split_thread = threading.Thread(target=self.split_file)
        self.split_thread.start()
    
    def cancel_split(self):
        self.is_cancelled = True
    
    def reset_ui(self):
        self.start_button.config(state=tk.NORMAL)
        self.cancel_button.config(state=tk.DISABLED)

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