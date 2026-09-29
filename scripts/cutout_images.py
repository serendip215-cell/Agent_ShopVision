"""Suning 商品图批量抠图（rembg + isnet-general-use），一键运行。

流程：
  [1/4] 环境检查：Python 版本、缺的依赖自动 pip 安装
  [2/4] 准备模型：优先用项目内 scripts/models/ 里放的模型（离线可用），
        没有则用本机缓存，再没有才在线下载（需联网）
  [3/4] 并发抠图：按 CPU 核数和可用内存自动选并发数，每 100 张打印进度
  [4/4] 输出透明底 PNG，统计成功/跳过/失败

用法（项目根目录）：python scripts/cutout_images.py
输出：data/raw_data/Suning_data/images_cutout/<原名>.png
断点续跑：输出已存在则跳过，中断/失败后直接重跑即可接着抠。
并发覆盖：环境变量 CUTOUT_WORKERS=8（如内存不足或想跑更少）。
试跑几条：环境变量 CUTOUT_LIMIT=3 只跑前 3 张。
"""
import importlib
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

MODEL = "isnet-general-use"
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw_data" / "Suning_data" / "images"
DST = ROOT / "data" / "raw_data" / "Suning_data" / "images_cutout"
MODEL_DIR = ROOT / "scripts" / "models"  # 把 isnet-general-use.onnx 放这里即可离线使用

# import 名 -> pip 包名，探测到缺哪个就装哪个
REQUIRED = {
    "rembg": "rembg[cpu]",
    "PIL": "pillow",
    "numpy": "numpy",
    "onnxruntime": "onnxruntime",
    "pooch": "pooch",
    "scipy": "scipy",
    "imagehash": "imagehash",
    "filetype": "filetype",
}


def _log(msg: str) -> None:
    print(msg, flush=True)


def die(msg: str) -> None:
    _log(f"错误: {msg}")
    sys.exit(1)


def _missing_pkgs() -> list:
    out = []
    for mod, pkg in REQUIRED.items():
        try:
            importlib.import_module(mod)
        except Exception:
            out.append(pkg)
    return sorted(set(out))


def ensure_deps() -> None:
    """最多补装 3 轮，仍缺就给出可手动执行的命令。"""
    for _ in range(3):
        missing = _missing_pkgs()
        if not missing:
            return
        _log(f"      缺少 {missing}，自动 pip 安装 ...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-q", *missing]
            )
        except (subprocess.CalledProcessError, OSError) as e:
            die(
                f"pip 安装失败（{e}）。请手动执行后重跑:\n"
                f"      python -m pip install {' '.join(missing)}"
            )
    die(f"依赖安装后仍缺失: {_missing_pkgs()}，请检查 pip 是否可用")


def ensure_model() -> None:
    """模型三级获取：项目内放置 > 本机缓存 > 在线下载。"""
    from rembg import new_session
    from rembg.sessions import sessions

    fname = f"{MODEL}.onnx"
    try:
        cache = Path(sessions[MODEL].model_dir())
    except Exception:
        cache = Path.home() / ".rembg" / "models" / MODEL
    bundled = MODEL_DIR / fname

    if (cache / fname).exists():
        _log(f"      模型已缓存: {cache / fname}")
    elif bundled.exists():
        cache.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled, cache / fname)
        _log(f"      使用项目内模型: {bundled}")
    else:
        _log("      缓存为空且项目内无模型，将在线下载（需联网，约 170MB）")

    try:
        new_session(MODEL)  # 提前验证模型可用（会触发下载）
    except Exception as e:
        die(
            f"模型准备失败: {e}\n"
            f"      无网络时：把 {MODEL}.onnx 放到 {MODEL_DIR} 后重跑"
        )


def _avail_gb() -> int:
    """当前可用内存(GB)，探测不到返回 0。"""
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return stat.ullAvailPhys // (1024 ** 3)
    except Exception:
        pass
    try:  # 非 Windows
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") // (1024 ** 3)
    except Exception:
        return 0


def _auto_workers() -> int:
    # ponytail: 可用内存÷2 的经验值（每进程峰值约 1GB）；OEM 机上不准就用 CUTOUT_WORKERS 覆盖
    cpu = os.cpu_count() or 4
    avail = _avail_gb()
    limit = avail // 2 if avail else cpu
    return max(1, min(cpu, limit))


_session = None


def _init_worker() -> None:
    global _session
    # 每个推理线程独占 1 个 OMP 线程，避免 全核数×全核数 线程爆炸撑爆内存
    os.environ["OMP_NUM_THREADS"] = "1"
    from rembg import new_session

    _session = new_session(MODEL)


def _cut(name: str) -> str:
    from PIL import Image
    from rembg import remove

    dst = DST / (Path(name).stem + ".png")
    if dst.exists() and dst.stat().st_size > 0:
        return "skip"
    try:
        out = remove(Image.open(SRC / name), session=_session)
        tmp = dst.with_name(dst.name + ".part")  # 先写临时文件，防中断留半张
        out.save(tmp, "PNG")
        tmp.replace(dst)
        return "ok"
    except Exception as e:  # 单张失败不拖垮整批
        return f"fail: {e}"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    _log(f"[1/4] 环境检查 (Python {sys.version.split()[0]})")
    if sys.version_info < (3, 11):
        die(f"需要 Python 3.11+（rembg 要求），当前 {sys.version.split()[0]}")
    ensure_deps()

    _log(f"[2/4] 准备模型 {MODEL}")
    ensure_model()

    if not SRC.is_dir():
        die(f"输入目录不存在: {SRC}")
    files = sorted(
        p.name for p in SRC.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    if not files:
        die(f"输入目录没有图片: {SRC}")
    limit = int(os.environ.get("CUTOUT_LIMIT") or 0)
    if limit:
        files = files[:limit]
    DST.mkdir(parents=True, exist_ok=True)

    workers = int(os.environ.get("CUTOUT_WORKERS") or 0) or _auto_workers()
    _log(f"[3/4] 抠图 {len(files)} 张, 并发 {workers} -> {DST}")

    ok = fail = skip = 0
    t0 = time.monotonic()
    try:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
            futures = {ex.submit(_cut, n): n for n in files}
            for i, fut in enumerate(as_completed(futures), 1):
                r = fut.result()
                if r == "ok":
                    ok += 1
                elif r == "skip":
                    skip += 1
                else:
                    fail += 1
                    _log(f"      {futures[fut]}: {r}")
                if i % 100 == 0 or i == len(files):
                    _log(
                        f"      进度 {i}/{len(files)}"
                        f" (ok={ok} skip={skip} fail={fail})"
                        f" 已用 {time.monotonic() - t0:.0f}s"
                    )
    except Exception as e:  # BrokenProcessPool 等，常见于内存不足
        die(
            f"多进程中断: {e}\n"
            f"      已完成部分已保存，调小并发后重跑即可续传:\n"
            f"      CUTOUT_WORKERS=4 python scripts/cutout_images.py"
        )

    _log(
        f"[4/4] 完成: ok={ok} 跳过={skip} 失败={fail}"
        f" 耗时 {(time.monotonic() - t0) / 60:.1f} 分钟"
    )
    _log(f"      输出目录 {DST}")


if __name__ == "__main__":
    main()
