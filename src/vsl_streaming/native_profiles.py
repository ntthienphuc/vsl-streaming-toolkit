# SPDX-License-Identifier: Apache-2.0
# SPOTER normalization lineage: Copyright 2021-2022 Matyáš Boháček.
# NumPy compatibility implementation and validation: Copyright 2026 Nguyễn Trần Thiên Phúc.
# Modified from the owner's deployment contract; see docs/PREPROCESSING_PROFILES.md.
# The upstream Apache license is retained in third_party/SPOTER_LICENSE.txt.
"""Explicit compatibility transforms for two owner-validated tensor contracts.

These profiles describe deployment behavior, including historical ordering
quirks. They are not generic implementations of every SPOTER/SL-GCN checkpoint.
No pretrained weights, human keypoints, or model architecture are included.
"""
from collections.abc import Mapping

import numpy as np


PROFILE_CONTRACTS = {
    "spoter54-legacy-v1": ("BTVC", 70, 54, 2, "repeat-or-linspace-floor-v1"),
    "slgcn27-bone-v1": ("BCTVM", 150, 27, 3, "linear-min30-repeat-or-prefix-v1"),
}
SPOTER_POSE = (0, -1, 5, 2, 8, 7, 12, 11, 14, 13, 16, 15)
SPOTER_HAND = (0, 8, 7, 6, 5, 12, 11, 10, 9, 16, 15, 14, 13, 20, 19, 18, 17, 4, 3, 2, 1)
SLGCN_POSE = (0, 11, 12, 13, 14, 15, 16)
SLGCN_HAND = (0, 4, 5, 8, 9, 12, 13, 16, 17, 20)
BONE_EDGES = (
    (0, 1), (0, 2), (1, 3), (3, 5), (2, 4), (4, 6),
    (7, 8), (7, 9), (7, 11), (7, 13), (7, 15),
    (9, 10), (11, 12), (13, 14), (15, 16),
    (17, 18), (17, 19), (17, 21), (17, 23), (17, 25),
    (19, 20), (21, 22), (23, 24), (25, 26), (5, 7), (6, 17),
)


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + " must be a finite number")
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(name + " must be a finite number") from exc
    if not np.isfinite(value):
        raise ValueError(name + " must be a finite number")
    return value


def _landmarks(frame, name, count):
    # Canonical wire names only: aliases could silently select a different capture path.
    value = frame.get(name)
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise ValueError(name + " must be null or contain %d landmark objects" % count)
    result = np.empty((count, 3), dtype=np.float64)
    for index, point in enumerate(value):
        if not isinstance(point, Mapping):
            raise ValueError(name + " requires landmark objects with x/y/visibility")
        x, y = (_finite(point.get(axis), name + "." + axis) for axis in ("x", "y"))
        visibility = _finite(point.get("visibility", 1.0), name + ".visibility")
        if not 0 <= visibility <= 1:
            raise ValueError(name + ".visibility must be in [0, 1]")
        if "z" in point:
            _finite(point["z"], name + ".z")  # Validated, deliberately not used.
        result[index] = (x, y, visibility)
    return result


def _read_frames(frames):
    if not frames:
        raise ValueError("At least one frame is required")
    previous_seq, previous_time = None, None
    result = []
    for frame in frames:
        if not isinstance(frame, Mapping):
            raise ValueError("Each frame must be an object")
        if not any(key in frame for key in ("pose_landmarks", "left_hand_landmarks", "right_hand_landmarks")):
            raise ValueError("Native profiles require canonical landmark fields, not points or aliases")
        seq = frame.get("seq")
        if seq is not None:
            if type(seq) is not int or seq < 0 or (previous_seq is not None and seq <= previous_seq):
                raise ValueError("Frame seq must be a nonnegative strictly increasing integer")
            previous_seq = seq
        timestamp = frame.get("timestamp_ms", frame.get("timestamp"))
        if timestamp is not None:
            timestamp = _finite(timestamp, "timestamp_ms")
            if timestamp < 0 or (previous_time is not None and timestamp <= previous_time):
                raise ValueError("Frame timestamps must be nonnegative and increase strictly")
            previous_time = timestamp
        result.append(tuple(_landmarks(frame, name, count) for name, count in
                            (("pose_landmarks", 33), ("left_hand_landmarks", 21), ("right_hand_landmarks", 21))))
    return result


def _spoter(frames):
    selected = np.zeros((len(frames), 54, 2), dtype=np.float64)
    for t, (pose, left, right) in enumerate(frames):
        if pose is not None:
            for j, source in enumerate(SPOTER_POSE):
                if source != -1:
                    selected[t, j] = pose[source, :2]
        for hand, offset in ((left, 12), (right, 33)):
            if hand is not None:
                selected[t, offset:offset + 21] = hand[list(SPOTER_HAND), :2]
    length = len(selected)
    indices = (np.arange(70) % length if length < 70 else
               np.linspace(0, length - 1, 70, dtype=int))
    data = selected[indices].copy()
    last_box = None
    for row in data:
        # Historical body order: nose, zero neck, eyes, ears, shoulders, elbows, wrists.
        left_shoulder, right_shoulder, neck, nose = row[7], row[6], row[1], row[0]
        if (left_shoulder[0] == 0 or right_shoulder[0] == 0) and (neck[0] == 0 or nose[0] == 0):
            box = last_box
        else:
            distance = (np.linalg.norm(left_shoulder - right_shoulder)
                        if left_shoulder[0] != 0 and right_shoulder[0] != 0 else np.linalg.norm(neck - nose))
            start = [neck[0] - 3 * distance, row[3, 1] + distance]
            end = [neck[0] + 3 * distance, start[1] - 6 * distance]
            box = (np.maximum(start, 0), np.maximum(end, 0))
            last_box = box
        if box is None:
            continue
        start, end = box
        width, height = end[0] - start[0], start[1] - end[1]
        if width == 0 or height == 0:
            continue  # Preserve finite legacy raw-body fallback.
        for point in row[:12]:
            if point[0] != 0:
                point[0] = (point[0] - start[0]) / width
                point[1] = (point[1] - end[1]) / height
    # Deliberately preserve the deployment's alternating-name interpretation.
    # Correcting this to left/right contiguous blocks changes trained-model inputs.
    for offset in (12, 13):
        for row in data:
            indexes = list(range(offset, 54, 2))
            hand = row[indexes]
            xs, ys = hand[hand[:, 0] != 0, 0], hand[hand[:, 1] != 0, 1]
            if len(xs) == 0 or len(ys) == 0:
                continue
            width, height = max(xs) - min(xs), max(ys) - min(ys)
            if width > height:
                dx = 0.1 * width
                dy = dx + (width - height) / 2
            else:
                dy = 0.1 * height
                dx = dy + (height - width) / 2
            start = (min(xs) - dx, min(ys) - dy)
            end = (max(xs) + dx, max(ys) + dy)
            if end[0] == start[0] or end[1] == start[1]:
                raise ValueError("SPOTER legacy hand normalization is undefined for a zero-area hand group")
            for index in indexes:
                px, py = row[index]
                if px != 0:
                    row[index] = ((px - start[0]) / (end[0] - start[0]),
                                  (py - start[1]) / (end[1] - start[1]))
    return (data - 0.5)[None].astype(np.float32)


def _slgcn(frames):
    data = np.zeros((len(frames), 27, 3), dtype=np.float32)
    for t, components in enumerate(frames):
        for component, indexes, offset, pose in zip(components, (SLGCN_POSE, SLGCN_HAND, SLGCN_HAND), (0, 7, 17), (True, False, False)):
            if component is None:
                continue
            for j, source in enumerate(indexes):
                x, y, visibility = component[source]
                confidence = visibility if pose else 1.0
                if confidence > 0:
                    data[t, offset + j] = (x, y, confidence)
    if not np.isfinite(data).all():
        raise ValueError("SL-GCN coordinates must be representable as finite float32")
    length = len(data)
    if length < 30:
        expanded = np.empty((30, 27, 3), dtype=np.float32)
        before, after = np.linspace(0, 1, length), np.linspace(0, 1, 30)
        for joint in range(27):
            for channel in (0, 1):
                expanded[:, joint, channel] = np.interp(after, before, data[:, joint, channel])
        nearest = np.rint(np.linspace(0, length - 1, 30)).astype(np.int64)
        expanded[:, :, 2] = data[nearest, :, 2]
        expanded[:, :, :2][expanded[:, :, 2] <= 0] = 0
        data = expanded
    normalized = data.copy()
    for joint in range(27):
        valid = data[:, joint, 2] > 0
        if not np.any(valid):
            continue
        for channel in (0, 1):
            values = data[valid, joint, channel]
            std = float(values.std())
            mean = float(values.mean())
            if not np.isfinite(std) or not np.isfinite(mean):
                raise ValueError("SL-GCN coordinate distribution overflowed float32")
            normalized[valid, joint, channel] = ((values - mean) / std if std > 1e-7 else 0.0)
    data = normalized[np.arange(150) % len(normalized)] if len(normalized) < 150 else normalized[:150]
    bone = np.zeros_like(data)
    for source, target in BONE_EDGES:
        bone[:, target, :2] = data[:, target, :2] - data[:, source, :2]
        bone[:, target, 2] = np.minimum(data[:, target, 2], data[:, source, 2])
    # Root is zero in the bone stream. Keep the explicit historical operation.
    bone[:, :, 0] -= bone[:, 0, 0].mean()
    bone[:, :, 1] -= bone[:, 0, 1].mean()
    return bone.transpose(2, 0, 1)[None, ..., None]


def prepare_native_tensor(frames, name):
    if name not in PROFILE_CONTRACTS:
        raise ValueError("Unknown native preprocessing profile")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        parsed = _read_frames(frames)
        tensor = _spoter(parsed) if name == "spoter54-legacy-v1" else _slgcn(parsed)
    if not np.isfinite(tensor).all():
        raise ValueError("Native preprocessing produced nonfinite coordinates")
    return np.ascontiguousarray(tensor, dtype=np.float32)
