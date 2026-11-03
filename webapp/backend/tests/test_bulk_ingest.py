"""批量导入脚本的目录布局识别：子目录名当类别、--category 覆盖、根目录图片要报错。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bulk_ingest import collect_jobs  # noqa: E402


class CollectJobsTest(unittest.TestCase):
    def test_subdirectories_become_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "鞋").mkdir()
            (root / "包" / "子目录").mkdir(parents=True)
            (root / "鞋" / "a.JPG").write_bytes(b"x")
            (root / "鞋" / "b.png").write_bytes(b"x")
            (root / "鞋" / "readme.txt").write_text("忽略")
            (root / "包" / "子目录" / "c.webp").write_bytes(b"x")

            self.assertEqual(
                collect_jobs(root),
                [("鞋", root / "鞋" / "a.JPG"), ("鞋", root / "鞋" / "b.png")],
            )
            self.assertEqual(
                collect_jobs(root, recursive=True),
                [
                    ("包", root / "包" / "子目录" / "c.webp"),
                    ("鞋", root / "鞋" / "a.JPG"),
                    ("鞋", root / "鞋" / "b.png"),
                ],
            )

    def test_explicit_category_overrides_directory_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "随便叫什么").mkdir()
            (root / "随便叫什么" / "a.jpg").write_bytes(b"x")

            self.assertEqual(
                collect_jobs(root, category="鞋", recursive=True),
                [("鞋", root / "随便叫什么" / "a.jpg")],
            )

    def test_bare_images_without_category_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.png").write_bytes(b"x")
            with self.assertRaises(ValueError):
                collect_jobs(root)


if __name__ == "__main__":
    unittest.main()
