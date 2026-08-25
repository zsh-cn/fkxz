import os
import hashlib
import threading
from utils.helpers import parse_wjxx, sanitize_filename, format_size


class FileMerger:
    def __init__(self, callbacks=None):
        self.callbacks = callbacks or {}
        self._is_cancelled = False
        self._thread = None

    def cancel(self):
        self._is_cancelled = True

    @property
    def is_cancelled(self):
        return self._is_cancelled

    def _emit_progress(self, value, maximum):
        cb = self.callbacks.get('on_progress')
        if cb:
            cb(value, maximum)

    def _emit_chunk_progress(self, value, maximum):
        cb = self.callbacks.get('on_chunk_progress')
        if cb:
            cb(value, maximum)

    def _emit_status(self, text, color='#333333'):
        cb = self.callbacks.get('on_status')
        if cb:
            cb(text, color)

    def _emit_error(self, message):
        cb = self.callbacks.get('on_error')
        if cb:
            cb(message)

    def _emit_complete(self, result):
        cb = self.callbacks.get('on_complete')
        if cb:
            cb(result)

    def _emit_file_info(self, info):
        cb = self.callbacks.get('on_file_info')
        if cb:
            cb(info)

    def merge_async(self, wjxx_path, output_dir):
        self._is_cancelled = False
        self._thread = threading.Thread(
            target=self._merge,
            args=(wjxx_path, output_dir),
            daemon=True
        )
        self._thread.start()

    def _merge(self, wjxx_path, output_dir):
        try:
            if not wjxx_path:
                self._emit_error("请输入.wjx文件路径")
                return

            if not os.path.exists(wjxx_path):
                self._emit_error(f"本地文件不存在: {wjxx_path}")
                return

            if not output_dir:
                self._emit_error("请选择输出目录")
                return

            self._emit_status("正在解析文件信息...")

            try:
                with open(wjxx_path, 'r', encoding='utf-8') as f:
                    wjxx_content = f.read()
            except Exception as e:
                self._emit_error(f"无法读取文件信息: {str(e)}")
                return

            wjxx_info = parse_wjxx(wjxx_content)

            if 'filename' not in wjxx_info or 'chunks' not in wjxx_info:
                self._emit_error("文件信息格式不正确")
                return

            num_chunks = len(wjxx_info['chunks'])
            total_size = sum(chunk['size'] for chunk in wjxx_info['chunks'])

            self._emit_file_info({
                'filename': wjxx_info.get('filename', '-'),
                'total_size': total_size,
                'num_chunks': num_chunks,
            })

            base_path = os.path.dirname(os.path.abspath(wjxx_path))

            self._emit_progress(0, num_chunks)
            self._emit_chunk_progress(0, 100)

            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            downloaded_chunks = {}

            for i, chunk_info in enumerate(wjxx_info['chunks']):
                if self._is_cancelled:
                    self._emit_status("已取消合并", '#cc0000')
                    return

                self._emit_status(f"正在读取分片 {i+1}/{num_chunks}")

                chunk_path = os.path.join(base_path, chunk_info['filename'])
                chunk_path = os.path.normpath(chunk_path)

                if not os.path.exists(chunk_path):
                    self._emit_error(f"分片文件不存在: {chunk_info['filename']}")
                    return

                downloaded_chunks[i] = chunk_path
                self._emit_progress(i + 1, num_chunks)
                self._emit_chunk_progress(100, 100)

            self._emit_status("正在合并文件...")
            safe_filename = sanitize_filename(os.path.basename(wjxx_info['filename']))
            output_path = os.path.join(output_dir, safe_filename)
            output_path = os.path.normpath(output_path)

            with open(output_path, 'wb') as f:
                for i in range(num_chunks):
                    if self._is_cancelled:
                        if os.path.exists(output_path):
                            os.remove(output_path)
                        self._emit_status("已取消合并", '#cc0000')
                        return

                    chunk_path = downloaded_chunks[i]
                    with open(chunk_path, 'rb') as chunk_file:
                        for chunk in iter(lambda: chunk_file.read(65536), b""):
                            f.write(chunk)

            if 'sha256' in wjxx_info:
                self._emit_status("正在校验SHA-256...")
                actual_sha256 = hashlib.sha256()
                with open(output_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        if self._is_cancelled:
                            if os.path.exists(output_path):
                                os.remove(output_path)
                            self._emit_status("已取消合并", '#cc0000')
                            return
                        actual_sha256.update(chunk)

                if actual_sha256.hexdigest() != wjxx_info['sha256']:
                    self._emit_error("文件SHA-256校验失败")
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    return

            self._emit_progress(num_chunks, num_chunks)
            self._emit_chunk_progress(100, 100)
            self._emit_status("合并成功", '#006600')
            self._emit_complete({
                'mode': '本地',
                'file_name': safe_filename,
                'output_path': output_path,
            })

        except Exception as e:
            self._emit_error(f"合并过程发生错误: {str(e)}")