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


def build_wjfk():
    return [
        PYTHON_EXE, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--name", "wjfk",
        "--distpath", DIST_DIR,
        "--icon", "icon/wjfk.ico",
        "--add-data", f"icon{os.pathsep}icon",
        "wjfk.py",
    ]


def build_wjxz():
    return [
        PYTHON_EXE, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--name", "wjxz",
        "--distpath", DIST_DIR,
        "--icon", "icon/wjxz.ico",
        "--add-data", f"icon{os.pathsep}icon",
        "--hidden-import", "curl_cffi",
        "wjxz.py",
    ]


def build_wjfkxz():
    return [
        PYTHON_EXE, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--name", "wjfkxz",
        "--distpath", DIST_DIR,
        "--icon", "icon/wjfkxz.ico",
        "--add-data", f"icon{os.pathsep}icon",
        "main.py",
    ]


BUILD_TASKS = [
    ("wjfk.exe", build_wjfk),
    ("wjxz.exe", build_wjxz),
    ("wjfkxz.exe", build_wjfkxz),
]


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

def create_exe_zips():
    if not os.path.isdir(DIST_DIR):
        print("dist 目录不存在，跳过压缩")
        return

    for fname in os.listdir(DIST_DIR):
        if not fname.lower().endswith(".exe"):
            continue
        exe_path = os.path.join(DIST_DIR, fname)
        base = os.path.splitext(fname)[0]
        zip_path = os.path.join(DIST_DIR, f"{base}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            zf.write(exe_path, arcname=fname)
        exe_size = os.path.getsize(exe_path)
        zip_size = os.path.getsize(zip_path)
        print(f"[zip] {fname} ({exe_size} bytes) -> {base}.zip ({zip_size} bytes), 压缩率 {zip_size / exe_size * 100:.1f}%")
        os.remove(exe_path)
        print(f"[zip] 已删除 {fname}")


def clean_dist_artifacts():
    if not os.path.isdir(DIST_DIR):
        return

    removed = []
    for fname in os.listdir(DIST_DIR):
        if not fname.lower().endswith((".zip", ".exe")):
            continue
        try:
            os.remove(os.path.join(DIST_DIR, fname))
            removed.append(fname)
        except OSError as exc:
            print(f"[warn] 无法删除 {fname}: {exc}")

    if removed:
        print(f"[warn] 已清除 dist 中残留的旧产物: {', '.join(removed)}")


def create_source_zip():
    out_path = os.path.join(DOCS_DIR, SOURCE_ZIP_NAME)
    added = 0
    skipped = []
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
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
        print("压缩各 exe 为 zip...")
        create_exe_zips()
    else:
        print("部分目标打包失败, 请检查上方日志。")
        clean_dist_artifacts()

    print("=" * 60)
    cleanup()
    create_source_zip()
    copy_web_to_docs()

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
