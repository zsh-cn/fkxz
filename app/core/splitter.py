import os
import threading

from core.base_worker import BaseWorker
from utils.helpers import calculate_sha256


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
        try:
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

            fkx_content = [
                f"filename={file_name}",
                f"total_size={file_size}",
                f"chunk_size={chunk_size}",
                f"num_chunks={num_chunks}"
            ]

            with open(file_path, 'rb') as f:
                for i in range(num_chunks):
                    if self._is_cancelled:
                        self._emit_status("拆分已取消", '#cc0000')
                        self._cleanup_chunks(output_dir, file_name, i)
                        self._emit_complete({'cancelled': True})
                        return

                    chunk_data = f.read(chunk_size)
                    chunk_filename = f"{file_name}-{i+1}.fk"
                    chunk_path = os.path.join(output_dir, chunk_filename)

                    with open(chunk_path, 'wb') as chunk_file:
                        chunk_file.write(chunk_data)

                    fkx_content.append(f"chunk_{i+1}={chunk_filename},{len(chunk_data)}")

                    self._emit_progress(i + 1, num_chunks)
                    self._emit_status(f"正在拆分 {i+1}/{num_chunks}")

            if self._is_cancelled:
                self._emit_status("拆分已取消", '#cc0000')
                self._emit_complete({'cancelled': True})
                return

            self._emit_status("正在计算文件SHA-256...")
            file_sha256 = calculate_sha256(file_path)
            fkx_content.append(f"sha256={file_sha256}")

            fkx_filename = f"{file_name}.fkx"
            fkx_path = os.path.join(output_dir, fkx_filename)
            with open(fkx_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(fkx_content))

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

    def _cleanup_chunks(self, output_dir, file_name, count):
        for i in range(1, count + 1):
            chunk_path = os.path.join(output_dir, f"{file_name}-{i}.fk")
            try:
                os.remove(chunk_path)
            except FileNotFoundError:
                pass
            except Exception:
                pass