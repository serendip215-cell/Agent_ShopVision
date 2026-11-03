"""后端最小自检：索引检索、占位编码器、服务组合、三个接口的返回与错误码。

自建一个小索引（2 类 × 4 条，8 维），不依赖仓库里的大索引，可离线跑：

    cd webapp/backend && python -m unittest discover -s tests -v
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

# 异步任务测试跑 eager 模式：任务在进程内同步执行，CI 不需要 Redis。
# 必须在导入 app.* 之前设置（get_settings / celery_app 都是模块级单例）。
os.environ.setdefault("SHOPVISION_CELERY_ALWAYS_EAGER", "true")

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.deps import get_match_service  # noqa: E402
from app.errors import ApiError, ErrorCode  # noqa: E402
from app.main import app  # noqa: E402
from app.services.encoder import PlaceholderEncoder, build_encoder  # noqa: E402
from app.services.index_store import IndexStore  # noqa: E402
from app.services.matching import MatchService  # noqa: E402
from scripts.export_api_docs import render_markdown  # noqa: E402

DIM = 8
CATEGORIES = ["甲", "乙"]
ITEMS_PER_CATEGORY = 4


def _build_index(root: Path) -> IndexStore:
    """写一个最小可用的索引目录：注册表 + 每类 items.csv 与 image_embeddings.npy。"""
    rng = np.random.default_rng(20261101)
    registry: dict = {
        "version": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "categories": {},
        "model": {"name": "test", "checkpoint": "checkpoints/epoch3.pt"},
    }
    for category in CATEGORIES:
        vectors = rng.standard_normal((ITEMS_PER_CATEGORY, DIM)).astype("float32")
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        folder = root / category
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder / "image_embeddings.npy", vectors)
        with (folder / "items.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["vector_id", "item_name", "product_type", "type", "text"])
            for i in range(ITEMS_PER_CATEGORY):
                writer.writerow(
                    [
                        i,
                        f"{category}商品{i}",
                        category,
                        f"{category}细分类{i}",
                        f"{category} 的描述 {i}",
                    ]
                )
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

    def test_summary_reports_counts_from_registry(self) -> None:
        summary = self.store.summary()
        self.assertEqual(summary["category_counts"], {c: ITEMS_PER_CATEGORY for c in CATEGORIES})
        self.assertEqual(summary["total_items"], ITEMS_PER_CATEGORY * len(CATEGORIES))
        self.assertEqual(summary["category_ready"], {c: True for c in CATEGORIES})
        self.assertEqual(summary["model_name"], "test")
        self.assertEqual(summary["model_checkpoint"], "checkpoints/epoch3.pt")
        self.assertEqual(summary["updated_at"], "2026-01-01T00:00:00Z")

    def test_summary_marks_category_with_missing_files(self) -> None:
        (Path(self.tmp.name) / "甲" / "image_embeddings.npy").unlink()
        summary = self.store.summary()
        self.assertFalse(summary["category_ready"]["甲"])
        self.assertTrue(summary["category_ready"]["乙"])

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

    def test_best_category_checks_dimension_like_search(self) -> None:
        """不同源时也要给 DIM_MISMATCH，不能放过 matmul 的 ValueError。"""
        with self.assertRaises(ApiError) as caught:
            self.store.best_category(np.zeros(DIM + 3, dtype="float32"))
        self.assertEqual(caught.exception.code, ErrorCode.DIM_MISMATCH)


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
        self.service = MatchService(PlaceholderEncoder(dim=DIM), _build_index(Path(self.tmp.name)))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_classify_image(self) -> None:
        result = self.service.classify_image(Image.open(io.BytesIO(_png_bytes())))
        self.assertIn(result["category"], CATEGORIES)
        self.assertLessEqual(len(result["topk"]), 3)
        self.assertTrue(all("confidence" in row for row in result["topk"]))
        # 相似商品推荐来自判出类别内的真实检索结果
        self.assertTrue(result["items"])
        self.assertTrue(all(hit["category"] == result["category"] for hit in result["items"]))

    def test_search_text_respects_top_k(self) -> None:
        result = self.service.search_text("白色运动鞋", top_k=3)
        self.assertLessEqual(len(result["items"]), 3)
        self.assertEqual(result["query"], "白色运动鞋")

    def test_search_text_reports_model_category_independent_of_filter(self) -> None:
        result = self.service.search_text("白色运动鞋", top_k=3, category="甲")
        self.assertEqual(result["category"], "甲")
        self.assertIn(result["query_category"], CATEGORIES)
        self.assertIsNotNone(result["query_score"])

    def test_search_text_mismatched_category_returns_no_items(self) -> None:
        model_category, _, _ = self.service.index.best_category(
            self.service.encoder.encode_text("白色运动鞋")
        )
        other_category = next(c for c in CATEGORIES if c != model_category)
        result = self.service.search_text("白色运动鞋", top_k=3, category=other_category)
        self.assertEqual(result["category"], other_category)
        self.assertEqual(result["query_category"], model_category)
        self.assertEqual(result["items"], [])

    def test_search_text_matching_category_returns_items(self) -> None:
        model_category, _, _ = self.service.index.best_category(
            self.service.encoder.encode_text("白色运动鞋")
        )
        result = self.service.search_text("白色运动鞋", top_k=3, category=model_category)
        self.assertEqual(result["query_category"], model_category)
        self.assertTrue(result["items"])

    def test_match_reports_both_categories(self) -> None:
        result = self.service.match(Image.open(io.BytesIO(_png_bytes())), "白色运动鞋", top_k=2)
        self.assertIsInstance(result["match"], bool)
        self.assertIn(result["image_category"], CATEGORIES)
        self.assertIn(result["text_category"], CATEGORIES)
        # 图像塔细分类来自判出类别内最相似商品的 type
        self.assertTrue(str(result["image_type"]).startswith(result["image_category"]))


class ApiTest(unittest.TestCase):
    # 类级标注：setUpClass 里赋值的属性，mypy 只认这里的声明
    tmp: tempfile.TemporaryDirectory
    service: MatchService
    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.service = MatchService(PlaceholderEncoder(dim=DIM), _build_index(Path(cls.tmp.name)))
        app.dependency_overrides[get_match_service] = lambda: cls.service
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
        self.assertEqual(body["result"]["total_items"], ITEMS_PER_CATEGORY * len(CATEGORIES))
        self.assertEqual(
            body["result"]["category_counts"], {c: ITEMS_PER_CATEGORY for c in CATEGORIES}
        )
        self.assertEqual(body["result"]["category_ready"], {c: True for c in CATEGORIES})
        self.assertEqual(body["result"]["model_name"], "test")

    def test_image_endpoint_accepts_png(self) -> None:
        response = self.client.post(
            "/api/v1/image", files={"file": ("p.png", _png_bytes(), "image/png")}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)

    def test_oversized_upload_is_rejected(self) -> None:
        limit = get_settings().max_upload_mb * 1024 * 1024
        payload = b"\x89PNG" + b"\x00" * (limit + 1)
        response = self.client.post(
            "/api/v1/image", files={"file": ("big.png", payload, "image/png")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], ErrorCode.FILE_TOO_LARGE)

    def test_image_endpoint_rejects_non_image(self) -> None:
        response = self.client.post(
            "/api/v1/image", files={"file": ("p.txt", b"not an image", "text/plain")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], ErrorCode.INVALID_IMAGE)

    def test_encoder_index_mismatch_is_400_not_500(self) -> None:
        """编码器与索引不同源：图像分类要走 DIM_MISMATCH，不能掉进 500 兜底。"""
        mismatched = MatchService(
            PlaceholderEncoder(dim=DIM + 3), _build_index(Path(self.tmp.name))
        )
        app.dependency_overrides[get_match_service] = lambda: mismatched
        try:
            response = self.client.post(
                "/api/v1/image", files={"file": ("p.png", _png_bytes(), "image/png")}
            )
        finally:
            app.dependency_overrides[get_match_service] = lambda: self.service
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], ErrorCode.DIM_MISMATCH)

    def test_text_endpoint_validates_empty_query(self) -> None:
        response = self.client.post("/api/v1/text", json={"query": "", "top_k": 3})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], ErrorCode.BAD_REQUEST)

    def test_text_endpoint_returns_items(self) -> None:
        response = self.client.post("/api/v1/text", json={"query": "白色运动鞋", "top_k": 2})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.json()["result"]["items"]), 2)

    def test_text_endpoint_returns_model_category(self) -> None:
        response = self.client.post("/api/v1/text", json={"query": "白色运动鞋", "top_k": 2})
        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertIn("query_category", result)
        self.assertIn("query_score", result)

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


class AsyncTaskApiTest(unittest.TestCase):
    """异步任务接口：eager 模式下任务同步执行，不需要真 Redis。"""

    tmp: tempfile.TemporaryDirectory
    service: MatchService
    client: TestClient
    patcher: mock._patch

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.service = MatchService(PlaceholderEncoder(dim=DIM), _build_index(Path(cls.tmp.name)))
        app.dependency_overrides[get_match_service] = lambda: cls.service
        # 任务在进程内跑，不经过 FastAPI 依赖注入，直接 patch 任务模块里的取服务函数
        cls.patcher = mock.patch("app.tasks.get_match_service", lambda: cls.service)
        cls.patcher.start()
        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.patcher.stop()
        app.dependency_overrides.clear()
        cls.tmp.cleanup()

    def _submit_and_poll(self, response: Any) -> dict:
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["code"], 0)
        task_id = body["result"]["task_id"]
        polled = self.client.get(f"/api/v1/tasks/{task_id}").json()
        self.assertEqual(polled["code"], 0)
        return polled["result"]

    def test_single_image_task_completes(self) -> None:
        response = self.client.post(
            "/api/v1/tasks/image", files={"file": ("p.png", _png_bytes(), "image/png")}
        )
        polled = self._submit_and_poll(response)
        self.assertEqual(polled["status"], "SUCCESS")
        self.assertIn(polled["result"]["category"], CATEGORIES)

    def test_batch_task_returns_one_result_per_file(self) -> None:
        files = [
            ("files", ("a.png", _png_bytes(), "image/png")),
            ("files", ("b.png", _png_bytes(), "image/png")),
        ]
        response = self.client.post("/api/v1/tasks/batch", files=files)
        polled = self._submit_and_poll(response)
        self.assertEqual(polled["status"], "SUCCESS")
        self.assertEqual(len(polled["result"]), 2)
        self.assertEqual({item["file_name"] for item in polled["result"]}, {"a.png", "b.png"})
        for item in polled["result"]:
            self.assertEqual(item["code"], 0)
            self.assertIn(item["result"]["category"], CATEGORIES)

    def test_batch_rejects_invalid_image_before_enqueue(self) -> None:
        files = [("files", ("bad.txt", b"not an image", "text/plain"))]
        response = self.client.post("/api/v1/tasks/batch", files=files)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], ErrorCode.INVALID_IMAGE)

    def test_batch_rejects_too_many_files(self) -> None:
        limit = get_settings().async_batch_max_files
        files = [("files", (f"{i}.png", _png_bytes(), "image/png")) for i in range(limit + 1)]
        response = self.client.post("/api/v1/tasks/batch", files=files)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], ErrorCode.BAD_REQUEST)

    def test_unknown_task_id_reads_as_pending(self) -> None:
        body = self.client.get("/api/v1/tasks/not-a-real-task").json()
        self.assertEqual(body["code"], 0)
        self.assertEqual(body["result"]["status"], "PENDING")

    def test_single_task_business_error_is_reported_as_failure(self) -> None:
        """任务内部把业务错误当返回值；轮询接口要还原成 FAILURE，不能回 SUCCESS + null。"""
        from celery.result import EagerResult  # 延迟导入：只有这个用例需要

        from app.api import tasks as tasks_api

        task_id = "business-error-task"
        tasks_api._EAGER_RESULTS[task_id] = EagerResult(
            task_id,
            {"code": int(ErrorCode.INVALID_IMAGE), "result": None, "msg": "坏图"},
            "SUCCESS",
        )
        try:
            body = self.client.get(f"/api/v1/tasks/{task_id}").json()
        finally:
            tasks_api._EAGER_RESULTS.pop(task_id, None)
        self.assertEqual(body["result"]["status"], "FAILURE")
        self.assertEqual(body["result"]["error"]["code"], int(ErrorCode.INVALID_IMAGE))
        self.assertEqual(body["result"]["error"]["msg"], "坏图")


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
            ApiError(12345)  # type: ignore[arg-type]  # 故意传非法码，验证构造器会拒绝


class ConfigTest(unittest.TestCase):
    def test_settings_is_a_cached_singleton(self) -> None:
        self.assertIs(get_settings(), get_settings())

    def test_build_encoder_defaults_to_placeholder(self) -> None:
        class FakeSettings:
            model_backend = "placeholder"
            embedding_dim = DIM

        # 鸭子类型替身：build_encoder 只用这两个字段，不读 .env
        encoder = build_encoder(FakeSettings())  # type: ignore[arg-type]
        self.assertIsInstance(encoder, PlaceholderEncoder)
        self.assertEqual(encoder.dim, DIM)


class OpenApiTest(unittest.TestCase):
    """/docs 的数据源（OpenAPI）不该退化：result 必须是有形状的模型，不是 Any。"""

    def setUp(self) -> None:
        self.schema = app.openapi()

    def test_declares_the_seven_endpoints(self) -> None:
        self.assertEqual(
            set(self.schema["paths"]),
            {
                "/api/v1/health",
                "/api/v1/image",
                "/api/v1/text",
                "/api/v1/match",
                "/api/v1/tasks/image",
                "/api/v1/tasks/batch",
                "/api/v1/tasks/{task_id}",
            },
        )

    def test_every_response_keeps_the_three_field_shape(self) -> None:
        for name, result_model in [
            ("HealthResponse", "HealthResult"),
            ("ImageResponse", "ImageResult"),
            ("TextResponse", "TextResult"),
            ("MatchResponse", "MatchResult"),
            ("TaskSubmitResponse", "TaskSubmitResult"),
            ("TaskStatusResponse", "TaskStatusResult"),
        ]:
            props = self.schema["components"]["schemas"][name]["properties"]
            self.assertEqual(set(props), {"code", "result", "msg"}, name)
            self.assertEqual(
                props["result"]["anyOf"][0]["$ref"],
                f"#/components/schemas/{result_model}",
                name,
            )

    def test_error_codes_are_documented_per_endpoint(self) -> None:
        responses = self.schema["paths"]["/api/v1/image"]["post"]["responses"]
        for http_code in ("400", "404", "500"):
            self.assertIn(http_code, responses)

    def test_endpoints_are_grouped_by_page(self) -> None:
        post = self.schema["paths"]["/api/v1/match"]["post"]
        self.assertEqual(post["tags"], ["多模态匹配页"])


class ExportApiDocsTest(unittest.TestCase):
    """交付用的离线 API 文档是生成的，别让它悄悄生成出半截内容。"""

    def setUp(self) -> None:
        schema = app.openapi()
        self.markdown = render_markdown(schema, list(ErrorCode))

    def test_lists_every_endpoint(self) -> None:
        for path in (
            "/api/v1/health",
            "/api/v1/image",
            "/api/v1/text",
            "/api/v1/match",
            "/api/v1/tasks/image",
            "/api/v1/tasks/batch",
            "/api/v1/tasks/{task_id}",
        ):
            self.assertIn(path, self.markdown)

    def test_expands_result_into_concrete_fields(self) -> None:
        # result 那一支要能解出 $ref，解不出来表格里就只剩 code/msg
        for field in ("result.topk[].similarity", "result.items[].item_name", "result.match"):
            self.assertIn(f"`{field}`", self.markdown)

    def test_upload_field_is_marked_as_file(self) -> None:
        self.assertIn("| `file` | 文件 | 文件 | 是 |", self.markdown)

    def test_nested_objects_use_dot_paths_not_array_suffix(self) -> None:
        # progress / error 是对象，文档里必须写成 result.progress.done
        for field in ("result.progress.done", "result.error.code"):
            self.assertIn(f"`{field}`", self.markdown)
        self.assertNotIn("result.progress[]", self.markdown)
        self.assertNotIn("result.error[]", self.markdown)

    def test_carries_the_error_code_table(self) -> None:
        for code in (ErrorCode.FILE_TOO_LARGE, ErrorCode.DIM_MISMATCH):
            self.assertIn(f"| `{int(code)}` |", self.markdown)


if __name__ == "__main__":
    unittest.main()
