"""静态验证 train_lora.py 的配置构建逻辑（不装 torch / trl 也能跑）。

用法：python scripts/agent/finetune/_t_config.py

覆盖：
  - torch_supports_bf16() 在无 torch 时不抛异常
  - build_quant_config(no_4bit=True) 必返回 None
  - build_quant_config(False) 在缺 bitsandbytes 时不抛异常、返回 None
  - make_sft_config 的签名适配能过滤掉不支持的字段
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))

spec = importlib.util.spec_from_file_location("train_lora", HERE / "train_lora.py")
train_lora = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train_lora)

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


# --- 1. 无 torch 时 bf16 探测不能炸 ---
check("torch_supports_bf16 无 torch 不抛异常", train_lora.torch_supports_bf16() in (True, False))

# --- 2. --no-4bit 必返回 None（不依赖 bitsandbytes）---
check("build_quant_config(no_4bit=True) -> None", train_lora.build_quant_config(True) is None)

# --- 3. 缺 bitsandbytes 时返回 None 而非抛异常 ---
try:
    out = train_lora.build_quant_config(False)
    check("build_quant_config(False) 缺依赖时降级", out is None, f"返回 {out!r}")
except Exception as e:  # noqa: BLE001
    check("build_quant_config(False) 缺依赖时降级", False, f"抛了 {type(e).__name__}: {e}")


# --- 4. make_sft_config 的字段过滤逻辑 ---
class FakeSig:
    def __init__(self, allowed):
        self.allowed = allowed

    def __call__(self):
        class P:
            parameters = {k: None for k in self.allowed}
        return P()


class FakeSFTConfig:
    """模拟 trl 0.16+：认 max_length / eval_strategy，不认 max_seq_length。"""
    def __init__(self, **kw):
        self.kw = kw


class Args:
    output = Path("/tmp/out")
    epochs = 3.0
    batch_size = 2
    grad_accum = 8
    lr = 1e-4
    warmup_ratio = 0.1
    logging_steps = 5
    seed = 42
    max_seq_len = 1024


import inspect

real_build = train_lora.make_sft_config
orig_inspect = train_lora.inspect.signature


def fake_signature(obj):
    if obj is FakeSFTConfig.__init__:
        return FakeSig([
            "output_dir", "num_train_epochs", "per_device_train_batch_size",
            "per_device_eval_batch_size", "gradient_accumulation_steps",
            "learning_rate", "warmup_ratio", "logging_steps", "save_strategy",
            "eval_strategy", "eval_steps", "bf16", "fp16", "gradient_checkpointing",
            "gradient_checkpointing_kwargs", "report_to", "seed", "max_length",
            "dataset_text_field", "packing",
        ])()
    return orig_inspect(obj)


try:
    fake_trl = types.ModuleType("trl")
    fake_trl.SFTConfig = FakeSFTConfig
    sys.modules["trl"] = fake_trl
    train_lora.inspect.signature = fake_signature

    cfg = real_build(Args(), quantized=True)
    check("make_sft_config 可构建", cfg is not None)
    check("含 max_length", "max_length" in cfg.kw, str(sorted(cfg.kw))[:80])
    check("不含 max_seq_length", "max_seq_length" not in cfg.kw)
    check("含 eval_strategy", "eval_strategy" in cfg.kw)
    check("bf16 与 fp16 互斥",
          bool(cfg.kw.get("bf16")) != bool(cfg.kw.get("fp16")),
          f"bf16={cfg.kw.get('bf16')} fp16={cfg.kw.get('fp16')}")
finally:
    train_lora.inspect.signature = orig_inspect
    sys.modules.pop("trl", None)


# --- 5. LoRA 配置的 target_modules 必须覆盖注意力 + MLP ---
try:
    from peft import LoraConfig  # noqa: F401
    print("SKIP  LoRA 配置实测（peft 已装）")
except ImportError:
    print("SKIP  LoRA 配置实测（本机无 peft，SCNet 上会真正构造）")

print()
if fails:
    print(f"{len(fails)} 项失败：{fails}")
    raise SystemExit(1)
print("配置逻辑验证通过")