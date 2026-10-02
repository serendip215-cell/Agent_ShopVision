"""Small wrapper around the official Chinese-CLIP Python API.

Heavy dependencies are imported lazily so command help and configuration
inspection work before the optional model environment is installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import numpy as np


class ChineseClipEncoder:
    def __init__(
        self,
        model_name: str,
        download_root: str | Path,
        device: str = "auto",
        use_modelscope: bool = False,
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
        load_kwargs = {
            "device": self.device,
            "download_root": str(download_root),
        }
        if use_modelscope:
            load_kwargs["use_modelscope"] = True
        self.model, self.preprocess = load_from_name(model_name, **load_kwargs)
        self.model.eval()
        self.dimension: int | None = None

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
