import hashlib
import os
from typing import NamedTuple, Optional, Sequence, Tuple

import config


MANIFEST_SUFFIX = ".fkx"
CHUNK_SUFFIX = ".fk"


class Cancelled(Exception):
    pass


class SplitResult(NamedTuple):
    fkx_path: str
    file_name: str
    chunk_size: int
    num_chunks: int
    total_size: int
    sha256: str
    chunk_names: Tuple[str, ...]


class MergeResult(NamedTuple):
    path: str
    size: int
    sha256: Optional[str]


def manifest_name(file_name):
    return f"{file_name}{MANIFEST_SUFFIX}"


def chunk_name(file_name, index):
    return f"{file_name}-{index}{CHUNK_SUFFIX}"


def plan_num_chunks(file_size, chunk_size):
    if chunk_size <= 0:
        raise ValueError("分片大小必须大于 0")
    return (file_size + chunk_size - 1) // chunk_size


def decode_fkx(raw):
    if isinstance(raw, str):
        return raw
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8-sig', errors='replace')


def read_fkx_text(file_path):
    with open(file_path, 'rb') as handle:
        return decode_fkx(handle.read())


def write_fkx_text(path, text):
    part = _part_path(path)
    try:
        with open(part, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(part, path)
        return True
    except OSError:
        _quiet_remove(part)
        return False


def parse_fkx(content):
    info = {'chunks': []}
    raw_chunks = {}

    content = decode_fkx(content)
    content = content.lstrip('\ufeff')

    for raw_line in content.splitlines():
        line = raw_line.strip().lstrip('\ufeff')
        if not line or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if key.startswith('chunk_'):
            try:
                index = int(key.split('_', 1)[1])
            except (IndexError, ValueError):
                continue
            parts = value.split(',')
            if len(parts) >= 2:
                chunk_filename = os.path.basename(parts[0].strip())
                try:
                    chunk_size = int(parts[1])
                except ValueError:
                    raise ValueError(f"chunk_{index} 大小不是数字: {parts[1].strip()}")
                if index in raw_chunks:
                    raise ValueError(f"chunk 索引重复: chunk_{index}")
                chunk_info = {'filename': chunk_filename, 'size': chunk_size}
                if len(parts) >= 3 and parts[2].strip():
                    chunk_info['sha256'] = parts[2].strip()
                raw_chunks[index] = chunk_info
        else:
            info[key] = value.strip()

    if not raw_chunks:
        raise ValueError("未找到任何 chunk 条目")

    sorted_indices = sorted(raw_chunks.keys())
    for i, idx in enumerate(sorted_indices):
        if idx != 1 + i:
            raise ValueError(f"chunk 索引不连续: 期望 chunk_{1 + i}, 实际 chunk_{idx}")

    info['chunks'] = [raw_chunks[idx] for idx in sorted_indices]
    return info


def _part_path(path):
    return f"{path}.{os.getpid()}.part"


def _quiet_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def split_file(source_path, output_dir, file_name, chunk_size, num_chunks=None,
               on_progress=None, should_stop=None):
    if chunk_size <= 0:
        raise ValueError("分片大小必须大于 0")
    file_size = os.path.getsize(source_path)
    if num_chunks is None:
        num_chunks = plan_num_chunks(file_size, chunk_size)

    fkx_path = os.path.join(output_dir, manifest_name(file_name))
    part_fkx_path = _part_path(fkx_path)
    chunk_names = []
    file_hasher = hashlib.sha256()
    processed = 0
    total_size = 0
    digest = file_hasher.hexdigest()

    try:
        with open(part_fkx_path, 'w', encoding='utf-8', newline='\n') as fkx_file, \
                open(source_path, 'rb') as source:
            fkx_file.write(f"filename={file_name}\n")
            fkx_file.write(f"chunk_size={chunk_size}\n")
            fkx_file.write(f"num_chunks={num_chunks}\n")
            fkx_file.flush()

            for i in range(num_chunks):
                if should_stop and should_stop():
                    raise Cancelled()

                name = chunk_name(file_name, i + 1)
                chunk_path = os.path.join(output_dir, name)
                chunk_part = _part_path(chunk_path)
                chunk_hasher = hashlib.sha256()
                chunk_written = 0

                try:
                    with open(chunk_part, 'wb') as out:
                        while chunk_written < chunk_size:
                            if should_stop and should_stop():
                                raise Cancelled()
                            block = source.read(min(config.IO_BLOCK_SIZE, chunk_size - chunk_written))
                            if not block:
                                break
                            out.write(block)
                            chunk_hasher.update(block)
                            file_hasher.update(block)
                            chunk_written += len(block)
                            processed += len(block)
                            if on_progress:
                                on_progress(processed, file_size, i + 1, num_chunks)
                        out.flush()
                        os.fsync(out.fileno())
                except BaseException:
                    _quiet_remove(chunk_part)
                    raise

                if chunk_written == 0:
                    _quiet_remove(chunk_part)
                    raise RuntimeError("源文件在分块过程中被截断")
                if chunk_written < chunk_size and i < num_chunks - 1:
                    _quiet_remove(chunk_part)
                    raise RuntimeError("源文件在分块过程中被截断")

                os.replace(chunk_part, chunk_path)
                chunk_names.append(name)
                fkx_file.write(f"chunk_{i + 1}={name},{chunk_written},{chunk_hasher.hexdigest()}\n")
                fkx_file.flush()

            total_size = processed
            digest = file_hasher.hexdigest()
            fkx_file.write(f"total_size={total_size}\n")
            fkx_file.write(f"sha256={digest}\n")
            fkx_file.flush()

        os.replace(part_fkx_path, fkx_path)
    except BaseException:
        _quiet_remove(part_fkx_path)
        for name in chunk_names:
            _quiet_remove(os.path.join(output_dir, name))
        raise

    return SplitResult(
        fkx_path=fkx_path,
        file_name=file_name,
        chunk_size=chunk_size,
        num_chunks=num_chunks,
        total_size=total_size,
        sha256=digest,
        chunk_names=tuple(chunk_names),
    )


def merge_chunks(chunk_paths: Sequence[Optional[str]], target_path,
                 compute_sha256=True, on_progress=None, should_stop=None):
    part_path = _part_path(target_path)
    hasher = hashlib.sha256() if compute_sha256 else None
    merged_bytes = 0

    try:
        with open(part_path, 'wb') as out:
            for index, chunk_path in enumerate(chunk_paths, start=1):
                if should_stop and should_stop():
                    raise Cancelled()
                if not chunk_path:
                    raise FileNotFoundError(f"缺少分片 {index}")
                with open(os.path.normpath(chunk_path), 'rb') as chunk_file:
                    while True:
                        block = chunk_file.read(config.IO_BLOCK_SIZE)
                        if not block:
                            break
                        out.write(block)
                        if hasher is not None:
                            hasher.update(block)
                        merged_bytes += len(block)
                        if on_progress:
                            on_progress(merged_bytes)
            out.flush()
            os.fsync(out.fileno())

        if should_stop and should_stop():
            raise Cancelled()

        os.replace(part_path, target_path)
    except BaseException:
        _quiet_remove(part_path)
        raise

    return MergeResult(
        path=target_path,
        size=merged_bytes,
        sha256=hasher.hexdigest() if hasher is not None else None,
    )
