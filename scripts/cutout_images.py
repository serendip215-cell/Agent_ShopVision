"""批量抠图（rembg + isnet-general-use），一键运行。

流程：
  [1/5] 环境检查：Python 版本、缺的依赖自动 pip 安装
  [2/5] 扫描数据集：自动找 data/raw_data/*/images/ 下有图的目录，
        编号列出，输入编号选择（1 / 1,3 / 1 3 / all，可多选）
  [3/5] 准备模型：优先用 scripts/models/ 里放的模型（离线可用），
        没有则用本机缓存，再没有才在线下载（需联网）
  [4/5] 逐目录并发抠图，每 100 张打印进度
  [5/5] 输出透明底 PNG 到各数据集的 images_cutout/，统计汇总

用法（项目根目录）：python scripts/cutout_images.py
环境变量：
  CUTOUT_SELECT=1,3   跳过交互直接选数据集（非交互环境默认全部）
  CUTOUT_WORKERS=8    覆盖并发数
  CUTOUT_LIMIT=3      只跑前 3 张（试跑）
断点续跑：输出已存在则跳过，中断/失败后直接重跑即可接着抠。
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
SCAN_ROOT = ROOT / "data" / "raw_data"  # 扫描 */images/ 有图即数据集
MODEL_DIR = ROOT / "scripts" / "models"  # 把 isnet-general-use.onnx 放这里即可离线使用
IMG_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

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
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


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


def scan_datasets() -> list:
    """返回 [(数据集名, images目录, 图片文件名列表)]，只收有图的目录。"""
    out = []
    for d in sorted(SCAN_ROOT.iterdir()):
        img_dir = d / "images"
        if not d.is_dir() or not img_dir.is_dir():
            continue
        files = sorted(
            p.name for p in img_dir.iterdir() if p.suffix.lower() in IMG_SUFFIXES
        )
        if files:
            out.append((d.name, img_dir, files))
    return out


def _parse_select(raw: str, n: int) -> list:
    """解析 '1' / '1,3' / '1 3' / 'all'，无效返回 None。"""
    raw = raw.strip().lower()
    if raw in ("a", "all", "全部"):
        return list(range(n))
    parts = raw.replace(",", " ").replace("、", " ").split()
    try:
        idx = list(dict.fromkeys(int(p) - 1 for p in parts))
    except ValueError:
        return None
    if not idx or any(i < 0 or i >= n for i in idx):
        return None
    return idx


def select_datasets(datasets: list) -> list:
    _log(f"[2/5] 扫描到 {len(datasets)} 个数据集:")
    for i, (name, _, files) in enumerate(datasets, 1):
        _log(f"      {i}) {name:<30} {len(files)} 张")
    _log("      输入编号选择，如 1 或 1,3（all=全部；建议一次处理一个目录）")

    env = os.environ.get("CUTOUT_SELECT")
    raw = env if env is not None else None
    src = "CUTOUT_SELECT" if env is not None else "输入"
    while True:
        try:
            if raw is None:
                raw = input("      > ")
        except EOFError:  # 非交互环境（管道/后台）默认全部
            raw, src = "all", "非交互默认"
        idx = _parse_select(raw, len(datasets))
        if idx is not None:
            _log(f"      {src} [{raw}] -> 处理 {len(idx)} 个数据集")
            return idx
        _log(f"      输入无效 [{raw}]，重新输入")
        raw = None  # 下轮回到 input


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
    # ponytail: 可用内存÷2 的经验值（每进程峰值约 1GB）；不准就用 CUTOUT_WORKERS 覆盖
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


def _cut(src: Path, dst: Path) -> str:
    from PIL import Image
    from rembg import remove

    if dst.exists() and dst.stat().st_size > 0:
        return "skip"
    try:
        out = remove(Image.open(src), session=_session)
        tmp = dst.with_name(dst.name + ".part")  # 先写临时文件，防中断留半张
        out.save(tmp, "PNG")
        tmp.replace(dst)
        return "ok"
    except Exception as e:  # 单张失败不拖垮整批
        return f"fail: {e}"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    _log(f"[1/5] 环境检查 (Python {sys.version.split()[0]})")
    if sys.version_info < (3, 11):
        die(f"需要 Python 3.11+（rembg 要求），当前 {sys.version.split()[0]}")
    ensure_deps()

    datasets = scan_datasets()
    if not datasets:
        die(f"{SCAN_ROOT} 下没有含图片的 images/ 目录")
    picked = select_datasets(datasets)

    _log(f"[3/5] 准备模型 {MODEL}")
    ensure_model()

    # 组装任务 (数据集名, 源图, 输出图)，每个数据集输出到自己的 images_cutout/
    tasks = {}
    for i in picked:
        name, img_dir, files = datasets[i]
        dst_dir = img_dir.parent / "images_cutout"
        dst_dir.mkdir(parents=True, exist_ok=True)
        tasks[name] = [(img_dir / f, dst_dir / (Path(f).stem + ".png")) for f in files]
    limit = int(os.environ.get("CUTOUT_LIMIT") or 0)
    if limit:
        flat = [(k, *t) for k, v in tasks.items() for t in v][:limit]
        trimmed = {}
        for k, s, d in flat:
            trimmed.setdefault(k, []).append((s, d))
        tasks = trimmed
    total = sum(len(v) for v in tasks.values())
    if not total:
        die("没有要处理的图片")

    workers = int(os.environ.get("CUTOUT_WORKERS") or 0) or _auto_workers()
    _log(f"[4/5] 抠图 {total} 张 (来自 {len(tasks)} 个数据集), 并发 {workers}")

    ok = fail = skip = 0
    t0 = time.monotonic()
    try:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
            for name, sub in tasks.items():
                _log(f"      {name}: {len(sub)} 张 -> {sub[0][1].parent}")
                futures = {ex.submit(_cut, s, d): s.name for s, d in sub}
                for i, fut in enumerate(as_completed(futures), 1):
                    r = fut.result()
                    fname = futures[fut]
                    if r == "ok":
                        ok += 1
                    elif r == "skip":
                        skip += 1
                    else:
                        fail += 1
                    _log(f"        {r:<6} {fname} [{i}/{len(sub)}]")
                    if i % 100 == 0 or i == len(sub):
                        _log(
                            f"        进度 {i}/{len(sub)}"
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
        f"[5/5] 完成: ok={ok} 跳过={skip} 失败={fail}"
        f" 耗时 {(time.monotonic() - t0) / 60:.1f} 分钟"
    )
    for name in tasks:
        _log(f"      输出: {tasks[name][0][1].parent}")


if __name__ == "__main__":
    main()
