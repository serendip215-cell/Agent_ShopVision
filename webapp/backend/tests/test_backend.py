"""后端最小自检：索引检索、占位编码器、服务组合、三个接口的返回与错误码。

自建一个小索引（2 类 × 4 条，8 维），不依赖仓库里的大索引，可离线跑：

    cd webapp/backend && python -m unittest discover -s tests -v
"""

from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.deps import get_match_service  # noqa: E402
from app.errors import ApiError, ErrorCode  # noqa: E402
from app.main import app  # noqa: E402
from app.services.encoder import PlaceholderEncoder, build_encoder  # noqa: E402
from app.services.index_store import IndexStore  # noqa: E402
from app.services.matching import MatchService  # noqa: E402

DIM = 8
CATEGORIES = ["甲", "乙"]
ITEMS_PER_CATEGORY = 4


def _build_index(root: Path) -> IndexStore:
    """写一个最小可用的索引目录：注册表 + 每类 items.csv 与 image_embeddings.npy。"""
    rng = np.random.default_rng(20261101)
    registry = {"version": 1, "categories": {}, "model": {"name": "test"}}
    for category in CATEGORIES:
        vectors = rng.standard_normal((ITEMS_PER_CATEGORY, DIM)).astype("float32")
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        folder = root / category
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder / "image_embeddings.npy", vectors)
        with (folder / "items.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["vector_id", "item_name", "product_type", "text"])
            for i in range(ITEMS_PER_CATEGORY):
                writer.writerow([i, f"{category}商品{i}", category, f"{category} 的描述 {i}"])
        registry["categories"][category] = {
            "items": ITEMS_PER_CATEGORY,
            "dimension": DIM,
            "items_csv": f"{category}/items.csv",
            "image_index": f"{category}/image_index.faiss",
        }
    (root / "index_registry.json").write_text(
        json.dumps(registry, ensure_ascii=False), encoding="utf-8"
    )
    return IndexStore(root, candidate_k=10)


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class IndexStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = _build_index(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_loads_registry(self) -> None:
        self.assertEqual(self.store.categories, sorted(CATEGORIES))
        self.assertEqual(self.store.dimension, DIM)

    def test_exact_vector_hits_its_own_item(self) -> None:
        embeddings = np.load(Path(self.tmp.name) / "甲" / "image_embeddings.npy")
        hits = self.store.search(embeddings[2], ["甲"], top_k=1)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].vector_id, 2)
        self.assertEqual(hits[0].category, "甲")
        self.assertAlmostEqual(hits[0].score, 1.0, places=5)

    def test_result_hides_internal_fields(self) -> None:
        embeddings = np.load(Path(self.tmp.name) / "乙" / "image_embeddings.npy")
        hit = self.store.search(embeddings[0], ["乙"], top_k=1)[0].as_dict()
        self.assertNotIn("vector_id", hit)
        self.assertNotIn("text", hit)
        self.assertEqual(hit["category"], "乙")

    def test_wrong_dimension_is_rejected(self) -> None:
        with self.assertRaises(ApiError) as caught:
            self.store.search(np.zeros(DIM + 3, dtype="float32"), ["甲"], top_k=1)
        self.assertEqual(caught.exception.code, ErrorCode.DIM_MISMATCH)

    def test_best_category_returns_the_owning_category(self) -> None:
        embeddings = np.load(Path(self.tmp.name) / "乙" / "image_embeddings.npy")
        category, score, scores = self.store.best_category(embeddings[1])
        self.assertEqual(category, "乙")
        self.assertEqual(set(scores), set(CATEGORIES))
        self.assertGreaterEqual(score, max(scores.values()) - 1e-6)


class EncoderTest(unittest.TestCase):
    def test_placeholder_is_deterministic_and_normalised(self) -> None:
        encoder = PlaceholderEncoder(dim=DIM)
        self.assertFalse(encoder.model_loaded)
        first = encoder.encode_text("白色运动鞋")
        second = encoder.encode_text("白色运动鞋")
        np.testing.assert_allclose(first, second)
        self.assertAlmostEqual(float(np.linalg.norm(first)), 1.0, places=5)
        self.assertFalse(np.allclose(first, encoder.encode_text("黑色双肩包")))

    def test_placeholder_image_vector_is_stable(self) -> None:
        encoder = PlaceholderEncoder(dim=DIM)
        image = Image.open(io.BytesIO(_png_bytes()))
        np.testing.assert_allclose(encoder.encode_image(image), encoder.encode_image(image))


class ServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.service = MatchService(
            PlaceholderEncoder(dim=DIM), _build_index(Path(self.tmp.name))
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_classify_image(self) -> None:
        result = self.service.classify_image(Image.open(io.BytesIO(_png_bytes())))
        self.assertIn(result["category"], CATEGORIES)
        self.assertLessEqual(len(result["topk"]), 3)

    def test_search_text_respects_top_k(self) -> None:
        result = self.service.search_text("白色运动鞋", top_k=3)
        self.assertLessEqual(len(result["items"]), 3)
        self.assertEqual(result["query"], "白色运动鞋")

    def test_match_reports_both_categories(self) -> None:
        result = self.service.match(Image.open(io.BytesIO(_png_bytes())), "白色运动鞋", top_k=2)
        self.assertIsInstance(result["match"], bool)
        self.assertIn(result["image_category"], CATEGORIES)
        self.assertIn(result["text_category"], CATEGORIES)


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.service = MatchService(PlaceholderEncoder(dim=DIM), _build_index(Path(cls.tmp.name)))
        app.dependency_overrides[get_match_service] = lambda: cls.service
        from fastapi.testclient import TestClient

        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        cls.tmp.cleanup()

    def test_health_marks_placeholder_mode(self) -> None:
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["code"], 0)
        self.assertFalse(body["result"]["model_loaded"])

    def test_image_endpoint_accepts_png(self) -> None:
        response = self.client.post(
            "/api/v1/image", files={"file": ("p.png", _png_bytes(), "image/png")}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)

    def test_image_endpoint_rejects_non_image(self) -> None:
        response = self.client.post(
            "/api/v1/image", files={"file": ("p.txt", b"not an image", "text/plain")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], ErrorCode.INVALID_IMAGE)

    def test_text_endpoint_validates_empty_query(self) -> None:
        response = self.client.post("/api/v1/text", json={"query": "", "top_k": 3})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], ErrorCode.BAD_REQUEST)

    def test_text_endpoint_returns_items(self) -> None:
        response = self.client.post("/api/v1/text", json={"query": "白色运动鞋", "top_k": 2})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.json()["result"]["items"]), 2)

    def test_unknown_path_returns_404_body(self) -> None:
        response = self.client.get("/api/v1/nope")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], ErrorCode.NOT_FOUND)

    def test_error_body_keeps_the_agreed_shape(self) -> None:
        body = self.client.post("/api/v1/text", json={"query": ""}).json()
        self.assertEqual(set(body), {"code", "result", "msg"})
        self.assertIsNone(body["result"])
        self.assertTrue(body["msg"])

    def test_internal_error_hides_server_details(self) -> None:
        def boom():
            raise RuntimeError("boom-secret")

        app.dependency_overrides[get_match_service] = boom
        try:
            response = self.client.post("/api/v1/text", json={"query": "x"})
        finally:
            app.dependency_overrides[get_match_service] = lambda: self.service
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["code"], ErrorCode.INTERNAL_ERROR)
        self.assertNotIn("boom-secret", response.json()["msg"])


class ErrorCodeTest(unittest.TestCase):
    def test_http_status_is_derived_from_business_code(self) -> None:
        for code in ErrorCode:
            expected = 200 if code is ErrorCode.OK else int(code) // 100
            self.assertEqual(code.http_status, expected, f"{code.name}={int(code)}")

    def test_api_error_carries_status_and_message(self) -> None:
        error = ApiError(ErrorCode.CATEGORY_NOT_FOUND, "包")
        self.assertEqual(error.status, 404)
        self.assertIn("类别不存在", error.msg)
        self.assertIn("包", error.msg)

    def test_unknown_business_code_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ApiError(12345)


class ConfigTest(unittest.TestCase):
    def test_build_encoder_defaults_to_placeholder(self) -> None:
        class FakeSettings:
            model_backend = "placeholder"
            embedding_dim = DIM

        encoder = build_encoder(FakeSettings())
        self.assertIsInstance(encoder, PlaceholderEncoder)
        self.assertEqual(encoder.dim, DIM)


if __name__ == "__main__":
    unittest.main()