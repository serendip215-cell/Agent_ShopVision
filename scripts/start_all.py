# -*- coding: utf-8 -*-
"""一键启动 Agent ShopVision 前后端（支持直接双击根目录「一键启动ShopVision.cmd」）。

做三件事：
  1. 检查后端虚拟环境、配置与 ONNX 产物是否就绪，缺失时给出清晰引导或一键补齐；
  2. 自动避开被占用端口，启动 FastAPI（uvicorn app.main:app），等待 /api/v1/health 就绪；
  3. 用实际端口启动 Vite 并配置 IPv4 代理目标，前端就绪后自动打开默认浏览器。

为什么需要这个脚本：
  * 后端监听 0.0.0.0，且把 Vite 代理目标写为字面 127.0.0.1，避免 Node 将
    localhost 解析为 IPv6 [::1] 导致所有 /api 请求 502。
  * 8000/5173 常被其他项目占用，脚本会自动顺延到空闲端口并同步放行 CORS。
  * 直接调用 node 运行 vite.js 并在退出时递归清理进程树，避免 Windows 下残留僵尸进程。

用法：
    一键启动ShopVision.cmd                           # Windows 推荐：双击即可运行
    python scripts/start_all.py                     # 默认 后端8000 / 前端5173（占用则顺延）
    python scripts/start_all.py --api-port 8001 --web-port 3000
    python scripts/start_all.py --lan               # 开放局域网访问并打印局域网地址
    python scripts/start_all.py --no-web            # 只起后端
    python scripts/start_all.py --no-api            # 只起前端
    python scripts/start_all.py --no-browser        # 启动后不自动打开浏览器
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "webapp" / "backend"
FRONTEND = ROOT / "webapp" / "frontend"
VENV_PY = BACKEND / ".venv" / "Scripts" / "python.exe"
ENV_FILE = BACKEND / ".env"
ENV_EXAMPLE = BACKEND / ".env.example"
ONNX_VISUAL = ROOT / "data" / "optimize" / "2026-10-24_exp3-speed" / "onnx" / "visual_fp32.onnx"
ONNX_TEXT = ROOT / "data" / "optimize" / "2026-10-24_exp3-speed" / "onnx" / "text_fp32.onnx"

# 本地探活禁用系统代理，避免本机开启代理软件时 127.0.0.1 请求被劫持超时
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_ACTIVE_PROCS: list[tuple[str, subprocess.Popen]] = []
_CLEANED_UP = False
_WIN_JOB_HANDLE: int | None = None


def _create_win_job() -> int | None:
    """在 Windows 下创建 Job Object（KILL_ON_JOB_CLOSE），确保直接关窗口也不残留子进程。"""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _BasicLimitInfo(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class _IoCounters(ctypes.Structure):
            _fields_ = [(f"c{i}", ctypes.c_uint64) for i in range(6)]

        class _ExtendedLimitInfo(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _BasicLimitInfo),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        k32 = ctypes.windll.kernel32
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        k32.SetInformationJobObject.restype = wintypes.BOOL
        k32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]

        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _ExtendedLimitInfo()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        if not ok:
            k32.CloseHandle(job)
            return None
        return int(job)
    except Exception:
        return None


def _attach_win_job(proc: subprocess.Popen) -> None:
    """将启动的子进程加入 Job Object，父进程任意方式退出时由内核自动回收进程树。"""
    if os.name != "nt" or not _WIN_JOB_HANDLE:
        return
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.AssignProcessToJobObject.restype = wintypes.BOOL
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]

        # PROCESS_SET_QUOTA (0x0100) | PROCESS_TERMINATE (0x0001)
        h_proc = k32.OpenProcess(0x0101, False, proc.pid)
        if h_proc:
            try:
                k32.AssignProcessToJobObject(wintypes.HANDLE(_WIN_JOB_HANDLE), h_proc)
            finally:
                k32.CloseHandle(h_proc)
    except Exception:
        pass


def _configure_console() -> None:
    """确保 Windows 控制台统一按 UTF-8 实时输出中文，不乱码不卡缓冲。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
            except Exception:
                pass


def _is_interactive() -> bool:
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        return False


def _ask_yes_no(prompt: str, default: bool = True) -> bool:
    if not _is_interactive():
        return False
    hint = "[Y/n]" if default else "[y/N]"
    try:
        ans = input(f"{prompt} {hint}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not ans:
        return default
    return ans in ("y", "yes", "是")


def _tcp_accepting(host: str, port: int, family: int) -> bool:
    """探测某地址端口是否已有服务在监听（可建立 TCP 连接）。"""
    try:
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


def port_free(port: int) -> bool:
    """精确检测端口在本机是否空闲（兼容 Windows，同时排查 IPv4 与 IPv6 占用）。

    Windows 上设置 SO_REUSEADDR 会允许重绑已被监听的端口导致误判，因此这里
    先主动探测连接，再用无 SO_REUSEADDR / 独占选项做绑定校验。
    """
    if _tcp_accepting("127.0.0.1", port, socket.AF_INET):
        return False
    if socket.has_ipv6 and _tcp_accepting("::1", port, socket.AF_INET6):
        return False

    for bind_host in ("127.0.0.1", "0.0.0.0"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                s.bind((bind_host, port))
        except OSError:
            return False
    return True


def resolve_port(
    preferred: int,
    label: str,
    *,
    strict: bool = False,
    exclude: set[int] | None = None,
    max_tries: int = 50,
) -> int | None:
    """返回可用端口；未启用 strict 时若首选端口被占用则自动向上顺延。"""
    excluded = exclude or set()
    if preferred not in excluded and port_free(preferred):
        return preferred

    if strict:
        print(f"[错误] {label}端口 {preferred} 已被占用，请更换端口后重试。", file=sys.stderr)
        return None

    for offset in range(1, max_tries + 1):
        candidate = preferred + offset
        if candidate > 65535:
            break
        if candidate not in excluded and port_free(candidate):
            print(f"[提示] {label}默认端口 {preferred} 已被占用，已自动切换至空闲端口 {candidate}")
            return candidate

    print(
        f"[错误] 未找到可用的{label}端口（已尝试 {preferred}–{min(65535, preferred + max_tries)}）。",
        file=sys.stderr,
    )
    return None


def _detect_lan_ip() -> str | None:
    """探测可供局域网其他设备访问的本机 IPv4，优先 WLAN / 物理网卡。"""
    if os.name == "nt":
        try:
            out = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-NetIPAddress -AddressFamily IPv4 | "
                    "Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and "
                    "$_.InterfaceAlias -notlike '*vEthernet*' -and $_.InterfaceAlias -notlike 'Tailscale*' -and "
                    "$_.InterfaceAlias -notlike '*Loopback*' } | "
                    "Sort-Object @{Expression={$_.InterfaceAlias -like 'WLAN*'};Descending=$true}, InterfaceMetric | "
                    "Select-Object -ExpandProperty IPAddress",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=4,
            )
            ips = [x.strip() for x in out.stdout.splitlines() if x.strip()]
            if ips:
                return ips[0]
        except Exception:
            pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return None


def _ensure_env_file() -> None:
    """若后端 .env 不存在则从 .env.example 自动初始化（已有 .env 不改动）。"""
    if ENV_FILE.is_file() or not ENV_EXAMPLE.is_file():
        return
    content = ENV_EXAMPLE.read_text(encoding="utf-8")
    has_onnx = ONNX_VISUAL.is_file() and ONNX_TEXT.is_file()
    if has_onnx:
        content = re.sub(
            r"(?m)^SHOPVISION_MODEL_BACKEND\s*=\s*placeholder\s*$",
            "SHOPVISION_MODEL_BACKEND=onnx",
            content,
        )
    ENV_FILE.write_text(content, encoding="utf-8")
    mode = "onnx（已检测到本地双塔模型）" if has_onnx else "placeholder（占位模式）"
    print(f"[初始化] 未检测到 webapp\\backend\\.env，已自动生成默认配置：{mode}")


def _build_cors_origins(web_port: int | None, lan_ip: str | None) -> str | None:
    """在保留原有 CORS 配置的基础上，动态追加实际前端端口，避免顺延端口后跨域失败。"""
    if web_port is None:
        return None

    origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    raw_env = os.environ.get("SHOPVISION_CORS_ORIGINS")
    if not raw_env and ENV_FILE.is_file():
        try:
            for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith("SHOPVISION_CORS_ORIGINS="):
                    raw_env = line.split("=", 1)[1].strip()
                    break
        except OSError:
            pass

    if raw_env:
        try:
            parsed = json.loads(raw_env)
            if isinstance(parsed, list):
                origins = [str(x) for x in parsed]
        except json.JSONDecodeError:
            pass

    extras = [f"http://localhost:{web_port}", f"http://127.0.0.1:{web_port}"]
    if lan_ip:
        extras.append(f"http://{lan_ip}:{web_port}")

    for origin in extras:
        if origin not in origins:
            origins.append(origin)
    return json.dumps(origins, ensure_ascii=False)


def _ensure_backend_venv() -> bool:
    """检查后端虚拟环境；交互模式下缺失时可一键自动创建并安装依赖。"""
    if VENV_PY.is_file():
        return True

    print(f"[提示] 未找到后端虚拟环境：{VENV_PY}", file=sys.stderr)
    if _ask_yes_no("是否现在自动创建后端虚拟环境并安装依赖（约需 1–3 分钟）？", default=True):
        print("[安装] 正在创建 webapp\\backend\\.venv ...")
        r1 = subprocess.run([sys.executable, "-m", "venv", str(BACKEND / ".venv")], cwd=str(BACKEND))
        if r1.returncode != 0 or not VENV_PY.is_file():
            print("[错误] 创建虚拟环境失败，请手动排查 Python 环境。", file=sys.stderr)
            return False
        print("[安装] 正在安装后端 Python 依赖（requirements.txt）...")
        r2 = subprocess.run(
            [str(VENV_PY), "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=str(BACKEND),
        )
        if r2.returncode == 0:
            print("[安装] 后端依赖安装完成。")
            return True
        print("[错误] 依赖安装失败，请查看上方 pip 报错信息。", file=sys.stderr)
        return False

    print("       请先在仓库根目录手动执行：", file=sys.stderr)
    print("       cd webapp\\backend && py -3 -m venv .venv && .\\.venv\\Scripts\\pip install -r requirements.txt", file=sys.stderr)
    return False


def _ensure_frontend_deps() -> bool:
    """检查 Node.js 与前端 node_modules；交互模式下缺依赖时可一键 npm install。"""
    node_exe = shutil.which("node")
    npm_exe = shutil.which("npm")
    if not node_exe:
        print("[错误] 未检测到 Node.js，请先安装 Node.js 18+：https://nodejs.org/", file=sys.stderr)
        return False

    if (FRONTEND / "node_modules").is_dir():
        return True

    print("[提示] 前端依赖 node_modules 尚未安装。", file=sys.stderr)
    if npm_exe and _ask_yes_no("是否现在自动执行 npm install 安装前端依赖？", default=True):
        print("[安装] 正在安装前端依赖（npm install）...")
        r = subprocess.run([npm_exe, "install"], cwd=str(FRONTEND))
        if r.returncode == 0 and (FRONTEND / "node_modules").is_dir():
            print("[安装] 前端依赖安装完成。")
            return True
        print("[错误] npm install 执行失败，请查看上方日志。", file=sys.stderr)
        return False

    print("       请先手动执行：cd webapp\\frontend && npm install", file=sys.stderr)
    return False


def wait_health(
    url: str,
    proc: subprocess.Popen,
    port: int,
    timeout: float = 90.0,
) -> dict | None:
    """轮询 /api/v1/health 直到返回 JSON、进程提前退出或超时。ONNX 双塔加载约需 3–10 秒。"""
    start = time.time()
    deadline = start + timeout
    last_hint = start

    while time.time() < deadline:
        code = proc.poll()
        if code is not None:
            print(f"[错误] 后端进程提前退出（退出码 {code}），请查看上方 uvicorn 日志。", file=sys.stderr)
            return None

        # 先确认端口开始监听，避免尚未绑定前无意义的 HTTP 请求
        if _tcp_accepting("127.0.0.1", port, socket.AF_INET):
            try:
                remaining = max(5.0, min(20.0, deadline - time.time()))
                with _LOCAL_OPENER.open(url, timeout=remaining) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, json.JSONDecodeError):
                pass

        now = time.time()
        if now - last_hint >= 5.0:
            elapsed = int(now - start)
            print(f"      仍在等待后端加载模型与索引（已耗时 {elapsed}s）...")
            last_hint = now
        time.sleep(0.8)

    return None


def wait_http_ready(
    url: str,
    proc: subprocess.Popen,
    port: int,
    timeout: float = 30.0,
) -> bool:
    """轮询等待前端 Vite 服务可访问，避免浏览器抢跑报错。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        code = proc.poll()
        if code is not None:
            print(f"[错误] 前端进程提前退出（退出码 {code}），请查看上方 Vite 日志。", file=sys.stderr)
            return False

        if _tcp_accepting("127.0.0.1", port, socket.AF_INET):
            try:
                with _LOCAL_OPENER.open(url, timeout=3) as resp:
                    if 200 <= resp.status < 500:
                        return True
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                pass
        time.sleep(0.4)
    return False


def _build_vite_cmd(web_port: int, bind_host: str) -> list[str]:
    """优先直接用 node 执行 vite.js，避开 Windows npx.cmd 外壳导致的残留子进程。"""
    node_exe = shutil.which("node")
    vite_js = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if node_exe and vite_js.is_file():
        return [
            node_exe,
            str(vite_js),
            "--port",
            str(web_port),
            "--strictPort",
            "--host",
            bind_host,
        ]
    npx_exe = shutil.which("npx") or "npx"
    return [npx_exe, "vite", "--port", str(web_port), "--strictPort", "--host", bind_host]


def stop_processes(procs: list[tuple[str, subprocess.Popen]], quiet: bool = False) -> None:
    """彻底停止所有子进程（Windows 下递归清理整棵进程树，防止残留占用端口）。"""
    global _CLEANED_UP
    if _CLEANED_UP:
        return
    _CLEANED_UP = True

    alive = [(name, p) for name, p in procs if p.poll() is None]
    if not alive:
        return

    if not quiet:
        print("\n正在停止全部服务并清理子进程 ...")

    for name, p in reversed(alive):
        if p.poll() is not None:
            continue
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(p.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=8,
                )
            except Exception:
                try:
                    p.terminate()
                except Exception:
                    pass
        else:
            try:
                p.terminate()
            except Exception:
                pass

    for _, p in alive:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                p.kill()
                p.wait(timeout=3)
            except Exception:
                pass

    if not quiet:
        print("全部服务已停止。")


def _register_shutdown_hooks() -> None:
    atexit.register(lambda: stop_processes(_ACTIVE_PROCS, quiet=True))

    def _on_signal(_signum: int, _frame: object) -> None:
        stop_processes(_ACTIVE_PROCS)
        raise SystemExit(0)

    for sig_name in ("SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, _on_signal)
            except (OSError, ValueError):
                pass


def _print_banner(
    *,
    api_port: int | None,
    web_port: int | None,
    lan_ip: str | None,
    health: dict | None,
) -> None:
    bar = "=" * 62
    print(f"\n{bar}")
    print("  Agent ShopVision 已启动就绪")
    print(bar)
    if web_port is not None:
        print(f"  前端页面（本机）：  http://127.0.0.1:{web_port}")
        if lan_ip:
            print(f"  前端页面（局域网）：http://{lan_ip}:{web_port}")
    if api_port is not None:
        print(f"  后端接口（本机）：  http://127.0.0.1:{api_port}")
        print(f"  接口文档 Swagger：  http://127.0.0.1:{api_port}/docs")
        print(f"  接口文档 Scalar ：  http://127.0.0.1:{api_port}/scalar")
        if lan_ip:
            print(f"  后端接口（局域网）：http://{lan_ip}:{api_port}")
    if health:
        res = health.get("result", {})
        backend_name = res.get("backend", "unknown")
        loaded = res.get("model_loaded", False)
        cats = len(res.get("categories", []))
        items = res.get("total_items", 0)
        print(f"  模型与索引状态  ：  backend={backend_name} | model_loaded={loaded} | {cats} 类 / {items} 条")
    print("-" * 62)
    print("  提示：保持本窗口开启；按 Ctrl+C 或直接关闭窗口即可停止服务。")
    print(f"{bar}\n")


def main(argv: list[str]) -> int:
    global _CLEANED_UP
    _CLEANED_UP = False
    _ACTIVE_PROCS.clear()
    _configure_console()

    ap = argparse.ArgumentParser(description="一键启动 Agent ShopVision 前后端")
    ap.add_argument("--api-port", type=int, default=8000, help="后端首选端口（默认 8000，被占自动顺延）")
    ap.add_argument("--web-port", type=int, default=5173, help="前端首选端口（默认 5173，被占自动顺延）")
    ap.add_argument("--no-api", action="store_true", help="只启动前端，不启动后端")
    ap.add_argument("--no-web", action="store_true", help="只启动后端，不启动前端")
    ap.add_argument(
        "--lan",
        action="store_true",
        help="前端监听 0.0.0.0 供局域网其他设备访问（默认仅本机 127.0.0.1）",
    )
    ap.add_argument(
        "--no-browser",
        "--no-open",
        dest="no_browser",
        action="store_true",
        help="就绪后不自动打开默认浏览器",
    )
    ap.add_argument(
        "--strict-port",
        action="store_true",
        help="端口被占用时直接报错退出，不自动顺延",
    )
    args = ap.parse_args(argv)

    if args.no_api and args.no_web:
        print("[错误] 不能同时指定 --no-api 和 --no-web。", file=sys.stderr)
        return 1

    print("=" * 62)
    print("  Agent ShopVision 一键启动")
    print("=" * 62)

    # ---------- 启动前环境与端口规划 ----------
    if not args.no_api:
        if not _ensure_backend_venv():
            return 1
        _ensure_env_file()
        if not ONNX_VISUAL.is_file() or not ONNX_TEXT.is_file():
            print(f"[提示] 未检测到完整双塔 ONNX 模型：{ONNX_VISUAL.parent}")
            print("       若配置为 placeholder，可先跑通流程；拉取真模型请运行：")
            print("       python scripts/fetch_model_assets.py")

    if not args.no_web:
        if not _ensure_frontend_deps():
            return 1

    lan_ip = _detect_lan_ip() if args.lan else None
    used_ports: set[int] = set()

    api_port: int | None = args.api_port
    if not args.no_api:
        api_port = resolve_port(args.api_port, "后端", strict=args.strict_port)
        if api_port is None:
            return 1
        used_ports.add(api_port)

    web_port: int | None = None
    if not args.no_web:
        web_port = resolve_port(
            args.web_port,
            "前端",
            strict=args.strict_port,
            exclude=used_ports,
        )
        if web_port is None:
            return 1
        used_ports.add(web_port)

    _register_shutdown_hooks()
    global _WIN_JOB_HANDLE
    _WIN_JOB_HANDLE = _create_win_job()
    total_steps = int(not args.no_api) + int(not args.no_web)
    step = 0
    health: dict | None = None

    try:
        # ---------- 1. 启动后端 ----------
        if not args.no_api and api_port is not None:
            step += 1
            print(f"\n[{step}/{total_steps}] 正在启动后端 FastAPI -> http://127.0.0.1:{api_port} ...")
            api_env = dict(os.environ)
            cors_json = _build_cors_origins(web_port, lan_ip)
            if cors_json:
                api_env["SHOPVISION_CORS_ORIGINS"] = cors_json

            api_proc = subprocess.Popen(
                [
                    str(VENV_PY),
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(api_port),
                ],
                cwd=str(BACKEND),
                env=api_env,
            )
            _attach_win_job(api_proc)
            _ACTIVE_PROCS.append(("后端 FastAPI", api_proc))

            health = wait_health(
                f"http://127.0.0.1:{api_port}/api/v1/health",
                api_proc,
                api_port,
            )
            if health is None:
                print("[错误] 后端未能在 90 秒内就绪，正在停止已启动的进程。", file=sys.stderr)
                stop_processes(_ACTIVE_PROCS)
                return 1
            res = health.get("result", {})
            print(
                f"      后端就绪：backend={res.get('backend')} "
                f"model_loaded={res.get('model_loaded')} "
                f"类别={len(res.get('categories', []))} 条数={res.get('total_items')}"
            )

        # ---------- 2. 启动前端 ----------
        if not args.no_web and web_port is not None:
            step += 1
            bind_host = "0.0.0.0" if args.lan else "127.0.0.1"
            target_api_port = api_port if api_port is not None else args.api_port
            web_env = dict(os.environ)
            # 代理目标写字面 IPv4，避免 Node 把 localhost 解析到 [::1] 导致 502
            web_env["SHOPVISION_API_TARGET"] = f"http://127.0.0.1:{target_api_port}"

            print(f"\n[{step}/{total_steps}] 正在启动前端 Vite -> http://127.0.0.1:{web_port} （监听 {bind_host}）...")
            web_cmd = _build_vite_cmd(web_port, bind_host)
            web_proc = subprocess.Popen(
                web_cmd,
                cwd=str(FRONTEND),
                env=web_env,
            )
            _attach_win_job(web_proc)
            _ACTIVE_PROCS.append(("前端 Vite", web_proc))

            if not wait_http_ready(f"http://127.0.0.1:{web_port}/", web_proc, web_port):
                print("[错误] 前端未能在 30 秒内就绪，正在停止全部服务。", file=sys.stderr)
                stop_processes(_ACTIVE_PROCS)
                return 1
            print("      前端就绪！")

        # ---------- 3. 输出状态并自动打开浏览器 ----------
        _print_banner(
            api_port=None if args.no_api else api_port,
            web_port=web_port,
            lan_ip=lan_ip,
            health=health,
        )

        if not args.no_browser:
            open_url = (
                f"http://127.0.0.1:{web_port}"
                if web_port is not None
                else f"http://127.0.0.1:{api_port}/docs"
            )
            print(f"正在打开浏览器：{open_url}")
            try:
                webbrowser.open(open_url)
            except Exception as exc:
                print(f"[提示] 未能自动打开浏览器（{exc}），请手动复制上方链接访问。")

        # ---------- 4. 守护进程监控 ----------
        while True:
            for name, p in _ACTIVE_PROCS:
                code = p.poll()
                if code is not None:
                    print(f"\n[警告] {name} 已退出（退出码 {code}），正在同步停止其余服务 ...", file=sys.stderr)
                    stop_processes(_ACTIVE_PROCS)
                    return 0 if code == 0 else code
            time.sleep(0.5)

    except KeyboardInterrupt:
        stop_processes(_ACTIVE_PROCS)
        return 0
    except Exception as exc:
        print(f"\n[错误] 启动过程发生未预期异常：{exc}", file=sys.stderr)
        stop_processes(_ACTIVE_PROCS)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
