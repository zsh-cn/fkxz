import os
import hashlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading

class FileSplitterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("文件拆分器")
        self.root.geometry("650x450")
        self.root.resizable(True, True)
        
        self.file_path = ""
        self.output_dir = ""
        self.chunk_size = 10 * 1024 * 1024
        self.split_thread = None
        self.is_cancelled = False
        
        self.create_widgets()
    
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        input_frame = ttk.LabelFrame(main_frame, text="输入配置", padding="10")
        input_frame.pack(fill=tk.X, pady=5)
        input_frame.columnconfigure(1, weight=1)
        
        ttk.Label(input_frame, text="选择要拆分的文件:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.file_entry = ttk.Entry(input_frame)
        self.file_entry.grid(row=0, column=1, padx=10, pady=5, sticky=tk.EW)
        ttk.Button(input_frame, text="浏览", command=self.browse_file).grid(row=0, column=2, pady=5)
        
        ttk.Label(input_frame, text="输出目录:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.output_entry = ttk.Entry(input_frame)
        self.output_entry.grid(row=1, column=1, padx=10, pady=5, sticky=tk.EW)
        ttk.Button(input_frame, text="浏览", command=self.browse_output_dir).grid(row=1, column=2, pady=5)
        
        ttk.Label(input_frame, text="每个分片大小(MB):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.chunk_size_var = tk.StringVar(value="10")
        chunk_entry = ttk.Entry(input_frame, textvariable=self.chunk_size_var, width=15)
        chunk_entry.grid(row=2, column=1, sticky=tk.W, pady=5)
        chunk_entry.bind('<KeyRelease>', self.validate_chunk_size)
        
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
    
    def validate_chunk_size(self, event=None):
        try:
            size = int(self.chunk_size_var.get())
            if size < 1 or size > 1024:
                self.status_label.config(text="状态: 分片大小应在1-1024 MB之间", foreground="#cc0000")
            else:
                self.status_label.config(text="状态: 就绪", foreground="#333333")
        except ValueError:
            self.status_label.config(text="状态: 分片大小必须是数字", foreground="#cc0000")
    
    def browse_file(self):
        file_path = filedialog.askopenfilename()
        if file_path:
            self.file_path = file_path
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, file_path)
            
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                self.file_info_label.config(text=f"文件大小: {self.format_size(file_size)}")
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
    
    def calculate_md5(self, file_path):
        md5_hash = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    
    def update_status(self, text):
        self.status_label.config(text=text)
        self.root.update_idletasks()
    
    def show_error(self, message):
        messagebox.showerror("错误", message)
    
    def split_file(self):
        if not self.file_path:
            self.show_error("请选择要拆分的文件")
            self.reset_ui()
            return
        
        if not os.path.exists(self.file_path):
            self.show_error("所选文件不存在")
            self.reset_ui()
            return
        
        if not os.path.isfile(self.file_path):
            self.show_error("所选路径不是文件")
            self.reset_ui()
            return
        
        if not self.output_dir:
            self.show_error("请选择输出目录")
            self.reset_ui()
            return
        
        try:
            chunk_size_mb = int(self.chunk_size_var.get())
            if chunk_size_mb < 1 or chunk_size_mb > 1024:
                self.show_error("分片大小应在1-1024 MB之间")
                self.reset_ui()
                return
            self.chunk_size = chunk_size_mb * 1024 * 1024
        except ValueError:
            self.show_error("分片大小必须是数字")
            self.reset_ui()
            return
        
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
            except Exception as e:
                self.show_error(f"无法创建输出目录: {str(e)}")
                self.reset_ui()
                return
        
        self.start_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.NORMAL)
        self.is_cancelled = False
        
        file_name = os.path.basename(self.file_path)
        file_size = os.path.getsize(self.file_path)
        num_chunks = (file_size + self.chunk_size - 1) // self.chunk_size
        
        self.progress['maximum'] = num_chunks
        self.progress['value'] = 0
        
        wjxx_content = [
            f"filename={file_name}",
            f"total_size={file_size}",
            f"chunk_size={self.chunk_size}",
            f"num_chunks={num_chunks}"
        ]
        
        try:
            with open(self.file_path, 'rb') as f:
                for i in range(num_chunks):
                    if self.is_cancelled:
                        self.update_status("状态: 拆分已取消")
                        self.cleanup_chunks(self.output_dir, file_name, i)
                        self.reset_ui()
                        return
                    
                    chunk_data = f.read(self.chunk_size)
                    chunk_filename = f"{file_name}-{i}.fk"
                    chunk_path = os.path.join(self.output_dir, chunk_filename)
                    
                    with open(chunk_path, 'wb') as chunk_file:
                        chunk_file.write(chunk_data)
                    
                    chunk_md5 = hashlib.md5(chunk_data).hexdigest()
                    wjxx_content.append(f"chunk_{i}={chunk_filename},{len(chunk_data)},{chunk_md5}")
                    
                    self.progress['value'] = i + 1
                    self.update_status(f"状态: 正在拆分 {i+1}/{num_chunks}")
            
            if self.is_cancelled:
                self.update_status("状态: 拆分已取消")
                self.reset_ui()
                return
            
            self.update_status("状态: 正在计算文件MD5...")
            file_md5 = self.calculate_md5(self.file_path)
            wjxx_content.append(f"md5={file_md5}")
            
            wjxx_filename = f"{file_name}.wjx"
            wjxx_path = os.path.join(self.output_dir, wjxx_filename)
            with open(wjxx_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(wjxx_content))
            
            self.progress['value'] = num_chunks
            self.update_status(f"状态: 拆分完成！已生成 {num_chunks} 个分片")
            self.reset_ui()
            messagebox.showinfo("完成", f"文件拆分完成！\n文件名: {file_name}\n文件大小: {self.format_size(file_size)}\n分片数: {num_chunks}\n信息文件: {wjxx_filename}\n保存位置: {self.output_dir}")
        
        except Exception as e:
            self.show_error(f"拆分过程发生错误: {str(e)}")
            self.reset_ui()
    
    def cleanup_chunks(self, output_dir, file_name, count):
        for i in range(count):
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
    root = tk.Tk()
    app = FileSplitterApp(root)
    root.mainloop()