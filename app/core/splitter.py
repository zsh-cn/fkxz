import os
import threading

from core.base_worker import BaseWorker
from utils.helpers import calculate_sha256, fkx_chunk_to_line


class FileSplitter(BaseWorker):
    def split_async(self, file_path, output_dir, chunk_size_mb):
        with self._lock:
            if self._is_cancelled:
                self._is_cancelled = False
            if self._thread is not None and self._thread.is_alive():
                self._emit_status("正在取消之前的拆分...", '#cc0000')
                return
            self._thread = threading.Thread(
                target=self._split,
                args=(file_path, output_dir, chunk_size_mb),
                daemon=True
            )
            self._thread.start()

    def _split(self, file_path, output_dir, chunk_size_mb):
        fkx_path = None
        try:
            file_path = os.path.abspath(file_path)
            output_dir = os.path.abspath(output_dir)

            if not file_path or not os.path.exists(file_path):
                self._emit_error("请选择要拆分的文件")
                return

            if not os.path.isfile(file_path):
                self._emit_error("所选路径不是文件")
                return

            if not output_dir:
                self._emit_error("请选择输出目录")
                return

            try:
                chunk_size_mb = int(chunk_size_mb)
                if chunk_size_mb < 1 or chunk_size_mb > 1024:
                    self._emit_error("分片大小应在1-1024 MB之间")
                    return
            except ValueError:
                self._emit_error("分片大小必须是数字")
                return

            chunk_size = chunk_size_mb * 1024 * 1024

            if not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir)
                except Exception as e:
                    self._emit_error(f"无法创建输出目录: {str(e)}")
                    return

            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            num_chunks = (file_size + chunk_size - 1) // chunk_size

            self._emit_progress(0, num_chunks)

            fkx_filename = f"{file_name}.fkx"
            fkx_path = os.path.join(output_dir, fkx_filename)

            with open(fkx_path, 'w', encoding='utf-8') as fkx_file:
                fkx_file.write(f"filename={file_name}\n")
                fkx_file.write(f"total_size={file_size}\n")
                fkx_file.write(f"chunk_size={chunk_size}\n")
                fkx_file.write(f"num_chunks={num_chunks}\n")
                fkx_file.flush()

                with open(file_path, 'rb') as f:
                    for i in range(num_chunks):
                        if self._is_cancelled:
                            self._emit_status("拆分已取消（分片已保留）", '#cc0000')
                            self._emit_complete({'cancelled': True})
                            return

                        chunk_data = f.read(chunk_size)
                        chunk_filename = f"{file_name}-{i+1}.fk"
                        chunk_path = os.path.join(output_dir, chunk_filename)

                        with open(chunk_path, 'wb') as chunk_file:
                            chunk_file.write(chunk_data)

                        self._emit_status(f"正在计算分片SHA-256 {i+1}/{num_chunks}")
                        chunk_sha256 = calculate_sha256(
                            chunk_path,
                            cancel_check=lambda: self._is_cancelled,
                            progress_callback=lambda p, t: self._emit_chunk_progress(p, t)
                        )
                        if self._is_cancelled or chunk_sha256 is None:
                            self._emit_status("拆分已取消（分片已保留）", '#cc0000')
                            self._emit_complete({'cancelled': True})
                            return

                        chunk_info = {
                            'filename': chunk_filename,
                            'size': len(chunk_data),
                            'sha256': chunk_sha256
                        }
                        fkx_file.write(fkx_chunk_to_line(i + 1, chunk_info) + "\n")
                        fkx_file.flush()

                        self._emit_progress(i + 1, num_chunks)
                        self._emit_chunk_progress(100, 100)
                        self._emit_status(f"正在拆分 {i+1}/{num_chunks}")

            if self._is_cancelled:
                self._emit_status("拆分已取消（分片已保留）", '#cc0000')
                self._emit_complete({'cancelled': True})
                return

            self._emit_status("正在计算文件SHA-256...")
            file_sha256 = calculate_sha256(
                file_path,
                cancel_check=lambda: self._is_cancelled,
                progress_callback=lambda p, t: self._emit_chunk_progress(p, t)
            )
            if self._is_cancelled or file_sha256 is None:
                self._emit_status("拆分已取消（分片已保留）", '#cc0000')
                self._emit_complete({'cancelled': True})
                return

            with open(fkx_path, 'a', encoding='utf-8') as fkx_file:
                fkx_file.write(f"sha256={file_sha256}\n")

            self._emit_progress(num_chunks, num_chunks)
            self._emit_status(f"拆分完成！已生成 {num_chunks} 个分片", '#006600')
            self._emit_complete({
                'file_name': file_name,
                'file_size': file_size,
                'num_chunks': num_chunks,
                'fkx_filename': fkx_filename,
                'output_dir': output_dir,
            })

        except Exception as e:
            self._emit_error(f"拆分过程发生错误: {str(e)}")