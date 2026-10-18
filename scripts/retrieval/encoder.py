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


class ChineseClipEncoder:
    def __init__(
        self,
        model_name: str,
        download_root: str | Path,
        device: str = "auto",
        use_modelscope: bool = False,
        checkpoint: str | Path | None = None,
        text_model_name: str = DEFAULT_TEXT_MODEL,
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
        self.dimension: int | None = None

    @property
    def model_tag(self) -> str:
        """便于人读的模型标识，用于日志和注册表。"""
        if not self.checkpoint:
            return self.model_name
        return f"{self.model_name}+{Path(self.checkpoint).name}"

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
