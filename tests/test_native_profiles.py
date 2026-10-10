"""Analytic contract tests; optional local comparison uses generated landmarks only."""
import copy
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import numpy as np

from vsl_streaming.bundle import validate_profile
from vsl_streaming.runtime import prepare_tensor


def profile(name):
    spoter = name == "spoter54-legacy-v1"
    return {"schema_version": 1, "input_name": "poses", "output_name": "logits",
            "layout": "BTVC" if spoter else "BCTVM", "num_frames": 70 if spoter else 150,
            "num_points": 54 if spoter else 27, "num_channels": 2 if spoter else 3,
            "preprocessing": {"name": name, "config": {}}}


SPOTER = profile("spoter54-legacy-v1")
SLGCN = profile("slgcn27-bone-v1")


def points(count, x=0.4, y=0.5, visibility=1.0):
    return [{"x": x, "y": y, "z": 0.0, "visibility": visibility} for _ in range(count)]


def generated_frames(length):
    rng = np.random.default_rng(173 + length)
    result = []
    for t in range(length):
        frame = {"seq": t, "timestamp_ms": t * 1000 / 30}
        for name, count in (("pose_landmarks", 33), ("left_hand_landmarks", 21), ("right_hand_landmarks", 21)):
            if t % 11 == 7 or (name == "left_hand_landmarks" and t % 3 == 1):
                frame[name] = None
            else:
                coords = rng.uniform(0.01, 0.99, (count, 4))
                frame[name] = [{"x": float(x), "y": float(y), "z": float(z), "visibility": float(v)} for x, y, z, v in coords]
        result.append(frame)
    return result


class NativeProfileTests(unittest.TestCase):
    def test_fixed_shapes_temporal_contracts_and_options(self):
        for spec, sampling in ((SPOTER, "repeat-or-linspace-floor-v1"), (SLGCN, "linear-min30-repeat-or-prefix-v1")):
            self.assertEqual(validate_profile(spec)["temporal_sampling"], sampling)
            for key, bad in (("num_frames", 17), ("num_points", 49), ("num_channels", 4), ("layout", "BTVC" if spec["layout"] == "BCTVM" else "BCTVM")):
                with self.subTest(spec=spec, key=key), self.assertRaises(ValueError):
                    validate_profile(dict(spec, **{key: bad}))
            with self.assertRaises(ValueError):
                validate_profile(dict(spec, temporal_sampling="uniform-nearest-v1"))
            changed = copy.deepcopy(spec)
            changed["preprocessing"]["config"] = {"flip": True}
            with self.assertRaises(ValueError):
                validate_profile(changed)

    def test_missing_components_keep_legacy_mask_values(self):
        frames = [{"pose_landmarks": None, "left_hand_landmarks": None, "right_hand_landmarks": None}]
        first, second = prepare_tensor(frames, SPOTER), prepare_tensor(frames, SLGCN)
        self.assertEqual(first.shape, (1, 70, 54, 2))
        self.assertEqual(second.shape, (1, 3, 150, 27, 1))
        np.testing.assert_array_equal(first, -0.5)
        np.testing.assert_array_equal(second, 0.0)
        self.assertEqual(first.dtype, np.float32)
        self.assertTrue(second.flags.c_contiguous)

    def test_spoter_cycle_padding_and_floor_downsampling(self):
        def make(length):
            result = []
            for t in range(length):
                pose = points(33, 0.0, 0.0)
                pose[0]["x"] = float(t + 1)  # Missing shoulders retain the raw nose coordinate.
                result.append({"pose_landmarks": pose})
            return result
        short = prepare_tensor(make(3), SPOTER)[0, :, 0, 0]
        np.testing.assert_array_equal(short, np.resize([0.5, 1.5, 2.5], 70))
        long = prepare_tensor(make(73), SPOTER)[0, :, 0, 0]
        expected = np.floor(np.arange(70) * 72 / 69) + 0.5
        np.testing.assert_array_equal(long, expected)

    def test_spoter_dummy_neck_and_body_bounds(self):
        pose = points(33, 0.4, 0.2)
        pose[11], pose[12] = {"x": 0.6, "y": 0.5}, {"x": 0.4, "y": 0.5}
        pose[0] = {"x": 0.3, "y": 0.2}
        result = prepare_tensor([{"pose_landmarks": pose}], SPOTER)
        # Clipped box x=[0,.6], y=[0,.4], followed by -.5.
        np.testing.assert_allclose(result[0, 0, 0], [0.0, 0.0], atol=1e-7)
        np.testing.assert_array_equal(result[0, :, 1], -0.5)

    def test_spoter_historical_hand_grouping_is_explicit(self):
        # Left/right are concatenated, but the legacy dict names alternate.
        frame = {"pose_landmarks": None, "left_hand_landmarks": points(21, 0.2, 0.2),
                 "right_hand_landmarks": points(21, 0.8, 0.8)}
        result = prepare_tensor([frame], SPOTER)[0, 0]
        np.testing.assert_allclose(result[12:33], -5 / 12, atol=1e-7)
        np.testing.assert_allclose(result[33:], 5 / 12, atol=1e-7)

    def test_zero_area_spoter_hand_is_rejected_before_model(self):
        with self.assertRaisesRegex(ValueError, "zero-area"):
            prepare_tensor([{"pose_landmarks": None, "left_hand_landmarks": points(21)}], SPOTER)

    def test_slgcn_confidence_is_not_depth_and_hands_use_presence(self):
        frame = {"pose_landmarks": points(33, visibility=0.7), "left_hand_landmarks": points(21, visibility=0.0)}
        first = prepare_tensor([frame], SLGCN)
        for component in frame.values():
            for point in component:
                point["z"] = -999.0
        second = prepare_tensor([frame], SLGCN)
        np.testing.assert_array_equal(first, second)
        np.testing.assert_array_equal(first[0, :2], 0.0)  # A constant track has zero standardized xy.
        self.assertAlmostEqual(float(first[0, 2, 0, 7, 0]), 0.7, places=6)  # Pose-wrist to hand-wrist edge.
        self.assertEqual(float(first[0, 2, 0, 8, 0]), 1.0)
        np.testing.assert_array_equal(first[0, :, :, 0, 0], 0.0)  # No incoming edge for root.
        np.testing.assert_array_equal(first[0, 2, :, 17:, 0], 0.0)

    def test_slgcn_short_visibility_uses_nearest_then_cycle(self):
        frames = [{"pose_landmarks": points(33, visibility=1.0)}, {"pose_landmarks": points(33, visibility=0.0)}]
        result = prepare_tensor(frames, SLGCN)[0, 2, :, 1, 0]
        np.testing.assert_array_equal(result, np.tile(np.r_[np.ones(15), np.zeros(15)], 5))

    def test_slgcn_distribution_precedes_prefix_truncation(self):
        frames = []
        t = np.arange(180, dtype=np.float32)
        for value in t:
            pose = points(33)
            pose[0]["x"], pose[11]["x"] = float(value), float(value ** 2)
            frames.append({"pose_landmarks": pose})
        result = prepare_tensor(frames, SLGCN)
        expected = ((t ** 2 - (t ** 2).mean()) / (t ** 2).std() - (t - t.mean()) / t.std())[:150]
        np.testing.assert_allclose(result[0, 0, :, 1, 0], expected, atol=2e-7)

    def test_inputs_are_not_mutated(self):
        frames = generated_frames(9)
        original = copy.deepcopy(frames)
        for spec in (SPOTER, SLGCN):
            prepare_tensor(frames, spec)
            self.assertEqual(frames, original)

    def test_invalid_landmarks_and_order_are_rejected(self):
        bad_inputs = [[], [{}], [{"points": [[1, 2]]}], [{"pose": points(33)}],
                      [{"pose_landmarks": points(32)}], [{"pose_landmarks": points(33, x=float("nan"))}],
                      [{"pose_landmarks": points(33, x=True)}], [{"pose_landmarks": points(33, visibility=1.1)}],
                      [{"pose_landmarks": points(33, x=10 ** 400)}],
                      [{"pose_landmarks": None, "seq": 1}, {"pose_landmarks": None, "seq": 1}],
                      [{"pose_landmarks": None, "timestamp_ms": 2}, {"pose_landmarks": None, "timestamp_ms": 1}]]
        for spec in (SPOTER, SLGCN):
            for frames in bad_inputs:
                with self.subTest(profile=spec["preprocessing"]["name"], frames=repr(frames)[:80]), self.assertRaises(ValueError):
                    prepare_tensor(frames, spec)

    def test_finite_overflow_input_cannot_create_nonfinite_model_tensor(self):
        for spec in (SPOTER, SLGCN):
            with self.subTest(profile=spec), self.assertRaises(ValueError):
                prepare_tensor([{"pose_landmarks": points(33, x=1e300)}], spec)
        # Values may fit float32 while their variance overflows; do not silently
        # normalize with an infinite denominator and disguise the invalid input.
        with self.assertRaisesRegex(ValueError, "distribution overflowed"):
            prepare_tensor([{"pose_landmarks": points(33, x=value)} for value in (-1e30, 1e30)], SLGCN)


@unittest.skipUnless(os.environ.get("VSL_OWNER_SERVER_ROOT"), "Optional comparison requires a separately authorized owner checkout")
class OwnerTransformParityTests(unittest.TestCase):
    def test_generated_inputs_match_owner_transform_outputs(self):
        root = str(Path(os.environ["VSL_OWNER_SERVER_ROOT"]).resolve())
        sys.path.insert(0, root)
        try:
            from pipelines import spoter_onnx_inference as source
            from pipelines.slgcn_onnx_inference import SLGCNONNXInferer
            for length in (1, 2, 29, 30, 69, 70, 71, 149, 150, 151, 301):
                frames = generated_frames(length)
                converted = [SimpleNamespace(**{name: None if frame[name] is None else SimpleNamespace(
                    landmark=[SimpleNamespace(**point) for point in frame[name]]) for name in
                    ("pose_landmarks", "left_hand_landmarks", "right_hand_landmarks")}) for frame in frames]
                original = converted
                for transform in (source.JointSelect(), source.Pad(70), source.TensorToDict(), source.SingleBodyDictNormalize(),
                                  source.SingleHandDictNormalize(), source.DictToTensor(), source.Shift()):
                    original = transform(original)
                with self.subTest(name="spoter", length=length):
                    np.testing.assert_array_equal(prepare_tensor(frames, SPOTER), original.astype(np.float32)[None])
                inferer = SLGCNONNXInferer.__new__(SLGCNONNXInferer)
                inferer.num_frames, inferer.min_sequence_frames, inferer.motion_stream = 150, 30, False
                with self.subTest(name="slgcn", length=length):
                    np.testing.assert_array_equal(prepare_tensor(frames, SLGCN), inferer.preprocess(converted))
        finally:
            sys.path.remove(root)


if __name__ == "__main__":
    unittest.main()
