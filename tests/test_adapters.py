"""Checks for externally supplied preprocessing and representative parity."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
from vsl_streaming.bundle import sha256
from vsl_streaming.cli import identity_profile, write_json
from vsl_streaming.exporting import export_pytorch
from vsl_streaming.runtime import ONNXRecognizer


class AdapterTests(unittest.TestCase):
    def setUp(self):
        import torch
        from vsl_streaming.demo_model import build_model
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.profile = identity_profile()
        write_json(self.root / "labels.json", ["one", "two"])
        torch.save(build_model().state_dict(), self.root / "weights.pt")

    def tearDown(self):
        sys.modules.pop("vsl_external_fixture", None)
        if str(self.root) in sys.path:
            sys.path.remove(str(self.root))
        self.temporary.cleanup()

    def export(self, **kwargs):
        write_json(self.root / "profile.json", self.profile)
        return export_pytorch("vsl_streaming.demo_model:build_model", self.root / "weights.pt",
                              self.root / "labels.json", self.root / "profile.json", self.root / "bundle", **kwargs)

    def test_representative_tensors_are_counted_and_bound(self):
        samples = self.root / "samples.npz"
        np.savez(samples, inputs=np.full((5, 12, 3, 2), 0.2, dtype=np.float32))
        result = self.export(validation_tensors_path=samples)
        self.assertEqual(result["parity"]["num_probes"], 8)
        self.assertEqual(result["parity"]["num_user_tensors"], 5)
        self.assertEqual(result["parity"]["validation_npz_sha256"], sha256(samples))

    def test_malformed_validation_tensors_do_not_publish(self):
        for array in (np.zeros((1, 12, 3, 2), dtype=np.float64),
                      np.zeros((2, 12, 2, 2), dtype=np.float32),
                      np.full((1, 12, 3, 2), np.nan, dtype=np.float32)):
            samples = self.root / "bad.npz"
            np.savez(samples, inputs=array)
            with self.assertRaisesRegex(ValueError, "Validation inputs"):
                self.export(validation_tensors_path=samples)
            self.assertFalse((self.root / "bundle").exists())

    def test_external_preprocessor_checked_before_runtime(self):
        source = self.root / "vsl_external_fixture.py"
        source.write_text("import numpy as np\ndef prepare(frames, profile, value=1):\n    return np.full((1,12,3,2), value, dtype=np.float32)\n", encoding="utf-8")
        dependency = self.root / "rules.txt"
        dependency.write_text("original")
        sys.path.insert(0, str(self.root))
        importlib.invalidate_caches()
        self.profile["preprocessing"] = {"name": "external-python-v1", "config": {
            "factory": "vsl_external_fixture:prepare", "source_sha256": sha256(source),
            "kwargs": {"value": 2}, "source_dependencies": {str(dependency): sha256(dependency)}}}
        self.profile["temporal_sampling"] = "external-python-v1"
        self.export()
        result = ONNXRecognizer(self.root / "bundle").predict_segment([{"seq": 0, "timestamp_ms": 0}])
        self.assertIn(result["label"], ["one", "two"])
        dependency.write_text("changed")
        with self.assertRaisesRegex(ValueError, "dependency checksum"):
            ONNXRecognizer(self.root / "bundle")
        dependency.write_text("original")
        source.write_text(source.read_text() + "# changed\n")
        with self.assertRaisesRegex(ValueError, "source checksum"):
            ONNXRecognizer(self.root / "bundle")

    def test_overwrite_preserves_unrelated_file(self):
        self.export()
        extra = self.root / "bundle" / "unrelated.txt"
        extra.write_text("keep")
        with self.assertRaisesRegex(ValueError, "extra files"):
            self.export(overwrite=True)
        self.assertEqual(extra.read_text(), "keep")

if __name__ == "__main__":
    unittest.main()
