import os
import hashlib
import shutil
import threading

from core.base_worker import BaseWorker
from utils.helpers import parse_fkx, sanitize_filename, format_size


class FileMerger(BaseWorker):
    def merge_async(self, fkx_path, output_dir):
        self._is_cancelled = False
        self._thread = threading.Thread(
            target=self._merge,
            args=(fkx_path, output_dir),
            daemon=True
        )
        self._thread.start()

    def _merge(self, fkx_path, output_dir):
        try:
            if not fkx_path:
                self._emit_error("请输入.fkx文件路径")
                return

            if not os.path.exists(fkx_path):
                self._emit_error(f"本地文件不存在: {fkx_path}")
                return

            if not output_dir:
                self._emit_error("请选择输出目录")
                return

            self._emit_status("正在解析文件信息...")

            try:
                with open(fkx_path, 'r', encoding='utf-8') as f:
                    fkx_content = f.read()
            except Exception as e:
                self._emit_error(f"无法读取文件信息: {str(e)}")
                return

            fkx_info = parse_fkx(fkx_content)

            if 'filename' not in fkx_info or 'chunks' not in fkx_info:
                self._emit_error("文件信息格式不正确")
                return

            num_chunks = len(fkx_info['chunks'])
            total_size = sum(chunk['size'] for chunk in fkx_info['chunks'])

            self._emit_file_info({
                'filename': fkx_info.get('filename', '-'),
                'total_size': total_size,
                'num_chunks': num_chunks,
            })

            base_path = os.path.dirname(os.path.abspath(fkx_path))

            self._emit_progress(0, num_chunks)
            self._emit_chunk_progress(0, 100)

            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            downloaded_chunks = {}

            for i, chunk_info in enumerate(fkx_info['chunks']):
                if self._is_cancelled:
                    self._emit_status("已取消合并", '#cc0000')
                    self._emit_complete({'cancelled': True})
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
            filename = fkx_info['filename']
            assert isinstance(filename, str)
            safe_filename = sanitize_filename(os.path.basename(filename))
            output_path = os.path.join(output_dir, safe_filename)
            output_path = os.path.normpath(output_path)

            merged_bytes = [0]
            with open(output_path, 'wb') as f:
                for i in range(num_chunks):
                    if self._is_cancelled:
                        try:
                            os.remove(output_path)
                        except FileNotFoundError:
                            pass
                        self._emit_status("已取消合并", '#cc0000')
                        self._emit_complete({'cancelled': True})
                        return

                    chunk_path = downloaded_chunks[i]
                    with open(chunk_path, 'rb') as chunk_file:
                        for chunk in iter(lambda: chunk_file.read(65536), b""):
                            f.write(chunk)
                            merged_bytes[0] += len(chunk)
                            if total_size > 0:
                                percentage = merged_bytes[0] / total_size
                                self._emit_chunk_progress(percentage * 100, 100)

            if 'sha256' in fkx_info:
                self._emit_status("正在校验SHA-256...")
                actual_sha256 = hashlib.sha256()
                with open(output_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        if self._is_cancelled:
                            try:
                                os.remove(output_path)
                            except FileNotFoundError:
                                pass
                            self._emit_status("已取消合并", '#cc0000')
                            self._emit_complete({'cancelled': True})
                            return
                        actual_sha256.update(chunk)

                if actual_sha256.hexdigest() != fkx_info['sha256']:
                    self._emit_error("文件SHA-256校验失败")
                    try:
                        os.remove(output_path)
                    except FileNotFoundError:
                        pass
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