import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import config
import core
import utils


class FileSplitterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("文件分块")
        utils.scaled_geometry(self.root, *config.SPLITTER_WINDOW_SIZE)
        self.root.resizable(True, True)

        self._icon = utils.apply_window_icon(self.root, 'wjfk.png')

        self.file_path = ""
        self.output_dir = ""
        self.target_name = ""
        self.chunk_size = config.DEFAULT_CHUNK_SIZE_MB * 1024 * 1024
        self.split_thread = None
        self.is_cancelled = False
        self._closed = False

        self.create_widgets()
        utils.install_about_menu(self.root, "文件分块")

        self.ui = utils.UiDispatcher(self.root)

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
        utils.setup_context_menu(self.file_entry, self._on_file_entry_change)

        ttk.Label(input_frame, text="输出目录:").grid(row=1, column=0, sticky=tk.E, pady=5)
        self.output_entry = ttk.Entry(input_frame)
        self.output_entry.grid(row=1, column=1, padx=10, pady=5, sticky=tk.EW, ipady=2)
        self.output_browse_btn = ttk.Button(input_frame, text="浏览", command=self.browse_output_dir)
        self.output_browse_btn.grid(row=1, column=2, pady=5)
        utils.setup_context_menu(self.output_entry)

        ttk.Label(input_frame, text="输出文件名:").grid(row=2, column=0, sticky=tk.E, pady=5)
        self.target_name_entry = ttk.Entry(input_frame)
        self.target_name_entry.grid(row=2, column=1, padx=10, pady=5, sticky=tk.EW, ipady=2)
        ttk.Label(input_frame, text="(可选，不填则使用源文件名)").grid(row=2, column=2, sticky=tk.W, pady=5)
        utils.setup_context_menu(self.target_name_entry)

        ttk.Label(input_frame, text="分片大小(MB):").grid(row=3, column=0, sticky=tk.E, pady=5)
        self.chunk_size_var = tk.IntVar(value=config.DEFAULT_CHUNK_SIZE_MB)
        self.chunk_spinbox = ttk.Spinbox(input_frame, from_=config.MIN_CHUNK_SIZE_MB,
                                         to=config.MAX_CHUNK_SIZE_MB,
                                         textvariable=self.chunk_size_var, width=10)
        self.chunk_spinbox.grid(row=3, column=1, padx=10, pady=5, sticky=tk.W)
        utils.setup_context_menu(self.chunk_spinbox)
        self.chunk_spinbox.bind('<KeyRelease>', self._schedule_file_info_update)
        self.chunk_spinbox.bind('<<Increment>>', self._schedule_file_info_update)
        self.chunk_spinbox.bind('<<Decrement>>', self._schedule_file_info_update)

        ttk.Label(input_frame,
                  text=f"(范围: {config.MIN_CHUNK_SIZE_MB}-{config.MAX_CHUNK_SIZE_MB} MB)"
                  ).grid(row=3, column=2, sticky=tk.W, pady=5)

        control_frame = ttk.LabelFrame(main_frame, text="分块状态", padding="10")
        control_frame.pack(fill=tk.X, pady=5)
        control_frame.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(control_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.grid(row=0, column=0, pady=10, sticky=tk.EW)

        self.status_label = ttk.Label(control_frame, text="状态: 就绪", foreground=config.TEXT_NORMAL)
        self.status_label.grid(row=1, column=0, sticky=tk.W, pady=5)

        self.file_info_label = ttk.Label(control_frame, text="", foreground=config.TEXT_SECONDARY)
        self.file_info_label.grid(row=1, column=0, sticky=tk.E)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)

        self.start_button = ttk.Button(button_frame, text="开始分块", command=self.start_split, width=20)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.cancel_button = ttk.Button(button_frame, text="取消分块", command=self.cancel_split, width=15, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=5)


    def _run_on_ui(self, func, *args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            func(*args, **kwargs)
        else:
            self.ui.call(func, *args, **kwargs)

    def _run_on_ui_latest(self, key, func, *args, **kwargs):
        self.ui.call_latest(key, func, *args, **kwargs)


    def update_status(self, text, foreground=config.TEXT_NORMAL):
        self._run_on_ui(self._set_status, text, foreground)

    def _set_status(self, text, foreground=config.TEXT_NORMAL):
        self.status_label.config(text=text, foreground=foreground)

    def _set_progress(self, value, maximum=None):
        if maximum is not None:
            self.progress['maximum'] = maximum
        self.progress['value'] = value

    def _on_file_entry_change(self, event=None):
        self.file_path = self.file_entry.get().strip()
        if self.file_path and os.path.isfile(self.file_path):
            self.progress['value'] = 0
            self.status_label.config(text="状态: 就绪", foreground=config.TEXT_NORMAL)
            self._update_target_name_from_file()
            self._schedule_file_info_update()
        elif not self.file_path:
            self.progress['value'] = 0
            self.status_label.config(text="状态: 就绪", foreground=config.TEXT_NORMAL)
            self.file_info_label.config(text="")

    def _update_target_name_from_file(self):
        base_name = os.path.basename(self.file_path)
        self.target_name_entry.delete(0, tk.END)
        self.target_name_entry.insert(0, base_name)

    def _schedule_file_info_update(self, event=None):
        if hasattr(self, '_update_after_id') and self._update_after_id:
            self.root.after_cancel(self._update_after_id)
        self._update_after_id = self.root.after(300, self._update_file_info)

    def _update_file_info(self):
        if not self.file_path or not os.path.exists(self.file_path):
            self.file_info_label.config(text="")
            return
        try:
            chunk_size_mb = self.chunk_size_var.get()
            if not (config.MIN_CHUNK_SIZE_MB <= chunk_size_mb <= config.MAX_CHUNK_SIZE_MB):
                chunk_size_mb = None
        except (ValueError, tk.TclError):
            chunk_size_mb = None

        file_size = os.path.getsize(self.file_path)
        size_text = f"文件大小: {utils.format_size(file_size)}"

        if chunk_size_mb is not None:
            chunk_size = chunk_size_mb * 1024 * 1024
            num_chunks = core.plan_num_chunks(file_size, chunk_size)
            size_text += f" | 分片数: {num_chunks}"

        self.file_info_label.config(text=size_text)

    def browse_file(self):
        file_path = utils.browse_file_dialog(self.file_entry)
        if file_path:
            self.file_path = file_path
            self.progress['value'] = 0
            self.status_label.config(text="状态: 就绪", foreground=config.TEXT_NORMAL)
            if os.path.exists(file_path):
                self._update_target_name_from_file()
                self._update_file_info()
            else:
                self.file_info_label.config(text="")

    def browse_output_dir(self):
        dir_path = utils.browse_directory(self.output_entry)
        if dir_path:
            self.output_dir = dir_path


    def _validate_split_inputs(self):
        entry_file = self.file_entry.get().strip()
        self.file_path = os.path.abspath(entry_file) if entry_file else ""
        entry_output = self.output_entry.get().strip()
        self.output_dir = os.path.abspath(entry_output) if entry_output else ""
        entry_target = self.target_name_entry.get().strip()
        self.target_name = entry_target

        if not self.file_path:
            self.update_status("状态: 请选择要分块的文件", foreground=config.TEXT_ERROR)
            return None
        if not os.path.exists(self.file_path):
            self.update_status("状态: 所选文件不存在", foreground=config.TEXT_ERROR)
            return None
        if not os.path.isfile(self.file_path):
            self.update_status("状态: 所选路径不是文件", foreground=config.TEXT_ERROR)
            return None
        if not self.output_dir:
            self.update_status("状态: 请选择输出目录", foreground=config.TEXT_ERROR)
            return None

        try:
            chunk_size_mb = self.chunk_size_var.get()
        except (ValueError, tk.TclError):
            self.update_status("状态: 分片大小必须是数字", foreground=config.TEXT_ERROR)
            return None
        if not (config.MIN_CHUNK_SIZE_MB <= chunk_size_mb <= config.MAX_CHUNK_SIZE_MB):
            self.update_status(
                f"状态: 分片大小应在{config.MIN_CHUNK_SIZE_MB}-{config.MAX_CHUNK_SIZE_MB} MB之间",
                foreground=config.TEXT_ERROR)
            return None
        self.chunk_size = chunk_size_mb * 1024 * 1024

        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir, exist_ok=True)
            except OSError as exc:
                self.update_status(f"状态: 无法创建输出目录: {exc}", foreground=config.TEXT_ERROR)
                return None

        raw_name = self.target_name if self.target_name else os.path.basename(self.file_path)
        file_name = utils.safe_filename(raw_name, default="未命名")
        if not file_name:
            self.update_status("状态: 输出文件名非法", foreground=config.TEXT_ERROR)
            return None
        self.target_name = file_name

        try:
            utils.ensure_within_dir(self.output_dir, core.manifest_name(file_name))
        except ValueError as exc:
            self.update_status(f"状态: 输出文件名非法 - {exc}", foreground=config.TEXT_ERROR)
            return None

        try:
            file_size = os.path.getsize(self.file_path)
        except OSError as exc:
            self.update_status(f"状态: 无法读取文件: {exc}", foreground=config.TEXT_ERROR)
            return None

        num_chunks = core.plan_num_chunks(file_size, self.chunk_size)
        return (self.file_path, file_name, self.output_dir, self.chunk_size, num_chunks, file_size)


    def start_split(self):
        if self.split_thread and self.split_thread.is_alive():
            return

        inputs = self._validate_split_inputs()
        if inputs is None:
            self.file_info_label.config(text="")
            self.reset_ui()
            return

        file_path, file_name, output_dir, chunk_size, num_chunks, file_size = inputs

        self.is_cancelled = False
        self._set_running_ui(True)
        self._set_progress(0, max(1, file_size))

        self.split_thread = threading.Thread(
            target=self._split_worker,
            args=(file_path, file_name, output_dir, chunk_size, num_chunks),
            name="split-worker",
            daemon=True,
        )
        self.split_thread.start()

    def _split_worker(self, file_path, file_name, output_dir, chunk_size, num_chunks):
        started = time.monotonic()
        throttle = utils.Throttle(0.15)

        def on_progress(processed, total, index, count):
            if throttle.ready() or processed >= total:
                self._run_on_ui_latest(
                    'split-progress', self._push_split_progress,
                    processed, total, index, count, started,
                )

        try:
            result = core.split_file(
                file_path, output_dir, file_name, chunk_size,
                num_chunks=num_chunks,
                on_progress=on_progress,
                should_stop=lambda: self.is_cancelled,
            )
        except core.Cancelled:
            self._run_on_ui(self._finish_failure, "状态: 分块已取消", True)
            return
        except Exception as exc:
            self._run_on_ui(self._finish_failure, f"状态: 分块过程发生错误: {exc}")
            return

        self._run_on_ui(self._finish_success, result.file_name, result.total_size,
                        result.num_chunks, result.fkx_path, output_dir)

    def _push_split_progress(self, processed, total, index, count, started):
        total = max(1, total)
        self.progress['maximum'] = total
        self.progress['value'] = min(processed, total)
        speed = utils.measured_speed(processed, started)
        self.status_label.config(
            text=(f"状态: 正在分块 {index}/{count} | {utils.format_size(processed)}"
                  f" / {utils.format_size(total)} | 速度: {utils.speed_text(speed)}"),
            foreground=config.TEXT_NORMAL,
        )


    def _finish_success(self, file_name, file_size, num_chunks, fkx_path, output_dir):
        self._set_progress(max(1, file_size), max(1, file_size))
        self.update_status(f"状态: 分块完成！已生成 {num_chunks} 个分片", foreground=config.TEXT_SUCCESS)
        self.reset_ui()
        utils.flush_ui(self.root)
        messagebox.showinfo(
            "完成",
            f"文件分块完成！\n文件名: {file_name}\n文件大小: {utils.format_size(file_size)}\n"
            f"分片数: {num_chunks}\n信息文件: {os.path.basename(fkx_path)}\n保存位置: {output_dir}",
            parent=self.root,
        )

    def _finish_failure(self, status_text, is_cancel=False):
        self._set_progress(0)
        self.update_status(status_text, foreground=config.TEXT_NORMAL if is_cancel else config.TEXT_ERROR)
        self.reset_ui()


    def _set_running_ui(self, running):
        state = tk.DISABLED if running else tk.NORMAL
        self.start_button.config(state=state)
        self.cancel_button.config(state=tk.NORMAL if running else tk.DISABLED)
        self.file_entry.config(state=state)
        self.file_browse_btn.config(state=state)
        self.output_entry.config(state=state)
        self.output_browse_btn.config(state=state)
        self.target_name_entry.config(state=state)
        self.chunk_spinbox.config(state=state)

    def cancel_split(self):
        self.is_cancelled = True
        self.cancel_button.config(state=tk.DISABLED)
        self.update_status("状态: 正在取消...")

    def reset_ui(self):
        self._set_running_ui(False)


    def close(self, timeout=2.0):
        if self._closed:
            return
        self._closed = True
        self.is_cancelled = True
        thread = self.split_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self.ui.stop()


if __name__ == "__main__":
    utils.set_app_user_model_id(config.APP_ID_SPLITTER)
    utils.run_gui_app(FileSplitterApp)
