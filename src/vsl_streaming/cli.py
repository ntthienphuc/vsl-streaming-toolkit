"""Model onboarding, replay, and WebSocket deployment."""
import argparse
import json
from pathlib import Path
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


def replay(bundle_dir, frames_path, config, batch_size=30):
    from .runtime import ONNXRecognizer
    from .protocol import MessageProcessor
    if batch_size < 1 or batch_size > config.max_batch_frames:
        raise ValueError("batch_size must be positive and at most max_batch_frames")
    frames = read_json(frames_path)
    if not isinstance(frames, list) or not frames:
        raise ValueError("frames input must be a nonempty JSON array")
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
    parser = argparse.ArgumentParser(prog="vsl-stream", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "demo"):
        p = sub.add_parser(name, help="Create " + ("editable model/server configuration" if name == "init" else "a synthetic export/replay fixture"))
        p.add_argument("--out", required=True)
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
    p = sub.add_parser("replay", help="Replay a frame JSON array through the same segmentation/runtime")
    p.add_argument("--bundle", required=True)
    p.add_argument("--frames", required=True)
    p.add_argument("--config")
    p.add_argument("--batch-size", type=int, default=30)
    p.add_argument("--receipt")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=False)
            profile = identity_profile(60, 49, 2)
            profile["preprocessing"]["name"] = "mediapipe49-shoulder-v1"
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
            result = replay(args.bundle, args.frames, load_config(args.config), args.batch_size)
            if args.receipt:
                write_json(args.receipt, result)
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
            return 0 if result["status"] == "passed" else 2
        else:
            import uvicorn
            from .server import create_app
            settings = load_config(args.config)
            uvicorn.run(create_app(args.bundle, settings), host=args.host, port=args.port,
                        ws_max_size=settings.max_message_bytes, ws_max_queue=4, workers=1)
            return 0
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, TypeError, KeyError, OSError, ImportError, RuntimeError) as error:
        print("vsl-stream: " + str(error), file=sys.stderr)
        if isinstance(error, ImportError):
            print('Install required extras with: pip install ".[server,export]"', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
