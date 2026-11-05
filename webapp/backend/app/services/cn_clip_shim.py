"""torch-free 的 cn_clip 兼容垫片。

背景：官方 ``cn_clip.clip`` 在包顶层 ``import torch`` 与 ``torchvision``，装齐约 2 GB。
后端 ONNX 编码器只需要其中两件事：

* ``tokenize(texts, context_length=52)`` —— 分词并整理成 ``[CLS] ... [SEP] 0 0``
* ``image_transform(224)``            —— 缩放 224、BICUBIC、ToTensor、CLIP 归一化

二者都能用 ``bert_tokenizer`` + PIL + NumPy 等价实现，且**不依赖 torch**。
本模块按官方 ``cn_clip/clip/utils.py`` 的实现逐行对齐，对外提供同名同参函数，
返回值分别以 NumPy 数组（而非 torch 张量）给出——后端直接 ``.numpy()`` 或
``astype`` 即可，无需感知差异。

若官方 cn_clip（含 torch）可用，本模块**不会被使用**：``encoder`` 优先走官方实现。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import List, Union

import numpy as np
from PIL import Image

# 与官方 image_transform 的全量常量一致（CLIP 系列通用）
_MEAN = (0.48145466, 0.4578275, 0.40821073)
_STD = (0.26862954, 0.26130258, 0.27577711)

_TOKENIZER = None


def _load_tokenizer():
    """按文件路径加载 bert_tokenizer，绕开 cn_clip 包顶层对 torch 的导入。"""
    global _TOKENIZER
    if _TOKENIZER is not None:
        return _TOKENIZER
    path = Path(__file__).with_name("bert_tokenizer.py")
    if not path.is_file():
        raise ImportError(f"缺少分词器实现：{path}")
    spec = importlib.util.spec_from_file_location("_shopvision_bert_tokenizer", path)
    if spec is None or spec.loader is None:  # pragma: no cover - 环境异常
        raise ImportError(f"无法加载分词器：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _TOKENIZER = module.FullTokenizer()
    return _TOKENIZER


class _ArrayLike:
    """最小化的类张量包装：只提供后端用到的往返转换。"""

    def __init__(self, array: np.ndarray) -> None:
        self._array = np.asarray(array)

    def numpy(self) -> np.ndarray:
        return self._array

    def astype(self, dtype):
        return self._array.astype(dtype)

    def ne(self, value):
        return _ArrayLike(self._array != value)

    def long(self):
        return _ArrayLike(self._array.astype(np.int64))

    def __array__(self, dtype=None):
        return self._array.astype(dtype) if dtype else self._array

    def __getitem__(self, key):
        got = self._array[key]
        return _ArrayLike(got) if isinstance(got, np.ndarray) else got

    @property
    def shape(self):
        return self._array.shape

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"_ArrayLike(shape={self._array.shape}, dtype={self._array.dtype})"


def tokenize(texts: Union[str, List[str]], context_length: int = 52) -> _ArrayLike:
    """与 cn_clip.clip.utils.tokenize 等价：CLS + 正文(截断) + SEP，其余补 0。"""
    if isinstance(texts, str):
        texts = [texts]
    tokenizer = _load_tokenizer()
    cls_id, sep_id = tokenizer.vocab["[CLS]"], tokenizer.vocab["[SEP]"]
    result = np.zeros((len(texts), context_length), dtype=np.int64)
    for i, text in enumerate(texts):
        body = tokenizer.convert_tokens_to_ids(tokenizer.tokenize(text))[: context_length - 2]
        seq = [cls_id] + list(body) + [sep_id]
        result[i, : len(seq)] = seq
    return _ArrayLike(result)


class _ToTensor:
    """HWC uint8 -> CHW float32 且除以 255（等价 torchvision.ToTensor）。"""

    def __call__(self, image: Image.Image) -> np.ndarray:
        arr = np.asarray(image, dtype=np.uint8)
        return arr.astype(np.float32).transpose(2, 0, 1) / 255.0


class _Normalize:
    def __init__(self, mean, std) -> None:
        self._mean = np.asarray(mean, dtype=np.float32).reshape(3, 1, 1)
        self._std = np.asarray(std, dtype=np.float32).reshape(3, 1, 1)

    def __call__(self, tensor: np.ndarray) -> np.ndarray:
        return (tensor - self._mean) / self._std


class _Resize:
    """对齐 torchvision.Resize((h, w), interpolation=BICUBIC)。"""

    def __init__(self, size) -> None:
        self.size = size

    def __call__(self, image: Image.Image) -> Image.Image:
        return image.resize((self.size[1], self.size[0]), Image.BICUBIC)


class _ConvertRGB:
    def __call__(self, image: Image.Image) -> Image.Image:
        return image.convert("RGB")


class _Compose:
    def __init__(self, steps) -> None:
        self._steps = steps

    def __call__(self, image: Image.Image):
        out = image
        for step in self._steps:
            out = step(out)
        return _ArrayLike(out)


def image_transform(image_size: int = 224) -> _Compose:
    """与 cn_clip.clip.utils.image_transform 等价（输出 __array__ → float32 CHW）。"""
    return _Compose(
        [
            _Resize((image_size, image_size)),
            _ConvertRGB(),
            _ToTensor(),
            _Normalize(_MEAN, _STD),
        ]
    )