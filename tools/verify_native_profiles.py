"""Optional owner-authorized native/legacy parity check; no assets are downloaded.

The study directory must contain spoter/bundle and slgcn/bundle from the
previous external-adapter evaluation. Importing that adapter executes trusted
local Python. The output directory contains private model copies and must stay
outside release assets. Run from a checkout with the server extras installed.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import numpy as np

from vsl_streaming.bundle import register_onnx, sha256
from vsl_streaming.core import StreamConfig, StreamSession
from vsl_streaming.native_profiles import PROFILE_CONTRACTS
from vsl_streaming.runtime import ONNXRecognizer, external_tensor, prepare_tensor


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def generated(length):
    rng = np.random.default_rng(20261010)
    frames = []
    for index in range(length):
        frame = {"seq": index, "timestamp_ms": index * 40}
        for name, count in (("pose_landmarks", 33), ("left_hand_landmarks", 21),
                            ("right_hand_landmarks", 21)):
            frame[name] = [{"x": float(x), "y": float(y), "z": 0.0,
                            "visibility": 1.0} for x, y in rng.uniform(.1, .9, (count, 2))]
        frames.append(frame)
    return frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--adapter-dir", type=Path, required=True)
    parser.add_argument("--trace", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.adapter_dir.resolve()))
    report = {"scope": "Host-only preprocessing and ONNX integration parity; no accuracy, camera, Jetson or independent participant claim",
              "status": "running", "harness_sha256": sha256(__file__),
              "versions": {name: importlib.metadata.version(name) for name in
                           ("numpy", "onnxruntime", "onnx", "vsl-streaming-toolkit")},
              "sources": {}, "traces": [], "backends": {}}
    source = Path(__import__("vsl_streaming").__file__).parent
    report["sources"] = {p.name: sha256(p) for p in sorted(source.glob("*.py"))}
    segments = []
    for index, path in enumerate(args.trace):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        frames = [dict(frame, seq=i) for i, frame in enumerate(data["frames"])]
        session = StreamSession(StreamConfig(mode="signing_space"))
        actual = session.push_batch(frames) + session.flush()
        segments.extend(actual)
        report["traces"].append({"trace_index": index, "sha256": sha256(path),
                                 "frames": len(frames), "segments": len(actual)})
    for backend, profile_name in (("spoter", "spoter54-legacy-v1"),
                                  ("slgcn", "slgcn27-bone-v1")):
        legacy = ONNXRecognizer(args.study_dir / backend / "bundle")
        if legacy.profile["preprocessing"]["name"] != "external-python-v1":
            raise ValueError("Expected a hash-verified external legacy adapter")
        layout, length, points, channels, sampling = PROFILE_CONTRACTS[profile_name]
        profile = dict(legacy.profile, layout=layout, num_frames=length,
                       num_points=points, num_channels=channels, temporal_sampling=sampling,
                       preprocessing={"name": profile_name, "config": {}})
        directory = args.output / backend
        directory.mkdir()
        write(directory / "profile.json", profile)
        write(directory / "labels.json", legacy.labels)
        register_onnx(args.study_dir / backend / "bundle" / "model.onnx",
                      directory / "labels.json", directory / "profile.json", directory / "bundle")
        native = ONNXRecognizer(directory / "bundle")
        rows = []
        for segment_index, segment in enumerate(segments):
            old = external_tensor(segment.frames, legacy.profile, legacy._external)
            new = prepare_tensor(segment.frames, native.profile)
            ref, actual = legacy.predict_segment(segment.frames), native.predict_segment(segment.frames)
            rows.append({"segment_index": segment_index, "frames": len(segment.frames),
                         "tensor_exact": bool(np.array_equal(old, new)),
                         "tensor_max_abs_error": float(np.max(np.abs(old-new))),
                         "ordered_top3_agreement": [p["class_id"] for p in ref["top_k"]] == [p["class_id"] for p in actual["top_k"]],
                         "score_max_abs_error": max(abs(a["confidence"]-b["confidence"]) for a,b in zip(ref["top_k"], actual["top_k"]))})
        generated_rows = []
        for count in (1, 2, 29, 30, 69, 70, 71, 149, 150, 151, 301):
            frames = generated(count)
            old = external_tensor(frames, legacy.profile, legacy._external)
            new = prepare_tensor(frames, native.profile)
            generated_rows.append({"frames": count, "tensor_exact": bool(np.array_equal(old, new)),
                                   "max_abs_error": float(np.max(np.abs(old-new)))})
        cfg = legacy.profile["preprocessing"]["config"]
        report["backends"][backend] = {
            "model_sha256": sha256(directory / "bundle" / "model.onnx"),
            "labels_sha256": sha256(directory / "labels.json"),
            "native_profile": profile, "legacy_adapter_sha256": cfg["source_sha256"],
            "legacy_dependency_hashes": sorted(cfg["source_dependencies"].values()),
            "providers": native.session.get_providers(), "segments": rows,
            "generated_tensor_checks": generated_rows}
        write(args.output / "receipt.json", report)
        assert rows and all(r["tensor_exact"] and r["ordered_top3_agreement"] and r["score_max_abs_error"] <= 2e-6 for r in rows)
        assert all(r["tensor_exact"] for r in generated_rows)
        print(f"{backend}: {len(rows)} exact trace tensors and top3; {len(generated_rows)} exact generated tensors", flush=True)
    report["status"] = "passed"
    write(args.output / "receipt.json", report)


if __name__ == "__main__":
    main()
