"""Deterministic keypoint preparation and a persistent ONNX inference session."""
from __future__ import annotations

from pathlib import Path
import importlib
from typing import Mapping, Sequence

import numpy as np

from .bundle import check_logits, check_session, create_session, input_shape, sha256, validate_bundle, validate_profile
from .native_profiles import PROFILE_CONTRACTS, prepare_native_tensor


def external_preprocessor(profile):
    """Load trusted model-owner code; verify declared files before predictions.

    Module import executes Python (including package imports). File hashes
    provide reproducibility checks, not a sandbox or a trust signature.
    """
    config = profile["preprocessing"]["config"]
    module_name, function_name = config["factory"].split(":")
    module = importlib.import_module(module_name)
    source = getattr(module, "__file__", None)
    if not source or sha256(source) != config["source_sha256"]:
        raise ValueError("External preprocessing source checksum mismatch")
    for path, digest in config["source_dependencies"].items():
        if sha256(path) != digest:
            raise ValueError("External preprocessing dependency checksum mismatch: " + path)
    function = getattr(module, function_name)
    if not callable(function):
        raise ValueError("External preprocessor must be callable")
    return function


def external_tensor(frames, profile, function):
    tensor = function(frames, profile, **profile["preprocessing"]["config"]["kwargs"])
    if (not isinstance(tensor, np.ndarray) or tensor.dtype != np.float32
            or tensor.shape != input_shape(profile) or not np.isfinite(tensor).all()):
        raise ValueError("External preprocessor must return finite float32 tensor with declared model shape")
    return np.ascontiguousarray(tensor)


def _xy_landmarks(value, count, name):
    if value is None:
        return np.zeros((count, 2), dtype=np.float32), False
    if isinstance(value, list) and value and isinstance(value[0], Mapping):
        try:
            value = [[point["x"], point["y"]] for point in value]
        except KeyError as exc:
            raise ValueError(name + " landmarks require x and y") from exc
    array = np.asarray(value, dtype=np.float32)
    if array.ndim != 2 or array.shape[0] != count or array.shape[1] < 2 or not np.isfinite(array).all():
        raise ValueError(name + " must contain %d finite xy landmarks" % count)
    return array[:, :2], True


def prepare_tensor(frames: Sequence[Mapping], profile: dict) -> np.ndarray:
    """Prepare the exact versioned profile declared by the model bundle.

    Identity/shoulder profiles use uniform nearest sampling. The native model
    profiles have their own fixed temporal contracts (see PREPROCESSING_PROFILES).

    The new shoulder profile uses pose indexes 0,11,12,13,14,15,16,
    followed by all left-hand and right-hand points in MediaPipe order.
    xy coordinates are centered at shoulder midpoint and divided by shoulder
    width. Missing hands stay zero; a missing/degenerate pose is rejected.
    This is NOT the legacy SPOTER or SL-GCN training transform.
    """
    profile = validate_profile(profile)
    if not frames:
        raise ValueError("At least one frame is required")
    if profile["preprocessing"]["name"] in PROFILE_CONTRACTS:
        return prepare_native_tensor(frames, profile["preprocessing"]["name"])
    if profile["preprocessing"]["name"] == "external-python-v1":
        return external_tensor(frames, profile, external_preprocessor(profile))
    points = []
    previous_seq, previous_time = None, None
    for frame in frames:
        if not isinstance(frame, Mapping):
            raise ValueError("Each frame must be an object")
        seq = frame.get("seq")
        timestamp = frame.get("timestamp_ms", frame.get("timestamp"))
        if seq is not None:
            if type(seq) is not int or seq < 0 or (previous_seq is not None and seq <= previous_seq):
                raise ValueError("Frame seq must be a nonnegative strictly increasing integer")
            previous_seq = seq
        if timestamp is not None:
            if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not np.isfinite(timestamp) or timestamp < 0:
                raise ValueError("Frame timestamp must be finite and nonnegative")
            if previous_time is not None and timestamp <= previous_time:
                raise ValueError("Frame timestamps must increase strictly")
            previous_time = timestamp
        if profile["preprocessing"]["name"] == "identity-v1":
            array = np.asarray(frame.get("points"), dtype=np.float32)
            if array.shape != (profile["num_points"], profile["num_channels"]) or not np.isfinite(array).all():
                raise ValueError("points shape/values disagree with profile")
        else:
            pose, present = _xy_landmarks(frame.get("pose_landmarks", frame.get("pose", frame.get("pose33"))), 33, "pose_landmarks")
            left, left_present = _xy_landmarks(frame.get("left_hand_landmarks", frame.get("left_hand")), 21, "left_hand_landmarks")
            right, right_present = _xy_landmarks(frame.get("right_hand_landmarks", frame.get("right_hand")), 21, "right_hand_landmarks")
            width = float(np.linalg.norm(pose[11] - pose[12]))
            if not present or width <= 1e-6:
                raise ValueError("Shoulder profile requires visible distinct shoulders")
            center = (pose[11] + pose[12]) / 2
            body = (pose[[0, 11, 12, 13, 14, 15, 16]] - center) / width
            left = (left - center) / width if left_present else left
            right = (right - center) / width if right_present else right
            array = np.concatenate((body, left, right), axis=0)
        points.append(array)
    data = np.asarray(points, dtype=np.float32)
    indices = np.floor(np.linspace(0, len(data) - 1, profile["num_frames"]) + 0.5).astype(np.int64)
    sampled = data[indices]
    if profile["layout"] == "BTVC":
        result = sampled[np.newaxis]
    else:
        result = sampled.transpose(2, 0, 1)[np.newaxis, ..., np.newaxis]
    if not np.isfinite(result).all():
        raise ValueError("Preprocessing produced nonfinite coordinates")
    return np.ascontiguousarray(result, dtype=np.float32)


class ONNXRecognizer:
    def __init__(self, bundle_dir, provider="CPUExecutionProvider", top_k=3):
        if type(top_k) is not int or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        bundle = validate_bundle(bundle_dir)
        self.manifest = bundle["manifest"]
        self.profile = bundle["profile"]
        self.labels = bundle["labels"]
        self.top_k = min(top_k, len(self.labels))
        self.session = create_session(Path(bundle_dir) / "model.onnx", provider)
        check_session(self.session, self.profile, self.labels)
        self.provider = provider
        self._external = external_preprocessor(self.profile) if self.profile["preprocessing"]["name"] == "external-python-v1" else None

    def predict_segment(self, frames: Sequence[Mapping]) -> dict:
        tensor = external_tensor(frames, self.profile, self._external) if self._external else prepare_tensor(frames, self.profile)
        logits = self.session.run([self.profile["output_name"]], {self.profile["input_name"]: tensor})[0]
        check_logits(logits, len(self.labels))
        shifted = logits[0].astype(np.float64) - float(np.max(logits[0]))
        probabilities = np.exp(shifted)
        probabilities /= probabilities.sum()
        ranking = np.argsort(-probabilities, kind="stable")[:self.top_k]
        top = [{"class_id": int(index), "label": self.labels[index], "confidence": float(probabilities[index])} for index in ranking]
        return {**top[0], "top_k": top}
