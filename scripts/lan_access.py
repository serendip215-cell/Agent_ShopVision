# -*- coding: utf-8 -*-
"""一键开启 / 关闭局域网访问（防火墙 + 服务绑定 + 地址提示）。

用法（在仓库根目录，需管理员 PowerShell 才能改防火墙）：
    python scripts/lan_access.py on            # 放行端口并给出访问地址
    python scripts/lan_access.py off           # 撤销放行规则
    python scripts/lan_access.py status        # 只看当前状态
    python scripts/lan_access.py on --open-all # 直接关闭全部防火墙（不推荐，风险自负）

设计取向：默认只放行本项目端口，而不是关闭整个防火墙。
理由是本机还有别的服务在跑（其他 Vite、Tailscale、虚拟网卡），
关掉防火墙等于把它们一起暴露给同网段所有人。
"""
from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 需要放行的规则：显示名 -> 端口
RULES = {
    "ShopVision 前端 3000": 3000,
    "ShopVision 后端 8000": 8000,
}


def is_admin() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def lan_ip() -> str | None:
    """取能供局域网访问的 IPv4，优先 WLAN / 以太网，跳过虚拟网卡与回环。

    不能用 PrefixOrigin 过滤——实测会把真正的 WLAN 地址（10.244.38.144）
    一起滤掉，只剩 10.77.77.4 这类虚拟适配器地址。
    """
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-NetIPAddress -AddressFamily IPv4 | "
             "Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and "
             "$_.InterfaceAlias -notlike '*vEthernet*' -and $_.InterfaceAlias -notlike 'Tailscale*' -and "
             "$_.InterfaceAlias -notlike '*Loopback*' } | "
             "Sort-Object @{Expression={$_.InterfaceAlias -like 'WLAN*'};Descending=$true}, InterfaceMetric | "
             "Select-Object -ExpandProperty IPAddress"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        ips = [x.strip() for x in out.stdout.splitlines() if x.strip()]
        return ips[0] if ips else None
    except Exception:
        return None


def firewall_state() -> str:
    _, out = run(["netsh", "advfirewall", "show", "allprofiles", "state"])
    parts = []
    for line in out.splitlines():
        if "State" in line or "状态" in line:
            parts.append(line.strip())
    return " / ".join(parts)


def rule_exists(name: str) -> bool:
    code, out = run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"])
    return code == 0 and "No rules match" not in out and "没有与指定条件" not in out


def cmd_status() -> int:
    print("[防火墙]")
    print("  " + firewall_state())
    print("\n[本项目放行规则]")
    for name, port in RULES.items():
        print(f"  {name:24s} 端口 {port}  {'已放行' if rule_exists(name) else '未放行'}")
    ip = lan_ip()
    print(f"\n[访问地址] 局域网 IP: {ip or '未取到'}")
    if ip:
        for port in RULES.values():
            print(f"  http://{ip}:{port}")
    print("\n[本机监听]")
    for port in RULES.values():
        code, out = run(["powershell", "-NoProfile", "-Command",
                         f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
                         "Select-Object -ExpandProperty LocalAddress"])
        addrs = {x.strip() for x in out.splitlines() if x.strip()}
        state = ", ".join(sorted(addrs)) or "未监听"
        warn = ""
        if addrs and not any(a in ("0.0.0.0", "::") for a in addrs):
            warn = "  <- 只绑了本机，外部访问不到，需用 --host 0.0.0.0 启动"
        print(f"  端口 {port}: {state}{warn}")
    return 0


def cmd_on(open_all: bool) -> int:
    if not is_admin():
        print("[错误] 需要管理员权限。请用管理员身份打开 PowerShell 后重跑。", file=sys.stderr)
        return 1

    if open_all:
        code, out = run(["netsh", "advfirewall", "set", "allprofiles", "state", "off"])
        print("[防火墙] 已关闭全部配置文件" if code == 0 else f"[失败] {out}")
    else:
        failed = []
        for name, port in RULES.items():
            if rule_exists(name):
                print(f"[跳过] {name} 已存在")
                continue
            code, out = run(["netsh", "advfirewall", "firewall", "add", "rule",
                             f"name={name}", "dir=in", "action=allow", "protocol=TCP",
                             f"localport={port}", "profile=private,domain"])
            if code == 0:
                print(f"[放行] {name} (TCP {port})")
            else:
                failed.append(name)
                print(f"[失败] {name}: {out.strip()[:120]}")
        if failed:
            print(f"\n有 {len(failed)} 条规则未成功，可改用 --open-all 或手动检查组策略。", file=sys.stderr)

    ip = lan_ip()
    print("\n访问地址（同一局域网的其他设备）：")
    if ip:
        for port in RULES.values():
            print(f"  http://{ip}:{port}")
    else:
        print("  未取到局域网 IP")
    print("\n提醒：服务需以 --host 0.0.0.0 启动，外部才连得上：")
    print("  python scripts/start_all.py --api-port 8000 --web-port 3000 --lan")
    return 0


def cmd_off(open_all: bool) -> int:
    if not is_admin():
        print("[错误] 需要管理员权限。请用管理员身份打开 PowerShell 后重跑。", file=sys.stderr)
        return 1

    for name in RULES:
        code, out = run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={name}"])
        print(f"[撤销] {name}" if code == 0 else f"[跳过] {name}（不存在或已删除）")

    if open_all:
        code, _ = run(["netsh", "advfirewall", "set", "allprofiles", "state", "on"])
        print("[防火墙] 已恢复开启全部配置文件" if code == 0 else "[失败] 恢复防火墙失败")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="一键开启/关闭局域网访问")
    ap.add_argument("action", choices=["on", "off", "status"])
    ap.add_argument("--open-all", action="store_true",
                    help="on/off 时直接开关全部防火墙（默认只放行本项目端口）")
    args = ap.parse_args(argv)

    if args.action == "status":
        return cmd_status()
    if args.action == "on":
        return cmd_on(args.open_all)
    return cmd_off(args.open_all)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))