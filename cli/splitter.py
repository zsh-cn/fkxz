import os
import sys
import hashlib
from cli.utils import format_size, print_progress


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

    fkx_content = [
        f"filename={file_name}",
        f"total_size={file_size}",
        f"chunk_size={chunk_size}",
        f"num_chunks={num_chunks}"
    ]

    sha256_hash = hashlib.sha256()

    with open(file_path, 'rb') as f:
        for i in range(num_chunks):
            chunk_data = f.read(chunk_size)
            sha256_hash.update(chunk_data)

            chunk_filename = f"{file_name}-{i+1}.fk"
            chunk_path = os.path.join(output_dir, chunk_filename)

            with open(chunk_path, 'wb') as chunk_file:
                chunk_file.write(chunk_data)

            fkx_content.append(f"chunk_{i+1}={chunk_filename},{len(chunk_data)}")

            print_progress(i + 1, num_chunks,
                           prefix=f"拆分: ",
                           suffix=f"{i+1}/{num_chunks}")

    sys.stdout.write("\n")

    file_sha256 = sha256_hash.hexdigest()
    fkx_content.append(f"sha256={file_sha256}")

    fkx_filename = f"{file_name}.fkx"
    fkx_path = os.path.join(output_dir, fkx_filename)
    with open(fkx_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(fkx_content))

    sys.stdout.write(f"\n拆分完成！\n")
    sys.stdout.write(f"  分片数: {num_chunks}\n")
    sys.stdout.write(f"  信息文件: {fkx_filename}\n")
    sys.stdout.write(f"  SHA-256: {file_sha256}\n")
    sys.stdout.write(f"  保存位置: {output_dir}\n")