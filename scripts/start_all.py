# -*- coding: utf-8 -*-
"""一键启动 Agent ShopVision 前后端（Windows）。

做三件事：
  1. 检查后端虚拟环境与模型产物是否就绪，给出明确缺失提示；
  2. 后台启动 FastAPI（默认 8000），等待 /api/v1/health 返回 model_loaded；
  3. 用指定端口启动 Vite，并把代理目标通过环境变量传给前端。

为什么需要这个脚本：
  * 后端若只监听 127.0.0.1，而 Vite 代理走 localhost 解析到 IPv6 [::1]，
    会出现所有 /api 请求 502。脚本统一让后端监听 0.0.0.0，且代理目标
    写字面 127.0.0.1，绕开解析歧义。
  * 5173/8000 常被其他项目占用，脚本会先探测并提示换端口。

用法：
    python scripts/start_all.py                    # 默认 后端8000 / 前端5173
    python scripts/start_all.py --api-port 8001 --web-port 3000
    python scripts/start_all.py --no-web           # 只起后端
    python scripts/start_all.py --no-api           # 只起前端
"""
from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "webapp" / "backend"
FRONTEND = ROOT / "webapp" / "frontend"
VENV_PY = BACKEND / ".venv" / "Scripts" / "python.exe"
ONNX_VISUAL = ROOT / "data" / "optimize" / "2026-10-24_exp3-speed" / "onnx" / "visual_fp32.onnx"


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def wait_health(url: str, timeout: float = 90.0) -> dict | None:
    """轮询 /health，直到可解析或超时。ONNX 双塔加载约需 3–10 秒。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            time.sleep(1.5)
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="启动 Agent ShopVision 前后端")
    ap.add_argument("--api-port", type=int, default=8000)
    ap.add_argument("--web-port", type=int, default=5173)
    ap.add_argument("--no-api", action="store_true")
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--lan", action="store_true",
                    help="监听 0.0.0.0 供局域网其他设备访问（默认仅本机 127.0.0.1）")
    args = ap.parse_args(argv)

    procs: list[subprocess.Popen] = []

    # ---------- 后端 ----------
    if not args.no_api:
        if not VENV_PY.is_file():
            print(f"[错误] 找不到后端虚拟环境：{VENV_PY}", file=sys.stderr)
            print("       先执行：cd webapp\\backend && py -3.12 -m venv .venv "
                  "&& .\\.venv\\Scripts\\pip install -r requirements.txt", file=sys.stderr)
            return 1
        if not ONNX_VISUAL.is_file():
            print(f"[提示] 未找到 ONNX 产物：{ONNX_VISUAL}", file=sys.stderr)
            print("       后端会以 placeholder 启动（检索结果无意义）。"
                  "拉取产物：python scripts/fetch_model_assets.py", file=sys.stderr)
        if not port_free(args.api_port):
            print(f"[错误] 端口 {args.api_port} 已被占用，请用 --api-port 指定其他端口", file=sys.stderr)
            return 1

        print(f"[1/2] 启动后端 http://127.0.0.1:{args.api_port} ...")
        procs.append(
            subprocess.Popen(
                [str(VENV_PY), "-m", "uvicorn", "app.main:app",
                 "--host", "0.0.0.0", "--port", str(args.api_port)],
                cwd=str(BACKEND),
            )
        )
        health = wait_health(f"http://127.0.0.1:{args.api_port}/api/v1/health")
        if health is None:
            print("[错误] 后端 90 秒内未就绪，请查看上方 uvicorn 输出", file=sys.stderr)
            return 1
        res = health.get("result", {})
        print(f"      后端就绪：backend={res.get('backend')} "
              f"model_loaded={res.get('model_loaded')} "
              f"类别={len(res.get('categories', []))} 条数={res.get('total_items')}")

    # ---------- 前端 ----------
    if not args.no_web:
        if not (FRONTEND / "node_modules").is_dir():
            print("[错误] 前端依赖未安装，先执行：cd webapp\\frontend && npm install", file=sys.stderr)
            return 1
        if not port_free(args.web_port):
            print(f"[错误] 端口 {args.web_port} 已被占用，请用 --web-port 指定其他端口", file=sys.stderr)
            return 1

        import os

        env = dict(os.environ)
        # 代理目标写字面 IPv4，避免 Node 把 localhost 解析到 [::1] 导致 502
        env["SHOPVISION_API_TARGET"] = f"http://127.0.0.1:{args.api_port}"
        npx = shutil.which("npx") or "npx"
        bind_host = "0.0.0.0" if args.lan else "127.0.0.1"
        print(f"[2/2] 启动前端 http://127.0.0.1:{args.web_port} "
              f"（监听 {bind_host}）...")
        procs.append(
            subprocess.Popen(
                [npx, "vite", "--port", str(args.web_port), "--strictPort",
                 "--host", bind_host],
                cwd=str(FRONTEND),
                env=env,
            )
        )

    print("\n按 Ctrl+C 停止全部服务。")
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\n正在停止 ...")
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))