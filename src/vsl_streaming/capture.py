"""Capture provenance validation; this does not certify training compatibility."""
import hashlib
import json
import math
from pathlib import Path
import re

from .core import _frame


def load_frames(path):
    """Read a canonical JSON array or bounded-writer JSONL capture trace."""
    content = Path(path).read_text(encoding="utf-8-sig")
    if content.lstrip().startswith("["):
        frames = json.loads(content)
    else:
        frames = [json.loads(line) for line in content.splitlines() if line.strip()]
    if not isinstance(frames, list) or not frames or any(not isinstance(f, dict) for f in frames):
        raise ValueError("frames input must contain nonempty frame objects in a JSON array or JSONL file")
    canonical = []
    for index, value in enumerate(frames):
        frame = _frame(value)
        if canonical and (frame["seq"] <= canonical[-1]["seq"] or
                          frame["timestamp_ms"] <= canonical[-1]["timestamp_ms"]):
            raise ValueError("capture frame seq and timestamp_ms must increase strictly at frame " + str(index))
        canonical.append(frame)
    return canonical


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_capture_receipt(receipt, frames_path):
    """Check the sidecar schema and bind it to exact serialized frame bytes.

    Extractor profiles have separate identities on Android and desktop. A valid
    receipt establishes trace provenance, not equal landmarks across runtimes,
    equivalent training data, or independent approval of asset redistribution.
    """
    if not isinstance(receipt, dict) or type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1:
        raise ValueError("capture receipt requires schema_version 1")
    if not isinstance(receipt.get("extractor_profile"), str) or not receipt["extractor_profile"].strip():
        raise ValueError("capture receipt requires a named extractor_profile")
    for field in ("software", "assets", "coordinates", "clock", "sampling"):
        if not isinstance(receipt.get(field), dict):
            raise ValueError("capture receipt requires an object: " + field)
    for section, field in (("software", "client_version"), ("software", "mediapipe_tasks"),
                           ("coordinates", "rotation_policy"), ("clock", "source")):
        value = receipt[section].get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("capture receipt requires nonempty " + section + "." + field)
    delegates = [obj["delegate"] for obj in (receipt, receipt["software"]) if "delegate" in obj]
    if not delegates or any(value != "CPU" for value in delegates):
        raise ValueError("capture receipt schema 1 requires delegate CPU")
    for section, field in (("coordinates", "inference_mirrored"), ("coordinates", "preview_mirrored"),
                           ("clock", "strictly_increasing_ms")):
        if type(receipt[section].get(field)) is not bool:
            raise ValueError("capture receipt requires boolean " + section + "." + field)
    sampling = receipt["sampling"]
    fps = sampling.get("target_fps")
    try:
        valid_fps = type(fps) in (int, float) and math.isfinite(fps) and fps > 0
    except OverflowError:
        valid_fps = False
    if not valid_fps:
        raise ValueError("capture receipt requires finite positive sampling.target_fps")
    for field in ("observed_frames", "skipped_rate_limit", "skipped_busy", "emitted_frames",
                  "trace_frames", "missing_pose_frames", "processed_frames", "missing_pose_frames_retained",
                  "extraction_errors"):
        required = field in ("observed_frames", "skipped_rate_limit", "skipped_busy")
        if not required and field not in sampling:
            continue
        value = sampling.get(field)
        if field == "skipped_busy" and field in sampling and value is None:
            continue  # Camera backpressure drops are not observable on Android.
        if type(value) is not int or value < 0:
            raise ValueError("capture receipt requires nonnegative integer sampling." + field)
    for role in ("pose", "hand"):
        asset = receipt["assets"].get(role)
        if not isinstance(asset, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(asset.get("sha256", ""))):
            raise ValueError("capture receipt requires asset SHA-256: " + role)
    expected = receipt.get("frames_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("capture receipt requires frames_sha256")
    if sha256_file(frames_path) != expected:
        raise ValueError("capture receipt does not match frame file SHA-256")
    frames = load_frames(frames_path)
    count = len(frames)
    if sampling["observed_frames"] < count:
        raise ValueError("sampling.observed_frames cannot be smaller than the capture trace")
    for field in ("emitted_frames", "trace_frames"):
        if field in sampling and sampling[field] != count:
            raise ValueError("sampling." + field + " does not match the capture trace")
    if "missing_pose_frames" in sampling:
        missing = sum(frame["pose_landmarks"] is None for frame in frames)
        if sampling["missing_pose_frames"] != missing:
            raise ValueError("sampling.missing_pose_frames does not match the capture trace")
    # Android processing precedes transport admission; rejected offers are absent
    # from the JSONL trace. Its processed count must not be equated to trace size.
    if "processed_frames" in sampling and sampling["processed_frames"] < count:
        raise ValueError("sampling.processed_frames cannot be smaller than the capture trace")
    # Reject non-finite values and unpaired Unicode surrogates in nested fields.
    json.dumps(receipt, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return receipt


def load_capture_receipt(path, frames_path):
    return validate_capture_receipt(json.loads(Path(path).read_text(encoding="utf-8-sig")), frames_path)
