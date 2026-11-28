import os
import sys
import shutil
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "fkxz-main"))
DOCS_DIR = BASE_DIR
DIST_DIR = os.path.join(DOCS_DIR, "dist")
SOURCE_ZIP_NAME = "fkxz.zip"
SOURCE_ROOT = "fkxz"


def _find_venv_python():
    venv_python = os.path.join(MAIN_DIR, ".venv", "Scripts", "python.exe")
    if os.path.isfile(venv_python):
        return venv_python
    return None


VENV_PYTHON = _find_venv_python()
if VENV_PYTHON:
    PYTHON_EXE = VENV_PYTHON
else:
    PYTHON_EXE = sys.executable


# ---------------------------------------------------------------------------
# 产物体积优化配置
# ---------------------------------------------------------------------------

# 程序没有用到、但会被 PyInstaller 顺带收集的模块，显式排除以缩小 PYZ/exe 体积。
EXCLUDE_MODULES = (
    # 文档 / 测试 / 开发工具链
    "pydoc", "pydoc_data", "doctest", "unittest", "test", "idlelib", "lib2to3",
    "distutils", "setuptools", "pkg_resources", "_distutils_hack", "packaging",
    "ensurepip", "venv", "pdb", "bdb", "cProfile", "pstats", "profile",
    "timeit", "trace", "tracemalloc",
    "tkinter.test", "turtle", "turtledemo", "curses",
    # 未使用的标准库（注意：shlex 被 webbrowser 引用、calendar 被 http.cookiejar 引用，不能排除）
    "argparse", "xmlrpc", "http.server", "socketserver", "sqlite3", "dbm", "shelve",
    "smtplib", "imaplib", "poplib", "ftplib", "nntplib", "mailbox",
    "multiprocessing", "concurrent",
    "statistics", "fractions", "decimal", "_pydecimal", "_decimal",
    "csv", "zoneinfo", "gettext", "difflib", "pickle",
    # 压缩/序列化相关（zipfile 不能排除：PyInstaller 的 runtime hook 依赖它）
    "compression", "bz2", "lzma", "tarfile", "xml",
)

# 字节码优化级别：2 = 去掉 docstring / 断言，可让 .pyc 再小一截。
OPTIMIZE_LEVEL = 2

# 每个程序运行时真正会加载的图标（其余 ico/png 在打包后裁剪掉）。
APP_ICONS = {
    "wjfk": {"wjfk.png"},
    "wjxz": {"wjxz.png"},
    "wjfkxz": {"wjfkxz.png", "wjfk.png", "wjxz.png"},
}

# 打包后可安全删除的冗余目录（Tcl/Tk 的本地化、示例与调试数据）。
PRUNABLE_DIR_NAMES = {"msgs", "tzdata", "demos", "doc", "docs"}
PRUNABLE_SUFFIXES = (".pdb", ".chm", ".lib", ".exp", ".map")


def _common_args(name, icon, entry):
    cmd = [
        PYTHON_EXE, "-m", "PyInstaller",
        "--onedir",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--log-level", "WARN",
        "--optimize", str(OPTIMIZE_LEVEL),
        "--name", name,
        "--distpath", DIST_DIR,
        "--icon", icon,
        "--add-data", f"icon{os.pathsep}icon",
        "--noupx",
    ]
    for module in EXCLUDE_MODULES:
        cmd += ["--exclude-module", module]
    cmd.append(entry)
    return cmd


def build_wjfk():
    return _common_args("wjfk", "icon/wjfk.ico", "wjfk.py")


def build_wjxz():
    cmd = _common_args("wjxz", "icon/wjxz.ico", "wjxz.py")
    cmd[-1:-1] = ["--hidden-import", "curl_cffi"]
    return cmd


def build_wjfkxz():
    return _common_args("wjfkxz", "icon/wjfkxz.ico", "main.py")


BUILD_TASKS = [
    ("wjfk.exe", build_wjfk),
    ("wjxz.exe", build_wjxz),
    ("wjfkxz.exe", build_wjfkxz),
]

APP_NAMES = tuple(name.replace(".exe", "") for name, _ in BUILD_TASKS)


def run_build(name, cmd_func):
    cmd = cmd_func()
    print(f"[{name}] 开始打包: {' '.join(cmd)}")

    key = name.replace(".exe", "")
    cache_dir = os.path.join(MAIN_DIR, "build", key, "pyicache")
    env = os.environ.copy()
    env["PYINSTALLER_CONFIG_DIR"] = cache_dir
    if "--workpath" not in cmd:
        cmd = cmd + ["--workpath", os.path.join(MAIN_DIR, "build", key)]

    process = subprocess.run(
        cmd,
        cwd=MAIN_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    if process.returncode == 0:
        print(f"[{name}] 打包成功")
    else:
        print(f"[{name}] 打包失败 (code={process.returncode})")
        print(f"[{name}] stdout:\n{process.stdout[-2000:]}")
        print(f"[{name}] stderr:\n{process.stderr[-2000:]}")

    return name, process.returncode


def cleanup():
    build_dir = os.path.join(MAIN_DIR, "build")
    if os.path.isdir(build_dir):
        shutil.rmtree(build_dir)
        print("已删除 build/ 目录")

    for name, _ in BUILD_TASKS:
        spec_name = name.replace(".exe", "")
        spec_file = os.path.join(MAIN_DIR, f"{spec_name}.spec")
        if os.path.isfile(spec_file):
            os.remove(spec_file)
            print(f"已删除 {spec_name}.spec")


# ---------------------------------------------------------------------------
# 产物裁剪：删掉 PyInstaller 带进来但运行时用不到的文件
# ---------------------------------------------------------------------------

def _dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for fname in files:
            try:
                total += os.path.getsize(os.path.join(root, fname))
            except OSError:
                pass
    return total


def _remove_path(path, counter):
    try:
        if os.path.isdir(path):
            counter[0] += _dir_size(path)
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.isfile(path):
            counter[0] += os.path.getsize(path)
            os.remove(path)
    except OSError:
        pass


def prune_output(name, src_dir):
    """裁剪 onedir 产物：调试符号、冗余图标、多余的包与 Tcl/Tk 数据。"""
    before = _dir_size(src_dir)
    removed = [0]
    internal = os.path.join(src_dir, "_internal")
    root_dir = internal if os.path.isdir(internal) else src_dir

    # 1) 调试/链接期文件
    for root, _, files in os.walk(src_dir):
        for fname in files:
            if fname.lower().endswith(PRUNABLE_SUFFIXES):
                _remove_path(os.path.join(root, fname), removed)

    # 2) 图标：只保留该程序运行时真正加载的 png，ico 只在打包阶段用到
    icon_dir = os.path.join(root_dir, "icon")
    keep_icons = APP_ICONS.get(name, set())
    if os.path.isdir(icon_dir):
        for fname in os.listdir(icon_dir):
            lower = fname.lower()
            if lower.endswith(".ico") or (lower.endswith(".png") and fname not in keep_icons):
                _remove_path(os.path.join(icon_dir, fname), removed)

    # 3) 打包工具残留（即使被排除也可能留下空壳）
    for pkg in ("setuptools", "pkg_resources", "_distutils_hack", "packaging"):
        _remove_path(os.path.join(root_dir, pkg), removed)

    # 4) Tcl/Tk 的本地化消息、时区、示例数据
    for root, dirs, _ in os.walk(root_dir):
        parent = os.path.basename(root).lower()
        if "tcl" not in parent and "tk" not in parent:
            continue
        for dname in list(dirs):
            if dname.lower() in PRUNABLE_DIR_NAMES:
                _remove_path(os.path.join(root, dname), removed)
                dirs.remove(dname)

    # 5) 清理空目录
    for root, dirs, files in os.walk(src_dir, topdown=False):
        if root == src_dir:
            continue
        if not dirs and not files:
            try:
                os.rmdir(root)
            except OSError:
                pass

    after = _dir_size(src_dir)
    saved = max(0, before - after)
    pct = saved / before * 100 if before else 0.0
    print(f"[prune] {name}/ {before} -> {after} bytes, 减少 {saved} bytes ({pct:.1f}%)")


def prune_all():
    for fname in sorted(os.listdir(DIST_DIR)) if os.path.isdir(DIST_DIR) else []:
        if fname not in APP_NAMES:
            continue
        src_dir = os.path.join(DIST_DIR, fname)
        if os.path.isdir(src_dir):
            prune_output(fname, src_dir)


SOURCE_FILES = [
    "README.md",
    "LICENSE",
    "requirements.txt",
    "config.py",
    "main.py",
    "wjfk.py",
    "wjxz.py",
    "core.py",
    "utils.py",
    "icon/wjfk.ico",
    "icon/wjfk.png",
    "icon/wjfkxz.ico",
    "icon/wjfkxz.png",
    "icon/wjxz.ico",
    "icon/wjxz.png",
    "web/favicon.png",
    "web/index.html",
    "web/sw.js",
]


def _zip_directory(src_dir, zip_path, arc_root):
    """把整个目录压缩到 zip 中，zip 内以 arc_root 作为顶层目录。"""
    total = 0
    file_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(src_dir):
            dirs.sort()
            for fname in sorted(files):
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, src_dir).replace(os.sep, "/")
                zf.write(full, arcname=f"{arc_root}/{rel}")
                total += os.path.getsize(full)
                file_count += 1
    return total, file_count


def create_package_zips():
    """把每个 onedir 产物目录压缩为 zip（解压后得到同名文件夹，双击其中 exe 即可运行）。"""
    if not os.path.isdir(DIST_DIR):
        print("dist 目录不存在，跳过压缩")
        return

    for fname in sorted(os.listdir(DIST_DIR)):
        if fname not in APP_NAMES:
            continue
        src_dir = os.path.join(DIST_DIR, fname)
        if not os.path.isdir(src_dir):
            continue
        exe_name = f"{fname}.exe"
        if not os.path.isfile(os.path.join(src_dir, exe_name)):
            print(f"[zip] 跳过 {fname}：目录内未找到 {exe_name}")
            continue

        zip_path = os.path.join(DIST_DIR, f"{fname}.zip")
        total, file_count = _zip_directory(src_dir, zip_path, fname)
        zip_size = os.path.getsize(zip_path)
        ratio = zip_size / total * 100 if total else 0.0
        print(f"[zip] {fname}/ ({file_count} 个文件, {total} bytes) -> {fname}.zip ({zip_size} bytes), 压缩率 {ratio:.1f}%")
        shutil.rmtree(src_dir, ignore_errors=True)
        print(f"[zip] 已删除 {fname}/ 目录")


def clean_dist_artifacts():
    if not os.path.isdir(DIST_DIR):
        return

    removed = []
    for fname in os.listdir(DIST_DIR):
        path = os.path.join(DIST_DIR, fname)
        try:
            if os.path.isdir(path):
                if fname not in APP_NAMES:
                    continue
                shutil.rmtree(path)
            elif fname.lower().endswith((".zip", ".exe")):
                os.remove(path)
            else:
                continue
            removed.append(fname)
        except OSError as exc:
            print(f"[warn] 无法删除 {fname}: {exc}")

    if removed:
        print(f"[warn] 已清除 dist 中残留的旧产物: {', '.join(removed)}")


def create_source_zip():
    out_path = os.path.join(DOCS_DIR, SOURCE_ZIP_NAME)
    added = 0
    skipped = []
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in SOURCE_FILES:
            src = os.path.join(MAIN_DIR, *rel.split("/"))
            if not os.path.isfile(src):
                skipped.append(rel)
                continue
            zf.write(src, arcname=f"{SOURCE_ROOT}/{rel}")
            added += 1

    print(f"源码压缩包已生成: {out_path} (包含 {added} 个文件)")
    if skipped:
        print(f"跳过不存在的文件: {', '.join(skipped)}")

    return out_path


def copy_web_to_docs():
    web_src = os.path.join(MAIN_DIR, "web")
    web_dest = os.path.join(DOCS_DIR, "wjxz")
    if not os.path.isdir(web_src):
        print("web 目录不存在，跳过同步")
        return

    os.makedirs(web_dest, exist_ok=True)
    added = 0
    replaced = 0
    for root, _, files in os.walk(web_src):
        rel = os.path.relpath(root, web_src)
        target_dir = web_dest if rel == "." else os.path.join(web_dest, rel)
        os.makedirs(target_dir, exist_ok=True)
        for fname in files:
            dst = os.path.join(target_dir, fname)
            if os.path.exists(dst):
                replaced += 1
            else:
                added += 1
            shutil.copy2(os.path.join(root, fname), dst)

    print(f"web 资源已同步到: {web_dest} (新增 {added} 个, 覆盖 {replaced} 个)")


def main():
    os.makedirs(DIST_DIR, exist_ok=True)

    if VENV_PYTHON:
        print(f"使用虚拟环境: {PYTHON_EXE}")
    else:
        print(f"未找到虚拟环境, 使用当前 Python: {PYTHON_EXE}")

    print(f"字节码优化级别: {OPTIMIZE_LEVEL}, 排除模块: {len(EXCLUDE_MODULES)} 个")

    max_workers = min(len(BUILD_TASKS), os.cpu_count() or 4)
    print(f"并行打包 {len(BUILD_TASKS)} 个目标, 最大并发数: {max_workers}")
    print("=" * 60)

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_build, name, cmd_func): name for name, cmd_func in BUILD_TASKS}
        for future in as_completed(futures):
            name, returncode = future.result()
            results[name] = returncode

    print("=" * 60)
    print("打包结果汇总:")
    all_ok = True
    for name, _ in BUILD_TASKS:
        rc = results.get(name, -1)
        status = "成功" if rc == 0 else f"失败 ({rc})"
        if rc != 0:
            all_ok = False
        print(f"  {name}: {status}")

    if all_ok:
        print("全部打包成功!")
        print(f"已放置到: {DIST_DIR}")
        print("=" * 60)
        print("裁剪无用文件...")
        prune_all()

        print("=" * 60)
        print("压缩各程序目录为 zip...")
        create_package_zips()

        print("=" * 60)
        cleanup()
        create_source_zip()
        copy_web_to_docs()
    else:
        print("部分目标打包失败, 请检查上方日志。")
        clean_dist_artifacts()

        print("=" * 60)
        cleanup()
        print("已跳过源码压缩包与网页资源同步, docs 产物保持上次成功构建的状态。")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
