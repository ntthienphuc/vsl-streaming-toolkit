"""Optional, offline MediaPipe Tasks extraction with explicit capture provenance.

No raw video, model asset, or participant trace is bundled with the library.
Desktop and Android use separately identified capture profiles, even where
their assignment policies agree. Detector parity must be measured separately.
"""
from contextlib import ExitStack
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform

from .capture import sha256_file, validate_capture_receipt
from .core import _frame

EXTRACTOR_PROFILE = "desktop-mediapipe-tasks-pose-hands-v1"


def assign_hands(pose, hands, handedness, threshold=0.08):
    """Nearest visible pose wrist, then model handedness; no temporal cache.

    Collisions retain the closest wrist candidate (or first handedness-only
    candidate). Distances are squared normalized image distances. This local
    assignment is a specified heuristic, not person tracking or sign recognition.
    """
    chosen = {"left": (math.inf, None), "right": (math.inf, None)}
    for index, hand in enumerate(hands):
        candidates = []
        if pose is not None:
            for side, wrist_index in (("left", 15), ("right", 16)):
                wrist = pose[wrist_index]
                if wrist["visibility"] >= 0.5:
                    distance = sum((hand[0][axis] - wrist[axis]) ** 2 for axis in ("x", "y"))
                    candidates.append((distance, side))
        distance, side = min(candidates) if candidates else (math.inf, "")
        if distance > threshold:
            label = handedness[index].lower() if index < len(handedness) else ""
            if label not in chosen:
                continue
            side, distance = label, math.inf
        previous_distance, previous_hand = chosen[side]
        if previous_hand is None or distance < previous_distance:
            chosen[side] = (distance, hand)
    return chosen["left"][1], chosen["right"][1]


def _landmarks(values, visibility=True):
    return [{"x": float(p.x), "y": float(p.y), "z": float(p.z),
             "visibility": float(p.visibility) if visibility and p.visibility is not None else 1.0}
            for p in values]


class MediaPipeExtractor:
    """Synchronous CPU Tasks VIDEO mode, one pose and at most two hands."""

    def __init__(self, pose_model, hand_model):
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        self.mp = mp
        self.stack = ExitStack()
        try:
            base = lambda path: python.BaseOptions(model_asset_path=str(Path(path).resolve()),
                                                   delegate=python.BaseOptions.Delegate.CPU)
            self.pose = self.stack.enter_context(vision.PoseLandmarker.create_from_options(
                vision.PoseLandmarkerOptions(base_options=base(pose_model), running_mode=vision.RunningMode.VIDEO,
                    num_poses=1, min_pose_detection_confidence=0.5,
                    min_pose_presence_confidence=0.5, min_tracking_confidence=0.5)))
            self.hands = self.stack.enter_context(vision.HandLandmarker.create_from_options(
                vision.HandLandmarkerOptions(base_options=base(hand_model), running_mode=vision.RunningMode.VIDEO,
                    num_hands=2, min_hand_detection_confidence=0.5,
                    min_hand_presence_confidence=0.5, min_tracking_confidence=0.5)))
        except BaseException:
            self.stack.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stack.close()

    def extract(self, rgb, timestamp_ms):
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        result = self.pose.detect_for_video(image, timestamp_ms)
        detected_hands = self.hands.detect_for_video(image, timestamp_ms)
        pose = _landmarks(result.pose_landmarks[0]) if result.pose_landmarks else None
        hands = [_landmarks(hand, visibility=False) for hand in detected_hands.hand_landmarks]
        labels = [categories[0].category_name if categories else "" for categories in detected_hands.handedness]
        left, right = assign_hands(pose, hands, labels)
        return {"pose_landmarks": pose, "left_hand_landmarks": left, "right_hand_landmarks": right}


class FrameSampler:
    """Time-based sampling without relabeling irregular timestamps as fixed FPS."""

    def __init__(self, target_fps):
        if isinstance(target_fps, bool) or not isinstance(target_fps, (int, float)) or not 0 < target_fps <= 120 or not math.isfinite(target_fps):
            raise ValueError("target_fps must be finite and in (0, 120]")
        self.interval = 1000.0 / target_fps
        self.next_due = None
        self.previous = None

    def keep(self, timestamp_ms):
        if isinstance(timestamp_ms, bool) or not isinstance(timestamp_ms, (int, float)) or not math.isfinite(timestamp_ms) or timestamp_ms < 0:
            raise ValueError("video timestamp must be finite and nonnegative")
        if self.previous is not None and timestamp_ms <= self.previous:
            raise ValueError("video timestamps are not strictly increasing; inspect the file or explicitly select --timestamp-mode frame-index")
        self.previous = timestamp_ms
        if self.next_due is None:
            self.next_due = timestamp_ms
        if timestamp_ms + 1e-7 < self.next_due:
            return False
        self.next_due += (math.floor((timestamp_ms + 1e-7 - self.next_due) / self.interval) + 1) * self.interval
        return True


def extract_video(video_path, pose_model, hand_model, output_path, target_fps=15.0,
                  timestamp_mode="pos-msec", rotate=0, input_mirrored=False,
                  max_frames=100000, extractor_factory=MediaPipeExtractor):
    """Decode a local file and write canonical frames plus ``*.capture.json``.

    The default uses decoder timestamps and rejects discontinuities. The explicit
    frame-index mode synthesizes times from reported FPS and is unsuitable for
    claims about original variable-frame-rate timing. Decode failure versus EOF
    cannot always be distinguished by OpenCV; declared truncation is rejected.
    """
    import cv2
    from . import __version__
    sampler = FrameSampler(target_fps)
    if timestamp_mode not in ("pos-msec", "frame-index") or rotate not in (0, 90, 180, 270):
        raise ValueError("invalid timestamp mode or rotation")
    if type(max_frames) is not int or max_frames < 1:
        raise ValueError("max_frames must be a positive integer")
    paths = [Path(p) for p in (video_path, pose_model, hand_model)]
    for path in paths:
        if not path.is_file():
            raise ValueError("input file does not exist: " + str(path))
    out = Path(output_path)
    sidecar = out.with_suffix(".capture.json")
    if out == sidecar or out.exists() or sidecar.exists():
        raise ValueError("frame output and capture sidecar must be distinct, new files")
    source_hashes = [sha256_file(p) for p in paths]
    cap = cv2.VideoCapture(str(paths[0]))
    try:
        if not cap.isOpened():
            raise ValueError("video cannot be opened")
        backend = cap.getBackendName()
        rotation_disabled = bool(cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 0))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if timestamp_mode == "frame-index" and (not math.isfinite(fps) or fps <= 0):
            raise ValueError("frame-index mode requires positive reported FPS")
        reported_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        reported_count = int(reported_count) if math.isfinite(reported_count) and reported_count > 0 else None
        frames, source_indices, decoded, skipped, last_task_ms = [], [], 0, 0, None
        with extractor_factory(pose_model, hand_model) as extractor:
            while True:
                ok, bgr = cap.read()
                if not ok:
                    break
                if decoded >= max_frames:
                    raise ValueError("video exceeds max_frames; raise the bound explicitly for this file")
                timestamp = decoded * 1000.0 / fps if timestamp_mode == "frame-index" else float(cap.get(cv2.CAP_PROP_POS_MSEC))
                index = decoded
                decoded += 1
                if not sampler.keep(timestamp):
                    skipped += 1
                    continue
                task_ms = int(round(timestamp))
                if last_task_ms is not None and task_ms <= last_task_ms:
                    raise ValueError("sampled timestamps collide at MediaPipe millisecond resolution")
                last_task_ms = task_ms
                if rotate:
                    bgr = cv2.rotate(bgr, {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}[rotate])
                if input_mirrored:
                    bgr = cv2.flip(bgr, 1)
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                observations = extractor.extract(rgb, task_ms)
                # Missing detections are retained as null observations, never cached.
                frames.append(_frame(dict(observations, seq=len(frames), timestamp_ms=timestamp)))
                source_indices.append(index)
        if not frames:
            raise ValueError("video contains no decodable frames")
        if reported_count is not None and decoded < reported_count:
            raise ValueError("video ended before its reported frame count; no completed trace was written")
    finally:
        cap.release()
    # Detect files modified while the extraction was running.
    if source_hashes != [sha256_file(p) for p in paths]:
        raise ValueError("input video or detector asset changed during extraction")
    receipt = {
        "schema_version": 1, "extractor_profile": EXTRACTOR_PROFILE,
        "scope": "offline video extraction; no sign accuracy or Android capture parity is implied",
        "software": {"client_version": __version__, "python": platform.python_version(),
                     "mediapipe_tasks": version("mediapipe") if extractor_factory is MediaPipeExtractor else "test-double",
                     "opencv": cv2.__version__, "decoder_backend": backend, "delegate": "CPU"},
        "assets": {role: {"sha256": value, "source_url": None} for role, value in zip(("pose", "hand"), source_hashes[1:])},
        "source": {"video_sha256": source_hashes[0], "reported_fps": fps if math.isfinite(fps) else None,
                   "reported_frame_count": reported_count, "selected_source_indices": source_indices,
                   "decode_limit": max_frames, "decode_end": "read returned false; reported truncation rejected"},
        "coordinates": {"rotation_policy": "decoder output plus explicit clockwise rotation", "rotate_degrees": rotate,
                        "decoder_auto_rotation_disabled": rotation_disabled, "input_declared_mirrored": input_mirrored,
                        "inference_mirrored": False, "preview_mirrored": False},
        "clock": {"source": "decoder-pos-msec" if timestamp_mode == "pos-msec" else "frame-index/reported-fps",
                  "strictly_increasing_ms": True, "task_timestamp_policy": "round to nearest integer ms; reject collision"},
        "assignment": {"algorithm": "nearest-visible-pose-wrist-then-handedness-v1", "squared_distance_threshold": 0.08,
                       "visibility_threshold": 0.5, "collision_policy": "closest wrist, first fallback", "hand_cache_ms": 0},
        "detector": {"mode": "VIDEO", "num_poses": 1, "num_hands": 2, "confidence_thresholds": 0.5},
        "sampling": {"target_fps": target_fps, "observed_frames": decoded, "emitted_frames": len(frames),
                     "skipped_busy": 0, "skipped_rate_limit": skipped,
                     "missing_pose_frames": sum(f["pose_landmarks"] is None for f in frames)},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental replacement of a trace used in a study.
    with out.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(frames, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    receipt["frames_sha256"] = sha256_file(out)
    validate_capture_receipt(receipt, out)
    with sidecar.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    return {"status": "extracted", "frames": str(out.resolve()), "capture_receipt": str(sidecar.resolve()),
            "decoded_frames": decoded, "emitted_frames": len(frames), "frames_sha256": receipt["frames_sha256"]}
