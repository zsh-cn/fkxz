import os
import sys
import hashlib
from cli.utils import format_size, print_progress, calculate_sha256


def _report_split_sha256_progress(processed, total):
    pct = min(processed / total * 100, 100) if total > 0 else 100
    sys.stdout.write(
        f"\r    SHA-256: {format_size(processed)}/{format_size(total)} ({pct:.1f}%)" + " " * 20
    )
    sys.stdout.flush()


def cmd_split(args):
    file_path = os.path.abspath(args.input)
    output_dir = os.path.abspath(args.output)
    chunk_size_mb = args.chunk_size

    if not os.path.exists(file_path):
        sys.stdout.write(f"错误: 文件不存在 - {file_path}\n")
        sys.stdout.flush()
        sys.exit(1)
    if not os.path.isfile(file_path):
        sys.stdout.write(f"错误: 路径不是文件 - {file_path}\n")
        sys.stdout.flush()
        sys.exit(1)
    if chunk_size_mb < 1 or chunk_size_mb > 1024:
        sys.stdout.write("错误: 分片大小应在1-1024 MB之间\n")
        sys.stdout.flush()
        sys.exit(1)

    chunk_size = chunk_size_mb * 1024 * 1024

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    num_chunks = max(1, (file_size + chunk_size - 1) // chunk_size)

    sys.stdout.write(f"文件: {file_name}\n")
    sys.stdout.write(f"大小: {format_size(file_size)}\n")
    sys.stdout.write(f"分片大小: {chunk_size_mb} MB\n")
    sys.stdout.write(f"分片数: {num_chunks}\n")
    sys.stdout.write(f"输出目录: {output_dir}\n")
    sys.stdout.write("\n")
    sys.stdout.flush()

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
                chunk_data = f.read(chunk_size)
                chunk_filename = f"{file_name}-{i+1}.fk"
                chunk_path = os.path.join(output_dir, chunk_filename)

                with open(chunk_path, 'wb') as chunk_file:
                    chunk_file.write(chunk_data)

                sys.stdout.write(f"    计算分片SHA-256 {i+1}/{num_chunks}...")
                sys.stdout.flush()
                chunk_sha256 = calculate_sha256(
                    chunk_path,
                    progress_callback=lambda p, t: _report_split_sha256_progress(p, t)
                )
                sys.stdout.write("\r" + " " * 60 + "\r")
                sys.stdout.flush()
                fkx_file.write(f"chunk_{i+1}={chunk_filename},{len(chunk_data)},{chunk_sha256}\n")
                fkx_file.flush()

                print_progress(i + 1, num_chunks,
                               prefix=f"拆分: ",
                               suffix=f"{i+1}/{num_chunks}")

    sys.stdout.write("\n")

    sys.stdout.write("正在计算文件SHA-256...\n")
    sys.stdout.flush()
    file_sha256 = calculate_sha256(
        file_path,
        progress_callback=lambda p, t: _report_split_sha256_progress(p, t)
    )
    sys.stdout.write("\n")

    with open(fkx_path, 'a', encoding='utf-8') as f:
        f.write(f"sha256={file_sha256}\n")

    sys.stdout.write(f"\n拆分完成！\n")
    sys.stdout.write(f"  分片数: {num_chunks}\n")
    sys.stdout.write(f"  信息文件: {fkx_filename}\n")
    sys.stdout.write(f"  SHA-256: {file_sha256}\n")
    sys.stdout.write(f"  保存位置: {output_dir}\n")