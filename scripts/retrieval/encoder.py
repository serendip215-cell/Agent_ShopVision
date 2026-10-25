"""Small wrapper around the official Chinese-CLIP Python API.

Heavy dependencies are imported lazily so command help and configuration
inspection work before the optional model environment is installed.

Two ways to obtain a model:

* ``model_name`` only              -> official pretrained weights (cached/downloaded)
* ``model_name`` + ``checkpoint``  -> a local ``.pt``, e.g. our finetuned ``epoch3.pt``

For the checkpoint path we load the file ourselves (``torch.load(...,
weights_only=False)``) and call the official ``create_model()`` rather than going
through ``load_from_name()``: the latter calls ``torch.load`` without
``weights_only``, which since torch 2.6 defaults to ``True`` and rejects the numpy
scalars stored in optimizer state ("Weights only load failed"). ``create_model()``
also strips the ``module.`` prefix that DDP training leaves in ``state_dict``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np

DEFAULT_TEXT_MODEL = "RoBERTa-wwm-ext-base-chinese"


def _resolve_input_resolution(clip_module, model_name: str) -> int:
    """Read ``image_resolution`` from the official per-model config JSON."""
    config = (
        Path(clip_module.__file__).parent
        / "model_configs"
        / f"{model_name.replace('/', '-')}.json"
    )
    if not config.is_file():
        raise FileNotFoundError(f"找不到模型配置：{config}")
    return int(json.loads(config.read_text(encoding="utf-8"))["image_resolution"])


def _replace_dynamic_linear(model, predicate, per_channel: bool = False) -> int:
    """按名字过滤，把符合条件的 nn.Linear 换成动态量化版本，返回替换个数。

    官方 `quantize_dynamic()` 只能按“模块类型”整棵树替换，不能按名字挑层；
    实验三要分别量化文本塔/图像塔，所以这里手工做。

    注意：`Linear.from_float()` 依赖模块自带的 qconfig，未设置会原样返回，故先赋 qconfig。
    """
    import torch
    from torch.ao.nn.quantized.dynamic import Linear as DynLinear
    from torch.ao.quantization import (
        default_dynamic_qconfig,
        per_channel_dynamic_qconfig,
    )

    qconfig = per_channel_dynamic_qconfig if per_channel else default_dynamic_qconfig
    targets = [
        (name, module)
        for name, module in model.named_modules()
        if type(module) is torch.nn.Linear and predicate(name)
    ]
    for name, module in targets:
        module.qconfig = qconfig
        quantized = DynLinear.from_float(module)
        parts = name.split(".")
        parent = model
        for part in parts[:-1]:
            parent = getattr(parent, part)
        setattr(parent, parts[-1], quantized)
    return len(targets)


class ChineseClipEncoder:
    def __init__(
        self,
        model_name: str,
        download_root: str | Path,
        device: str = "auto",
        use_modelscope: bool = False,
        checkpoint: str | Path | None = None,
        text_model_name: str = DEFAULT_TEXT_MODEL,
        quant: str = "none",
    ) -> None:
        try:
            import torch
            import cn_clip.clip as clip
            from cn_clip.clip import load_from_name
        except ImportError as exc:
            raise RuntimeError(
                "缺少 Chinese-CLIP 运行依赖，请先安装 scripts/retrieval/requirements.txt。"
            ) from exc

        self.torch = torch
        self.clip = clip
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("已指定 --device cuda，但当前 PyTorch 未检测到可用 CUDA。")
        self.device = torch.device(device)
        self.model_name = model_name
        self.text_model_name = text_model_name
        self.quant = (quant or "none").strip().lower()
        self.download_root = str(download_root)

        if checkpoint:
            ckpt_path = Path(checkpoint).expanduser()
            if not ckpt_path.is_absolute():
                ckpt_path = (Path.cwd() / ckpt_path).resolve()
            if not ckpt_path.is_file():
                raise FileNotFoundError(f"权重文件不存在：{ckpt_path}")
            self.checkpoint: str | None = str(ckpt_path)
            # 自己加载而不是交给官方 load_from_name()：官方内部 torch.load 未传
            # weights_only，torch>=2.6 默认 True 会拦下 checkpoint 里的 numpy 标量
            # （优化器状态带的），报 "Weights only load failed"。
            raw = torch.load(self.checkpoint, map_location="cpu", weights_only=False)
            if not isinstance(raw, dict) or "state_dict" not in raw:
                raise RuntimeError(
                    f"权重文件格式不符，应包含 'state_dict'：{ckpt_path}"
                )
            from cn_clip.clip.utils import create_model

            # create_model() 会自动剥离 DDP 训练留下的 "module." 前缀。
            self.model = create_model(f"{model_name}@{text_model_name}", raw)
            if str(self.device) == "cpu":
                self.model.float()
            else:
                self.model.to(self.device)
            self.preprocess = clip.image_transform(
                _resolve_input_resolution(clip, model_name)
            )
        else:
            self.checkpoint = None
            load_kwargs = {
                "device": self.device,
                "download_root": self.download_root,
            }
            if use_modelscope:
                load_kwargs["use_modelscope"] = True
            self.model, self.preprocess = load_from_name(model_name, **load_kwargs)

        self.model.eval()
        self._apply_quant()
        self.dimension: int | None = None

    def _apply_quant(self) -> None:
        """按需调整数值精度（实验三）。

        三档口径：
          none —— 官方默认。注意 create_model() 会把权重转成 FP16，所以实际是 FP16；
          fp32 —— 显式 float()，真正的 FP32（仅作精度参照）；
          fp16 —— 半精度，只在 CUDA 上有意义；
          int8 —— 动态量化，只作用于 nn.Linear，是 CPU 路径。

        注意本方法不落盘：同一份权重加 --quant 就能按不同精度运行。
        要量「模型大小」请用 scripts/optimize/quantize.py。
        """
        if self.quant in ("", "none"):
            return
        if self.quant == "fp32":
            self.model.float()
            return
        if self.quant in ("int8-text", "int8-visual"):
            if self.device.type == "cuda":
                raise RuntimeError("INT8 动态量化是 CPU 路径，请加 --device cpu。")
            # 文本塔是 HF 的 BertModel，挂在 `bert.` 下；图像塔在 `visual.` 下。
            prefix = "bert." if self.quant == "int8-text" else "visual."
            replaced = _replace_dynamic_linear(self.model, lambda name: name.startswith(prefix))
            print(f"[quant] {self.quant}：量化 {replaced} 个 Linear（前缀 {prefix}）", flush=True)
            if replaced == 0:
                raise RuntimeError(f"没有匹配到可量化的层（前缀 {prefix}）")
            return
        if self.quant in ("int8", "int8-pc"):
            if self.device.type == "cuda":
                raise RuntimeError(
                    "INT8 动态量化是 CPU 路径，请加 --device cpu（或改用 --quant fp16）。"
                )
            from torch.ao.quantization import quantize_dynamic

            if self.quant == "int8-pc":
                # 按输出通道量化（per-channel）：缩放系数更细，Transformer 通常明显更稳。
                from torch.ao.quantization import per_channel_dynamic_qconfig

                qspec = {self.torch.nn.Linear: per_channel_dynamic_qconfig}
            else:
                # 默认：整层一个缩放系数（per-tensor）。
                qspec = {self.torch.nn.Linear}
            self.model = quantize_dynamic(self.model, qspec, dtype=self.torch.qint8)
            return
        if self.quant == "fp16":
            if self.device.type != "cuda":
                raise RuntimeError("FP16 推理需要在 CUDA 上运行，请加 --device cuda（或改用 --quant int8）。")
            self.model.half()
            return
        raise ValueError(
            f"不支持的 quant：{self.quant}（可选 none / fp32 / fp16 / int8 / int8-pc）"
        )

    @property
    def model_tag(self) -> str:
        """便于人读的模型标识，用于日志和注册表。"""
        base = (
            self.model_name
            if not self.checkpoint
            else f"{self.model_name}+{Path(self.checkpoint).name}"
        )
        return base if self.quant == "none" else f"{base}@{self.quant}"

    @staticmethod
    def _normalise(features):
        return features / features.norm(dim=-1, keepdim=True).clamp_min(1e-12)

    def _remember_dimension(self, features) -> None:
        dimension = int(features.shape[-1])
        if self.dimension is None:
            self.dimension = dimension
        elif self.dimension != dimension:
            raise RuntimeError("模型返回的向量维度不一致。")

    def encode_images(self, image_paths: Sequence[Path], batch_size: int = 16) -> np.ndarray:
        from PIL import Image

        vectors = []
        total_batches = (len(image_paths) + batch_size - 1) // batch_size
        with self.torch.no_grad():
            for batch_number, start in enumerate(range(0, len(image_paths), batch_size), start=1):
                batch_paths = image_paths[start : start + batch_size]
                tensors = []
                for path in batch_paths:
                    with Image.open(path) as image:
                        tensors.append(self.preprocess(image.convert("RGB")))
                inputs = self.torch.stack(tensors).to(self.device)
                features = self._normalise(self.model.encode_image(inputs))
                self._remember_dimension(features)
                vectors.append(features.detach().cpu().numpy().astype("float32"))
                print(f"[Chinese-CLIP] 图片批次 {batch_number}/{total_batches}", flush=True)
        if not vectors:
            raise ValueError("没有可编码的商品图片。")
        return np.concatenate(vectors, axis=0)

    def encode_texts(self, texts: Sequence[str], batch_size: int = 32) -> np.ndarray:
        vectors = []
        total_batches = (len(texts) + batch_size - 1) // batch_size
        with self.torch.no_grad():
            for batch_number, start in enumerate(range(0, len(texts), batch_size), start=1):
                batch = list(texts[start : start + batch_size])
                tokens = self.clip.tokenize(batch).to(self.device)
                features = self._normalise(self.model.encode_text(tokens))
                self._remember_dimension(features)
                vectors.append(features.detach().cpu().numpy().astype("float32"))
                print(f"[Chinese-CLIP] 文本批次 {batch_number}/{total_batches}", flush=True)
        if not vectors:
            raise ValueError("没有可编码的文本。")
        return np.concatenate(vectors, axis=0)
