import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from vsl_streaming.capture import load_frames, sha256_file, validate_capture_receipt
from vsl_streaming.video import FrameSampler, assign_hands


def capture_receipt(frames):
    return dict(schema_version=1, extractor_profile="custom-profile", software={
        "client_version": "test", "mediapipe_tasks": "test", "delegate": "CPU"},
        assets={key: {"sha256": "a" * 64} for key in ("pose", "hand")},
        coordinates={"rotation_policy": "upright", "inference_mirrored": False, "preview_mirrored": False},
        clock={"source": "test-clock", "strictly_increasing_ms": True},
        sampling={"target_fps": 10, "observed_frames": 2, "skipped_rate_limit": 0, "skipped_busy": 0},
        frames_sha256=sha256_file(frames))


class CaptureContractTests(unittest.TestCase):
    def test_evaluate_cli_accepts_direct_events_responses_and_replay_receipts(self):
        from vsl_streaming.cli import main
        annotations = {"schema_version": 1, "scope": "synthetic", "recordings": [{
            "recording_id": "synthetic-1", "split_role": "demo", "source_group": "generated-1",
            "speaker_identity": {"status": "unverified"},
            "annotations": [{"start_ms": 0, "end_ms": 100, "label": "A"}]}]}
        event = dict(start_ms=0, end_ms=100, status="predicted", reason="gap", prediction={"label": "A"})
        reply = dict(type="result", request_id="r1", replayed=False, events=[event])
        responses = [{"type": "ready"}, reply, dict(reply, replayed=True)]
        formats = [[dict(event, label="A")], responses, {"responses": responses}]
        with tempfile.TemporaryDirectory() as tmp:
            annotations_path, predictions_path, output_path = (Path(tmp) / name for name in
                ("annotations.json", "predictions.json", "evaluation.json"))
            annotations_path.write_text(json.dumps(annotations), encoding="utf-8")
            totals = []
            for predictions in formats:
                predictions_path.write_text(json.dumps({"synthetic-1": predictions}), encoding="utf-8")
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["evaluate", "--annotations", str(annotations_path),
                        "--predictions", str(predictions_path), "--out", str(output_path)]), 0)
                result = json.loads(output_path.read_text(encoding="utf-8"))
                totals.append(result["totals"])
                self.assertEqual(result["totals"]["matched_signs"], 1)
                self.assertEqual(result["totals"]["matched_gloss_accuracy"], 1)
                self.assertEqual(result["totals"]["gloss_sequence"]["distance"], 0)
                self.assertEqual(result["inputs"]["predictions"]["sha256"], sha256_file(predictions_path))
                self.assertTrue(result["software_version"])
            self.assertEqual(totals[0], totals[1])
            self.assertEqual(totals[1], totals[2])

    def test_jsonl_and_array_have_same_frames_but_different_byte_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            array, lines = Path(tmp) / "array.json", Path(tmp) / "phone.jsonl"
            values = [{"seq": 1, "timestamp_ms": 5}, {"seq": 2, "timestamp_ms": 7}]
            array.write_text(json.dumps(values), encoding="utf-8")
            lines.write_text("\n".join(json.dumps(f) for f in values) + "\n", encoding="utf-8")
            self.assertEqual(load_frames(array), load_frames(lines))
            self.assertNotEqual(sha256_file(array), sha256_file(lines))
            lines.write_text("\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_frames(lines)

    def test_receipt_binds_exact_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            frames = Path(tmp) / "frames.json"
            frames.write_text('[{"seq": 0, "timestamp_ms": 0}]\n', encoding="utf-8")
            receipt = capture_receipt(frames)
            self.assertIs(validate_capture_receipt(receipt, frames), receipt)
            for key in ("assets", "clock", "sampling", "frames_sha256"):
                bad = copy.deepcopy(receipt)
                del bad[key]
                with self.assertRaises(ValueError):
                    validate_capture_receipt(bad, frames)
            frames.write_text("[ ]\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                validate_capture_receipt(receipt, frames)

    def test_receipt_requires_typed_common_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            frames = Path(tmp) / "frames.json"
            frames.write_text('[{"seq":0,"timestamp_ms":0}]', encoding="utf-8")
            good = capture_receipt(frames)
            mutations = [("software", "client_version", ""), ("software", "mediapipe_tasks", None),
                         ("software", "delegate", "GPU"), ("coordinates", "rotation_policy", 90),
                         ("coordinates", "inference_mirrored", 0), ("coordinates", "preview_mirrored", "false"),
                         ("clock", "source", " "), ("clock", "strictly_increasing_ms", 1),
                         ("sampling", "target_fps", True), ("sampling", "target_fps", float("nan")),
                         ("sampling", "target_fps", 10**400), ("sampling", "target_fps", 0),
                         ("sampling", "observed_frames", -1), ("sampling", "skipped_rate_limit", True),
                         ("sampling", "skipped_busy", -1)]
            for section, key, value in mutations:
                with self.subTest(section=section, key=key, value=value):
                    bad = copy.deepcopy(good)
                    bad[section][key] = value
                    with self.assertRaises(ValueError):
                        validate_capture_receipt(bad, frames)
            for section, key, _ in mutations:
                bad = copy.deepcopy(good)
                del bad[section][key]
                with self.assertRaises(ValueError):
                    validate_capture_receipt(bad, frames)

    def test_receipt_counts_distinguish_processed_and_admitted_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            frames = Path(tmp) / "frames.jsonl"
            frames.write_text('{"seq":2,"timestamp_ms":100}\n{"seq":5,"timestamp_ms":200}\n', encoding="utf-8")
            receipt = capture_receipt(frames)
            receipt["delegate"] = receipt["software"].pop("delegate")
            receipt["sampling"].update(observed_frames=8, skipped_busy=None, processed_frames=5,
                                       missing_pose_frames_retained=5, trace_frames=2)
            validate_capture_receipt(receipt, frames)
            for key, value in (("trace_frames", 5), ("processed_frames", 1), ("observed_frames", 1)):
                bad = copy.deepcopy(receipt)
                bad["sampling"][key] = value
                with self.assertRaises(ValueError):
                    validate_capture_receipt(bad, frames)
            receipt["sampling"].update(emitted_frames=2, missing_pose_frames=2)
            validate_capture_receipt(receipt, frames)
            for key in ("emitted_frames", "missing_pose_frames"):
                bad = copy.deepcopy(receipt)
                bad["sampling"][key] = 1
                with self.assertRaises(ValueError):
                    validate_capture_receipt(bad, frames)

    def test_trace_contract_rejects_corrupt_frames_even_with_matching_hash(self):
        invalid = [[], [{"seq": 0}], [{"seq": True, "timestamp_ms": 0}],
                   [{"seq": 0, "timestamp_ms": float("nan")}],
                   [{"seq": 0, "timestamp_ms": 0, "pose_landmarks": []}],
                   [{"seq": 0, "timestamp_ms": 0}, {"seq": 0, "timestamp_ms": 1}],
                   [{"seq": 0, "timestamp_ms": 1}, {"seq": 1, "timestamp_ms": 1}],
                   [{"seq": 1, "timestamp_ms": 2}, {"seq": 0, "timestamp_ms": 3}]]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.json"
            for values in invalid:
                with self.subTest(values=values):
                    path.write_text(json.dumps(values), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        validate_capture_receipt(capture_receipt(path), path)

    def test_receipt_rejects_impossible_processing_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            frames = Path(tmp) / "frames.json"
            frames.write_text('[{"seq":0,"timestamp_ms":0}]', encoding="utf-8")
            receipt = capture_receipt(frames)
            receipt["sampling"].update(observed_frames=5, processed_frames=2, extraction_errors=1,
                                       skipped_rate_limit=2, missing_pose_frames_retained=3)
            # A delivery callback may fail after a missing-pose detection was counted.
            validate_capture_receipt(receipt, frames)
            for field, value in (("processed_frames", 6), ("processed_frames", 3),
                                 ("skipped_rate_limit", 3), ("extraction_errors", 2),
                                 ("missing_pose_frames_retained", 4)):
                bad = copy.deepcopy(receipt)
                bad["sampling"][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_capture_receipt(bad, frames)

    def test_timestamp_sampling_preserves_irregular_times(self):
        sampler = FrameSampler(10)
        values = [0, 33, 66, 101, 132, 165, 220, 400]
        self.assertEqual([t for t in values if sampler.keep(t)], [0, 101, 220, 400])
        with self.assertRaises(ValueError):
            sampler.keep(400)
        for value in (0, -1, float("nan"), True, 121, 10**400):
            with self.assertRaises(ValueError):
                FrameSampler(value)

    def test_hand_assignment_and_collision_policy(self):
        pose = [{"x": 0, "y": 0, "visibility": 1} for _ in range(33)]
        pose[16]["x"] = 1
        left = [{"x": .1, "y": 0}] * 21
        closer = [{"x": .01, "y": 0}] * 21
        right = [{"x": .99, "y": 0}] * 21
        chosen = assign_hands(pose, [left, right, closer], ["Right", "Left", "Right"])
        self.assertIs(chosen[0], closer)
        self.assertIs(chosen[1], right)
        self.assertEqual(assign_hands(None, [left], ["Left"]), (left, None))
        self.assertEqual(assign_hands(None, [left], ["Unknown"]), (None, None))


class VideoDecodeTests(unittest.TestCase):
    def test_decode_no_pose_retained_and_overwrite_rejected(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("optional video dependencies unavailable")
        from vsl_streaming.video import extract_video

        class EmptyExtractor:
            def __init__(self, *args):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def extract(self, rgb, timestamp_ms):
                return {"pose_landmarks": None, "left_hand_landmarks": None, "right_hand_landmarks": None}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "blank.avi"
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 20, (64, 64))
            if not writer.isOpened():
                self.skipTest("MJPG writer unavailable")
            for _ in range(20):
                writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
            writer.release()
            assets = root / "dummy.task"
            assets.write_bytes(b"test double asset")
            output = root / "frames.json"
            for kwargs in ({"input_mirrored": "false"}, {"rotate": False}, {"rotate": 90.0}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    extract_video(video, assets, assets, output, extractor_factory=EmptyExtractor, **kwargs)
                self.assertFalse(output.exists())
                self.assertFalse(output.with_suffix(".capture.json").exists())
            result = extract_video(video, assets, assets, output, target_fps=10,
                                   timestamp_mode="frame-index", extractor_factory=EmptyExtractor)
            self.assertEqual(result["decoded_frames"], 20)
            frames = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(frames), 10)
            self.assertEqual([f["seq"] for f in frames], list(range(10)))
            self.assertTrue(all(f["pose_landmarks"] is None for f in frames))
            receipt = json.loads(output.with_suffix(".capture.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["sampling"]["missing_pose_frames"], 10)
            validate_capture_receipt(receipt, output)
            with self.assertRaisesRegex(ValueError, "new files"):
                extract_video(video, assets, assets, output, extractor_factory=EmptyExtractor)
            with self.assertRaisesRegex(ValueError, "max_frames"):
                extract_video(video, assets, assets, root / "limited.json", max_frames=3,
                              timestamp_mode="frame-index", extractor_factory=EmptyExtractor)
            self.assertFalse((root / "limited.json").exists())


if __name__ == "__main__":
    unittest.main()
