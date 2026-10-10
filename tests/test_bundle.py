import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

from vsl_streaming.bundle import register_onnx, validate_bundle, validate_profile
from vsl_streaming.runtime import ONNXRecognizer, prepare_tensor


PROFILE = {"schema_version": 1, "input_name": "keypoints", "output_name": "logits", "layout": "BTVC",
           "num_frames": 4, "num_points": 2, "num_channels": 2,
           "preprocessing": {"name": "identity-v1", "config": {}}}


def make_model(path, classes=2, shape=None):
    shape = shape or [1, 4, 2, 2]
    weights = np.arange(16 * classes, dtype=np.float32).reshape(16, classes) / 100
    graph = helper.make_graph([
        helper.make_node("Flatten", ["keypoints"], ["flat"], axis=1),
        helper.make_node("MatMul", ["flat", "weights"], ["logits"]),
    ], "toy", [helper.make_tensor_value_info("keypoints", TensorProto.FLOAT, shape)],
       [helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, classes])],
       [numpy_helper.from_array(weights, "weights")])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, path)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.model = self.directory / "model.onnx"
        self.labels = self.directory / "labels.json"
        self.profile = self.directory / "profile.json"
        self.bundle = self.directory / "bundle"
        make_model(self.model)
        self.labels.write_text(json.dumps(["hello", "thanks"]), encoding="utf-8")
        self.profile.write_text(json.dumps(PROFILE), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def register(self):
        return register_onnx(self.model, self.labels, self.profile, self.bundle)

    def test_register_and_predict(self):
        self.assertEqual(self.register()["parity"]["status"], "unverified")
        recognizer = ONNXRecognizer(self.bundle)
        result = recognizer.predict_segment([{"seq": 0, "timestamp": 0, "points": [[1, 1], [1, 1]]}])
        self.assertEqual(result["label"], "thanks")
        self.assertEqual(len(result["top_k"]), 2)
        self.assertAlmostEqual(sum(x["confidence"] for x in result["top_k"]), 1)

    def test_artifact_tampering_is_detected(self):
        self.register()
        for name in ("model.onnx", "labels.json", "profile.json"):
            path = self.bundle / name
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "checksum"):
                validate_bundle(self.bundle)
            path.write_bytes(original)

    def test_ordered_labels_change_is_detected(self):
        self.register()
        (self.bundle / "labels.json").write_text('["thanks", "hello"]')
        with self.assertRaisesRegex(ValueError, "checksum"):
            ONNXRecognizer(self.bundle)

    def test_malformed_manifest_rejected_before_runtime(self):
        original = self.register()
        path = self.bundle / "manifest.json"
        malformed = [None, [], True,
                     dict(original, schema_version=True),
                     dict(original, schema_version=1.0),
                     dict(original, sha256=None),
                     dict(original, sha256=list(original["sha256"])),
                     dict(original, sha256=dict(original["sha256"], **{"model.onnx": 42})),
                     dict(original, num_classes=True),
                     dict(original, num_classes=2.0)]
        for manifest in malformed:
            with self.subTest(manifest=manifest):
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(ValueError):
                    ONNXRecognizer(self.bundle)

    def test_profile_version_requires_integer_not_boolean_or_float(self):
        for value in (True, 1.0, "1", None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "schema_version"):
                validate_profile(dict(PROFILE, schema_version=value))

    def test_class_mismatch_rejected_before_publish(self):
        make_model(self.model, classes=3)
        with self.assertRaisesRegex(ValueError, "class count"):
            self.register()
        self.assertFalse(self.bundle.exists())

    def test_shape_mismatch_rejected_before_publish(self):
        profile = dict(PROFILE, num_frames=5)
        self.profile.write_text(json.dumps(profile))
        with self.assertRaisesRegex(ValueError, "input shape"):
            self.register()
        self.assertFalse(self.bundle.exists())

    def test_unknown_preprocessing_setting_rejected(self):
        profile = dict(PROFILE, preprocessing={"name": "identity-v1", "config": {"flip": True}})
        self.profile.write_text(json.dumps(profile))
        with self.assertRaisesRegex(ValueError, "unknown options"):
            self.register()

    def test_provider_must_be_available(self):
        self.register()
        with self.assertRaisesRegex(ValueError, "provider is unavailable"):
            ONNXRecognizer(self.bundle, provider="MissingExecutionProvider")

    def test_temporal_sampling_and_bctvm_are_deterministic(self):
        frames = [{"points": [[i, i], [i, i]]} for i in range(3)]
        tensor = prepare_tensor(frames, PROFILE)
        np.testing.assert_array_equal(tensor[0, :, 0, 0], [0, 1, 1, 2])
        other = prepare_tensor(frames, dict(PROFILE, layout="BCTVM"))
        np.testing.assert_array_equal(other[0, :, :, :, 0], tensor[0].transpose(2, 0, 1))

    def test_shoulder_translation_scale_invariance_and_missing_hands(self):
        profile = dict(PROFILE, num_points=49, preprocessing={"name": "mediapipe49-shoulder-v1", "config": {}})
        pose = np.ones((33, 2), dtype=np.float32)
        pose[11], pose[12] = [0.3, 0.5], [0.7, 0.5]
        first = prepare_tensor([{"pose": pose.tolist()}], profile)
        second = prepare_tensor([{"pose": (pose * 2 + 5).tolist()}], profile)
        np.testing.assert_allclose(first, second, atol=1e-5)
        np.testing.assert_array_equal(first[0, :, 7:, :], 0)

    def test_bad_frame_and_time_rejected(self):
        for frames in ([{"points": [[float("nan"), 0], [0, 0]]}],
                       [{"seq": 1, "points": [[0, 0], [0, 0]]}, {"seq": 1, "points": [[0, 0], [0, 0]]}]):
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                prepare_tensor(frames, PROFILE)

    def test_overwrite_requires_explicit_flag(self):
        self.register()
        with self.assertRaises(FileExistsError):
            self.register()
        register_onnx(self.model, self.labels, self.profile, self.bundle, overwrite=True)
        self.assertEqual(validate_bundle(self.bundle)["labels"], ["hello", "thanks"])

    def test_torch_export_parity_and_failure_is_not_published(self):
        import torch
        from vsl_streaming.exporting import export_pytorch
        model = torch.nn.Sequential(torch.nn.Flatten(), torch.nn.Linear(16, 2))
        checkpoint = self.directory / "weights.pt"
        torch.save(model.state_dict(), checkpoint)
        module = type(sys)("vsl_test_factory")
        module.build = lambda: torch.nn.Sequential(torch.nn.Flatten(), torch.nn.Linear(16, 2))
        with patch.dict(sys.modules, {"vsl_test_factory": module}):
            result = export_pytorch("vsl_test_factory:build", checkpoint, self.labels, self.profile, self.bundle)
            self.assertEqual(result["parity"]["status"], "passed")
            self.assertLess(result["parity"]["max_absolute_error"], 1e-5)
            # A wrapper intentionally changes class decisions inside ONNX execution.
            from vsl_streaming import exporting
            original_create = exporting.create_session
            class WrongSession:
                def __init__(self, session): self.session = session
                def get_inputs(self): return self.session.get_inputs()
                def get_outputs(self): return self.session.get_outputs()
                def run(self, *args): return [self.session.run(*args)[0] + 10]
            with patch.object(exporting, "create_session", side_effect=lambda path: WrongSession(original_create(path))):
                destination = self.directory / "failed"
                with self.assertRaisesRegex(ValueError, "parity failed"):
                    export_pytorch("vsl_test_factory:build", checkpoint, self.labels, self.profile, destination)
                self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
