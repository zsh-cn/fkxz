import os
import sys
import hashlib
from cli.utils import format_size, sanitize_filename, calculate_sha256, parse_fkx, print_progress


def read_local_fkx(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def merge_chunks(chunk_sources, output_path, num_chunks, total_size=0):
    merged_bytes = [0]
    with open(output_path, 'wb') as out_f:
        for i in range(num_chunks):
            chunk_path = chunk_sources[i]
            chunk_path = os.path.normpath(chunk_path)
            with open(chunk_path, 'rb') as chunk_f:
                for chunk in iter(lambda: chunk_f.read(65536), b""):
                    out_f.write(chunk)
                    merged_bytes[0] += len(chunk)
                    if total_size > 0:
                        print_progress(merged_bytes[0], total_size,
                                       prefix="合并: ",
                                       percent_text=f"{format_size(merged_bytes[0])}/{format_size(total_size)}")
                    else:
                        print_progress(i + 1, num_chunks,
                                       prefix="合并: ",
                                       suffix=f"{i+1}/{num_chunks}")
    sys.stdout.write("\n")
    sys.stdout.flush()


def cmd_merge(args):
    fkx_path = os.path.abspath(args.input)
    output_dir = os.path.abspath(args.output)

    if not os.path.exists(fkx_path):
        sys.stdout.write(f"错误: .fkx文件不存在 - {fkx_path}\n")
        sys.stdout.flush()
        sys.exit(1)
    if not fkx_path.endswith('.fkx'):
        sys.stdout.write("错误: 输入必须是.fkx文件\n")
        sys.stdout.flush()
        sys.exit(1)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    sys.stdout.write(f"解析文件信息: {fkx_path}\n")
    fkx_content = read_local_fkx(fkx_path)
    fkx_info = parse_fkx(fkx_content)

    if 'filename' not in fkx_info or 'chunks' not in fkx_info:
        sys.stdout.write("错误: 文件信息格式不正确\n")
        sys.stdout.flush()
        sys.exit(1)

    num_chunks = len(fkx_info['chunks'])
    total_size = sum(c['size'] for c in fkx_info['chunks'])
    base_path = os.path.dirname(fkx_path)

    sys.stdout.write(f"文件名: {fkx_info['filename']}\n")
    sys.stdout.write(f"文件大小: {format_size(total_size)}\n")
    sys.stdout.write(f"分片数: {num_chunks}\n")
    sys.stdout.write("\n")
    sys.stdout.flush()

    chunk_sources = {}
    for i, chunk_info in enumerate(fkx_info['chunks']):
        chunk_path = os.path.join(base_path, chunk_info['filename'])
        chunk_path = os.path.normpath(chunk_path)
        if not os.path.exists(chunk_path):
            sys.stdout.write(f"错误: 分片文件不存在 - {chunk_path}\n")
            sys.stdout.flush()
            sys.exit(1)
        chunk_sources[i] = chunk_path

    safe_filename = sanitize_filename(os.path.basename(fkx_info['filename']))
    output_path = os.path.join(output_dir, safe_filename)
    output_path = os.path.normpath(output_path)

    sys.stdout.write("正在合并文件...\n")
    sys.stdout.flush()
    merge_chunks(chunk_sources, output_path, num_chunks, total_size)

    if 'sha256' in fkx_info and not getattr(args, 'skip_sha256', False):
        sys.stdout.write("正在校验SHA-256...\n")
        sys.stdout.flush()
        actual_sha256 = hashlib.sha256()
        sha256_bytes = [0]
        with open(output_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b""):
                actual_sha256.update(chunk)
                sha256_bytes[0] += len(chunk)
                if total_size > 0:
                    print_progress(sha256_bytes[0], total_size,
                                   prefix="校验: ",
                                   percent_text=f"{format_size(sha256_bytes[0])}/{format_size(total_size)}")
        sys.stdout.write("\n")
        sys.stdout.flush()
        if actual_sha256.hexdigest() != fkx_info['sha256']:
            sys.stdout.write(f"错误: SHA-256校验失败!\n")
            sys.stdout.write(f"  期望: {fkx_info['sha256']}\n")
            sys.stdout.write(f"  实际: {actual_sha256.hexdigest()}\n")
            sys.stdout.flush()
            os.remove(output_path)
            sys.exit(1)
        sys.stdout.write(f"  SHA-256校验通过: {actual_sha256.hexdigest()}\n")
        sys.stdout.flush()

    sys.stdout.write(f"\n合并完成！\n")
    sys.stdout.write(f"  文件名: {safe_filename}\n")
    sys.stdout.write(f"  保存位置: {output_path}\n")