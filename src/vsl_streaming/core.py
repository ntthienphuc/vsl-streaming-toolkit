"""Deterministic, dependency-free segmentation of MediaPipe keypoint streams.

An arm is active when its visible elbow is bent, or its detected hand is above
the hip. Consecutive active frames open a segment; consecutive inactive frames
and elapsed inactive time close it. Onset and debounce-tail frames are retained.
Missing pose is an inactive observation, never a reused previous observation.
This heuristic does not claim equivalence to the legacy VSL segmenter.
"""
from dataclasses import dataclass
from math import acos, degrees, hypot, isfinite
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional


class ProtocolError(ValueError):
    """Invalid stream input. The entire submitted batch remains unapplied."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError("invalid_number", f"{name} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise ProtocolError("invalid_number", f"{name} must be a finite number") from None
    if not isfinite(result):
        raise ProtocolError("invalid_number", f"{name} must be a finite number")
    return result


@dataclass(frozen=True)
class StreamConfig:
    mode: str = "signing_space"
    window_frames: int = 60
    angle_threshold: float = 140.0
    visibility_threshold: float = 0.5
    min_up_frames: int = 4
    min_down_frames: int = 4
    min_down_ms: float = 300.0
    min_segment_frames: int = 6
    max_gap_ms: float = 1000.0
    max_buffer_frames: int = 300

    def __post_init__(self):
        if self.mode not in ("signing_space", "fixed_window"):
            raise ValueError("mode must be signing_space or fixed_window")
        for name in ("window_frames", "min_up_frames", "min_down_frames", "min_segment_frames", "max_buffer_frames"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("angle_threshold", "visibility_threshold", "min_down_ms", "max_gap_ms"):
            _number(getattr(self, name), name)
        if not 0 < self.angle_threshold <= 180:
            raise ValueError("angle_threshold must be in (0, 180]")
        if not 0 <= self.visibility_threshold <= 1:
            raise ValueError("visibility_threshold must be in [0, 1]")
        if self.min_down_ms < 0 or self.max_gap_ms <= 0:
            raise ValueError("min_down_ms must be nonnegative and max_gap_ms positive")
        if self.max_buffer_frames < max(self.min_up_frames, self.min_segment_frames):
            raise ValueError("max_buffer_frames must cover onset and minimum segment length")
        if self.mode == "fixed_window" and not self.min_segment_frames <= self.window_frames <= self.max_buffer_frames:
            raise ValueError("window_frames must fit between min_segment_frames and max_buffer_frames")


@dataclass
class Segment:
    id: int
    frames: List[Dict[str, Any]]
    start_ms: float
    end_ms: float
    reason: str

    def to_dict(self, include_frames: bool = True) -> dict:
        result = {"id": self.id, "start_ms": self.start_ms, "end_ms": self.end_ms,
                  "reason": self.reason, "frame_count": len(self.frames)}
        if include_frames:
            result["frames"] = self.frames
        return result


def _frame(value: Mapping) -> dict:
    if not isinstance(value, Mapping):
        raise ProtocolError("invalid_frame", "each frame must be an object")
    seq = value.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise ProtocolError("invalid_seq", "seq must be a nonnegative integer")
    timestamp = _number(value.get("timestamp_ms"), "timestamp_ms")
    if timestamp < 0:
        raise ProtocolError("invalid_timestamp", "timestamp_ms must be nonnegative")
    result = {"seq": seq, "timestamp_ms": timestamp}
    if "points" in value:
        points = value["points"]
        if not isinstance(points, (list, tuple)) or not points:
            raise ProtocolError("invalid_points", "points must be a nonempty N by C matrix")
        validated_points = []
        width = None
        for row in points:
            if not isinstance(row, (list, tuple)) or not row or (width is not None and len(row) != width):
                raise ProtocolError("invalid_points", "points rows must be nonempty and have equal length")
            width = len(row)
            validated_points.append([_number(x, "points coordinate") for x in row])
        result["points"] = validated_points
    for name, count in (("pose_landmarks", 33), ("left_hand_landmarks", 21), ("right_hand_landmarks", 21)):
        landmarks = value.get(name)
        if landmarks is None:
            result[name] = None
            continue
        if not isinstance(landmarks, (list, tuple)) or len(landmarks) != count:
            raise ProtocolError("invalid_landmarks", f"{name} must be null or contain {count} landmarks")
        validated = []
        for index, landmark in enumerate(landmarks):
            if not isinstance(landmark, Mapping):
                raise ProtocolError("invalid_landmarks", f"{name}[{index}] must be an object")
            item = {axis: _number(landmark.get(axis, 0.0 if axis == "z" else None), f"{name}[{index}].{axis}")
                    for axis in ("x", "y", "z")}
            item["visibility"] = _number(landmark.get("visibility", 1.0), f"{name}[{index}].visibility")
            if not 0 <= item["visibility"] <= 1:
                raise ProtocolError("invalid_visibility", "landmark visibility must be in [0, 1]")
            validated.append(item)
        result[name] = validated
    return result


def _arm_active(frame: dict, side: str, config: StreamConfig) -> bool:
    pose = frame["pose_landmarks"]
    if pose is None:
        return False
    offset = 0 if side == "left" else 1
    shoulder, elbow, wrist, hip = (pose[i + offset] for i in (11, 13, 15, 23))
    if any(p["visibility"] < config.visibility_threshold for p in (shoulder, elbow, wrist)):
        return False
    # Unit-vector dot product avoids the legacy arctangent implementation.
    u = (shoulder["x"] - elbow["x"], shoulder["y"] - elbow["y"])
    v = (wrist["x"] - elbow["x"], wrist["y"] - elbow["y"])
    un, vn = hypot(*u), hypot(*v)
    if un > 0 and vn > 0:
        cosine = (u[0] / un) * (v[0] / vn) + (u[1] / un) * (v[1] / vn)
        angle = degrees(acos(max(-1.0, min(1.0, cosine))))
        if 0 < angle < config.angle_threshold:
            return True
    hand = frame[f"{side}_hand_landmarks"]
    if not hand or hand[0]["visibility"] < config.visibility_threshold:
        return False
    if hip["visibility"] >= config.visibility_threshold:
        margin = max(0.04, 0.12 * abs(hip["y"] - shoulder["y"]))
        return wrist["y"] < hip["y"] - margin
    return wrist["y"] < shoulder["y"] + 0.30


class StreamSession:
    """One ordered stream; use a separate session per client.

    A sequence-number jump or excessive time gap closes the old segment and
    resets debounce. Capacity splits long active signs into bounded chunks.
    Flush closes pending work but retains ordering; reset starts a new stream.
    Calls must be serialized by the caller when shared across threads/tasks.
    """

    def __init__(self, config: StreamConfig = StreamConfig()):
        if not isinstance(config, StreamConfig):
            raise TypeError("config must be a StreamConfig")
        self.config = config
        self.reset()

    def reset(self) -> None:
        self._last_seq: Optional[int] = None
        self._last_ms: Optional[float] = None
        self._segment_id = 0
        self._received = 0
        self._gap_resets = 0
        self._discarded = 0
        self._points_shape = None
        self._frame_schema = None
        self._clear()

    def _clear(self) -> None:
        self._frames: List[dict] = []
        self._active = False
        self._up = 0
        self._down = 0
        self._down_since: Optional[float] = None

    def _close(self, reason: str) -> List[Segment]:
        emitted = []
        if self._active and len(self._frames) >= self.config.min_segment_frames:
            self._segment_id += 1
            emitted.append(Segment(self._segment_id, self._frames,
                                   self._frames[0]["timestamp_ms"], self._frames[-1]["timestamp_ms"], reason))
        elif self._frames:
            self._discarded += len(self._frames)
        self._clear()
        return emitted

    def push_batch(self, frames: Sequence) -> List[Segment]:
        if not isinstance(frames, Sequence) or isinstance(frames, (str, bytes, bytearray)):
            raise ProtocolError("invalid_batch", "frames must be a sequence of frame objects")
        # Validate and copy all frames before touching session state.
        checked = []
        last_seq, last_ms = self._last_seq, self._last_ms
        points_shape, frame_schema = self._points_shape, self._frame_schema
        for value in frames:
            frame = _frame(value)
            if self.config.mode == "fixed_window":
                schema = "points" if "points" in frame else "mediapipe"
                if frame_schema is not None and frame_schema != schema:
                    raise ProtocolError("schema_changed", "frame representation must remain consistent until reset")
                frame_schema = schema
                if schema == "points":
                    shape = (len(frame["points"]), len(frame["points"][0]))
                    if points_shape is not None and points_shape != shape:
                        raise ProtocolError("points_shape_changed", "points shape must remain consistent until reset")
                    points_shape = shape
            if last_seq is not None and frame["seq"] <= last_seq:
                raise ProtocolError("out_of_order_seq", "seq must strictly increase across the stream")
            if last_ms is not None and frame["timestamp_ms"] <= last_ms:
                raise ProtocolError("out_of_order_timestamp", "timestamp_ms must strictly increase across the stream")
            checked.append(frame)
            last_seq, last_ms = frame["seq"], frame["timestamp_ms"]
        self._points_shape, self._frame_schema = points_shape, frame_schema
        emitted = []
        for frame in checked:
            timestamp = frame["timestamp_ms"]
            if self._last_seq is not None and (frame["seq"] != self._last_seq + 1
                    or timestamp - self._last_ms > self.config.max_gap_ms):
                emitted.extend(self._close("gap"))
                self._gap_resets += 1
            self._last_seq, self._last_ms = frame["seq"], timestamp
            self._received += 1
            if self.config.mode == "fixed_window":
                self._active = True
                self._frames.append(frame)
                if len(self._frames) == self.config.window_frames:
                    emitted.extend(self._close("window"))
                continue
            active = _arm_active(frame, "left", self.config) or _arm_active(frame, "right", self.config)
            if not self._active:
                if not active:
                    self._discarded += len(self._frames)
                    self._clear()
                    continue
                self._frames.append(frame)
                self._up += 1
                if self._up >= self.config.min_up_frames:
                    self._active = True
            else:
                self._frames.append(frame)
                if active:
                    self._down = 0
                    self._down_since = None
                else:
                    self._down += 1
                    if self._down_since is None:
                        self._down_since = timestamp
                    if (self._down >= self.config.min_down_frames
                            and timestamp - self._down_since >= self.config.min_down_ms):
                        emitted.extend(self._close("inactive"))
                        continue
            if len(self._frames) >= self.config.max_buffer_frames:
                emitted.extend(self._close("capacity"))
                # Continuous activity resumes without dropping another onset.
                self._active = active
        return emitted

    def flush(self) -> List[Segment]:
        return self._close("flush")

    def status(self) -> dict:
        return {"mode": self.config.mode, "active": self._active, "buffered_frames": len(self._frames),
                "up_frames": self._up, "down_frames": self._down,
                "last_seq": self._last_seq, "last_timestamp_ms": self._last_ms,
                "received_frames": self._received, "emitted_segments": self._segment_id,
                "gap_resets": self._gap_resets, "discarded_candidate_frames": self._discarded}
