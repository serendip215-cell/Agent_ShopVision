"""编码器接缝：图/文 -> 512 维归一化向量。

两档实现，形状一致，用 SHOPVISION_MODEL_BACKEND 切换：

* ``PlaceholderEncoder`` —— 确定性占位，同一输入恒定向量。模型产物未到位时先把
  前后端链路跑通；检索结果无意义，``model_loaded`` 为 False。
* ``OnnxEncoder`` —— 加载实验三双塔 ONNX（visual: image -> embedding，
  text: input_ids/attention_mask -> embedding），输出需自行 L2 归一化。

重依赖（onnxruntime / PIL / cn_clip）只在真用时导入。
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from ..errors import ApiError, ErrorCode

if TYPE_CHECKING:  # 仅类型标注，避免占位模式拖入 PIL / settings 运行时依赖
    from PIL.Image import Image

    from ..config import Settings


def _l2(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype="float32").reshape(-1)
    return vector / (np.linalg.norm(vector) + 1e-12)


class Encoder(ABC):
    """接口：api 层只依赖它，不关心背后是占位还是 ONNX。"""

    dim: int
    model_loaded: bool

    @abstractmethod
    def encode_image(self, image: "Image") -> np.ndarray: ...

    @abstractmethod
    def encode_text(self, text: str) -> np.ndarray: ...


class PlaceholderEncoder(Encoder):
    """确定性占位编码器：sha256 输入 -> 固定种子 RNG -> 512 维归一化向量。"""

    model_loaded = False

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _vec(self, key: str) -> np.ndarray:
        seed = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
        rng = np.random.default_rng(seed)
        return _l2(rng.standard_normal(self.dim))

    def encode_image(self, image: "Image") -> np.ndarray:
        rgb = image.convert("RGB")
        key = f"image:{rgb.width}x{rgb.height}:{hashlib.sha256(rgb.tobytes()).hexdigest()}"
        return self._vec(key)

    def encode_text(self, text: str) -> np.ndarray:
        return self._vec(f"text:{text.strip()}")


class OnnxEncoder(Encoder):
    """实验三双塔 ONNX。分词仍用 cn_clip，ONNX 只吃 ids/mask。"""

    model_loaded = True

    def __init__(
        self,
        visual_path: Path,
        text_path: Path,
        provider: str = "CPUExecutionProvider",
        context_length: int = 52,
        image_size: int = 224,
    ) -> None:
        try:
            import onnxruntime as ort
            from PIL import Image  # noqa: F401
            from cn_clip.clip import image_transform, tokenize
        except ImportError as exc:
            raise ApiError(
                ErrorCode.MODEL_UNAVAILABLE,
                f"ONNX 后端缺依赖（onnxruntime / Pillow / cn_clip）：{exc}",
            ) from exc
        if not visual_path.is_file() or not text_path.is_file():
            raise ApiError(
                ErrorCode.MODEL_UNAVAILABLE,
                f"找不到 ONNX 产物：{visual_path} / {text_path}",
            )
        self._tokenize = tokenize
        self._preprocess = image_transform(image_size)
        self.context_length = context_length
        self._visual = ort.InferenceSession(str(visual_path), providers=[provider])
        self._text = ort.InferenceSession(str(text_path), providers=[provider])
        self.dim = int(self._visual.get_outputs()[0].shape[-1])

    def encode_image(self, image: "Image") -> np.ndarray:
        arr = self._preprocess(image.convert("RGB")).numpy()[None].astype("float32")
        out = self._visual.run(None, {"image": arr})[0]
        return _l2(out[0])

    def encode_text(self, text: str) -> np.ndarray:
        ids = self._tokenize([text], context_length=self.context_length)
        mask = ids.ne(0).long()
        out = self._text.run(
            None,
            {
                "input_ids": ids.numpy().astype("int64"),
                "attention_mask": mask.numpy().astype("int64"),
            },
        )[0]
        return _l2(out[0])


def build_encoder(settings: "Settings") -> Encoder:
    """按配置产出编码器。占位/ONNX 的分支只在这里。"""
    backend = (settings.model_backend or "placeholder").strip().lower()
    if backend == "onnx":
        return OnnxEncoder(
            settings.repo_path(settings.onnx_visual or "data/optimize/2026-10-24_exp3-speed/onnx/visual_fp32.onnx"),
            settings.repo_path(settings.onnx_text or "data/optimize/2026-10-24_exp3-speed/onnx/text_fp32.onnx"),
            provider=settings.onnx_provider,
            context_length=settings.onnx_context_length,
        )
    if backend != "placeholder":
        raise ApiError(
            ErrorCode.MODEL_UNAVAILABLE,
            f"不支持的 model_backend：{backend}（可选 placeholder / onnx）",
        )
    return PlaceholderEncoder(dim=settings.embedding_dim)