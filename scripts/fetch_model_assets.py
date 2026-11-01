"""一条命令拉取实验三双塔 ONNX 产物并切换后端到真模型。

背景：ONNX 产物（约 700MB）在 .gitignore 里进不了 git，约定放在 GitHub Release
``assets-exp3-20261025``（见 docs/流程与交接/实验四模型产物上传说明.md）。
训练机上传后，其他组员只需：

    python scripts/fetch_model_assets.py

脚本做四件事：下载 fp32 双塔 -> 校验 sha256（有 assets_manifest.json 时）->
把 webapp/backend/.env 的 SHOPVISION_MODEL_BACKEND 切成 onnx -> 打印依赖检查结果。
产物已存在且校验通过时跳过下载，可重复执行。

可选参数：
    --fp16        额外下载 fp16 两个文件（仅 GPU 后端用，默认不拉）
    --no-switch   只下载校验，不改 .env
    --check-deps  不下载，只检查当前解释器有没有 onnxruntime / cn_clip / PIL
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

RELEASE_BASE = (
    "https://github.com/serendip215-cell/Agent_ShopVision"
    "/releases/download/assets-exp3-20261025"
)
DEST_DIR = REPO_ROOT / "data" / "optimize" / "2026-10-24_exp3-speed" / "onnx"
MANIFEST_PATH = REPO_ROOT / "assets_manifest.json"
ENV_PATH = REPO_ROOT / "webapp" / "backend" / ".env"
ENV_EXAMPLE_PATH = REPO_ROOT / "webapp" / "backend" / ".env.example"

# 必需：本地 CPU 后端加载的两个塔；可选：GPU/TensorRT 用的 fp16
ASSETS_FP32 = ["visual_fp32.onnx", "text_fp32.onnx"]
ASSETS_FP16 = ["visual_fp16.onnx", "text_fp16.onnx"]

CHUNK = 1 << 20  # 1MB
PROGRESS_STEP = 32 << 20  # 每 32MB 打一行进度


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, dest: Path) -> None:
    """断点续传下载：写 .part，成功后改名。"""
    part = dest.with_suffix(dest.suffix + ".part")
    part.parent.mkdir(parents=True, exist_ok=True)
    done = part.stat().st_size if part.exists() else 0

    headers = {"User-Agent": "shopvision-fetch/1.0"}
    if done:
        headers["Range"] = f"bytes={done}-"
    request = urllib.request.Request(url, headers=headers)

    # 大文件下载网络抖一下很常见：连接被重置/超时自动重试一次，续传接着下
    response = None
    for attempt in (1, 2):
        try:
            response = urllib.request.urlopen(request, timeout=60)
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise SystemExit(
                    f"[x] 远端没有这个文件（404）：{url}\n"
                    "    说明训练机还没把产物传上 Release（tag: assets-exp3-20261025）。\n"
                    "    按 docs/流程与交接/实验四模型产物上传说明.md 催上传后再跑本脚本。"
                ) from exc
            raise SystemExit(f"[x] 下载失败：HTTP {exc.code} {url}") from exc
        except OSError as exc:  # URLError / ConnectionResetError / 超时都在这
            if attempt == 2:
                raise SystemExit(
                    f"[x] 连不上 GitHub（{exc.__class__.__name__}: {exc}）。\n"
                    "    检查网络/代理后重跑本脚本；已下载的部分在 .part 里，会自动续传。"
                ) from exc
            print(f"    连接中断（{exc.__class__.__name__}），重试一次...", flush=True)

    total_header = response.headers.get("Content-Length")
    total = int(total_header) + done if total_header else None

    mode = "ab" if done else "wb"
    printed = done
    with response, part.open(mode) as handle:
        while True:
            block = response.read(CHUNK)
            if not block:
                break
            handle.write(block)
            done += len(block)
            if total and done - printed >= PROGRESS_STEP:
                print(f"    {done / 1e6:>9.0f} / {total / 1e6:.0f} MB", flush=True)
                printed = done

    expected = f"{total / 1e6:.0f} MB" if total else "未知大小"
    if total and done != total:
        part.unlink(missing_ok=True)
        raise SystemExit(f"[x] 下载不完整（{done} / {total} 字节），重跑本脚本会续传")
    print(f"    下载完成（{expected}）")
    shutil.move(str(part), str(dest))


def fetch(name: str, manifest: dict | None) -> Path:
    """下载单个产物并校验；已存在且校验通过则跳过。"""
    dest = DEST_DIR / name
    url = f"{RELEASE_BASE}/{name}"
    entry = (manifest or {}).get(name)

    if dest.is_file():
        print(f"[1/2] {name} 已存在，校验中...")
        actual = sha256_file(dest)
        if entry:
            if actual == entry.get("sha256"):
                print(f"      sha256 与 manifest 一致，跳过下载")
                return dest
            print(f"      [!] sha256 与 manifest 不一致，重新下载")
        else:
            print(f"      本地文件 sha256={actual[:16]}...（暂无 manifest 可比对，跳过下载）")
            return dest

    print(f"[1/2] 下载 {name}")
    print(f"      {url}")
    download(url, dest)

    actual = sha256_file(dest)
    if entry:
        if actual != entry.get("sha256"):
            dest.unlink(missing_ok=True)
            raise SystemExit(
                f"[x] {name} sha256 校验失败，已删除坏文件，请重跑。\n"
                f"    期望 {entry.get('sha256')}\n实际 {actual}"
            )
        print(f"      sha256 校验通过")
    else:
        print(f"      字节数 {dest.stat().st_size}  sha256 {actual}")
        print("      （仓库还没有 assets_manifest.json，把上面两行发给管理员回填）")
    return dest


def switch_env() -> None:
    """把 .env 的 model_backend 切到 onnx；.env 不存在则从 example 复制。"""
    if ENV_PATH.is_file():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    else:
        print("[2/2] webapp/backend/.env 不存在，从 .env.example 复制")
        lines = ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()

    seen_backend = False
    for index, line in enumerate(lines):
        if line.startswith("SHOPVISION_MODEL_BACKEND="):
            lines[index] = "SHOPVISION_MODEL_BACKEND=onnx"
            seen_backend = True
    if not seen_backend:
        lines.append("SHOPVISION_MODEL_BACKEND=onnx")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[2/2] 已写入 {ENV_PATH.relative_to(REPO_ROOT)}：SHOPVISION_MODEL_BACKEND=onnx")
    print("      重启 uvicorn 后生效；健康检查 model_loaded=true 即切换成功。")


def check_deps() -> bool:
    """检查真后端需要的三个依赖，缺了就打印精确的安装命令。"""
    print("[依赖检查] 当前解释器：", sys.executable)
    wanted = [("onnxruntime", "onnxruntime"), ("cn_clip", "cn-clip"), ("PIL", "Pillow")]
    missing = []
    for module, package in wanted:
        try:
            __import__(module)
            print(f"  {module:<12} OK")
        except ImportError:
            missing.append(package)
            print(f"  {module:<12} 缺失")
    if missing:
        pip = f'"{sys.executable}" -m pip install'
        print("\n  补装命令（按顺序执行，torch 必须走 CPU 源避免拉到 2GB CUDA 包）：")
        if "onnxruntime" in missing:
            print(f"    {pip} onnxruntime")
        if any(p in missing for p in ("cn-clip", "Pillow")):
            print(f"    {pip} torch torchvision --index-url https://download.pytorch.org/whl/cpu")
        if "cn-clip" in missing:
            print(f"    {pip} cn-clip")
        if "Pillow" in missing:
            print(f"    {pip} Pillow")
        return False
    print("  依赖齐全。")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="拉取实验三 ONNX 产物并切换 onnx 后端")
    parser.add_argument("--fp16", action="store_true", help="额外下载 fp16 两个文件")
    parser.add_argument("--no-switch", action="store_true", help="只下载校验，不改 .env")
    parser.add_argument("--check-deps", action="store_true", help="不下载，只检查依赖")
    args = parser.parse_args()

    if args.check_deps:
        sys.exit(0 if check_deps() else 1)

    manifest = None
    if MANIFEST_PATH.is_file():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        print(f"已加载 {MANIFEST_PATH.name}，下载后将做 sha256 校验")

    names = ASSETS_FP32 + (ASSETS_FP16 if args.fp16 else [])
    for name in names:
        fetch(name, manifest)

    if not args.no_switch:
        switch_env()
    else:
        print("[2/2] 按要求跳过 .env 切换（--no-switch）")

    print("\n收尾清单：")
    print(f"  1. 用后端 venv 跑：python {Path(__file__).name} --check-deps  补齐缺失依赖")
    print("  2. 重启 uvicorn（.env 只在启动时读）")
    print("  3. curl http://localhost:8000/api/v1/health 确认 model_loaded=true")
    print("  4. 前端 http://localhost:5173/image 重新识别，置信度应明显高于 11% 水平")


if __name__ == "__main__":
    main()
