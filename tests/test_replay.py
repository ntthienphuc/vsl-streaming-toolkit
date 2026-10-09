"""Replay receipts must identify the data and full interpretation contract."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from test_bundle import make_model, PROFILE
from vsl_streaming.bundle import register_onnx
from vsl_streaming.cli import replay
from vsl_streaming.config import ServerConfig
from vsl_streaming.core import StreamConfig


class ReplayReceiptTests(unittest.TestCase):
    def test_receipt_distinguishes_same_graph_with_different_label_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model, labels, profile = (root / name for name in
                                      ("model.onnx", "labels.json", "profile.json"))
            make_model(model)
            profile.write_text(json.dumps(PROFILE), encoding="utf-8")
            frames = root / "frames.json"
            frames.write_text(json.dumps([{"seq": i, "timestamp_ms": i * 20,
                                           "points": [[1, 1], [1, 1]]}
                                          for i in range(4)]), encoding="utf-8")
            config = ServerConfig(stream=StreamConfig(mode="fixed_window", window_frames=4,
                                                       min_segment_frames=1, min_up_frames=1))
            receipts = []
            for index, order in enumerate((["hello", "thanks"], ["thanks", "hello"])):
                labels.write_text(json.dumps(order), encoding="utf-8")
                bundle = root / ("bundle%d" % index)
                manifest = register_onnx(model, labels, profile, bundle)
                receipt = replay(bundle, frames, config, batch_size=2)
                self.assertEqual(receipt["status"], "passed")
                self.assertEqual(receipt["input_sha256"], hashlib.sha256(frames.read_bytes()).hexdigest())
                self.assertEqual(receipt["bundle_sha256"], manifest["sha256"])
                self.assertIn("onnxruntime", receipt["environment"]["versions"])
                receipts.append(receipt)
            self.assertEqual(receipts[0]["model_sha256"], receipts[1]["model_sha256"])
            self.assertNotEqual(receipts[0]["bundle_sha256"]["labels.json"],
                                receipts[1]["bundle_sha256"]["labels.json"])
            self.assertNotEqual(receipts[0]["responses"][-1]["events"][0]["prediction"]["label"],
                                receipts[1]["responses"][-1]["events"][0]["prediction"]["label"])


if __name__ == "__main__":
    unittest.main()
