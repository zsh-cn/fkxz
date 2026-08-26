import os
import sys
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
                                       suffix=f"{format_size(merged_bytes[0])}/{format_size(total_size)}")
                    else:
                        print_progress(i + 1, num_chunks,
                                       prefix="合并: ",
                                       suffix=f"{i+1}/{num_chunks}")
    sys.stdout.write("\n")
    sys.stdout.flush()


def cmd_merge(args):
    fkx_path = args.input
    output_dir = args.output

    if not os.path.exists(fkx_path):
        print(f"错误: .fkx文件不存在 - {fkx_path}")
        sys.exit(1)
    if not fkx_path.endswith('.fkx'):
        print(f"错误: 输入必须是.fkx文件")
        sys.exit(1)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    print(f"解析文件信息: {fkx_path}")
    fkx_content = read_local_fkx(fkx_path)
    fkx_info = parse_fkx(fkx_content)

    if 'filename' not in fkx_info or 'chunks' not in fkx_info:
        print("错误: 文件信息格式不正确")
        sys.exit(1)

    num_chunks = len(fkx_info['chunks'])
    total_size = sum(c['size'] for c in fkx_info['chunks'])
    base_path = os.path.dirname(os.path.abspath(fkx_path))

    print(f"文件名: {fkx_info['filename']}")
    print(f"文件大小: {format_size(total_size)}")
    print(f"分片数: {num_chunks}")
    print()

    chunk_sources = {}
    for i, chunk_info in enumerate(fkx_info['chunks']):
        chunk_path = os.path.join(base_path, chunk_info['filename'])
        chunk_path = os.path.normpath(chunk_path)
        if not os.path.exists(chunk_path):
            print(f"错误: 分片文件不存在 - {chunk_path}")
            sys.exit(1)
        chunk_sources[i] = chunk_path

    safe_filename = sanitize_filename(os.path.basename(fkx_info['filename']))
    output_path = os.path.join(output_dir, safe_filename)
    output_path = os.path.normpath(output_path)

    print("正在合并文件...")
    merge_chunks(chunk_sources, output_path, num_chunks, total_size)

    if 'sha256' in fkx_info:
        print("正在校验SHA-256...")
        actual_sha256 = calculate_sha256(output_path)
        if actual_sha256 != fkx_info['sha256']:
            print(f"错误: SHA-256校验失败!")
            print(f"  期望: {fkx_info['sha256']}")
            print(f"  实际: {actual_sha256}")
            os.remove(output_path)
            sys.exit(1)
        print(f"  SHA-256校验通过: {actual_sha256}")

    print(f"\n合并完成！")
    print(f"  文件名: {safe_filename}")
    print(f"  保存位置: {output_path}")