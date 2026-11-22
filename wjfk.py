import os
import threading
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

        self.settings = utils.Settings()
        utils.apply_theme(self.root, self.settings.get('ttk_theme', config.THEME_AUTO))
        self.file_path = ""
        self.output_dir = ""
        self._output_dir_explicit = False
        self.target_name = ""
        self.chunk_size = config.DEFAULT_CHUNK_SIZE_MB * 1024 * 1024
        self.hash_mode = config.DEFAULT_HASH_MODE
        self.split_thread = None
        self.is_cancelled = False
        self._closed = False

        self.settings.discard('auto_shutdown_split')
        self.auto_shutdown = False
        self.auto_shutdown_var = tk.BooleanVar(value=self.auto_shutdown)
        self.open_folder_var = tk.BooleanVar(value=config.DEFAULT_OPEN_FOLDER)
        self._shutdown = utils.ShutdownCountdown(
            self.root, message="文件分块已完成，系统将在 {left} 秒后关机。",
            on_status=self.update_status)

        self.create_widgets()
        utils.install_about_menu(self.root, "文件分块", show_network=False)
        self.taskbar = utils.TaskbarProgress(self.root)
        self._restore_settings()
        self._refresh_open_folder_state()

        self.ui = utils.UiDispatcher(self.root)
        if isinstance(self.root, tk.Tk):
            utils.enable_file_drop(self.root, self.handle_drop)

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

        ttk.Label(input_frame, text="输出目录(留空用程序目录):").grid(row=1, column=0, sticky=tk.E, pady=5)
        self.output_entry = ttk.Entry(input_frame)
        self.output_entry.grid(row=1, column=1, padx=10, pady=5, sticky=tk.EW, ipady=2)
        self.output_entry.bind('<KeyRelease>', self._on_output_entry_change)
        self.output_entry.bind('<<Paste>>', lambda e: self.output_entry.after(10, self._on_output_entry_change))
        self.output_entry.bind('<<Cut>>', lambda e: self.output_entry.after(10, self._on_output_entry_change))
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

        ttk.Label(input_frame, text="校验方式:").grid(row=4, column=0, sticky=tk.E, pady=5)
        self.verify_combo = ttk.Combobox(
            input_frame, state='readonly', width=24,
            values=[label for label, _ in config.VERIFY_OPTIONS])
        self.verify_combo.current(self._verify_index())
        self.verify_combo.grid(row=4, column=1, padx=10, pady=5, sticky=tk.W)
        utils.setup_context_menu(self.verify_combo)
        self.verify_combo.bind('<<ComboboxSelected>>', self._on_verify_selected)
        ttk.Label(input_frame, text="(写入清单的校验信息)").grid(row=4, column=2, sticky=tk.W, pady=5)

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

        self.open_folder_button = ttk.Button(button_frame, text="打开文件夹", command=self._open_output_dir,
                                             width=13, state=tk.DISABLED)
        self.open_folder_button.pack(side=tk.LEFT, padx=5)

        option_frame = ttk.Frame(main_frame)
        option_frame.pack(fill=tk.X)
        self.open_folder_checkbox = ttk.Checkbutton(
            option_frame, text="完成后打开文件夹",
            variable=self.open_folder_var,
            command=self._on_open_folder_toggle)
        self.open_folder_checkbox.pack(side=tk.LEFT)
        self.shutdown_checkbox = ttk.Checkbutton(
            option_frame, text="分块完成后关机",
            variable=self.auto_shutdown_var,
            command=self._on_auto_shutdown_toggle)
        self.shutdown_checkbox.pack(side=tk.LEFT, padx=(16, 0))

    def _on_open_folder_toggle(self):
        self.settings.set('split_open_folder', bool(self.open_folder_var.get()))

    def _on_auto_shutdown_toggle(self):
        self.set_auto_shutdown(self.auto_shutdown_var.get())

    def set_auto_shutdown(self, enabled):
        self.auto_shutdown = bool(enabled)
        try:
            if self.auto_shutdown_var.get() != self.auto_shutdown:
                self.auto_shutdown_var.set(self.auto_shutdown)
        except tk.TclError:
            pass
        if not self.auto_shutdown and self._shutdown.active:
            self._shutdown.cancel()

    def _begin_auto_shutdown(self):
        if self._shutdown.start():
            return
        self.update_status("状态: 自动关机指令下发失败", foreground=config.TEXT_ERROR)
        messagebox.showwarning(
            "自动关机失败",
            "已勾选分块完成后关机，但无法安排系统关机。\n请检查系统权限，或手动关闭计算机。",
            parent=self.root)

    def _verify_index(self):
        for index, (_, value) in enumerate(config.VERIFY_OPTIONS):
            if value == self.hash_mode:
                return index
        return 0

    def _current_hash_mode(self):
        index = self.verify_combo.current()
        if 0 <= index < len(config.VERIFY_OPTIONS):
            return config.VERIFY_OPTIONS[index][1]
        return config.DEFAULT_HASH_MODE

    def _on_verify_selected(self, event=None):
        mode = self._current_hash_mode()
        self.hash_mode = mode
        self.settings.set('split_hash_mode', mode)

    def _restore_settings(self):
        saved = utils.output_dir_setting(self.settings, 'split_output_dir')
        if saved and os.path.isdir(saved):
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, saved)
            self.output_dir = saved

        saved_chunk_mb = self._valid_chunk_size_mb(self.settings.get('chunk_size_mb'))
        if saved_chunk_mb is not None:
            self.chunk_size_var.set(saved_chunk_mb)
            self.chunk_size = saved_chunk_mb * 1024 * 1024

        saved_hash = self.settings.get('split_hash_mode', '')
        if saved_hash in {value for _label, value in config.VERIFY_OPTIONS}:
            self.hash_mode = saved_hash
            self.verify_combo.current(self._verify_index())

        saved_open_folder = self.settings.get('split_open_folder')
        if isinstance(saved_open_folder, bool):
            self.open_folder_var.set(saved_open_folder)

        self.chunk_size_var.trace_add('write', self._on_chunk_size_var_change)

        pending = self.settings.get('split_pending_file', '')
        if pending and os.path.isfile(pending):
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, pending)
            self._on_file_entry_change()

    @staticmethod
    def _valid_chunk_size_mb(value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
        if config.MIN_CHUNK_SIZE_MB <= value <= config.MAX_CHUNK_SIZE_MB:
            return value
        return None

    def _on_chunk_size_var_change(self, *args):
        try:
            current = self.chunk_size_var.get()
        except (ValueError, tk.TclError):
            return
        value = self._valid_chunk_size_mb(current)
        if value is not None:
            self.settings.set('chunk_size_mb', value)

    def _remember_output_dir(self, directory):
        if directory and os.path.isdir(directory):
            self.settings.set('split_output_dir', directory)

    def handle_drop(self, paths):
        for path in paths:
            if os.path.isfile(path):
                self.file_entry.delete(0, tk.END)
                self.file_entry.insert(0, path)
                self._on_file_entry_change()
                return True
        return False

    def _current_output_dir(self):
        raw = self.output_entry.get().strip()
        return os.path.abspath(raw) if raw else utils.app_dir()

    def _refresh_open_folder_state(self):
        target = self._current_output_dir()
        state = tk.NORMAL if (target and os.path.isdir(target)) else tk.DISABLED
        self.open_folder_button.config(state=state)

    def _on_output_entry_change(self, event=None):
        self._refresh_open_folder_state()

    def _open_output_dir(self):
        target = self._current_output_dir()
        if os.path.isdir(target):
            utils.open_folder(target)
        else:
            self.update_status(f"状态: 输出目录不存在: {target}", foreground=config.TEXT_ERROR)

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
            self._remember_output_dir(dir_path)
        self._refresh_open_folder_state()

    def _validate_split_inputs(self):
        entry_file = self.file_entry.get().strip()
        self.file_path = os.path.abspath(entry_file) if entry_file else ""
        entry_output = self.output_entry.get().strip()
        self._output_dir_explicit = bool(entry_output)
        self.output_dir = os.path.abspath(entry_output) if entry_output else utils.app_dir()
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
        self.hash_mode = self._current_hash_mode()

        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir, exist_ok=True)
            except OSError as exc:
                self.update_status(f"状态: 无法创建输出目录: {exc}", foreground=config.TEXT_ERROR)
                return None
        self._refresh_open_folder_state()

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

        try:
            utils.check_free_space(self.output_dir, file_size)
        except OSError as exc:
            self.update_status(f"状态: {exc}", foreground=config.TEXT_ERROR)
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
        if self._output_dir_explicit:
            self._remember_output_dir(output_dir)
        else:
            self.settings.set('split_output_dir', '')

        self.settings.set('split_pending_file', file_path)

        self.is_cancelled = False
        self._set_running_ui(True)
        self._set_progress(0, max(1, file_size))
        self.taskbar.update(0, file_size)

        self.split_thread = threading.Thread(
            target=self._split_worker,
            args=(file_path, file_name, output_dir, chunk_size, num_chunks, self.hash_mode),
            name="split-worker",
            daemon=True,
        )
        self.split_thread.start()

    def _split_worker(self, file_path, file_name, output_dir, chunk_size, num_chunks, hash_mode):
        throttle = utils.Throttle(0.15)
        meter = utils.SpeedMeter()

        def on_progress(processed, total, index, count):
            if throttle.ready() or processed >= total:
                meter.update(processed)
                self._run_on_ui_latest(
                    'split-progress', self._push_split_progress,
                    processed, total, index, count, meter.speed(),
                )

        try:
            result = core.split_file(
                file_path, output_dir, file_name, chunk_size,
                num_chunks=num_chunks,
                on_progress=on_progress,
                should_stop=lambda: self.is_cancelled,
                hash_mode=hash_mode,
            )
        except core.Cancelled:
            self._run_on_ui(self._finish_failure, "状态: 分块已取消", True)
            return
        except Exception as exc:
            self._run_on_ui(self._finish_failure, f"状态: 分块过程发生错误: {exc}")
            return

        self._run_on_ui(self._finish_success, result.file_name, result.total_size,
                        result.num_chunks, result.fkx_path, output_dir)

    def _push_split_progress(self, processed, total, index, count, speed):
        total = max(1, total)
        self.progress['maximum'] = total
        self.progress['value'] = min(processed, total)
        self.taskbar.update(processed, total)
        self.status_label.config(
            text=(f"状态: 正在分块 {index}/{count} | {utils.format_size(processed)}"
                  f" / {utils.format_size(total)} | 速度: {utils.speed_text(speed)}"),
            foreground=config.TEXT_NORMAL,
        )

    def _finish_success(self, file_name, file_size, num_chunks, fkx_path, output_dir):
        self._set_progress(max(1, file_size), max(1, file_size))
        self.taskbar.complete()
        self.settings.discard('split_pending_file')
        self.update_status(
            f"状态: 分块完成！已生成 {num_chunks} 个分片 | {file_name}"
            f" ({utils.format_size(file_size)})",
            foreground=config.TEXT_SUCCESS)
        self.reset_ui()
        self._refresh_open_folder_state()

        if self.open_folder_var.get():
            utils.open_folder(fkx_path)

        if self.auto_shutdown:
            self._begin_auto_shutdown()

    def _finish_failure(self, status_text, is_cancel=False):
        self._set_progress(0)
        if is_cancel:
            self.taskbar.clear()
        else:
            self.taskbar.fail()
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
        self.verify_combo.config(state=tk.DISABLED if running else 'readonly')
        self._refresh_open_folder_state()

    def cancel_split(self):
        self.is_cancelled = True
        self.cancel_button.config(state=tk.DISABLED)
        self.taskbar.pause()
        self.update_status("状态: 正在取消...")

    def reset_ui(self):
        self._set_running_ui(False)

    def close(self, timeout=2.0):
        if self._closed:
            return
        self._closed = True
        self.is_cancelled = True
        self._shutdown.dispose()
        thread = self.split_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self.ui.stop()
        self.taskbar.close()

    def on_close(self):
        self.close()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    utils.run_gui_app(FileSplitterApp, config.APP_ID_SPLITTER)
