"""Protect acceptance boundaries and prevent unfair backend comparisons."""
import copy
import sys
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1] / "code"
sys.path.insert(0, str(CODE))
from evaluate_acceleration import (
    REPO_ROOT, DEFAULT_CONFIG, read_json, resolve_relative, runtime_rows,
    accuracy_row, acceptance_rows,
)


class AccelerationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = read_json(REPO_ROOT / DEFAULT_CONFIG)
        cls.thresholds = cls.config["thresholds"]
        cls.payload = read_json(REPO_ROOT / cls.config["sources"]["runtime_trt"])
        cls.group = cls.config["runtime_groups"][2]
        cls.baseline = read_json(REPO_ROOT / cls.config["sources"]["baseline"])

    def test_paired_latency_and_source_throughput(self):
        rows = runtime_rows(self.payload, self.group, self.thresholds)
        self.assertAlmostEqual(rows[0]["speedup"], 4.59/1.94)
        self.assertAlmostEqual(rows[0]["throughput_gain_pct"], (515.5/217.9-1)*100)
        self.assertTrue(all(row["latency_pass"] and row["throughput_pass"] for row in rows))

    def test_provider_fallback_is_rejected(self):
        payload = copy.deepcopy(self.payload)
        payload["results"][0]["ort"]["actual_providers"] = ["CPUExecutionProvider"]
        with self.assertRaisesRegex(ValueError, "回退"):
            runtime_rows(payload, self.group, self.thresholds)

    def test_cross_device_comparison_is_rejected(self):
        payload = copy.deepcopy(self.payload)
        payload["results"][0]["torch"]["device"] = "cpu"
        with self.assertRaisesRegex(ValueError, "设备"):
            runtime_rows(payload, self.group, self.thresholds)

    def test_mismatched_cpu_threads_are_rejected(self):
        group = self.config["runtime_groups"][0]
        payload = read_json(REPO_ROOT / self.config["sources"][group["source"]])
        payload["torch_threads"] = 4
        with self.assertRaisesRegex(ValueError, "线程"):
            runtime_rows(payload, group, self.thresholds)

    def test_accuracy_uses_own_baseline_and_pp(self):
        group = self.config["accuracy_groups"][1]
        payload = read_json(REPO_ROOT / self.config["sources"][group["source"]])
        row = accuracy_row(payload, self.baseline, group, self.thresholds)
        self.assertAlmostEqual(row["delta_r1_pp"], -.4283)
        self.assertTrue(row["graph_accuracy_pass"])
        payload["candidate_pool"] = 933
        with self.assertRaisesRegex(ValueError, "候选池"):
            accuracy_row(payload, self.baseline, group, self.thresholds)

    def test_inclusive_acceptance_boundary(self):
        runtime = [{"group": "trt", "batch": b, "latency_reduction_pct": 40.,
                    "throughput_gain_pct": 50., "speedup": 1.2} for b in (1, 32)]
        accuracy = [{"group": "trt", "delta_r1_pp": -.5}]
        self.assertTrue(all(r["passed"] for r in acceptance_rows(runtime, accuracy, "trt", self.thresholds)))
        accuracy[0]["delta_r1_pp"] = -.5001
        rows = acceptance_rows(runtime, accuracy, "trt", self.thresholds)
        self.assertFalse(next(r["passed"] for r in rows if r["task"] == "3.2.1" and r["unit"] == "pp"))

    def test_zero_latency_is_rejected(self):
        payload = copy.deepcopy(self.payload)
        payload["results"][0]["ort"]["median_ms"] = 0
        with self.assertRaises(ValueError):
            runtime_rows(payload, self.group, self.thresholds)

    def test_output_and_input_paths_are_repo_relative(self):
        for path in ("../outside", "D:/external", "/tmp/external"):
            with self.assertRaises(ValueError):
                resolve_relative(path)


if __name__ == "__main__":
    unittest.main()
