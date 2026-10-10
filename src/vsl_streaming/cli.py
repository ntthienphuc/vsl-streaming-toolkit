"""Model onboarding, replay, and WebSocket deployment."""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
from .config import ServerConfig, load_config
from .core import StreamConfig


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def identity_profile(num_frames=12, num_points=3, num_channels=2):
    return {"schema_version": 1, "input_name": "keypoints", "output_name": "logits",
            "layout": "BTVC", "num_frames": num_frames, "num_points": num_points,
            "num_channels": num_channels, "temporal_sampling": "uniform-nearest-v1",
            "preprocessing": {"name": "identity-v1", "config": {}}}


def replay(bundle_dir, frames_path, config, batch_size=30, capture_receipt=None):
    from .runtime import ONNXRecognizer
    from .protocol import MessageProcessor
    if batch_size < 1 or batch_size > config.max_batch_frames:
        raise ValueError("batch_size must be positive and at most max_batch_frames")
    frame_bytes = Path(frames_path).read_bytes()
    from .capture import load_frames
    frames = load_frames(frames_path)
    capture = None
    if capture_receipt is not None:
        from .capture import load_capture_receipt, sha256_file
        capture = load_capture_receipt(capture_receipt, frames_path)
        capture = {"receipt_sha256": sha256_file(capture_receipt),
                   "extractor_profile": capture["extractor_profile"],
                   "frames_hash_verified": True,
                   "training_capture_compatibility": "not established by this provenance check"}
    recognizer = ONNXRecognizer(bundle_dir, provider=config.provider, top_k=config.top_k)
    processor = MessageProcessor(recognizer, config)
    responses = []
    for offset in range(0, len(frames), batch_size):
        response = processor.process({"type": "frames", "request_id": "replay-%d" % offset,
                                      "frames": frames[offset:offset + batch_size],
                                      "flush": offset + batch_size >= len(frames)})
        responses.append(response)
        if response["type"] == "error":
            break
    events = [event for response in responses for event in response.get("events", [])]
    errors = sum(response["type"] == "error" for response in responses)
    rejected = sum(event["status"] != "predicted" for event in events)
    return {"status": "failed" if errors or rejected else ("passed" if events else "no_segments"),
            "scope": "stream replay; predictions are not an accuracy measurement without ground truth",
            "input_frames": len(frames), "predicted_segments": len(events) - rejected,
            "rejected_segments": rejected, "protocol_errors": errors,
            "model_sha256": recognizer.manifest["sha256"]["model.onnx"],
            "input_sha256": hashlib.sha256(frame_bytes).hexdigest(),
            "bundle_sha256": dict(recognizer.manifest["sha256"]),
            "capture": capture,
            "environment": {"python": platform.python_version(),
                            "platform": platform.platform(),
                            "versions": {name: version(name) for name in
                                         ("vsl-streaming-toolkit", "numpy", "onnxruntime", "onnx")}},
            "settings": config.to_dict(), "responses": responses}


def create_demo(output_dir):
    import torch
    from .demo_model import build_model
    from .exporting import export_pytorch
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "profile.json", identity_profile())
    write_json(out / "labels.json", ["SYNTHETIC_NEGATIVE", "SYNTHETIC_POSITIVE"])
    settings = ServerConfig(stream=StreamConfig(mode="fixed_window", window_frames=12))
    write_json(out / "server.json", settings.to_dict())
    model = build_model()
    with torch.no_grad():
        model[1].weight[0].fill_(-1.0 / 72)
        model[1].weight[1].fill_(1.0 / 72)
        model[1].bias.zero_()
    torch.save(model.state_dict(), out / "weights.pt")
    export_pytorch("vsl_streaming.demo_model:build_model", out / "weights.pt",
                   out / "labels.json", out / "profile.json", out / "bundle")
    frames = [{"seq": index, "timestamp_ms": index * (1000 / 30),
               "points": [[-1.0 if index < 12 else 1.0] * 2 for _ in range(3)]}
              for index in range(24)]
    write_json(out / "frames.json", frames)
    receipt = replay(out / "bundle", out / "frames.json", settings, batch_size=5)
    actual = [event["prediction"]["label"] for response in receipt["responses"] for event in response["events"]]
    if actual != ["SYNTHETIC_NEGATIVE", "SYNTHETIC_POSITIVE"]:
        raise RuntimeError("Synthetic fixture produced unexpected labels")
    receipt["fixture_labels_match"] = True
    receipt["scope"] = "synthetic execution fixture only; not sign-language accuracy or a trained VSL model"
    write_json(out / "receipt.json", receipt)
    return {"status": receipt["status"], "directory": str(out.resolve()), "fixture_labels_match": True,
            "predicted_segments": len(actual),
            "next": "vsl-stream serve --bundle \"%s\" --config \"%s\"" % (out / "bundle", out / "server.json")}


def main(argv=None):
    # JSON output is UTF-8 even when Windows redirects to a legacy code page.
    # Test/caller supplied StringIO streams do not expose reconfigure().
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="vsl-stream", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "demo"):
        p = sub.add_parser(name, help="Create " + ("editable model/server configuration" if name == "init" else "a synthetic export/replay fixture"))
        p.add_argument("--out", required=True)
        if name == "init":
            p.add_argument("--profile", choices=("mediapipe49-shoulder-v1", "spoter54-legacy-v1", "slgcn27-bone-v1"),
                           default="mediapipe49-shoulder-v1", help="Tensor contract; must match the specific checkpoint")
    for name in ("export", "register"):
        p = sub.add_parser(name, help="Build a model bundle from " + ("PyTorch" if name == "export" else "ONNX"))
        p.add_argument("--labels", required=True)
        p.add_argument("--profile", required=True)
        p.add_argument("--out", required=True)
        p.add_argument("--overwrite", action="store_true")
        if name == "export":
            p.add_argument("--factory", required=True, help="Trusted importable module:function returning the architecture")
            p.add_argument("--checkpoint", required=True, help="weights-only state_dict checkpoint")
            p.add_argument("--model-kwargs", default="{}", help="JSON constructor arguments")
            p.add_argument("--model-kwargs-file", help="JSON file with constructor arguments (convenient on Windows)")
            p.add_argument("--validation-tensors", help="NPZ with float32 inputs: representative preprocessed samples")
        else:
            p.add_argument("--model", required=True)
    p = sub.add_parser("inspect", help="Validate bundle and executable model/input/label compatibility")
    p.add_argument("--bundle", required=True)
    p = sub.add_parser("serve", help="Run one model bundle and isolated WebSocket sessions")
    p.add_argument("--bundle", required=True)
    p.add_argument("--config")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--session-log-dir", help="Opt-in local per-session JSONL evidence; keep outside public artifacts")
    p = sub.add_parser("replay", help="Replay JSON array or JSONL frames through the same segmentation/runtime")
    p.add_argument("--bundle", required=True)
    p.add_argument("--frames", required=True)
    p.add_argument("--config")
    p.add_argument("--batch-size", type=int, default=30)
    p.add_argument("--receipt")
    p.add_argument("--capture-receipt", help="Optional capture sidecar whose frame-file hash must match")
    p = sub.add_parser("extract-video", help="Extract canonical keypoints from a local video using explicit MediaPipe assets")
    p.add_argument("--video", required=True)
    p.add_argument("--pose-model", required=True)
    p.add_argument("--hand-model", required=True)
    p.add_argument("--out", required=True, help="New frame JSON; adjacent .capture.json sidecar is also written")
    p.add_argument("--target-fps", type=float, default=15.0)
    p.add_argument("--timestamp-mode", choices=("pos-msec", "frame-index"), default="pos-msec")
    p.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=0, help="Clockwise rotation after decoding")
    p.add_argument("--input-mirrored", action="store_true", help="Declare a mirrored source and horizontally undo that mirror")
    p.add_argument("--max-frames", type=int, default=100000)
    p = sub.add_parser("evaluate", help="Evaluate annotated word intervals and gloss events; no model execution")
    p.add_argument("--annotations", required=True)
    p.add_argument("--predictions", required=True, help="JSON mapping recording IDs to event arrays or replay receipt objects")
    p.add_argument("--iou-threshold", type=float, default=0.5)
    p.add_argument("--out")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=False)
            profile = identity_profile(60, 49, 2)
            profile["preprocessing"]["name"] = args.profile
            if args.profile != "mediapipe49-shoulder-v1":
                from .native_profiles import PROFILE_CONTRACTS
                layout, length, points, channels, sampling = PROFILE_CONTRACTS[args.profile]
                profile.update(layout=layout, num_frames=length, num_points=points,
                               num_channels=channels, temporal_sampling=sampling)
            write_json(out / "profile.json", profile)
            write_json(out / "labels.json", ["REPLACE_WITH_CLASS_0", "REPLACE_WITH_CLASS_1"])
            write_json(out / "model_kwargs.json", {"num_classes": 2})
            write_json(out / "server.json", ServerConfig().to_dict())
            result = {"directory": str(out.resolve()), "next": "Edit ordered labels and profile to exactly match training before export."}
        elif args.command == "demo":
            result = create_demo(args.out)
        elif args.command == "export":
            from .exporting import export_pytorch
            if args.model_kwargs_file and args.model_kwargs != "{}":
                raise ValueError("Use either model-kwargs or model-kwargs-file")
            kwargs = read_json(args.model_kwargs_file) if args.model_kwargs_file else json.loads(args.model_kwargs)
            if not isinstance(kwargs, dict):
                raise ValueError("model-kwargs must be a JSON object")
            result = export_pytorch(args.factory, args.checkpoint, args.labels, args.profile,
                                    args.out, model_kwargs=kwargs, overwrite=args.overwrite,
                                    validation_tensors_path=args.validation_tensors)
        elif args.command == "register":
            from .bundle import register_onnx
            result = register_onnx(args.model, args.labels, args.profile, args.out, overwrite=args.overwrite)
        elif args.command == "inspect":
            from .runtime import ONNXRecognizer
            model = ONNXRecognizer(args.bundle)
            result = {"status": "valid", "manifest": model.manifest, "profile": model.profile, "labels": model.labels}
        elif args.command == "replay":
            result = replay(args.bundle, args.frames, load_config(args.config), args.batch_size, args.capture_receipt)
            if args.receipt:
                write_json(args.receipt, result)
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
            return 0 if result["status"] == "passed" else 2
        elif args.command == "extract-video":
            from .video import extract_video
            result = extract_video(args.video, args.pose_model, args.hand_model, args.out,
                                   args.target_fps, args.timestamp_mode, args.rotate,
                                   args.input_mirrored, args.max_frames)
        elif args.command == "evaluate":
            from .evaluation import evaluate_events, events_from_responses
            from .capture import sha256_file
            predictions = read_json(args.predictions)
            if not isinstance(predictions, dict):
                raise ValueError("predictions must map recording IDs to event arrays or replay receipts")
            for key, value in predictions.items():
                if isinstance(value, dict) and "responses" in value:
                    predictions[key] = events_from_responses(value)
                elif (isinstance(value, list) and value and isinstance(value[0], dict)
                      and "type" in value[0]):
                    predictions[key] = events_from_responses(value)
            result = evaluate_events(read_json(args.annotations), predictions, args.iou_threshold)
            result["inputs"] = {key: {"sha256": sha256_file(path)} for key, path in
                                (("annotations", args.annotations), ("predictions", args.predictions))}
            from . import __version__
            result["software_version"] = __version__
            if args.out:
                write_json(args.out, result)
        else:
            import uvicorn
            from .server import create_app
            settings = load_config(args.config)
            uvicorn.run(create_app(args.bundle, settings, session_log_dir=args.session_log_dir), host=args.host, port=args.port,
                        ws_max_size=settings.max_message_bytes, ws_max_queue=4, workers=1)
            return 0
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, TypeError, KeyError, OSError, ImportError, RuntimeError) as error:
        print("vsl-stream: " + str(error), file=sys.stderr)
        if isinstance(error, ImportError):
            print('Install the required extra: pip install ".[server]", ".[export]", or ".[video]"', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
