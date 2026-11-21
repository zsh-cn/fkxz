import hashlib
import os
from typing import NamedTuple, Optional, Sequence, Tuple

import config


MANIFEST_SUFFIX = ".fkx"
CHUNK_SUFFIX = ".fk"

HASH_MODES = (config.HASH_MODE_BOTH, config.HASH_MODE_CHUNKS,
              config.HASH_MODE_FILE, config.HASH_MODE_NONE)


class Cancelled(Exception):
    pass


class ManifestError(ValueError):
    pass


class SplitResult(NamedTuple):
    fkx_path: str
    file_name: str
    chunk_size: int
    num_chunks: int
    total_size: int
    sha256: Optional[str]
    chunk_names: Tuple[str, ...]
    hash_mode: str


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
    if file_size <= 0:
        return 1
    return (file_size + chunk_size - 1) // chunk_size


def part_path(path, tag=None):
    suffix = f".{tag}" if tag else ""
    return f"{path}.{os.getpid()}{suffix}.part"


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


def write_text_atomic(path, text):
    part = part_path(path)
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


def _parse_int(value, field):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ManifestError(f"{field} 不是数字: {value}")


def validate_manifest(info):
    chunks = info.get('chunks') or []
    if not chunks:
        raise ManifestError("未找到任何 chunk 条目")
    if not str(info.get('filename') or '').strip():
        raise ManifestError("缺少 filename 字段")

    for index, chunk in enumerate(chunks, start=1):
        size = chunk.get('size')
        if not isinstance(size, int) or size < 0:
            raise ManifestError(f"chunk_{index} 大小非法: {size}")

    total = sum(chunk['size'] for chunk in chunks)
    declared_total = info.get('total_size')
    if declared_total not in (None, ''):
        declared_total = _parse_int(declared_total, 'total_size')
        if declared_total != total:
            raise ManifestError(
                f"清单总大小与分片之和不一致 ({declared_total} != {total})")

    declared_count = info.get('num_chunks')
    if declared_count not in (None, ''):
        declared_count = _parse_int(declared_count, 'num_chunks')
        if declared_count != len(chunks):
            raise ManifestError(
                f"清单分片数与条目数不一致 ({declared_count} != {len(chunks)})")

    return info


def manifest_hash_capability(info):
    chunks = info.get('chunks') or []
    has_chunk_sha = any(str(chunk.get('sha256') or '').strip() for chunk in chunks)
    has_file_sha = bool(str(info.get('sha256') or '').strip())
    return has_chunk_sha, has_file_sha


def supported_hash_modes(info):
    has_chunk_sha, has_file_sha = manifest_hash_capability(info)
    modes = []
    if has_chunk_sha and has_file_sha:
        modes.append(config.HASH_MODE_BOTH)
    if has_chunk_sha:
        modes.append(config.HASH_MODE_CHUNKS)
    if has_file_sha:
        modes.append(config.HASH_MODE_FILE)
    modes.append(config.HASH_MODE_NONE)
    return tuple(modes)


def resolve_hash_mode(info, mode):
    supported = supported_hash_modes(info)
    if mode in supported:
        return mode
    if mode == config.HASH_MODE_BOTH:
        for candidate in (config.HASH_MODE_CHUNKS, config.HASH_MODE_FILE):
            if candidate in supported:
                return candidate
        return config.HASH_MODE_NONE
    if mode in (config.HASH_MODE_CHUNKS, config.HASH_MODE_FILE):
        other = (config.HASH_MODE_FILE if mode == config.HASH_MODE_CHUNKS
                 else config.HASH_MODE_CHUNKS)
        return other if other in supported else config.HASH_MODE_NONE
    return config.HASH_MODE_NONE


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
                    raise ManifestError(f"chunk_{index} 大小不是数字: {parts[1].strip()}")
                if index in raw_chunks:
                    raise ManifestError(f"chunk 索引重复: chunk_{index}")
                chunk_info = {'filename': chunk_filename, 'size': chunk_size}
                if len(parts) >= 3 and parts[2].strip():
                    chunk_info['sha256'] = parts[2].strip()
                raw_chunks[index] = chunk_info
        else:
            info[key] = value.strip()

    if not raw_chunks:
        raise ManifestError("未找到任何 chunk 条目")

    sorted_indices = sorted(raw_chunks.keys())
    for i, idx in enumerate(sorted_indices):
        if idx != 1 + i:
            raise ManifestError(f"chunk 索引不连续: 期望 chunk_{1 + i}, 实际 chunk_{idx}")

    info['chunks'] = [raw_chunks[idx] for idx in sorted_indices]
    return validate_manifest(info)


def _quiet_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def split_file(source_path, output_dir, file_name, chunk_size, num_chunks=None,
               on_progress=None, should_stop=None, hash_mode=config.DEFAULT_HASH_MODE):
    if chunk_size <= 0:
        raise ValueError("分片大小必须大于 0")
    if hash_mode not in HASH_MODES:
        raise ValueError(f"未知的校验方式: {hash_mode}")

    file_size = os.path.getsize(source_path)
    if num_chunks is None:
        num_chunks = plan_num_chunks(file_size, chunk_size)

    hash_chunks = hash_mode in (config.HASH_MODE_BOTH, config.HASH_MODE_CHUNKS)
    hash_file = hash_mode in (config.HASH_MODE_BOTH, config.HASH_MODE_FILE)

    fkx_path = os.path.join(output_dir, manifest_name(file_name))
    manifest_part = part_path(fkx_path)
    chunk_names = []
    file_hasher = hashlib.sha256() if hash_file else None
    processed = 0
    total_size = 0
    digest = None

    try:
        with open(manifest_part, 'w', encoding='utf-8', newline='\n') as fkx_file, \
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
                chunk_part = part_path(chunk_path)
                chunk_hasher = hashlib.sha256() if hash_chunks else None
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
                            if chunk_hasher is not None:
                                chunk_hasher.update(block)
                            if file_hasher is not None:
                                file_hasher.update(block)
                            chunk_written += len(block)
                            processed += len(block)
                            if on_progress:
                                on_progress(processed, file_size, i + 1, num_chunks)
                        out.flush()
                except BaseException:
                    _quiet_remove(chunk_part)
                    raise

                if chunk_written < chunk_size and i < num_chunks - 1:
                    _quiet_remove(chunk_part)
                    raise RuntimeError("源文件在分块过程中被截断")
                if chunk_written == 0 and file_size > 0:
                    _quiet_remove(chunk_part)
                    raise RuntimeError("源文件在分块过程中被截断")

                os.replace(chunk_part, chunk_path)
                chunk_names.append(name)
                line = f"chunk_{i + 1}={name},{chunk_written}"
                if chunk_hasher is not None:
                    line += f",{chunk_hasher.hexdigest()}"
                fkx_file.write(f"{line}\n")
                fkx_file.flush()

            try:
                source.seek(0, os.SEEK_END)
                current_size = source.tell()
            except OSError:
                current_size = processed
            if current_size != processed:
                raise RuntimeError("源文件在分块过程中被修改")

            total_size = processed
            fkx_file.write(f"total_size={total_size}\n")
            if file_hasher is not None:
                digest = file_hasher.hexdigest()
                fkx_file.write(f"sha256={digest}\n")
            fkx_file.flush()
            os.fsync(fkx_file.fileno())

        os.replace(manifest_part, fkx_path)
    except BaseException:
        _quiet_remove(manifest_part)
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
        hash_mode=hash_mode,
    )


def merge_chunks(chunk_paths: Sequence[Optional[str]], target_path,
                 compute_sha256=True, on_progress=None, should_stop=None):
    merge_part = part_path(target_path)
    hasher = hashlib.sha256() if compute_sha256 else None
    merged_bytes = 0

    try:
        with open(merge_part, 'wb') as out:
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

        os.replace(merge_part, target_path)
    except BaseException:
        _quiet_remove(merge_part)
        raise

    return MergeResult(
        path=target_path,
        size=merged_bytes,
        sha256=hasher.hexdigest() if hasher is not None else None,
    )
