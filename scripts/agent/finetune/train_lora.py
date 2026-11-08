"""实验5 5.2 LoRA/QLoRA 微调入口（SFTTrainer）。

设计约束（针对本组实际情况，逐条对应）：
  1. 只有 100 条数据 —— 默认 3 epoch + 小 lr，跑多了必然过拟合；valid 损失会先降后升。
  2. 基座是 Qwen3 系 4B —— 用 QLoRA（4-bit 冻结 + LoRA 旁路），单张 16GB 卡即可，
     不用 A800 那种 80GB，为组里省预算。
  3. 任务输出是严格 JSON / 模板串 —— 必须关掉「思考模式」（Qwen3 默认会输出
     思考块），否则 _parse_intent 解析会拿到一堆废话。这一点在 SFTConfig 侧
     通过 chat template 的 enable_thinking=False 控制，见 dataset_text_field 处理。
  4. trl 0.16 起 SFTTrainer 的签名大改（SFTConfig 取代直接 kwargs）；
     脚本用 inspect 探测，新旧都能跑，避免换机器就崩。

用法（SCNet 训练机 / 任意 CUDA 机器，仓库根目录）：
    python scripts/agent/finetune/train_lora.py \
        --model Qwen/Qwen3-4B-Instruct-2507 \
        --output data/agent/finetune/run1

    # 无 4-bit 依赖（bitsandbytes 装不上）时退回纯 LoRA
    python scripts/agent/finetune/train_lora.py --no-4bit

    # 显存紧张：降 batch、加梯度累积
    python scripts/agent/finetune/train_lora.py --batch-size 1 --grad-accum 16

产物：
    <output>/final_adapter/        LoRA 权重（约 30-60 MB，可直接传 Release）
    <output>/trainer_state.json    训练曲线（写报告用）
    <output>/run_config.json       本次全部超参，便于复现与写报告
    <output>/train.log
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# 允许从仓库根 import，也允许被当作脚本直接跑
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="实验5 5.2 LoRA 微调")

    # 模型与数据
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507",
                    help="HF 模型 id 或本地路径")
    ap.add_argument("--train-file", type=Path, default=REPO_ROOT / "data/agent/sft/train.jsonl")
    ap.add_argument("--valid-file", type=Path, default=REPO_ROOT / "data/agent/sft/valid.jsonl")
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "data/agent/finetune/run1")

    # 量化
    ap.add_argument("--no-4bit", action="store_true",
                    help="关闭 4-bit，退回纯 LoRA（bitsandbytes 不可用时用）")

    # 训练超参（默认值针对 100 条小数据）
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--batch-size", type=int, default=2, help="单卡 micro batch")
    ap.add_argument("--grad-accum", type=int, default=8, help="梯度累积步数")
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--max-seq-len", type=int, default=1024,
                    help="数据最长约 190 字符，1024 足够；不要设太小以免截断输出")
    ap.add_argument("--warmup-ratio", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)

    # LoRA
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--lora-dropout", type=float, default=0.05)

    # 行为
    ap.add_argument("--logging-steps", type=int, default=5)
    ap.add_argument("--save-steps", type=int, default=0,
                    help="0 = 只在结束时存 final_adapter")
    return ap.parse_args()


def build_quant_config(no_4bit: bool):
    """4-bit 量化配置；bitsandbytes 缺失时优雅降级。"""
    if no_4bit:
        print("[info] --no-4bit：使用 bf16/fp16 纯 LoRA")
        return None
    try:
        import torch
        from transformers import BitsAndBytesConfig
    except ImportError as e:
        print(f"[warn] 无法构造 4-bit 配置（{e}），退回纯 LoRA")
        return None

    try:
        import bitsandbytes  # noqa: F401
    except ImportError:
        print("[warn] bitsandbytes 未安装，退回纯 LoRA。装不上就先这样跑，LoRA 本身也够")
        return None

    has_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    compute_dtype = torch.bfloat16 if has_bf16 else torch.float16
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )


def build_lora_config(args):
    from peft import LoraConfig, TaskType

    # Qwen3 全系这些模块名通用；snake_case 与 camelCase 由 peft 自己匹配
    targets = [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ]
    return LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=targets,
        bias="none",
    )


def torch_supports_bf16() -> bool:
    """A100/A800/4090 支持 bf16；T4/P100 等老卡不支持，得退 fp16，否则训练报错。"""
    try:
        import torch

        return torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    except Exception:
        return False


def make_sft_config(args, quantized: bool):
    """兼容 trl 0.16+ 的 SFTConfig 与老版本的 kwargs 两种调用方式。"""
    from trl import SFTConfig

    kwargs = dict(
        output_dir=str(args.output),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_ratio=args.warmup_ratio,
        logging_steps=args.logging_steps,
        save_strategy="no",
        eval_strategy="steps",
        eval_steps=max(args.logging_steps * 4, 20),
        bf16=torch_supports_bf16(),
        fp16=not torch_supports_bf16(),
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to=[],
        seed=args.seed,
        max_length=args.max_seq_len,
        dataset_text_field="text",
        packing=False,
    )

    sig = inspect.signature(SFTConfig.__init__).parameters
    # 老版本用 max_seq_length / evaluation_strategy
    if "max_length" not in sig and "max_seq_length" in sig:
        kwargs["max_seq_length"] = kwargs.pop("max_length")
    if "eval_strategy" not in sig and "evaluation_strategy" in sig:
        kwargs["evaluation_strategy"] = kwargs.pop("eval_strategy")
    # 有些版本没有这两个字段
    for k in ("dataset_text_field", "packing"):
        if k not in sig:
            kwargs.pop(k, None)
    return SFTConfig(**{k: v for k, v in kwargs.items() if k in sig or k == "output_dir"})


def main() -> None:
    args = parse_args()

    if not args.train_file.exists() or not args.valid_file.exists():
        raise SystemExit(
            f"找不到数据：{args.train_file} / {args.valid_file}\n"
            "先跑 python scripts/agent/finetune/prepare_sft_data.py"
        )

    args.output.mkdir(parents=True, exist_ok=True)

    import torch
    from datasets import load_dataset
    from peft import prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTTrainer

    quant_config = build_quant_config(args.no_4bit)
    quantized = quant_config is not None

    print(f"[info] torch {torch.__version__}  cuda={torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"[info] GPU: {torch.cuda.get_device_name(0)} "
              f"{torch.cuda.get_device_properties(0).total_memory / 2**30:.1f} GiB")

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=quant_config,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    model.config.use_cache = False

    if quantized:
        model = prepare_model_for_kbit_training(model)

    ds = load_dataset(
        "json",
        data_files={"train": str(args.train_file), "valid": str(args.valid_file)},
    )

    def render(example):
        """messages -> 单条 text。关掉 Qwen3 的思考块，只保留最终答案。"""
        msgs = example["messages"]
        try:
            text = tokenizer.apply_chat_template(
                msgs,
                tokenize=False,
                add_generation_prompt=False,
                enable_thinking=False,
            )
        except TypeError:
            # 非 Qwen3 系 tokenizer 不认识 enable_thinking
            text = tokenizer.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=False
            )
        return {"text": text}

    ds = ds.map(render, remove_columns=["messages", "meta"])
    print(f"[info] train {len(ds['train'])} 条 / valid {len(ds['valid'])} 条")
    print("[info] 样例渲染结果：\n" + ds["train"][0]["text"])

    sft_config = make_sft_config(args, quantized)

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        args=sft_config,
        train_dataset=ds["train"],
        eval_dataset=ds["valid"],
        peft_config=build_lora_config(args),
    )

    trainer.train()

    adapter_dir = args.output / "final_adapter"
    trainer.model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"[ok] LoRA 权重已存：{adapter_dir}")

    run_config = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}
    run_config.update({
        "quantized_4bit": quantized,
        "train_count": len(ds["train"]),
        "valid_count": len(ds["valid"]),
        "torch": torch.__version__,
    })
    (args.output / "run_config.json").write_text(
        json.dumps(run_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()