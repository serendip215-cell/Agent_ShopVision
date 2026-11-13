"""端到端延迟压测：文本检索 / 图片检索 / Agent 文本对话 / Agent 图片对话。

用法（先启动后端，onnx 后端）：
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    python scripts/bench_e2e_latency.py

每个接口先发 1 次暖机请求（触发 ONNX 双塔加载），再打 30 次，
输出冷启动耗时、暖机均值、P95。对应报告 8.2 表 @tbl-latency 的四行。
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
RUNS = 30
SAMPLE_IMAGE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "processed_data_cleaning"
    / "鞋"
    / "images"
    / "10811429799__10811429799.png"
)


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(0.95 * len(ordered) + 0.5) - 1)
    return ordered[max(0, idx)]


def bench(client: httpx.Client, name: str, fn) -> None:
    # 暖机一次：触发模型/索引加载，测冷启动
    t0 = time.perf_counter()
    fn(client)
    cold_ms = (time.perf_counter() - t0) * 1000

    lat = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        fn(client)
        lat.append((time.perf_counter() - t0) * 1000)

    print(f"\n== {name} ==")
    print(f"  冷启动(首次): {cold_ms:8.1f} ms")
    print(f"  暖机均值    : {statistics.mean(lat):8.1f} ms   (n={RUNS})")
    print(f"  暖机 P95    : {p95(lat):8.1f} ms")
    print(f"  min/max     : {min(lat):.1f} / {max(lat):.1f} ms")


def main() -> None:
    image_bytes = SAMPLE_IMAGE.read_bytes()
    client = httpx.Client(base_url=BASE, timeout=120.0)

    h = client.get("/api/v1/health").json()
    result = h.get("result") or {}
    print(f"health: model_loaded={result.get('model_loaded')} backend={result.get('backend')}")
    print(f"        categories={result.get('categories')} total_items={result.get('total_items')}")

    def do_text(c: httpx.Client) -> None:
        r = c.post("/api/v1/text", json={"query": "白色运动鞋", "top_k": 5})
        r.raise_for_status()

    def do_image(c: httpx.Client) -> None:
        r = c.post(
            "/api/v1/image",
            files={"file": ("sample.png", image_bytes, "image/png")},
        )
        r.raise_for_status()

    def do_agent_chat(c: httpx.Client) -> None:
        r = c.post(
            "/api/v1/agent/chat",
            json={"message": "帮我找白色运动鞋", "session_id": None},
        )
        r.raise_for_status()

    def do_agent_image(c: httpx.Client) -> None:
        r = c.post(
            "/api/v1/agent/image",
            files={"file": ("sample.png", image_bytes, "image/png")},
            data={"message": "", "alpha": "0.6", "top_k": "5"},
        )
        r.raise_for_status()

    bench(client, "文本检索 /api/v1/text", do_text)
    bench(client, "图片检索 /api/v1/image", do_image)
    bench(client, "Agent 文本对话 /api/v1/agent/chat", do_agent_chat)
    bench(client, "Agent 图片对话 /api/v1/agent/image", do_agent_image)


if __name__ == "__main__":
    main()
