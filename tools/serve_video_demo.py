"""Optional sequential video-upload adapter; run from an installed checkout.

The toolkit's extractor and replay APIs remain the source of interpretation.
HTTP dependencies are imported only by create_app/main, not by the library.
"""
import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path
import threading
import uuid


VIDEO_SUFFIXES = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")
ARTIFACTS = frozenset({"upload.partial", "request.json", "frames.json",
                       "frames.capture.json", "replay.json", "failure.json"}
                      | {"original" + suffix for suffix in VIDEO_SUFFIXES})
SCOPE = ("Sequential uploaded-video demo using desktop MediaPipe Tasks. "
         "Training-extractor compatibility and Android detector parity are unverified; "
         "predictions without ground truth are not sign-accuracy results.")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, data):
    with Path(path).open("x", encoding="utf-8", newline="\n") as output:
        json.dump(data, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")


class UploadError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class MultipartUpload:
    """Bound video/field/header bytes as they arrive; retain incomplete bytes."""

    def __init__(self, content_type, directory, max_bytes):
        from python_multipart.multipart import MultipartParser, parse_options_header
        self.parse_options_header = parse_options_header
        media, options = parse_options_header(content_type)
        boundary = options.get(b"boundary")
        if media != b"multipart/form-data" or not boundary or len(boundary) > 200:
            raise UploadError("Expected multipart/form-data with a bounded boundary")
        self.directory = directory
        self.max_bytes = max_bytes
        self.fields = {}
        self.file = None
        self.video_path = None
        self.video_name = None
        self.file_bytes = 0
        self.total_bytes = 0
        self.parts = 0
        self.complete = False
        self.parser = MultipartParser(boundary, {"on_" + name: getattr(self, name) for name in (
            "part_begin", "header_field", "header_value", "header_end",
            "headers_finished", "part_data", "part_end", "end")})

    def part_begin(self):
        self.parts += 1
        if self.parts > 6:
            raise UploadError("Too many multipart fields")
        self.headers = {}
        self.header_key = bytearray()
        self.header_content = bytearray()
        self.header_bytes = 0
        self.field = bytearray()
        self.current_name = None
        self.is_video = False

    def _header(self, target, data, start, end):
        self.header_bytes += end - start
        if self.header_bytes > 8192:
            raise UploadError("Multipart headers exceed 8192 bytes")
        target.extend(data[start:end])

    def header_field(self, data, start, end):
        self._header(self.header_key, data, start, end)

    def header_value(self, data, start, end):
        self._header(self.header_content, data, start, end)

    def header_end(self):
        key = bytes(self.header_key).lower()
        if key in self.headers:
            raise UploadError("Duplicate multipart header")
        self.headers[key] = bytes(self.header_content)
        self.header_key.clear()
        self.header_content.clear()

    def headers_finished(self):
        disposition, options = self.parse_options_header(self.headers.get(b"content-disposition", b""))
        if disposition != b"form-data" or b"name" not in options:
            raise UploadError("Each part must identify a form field")
        self.current_name = options[b"name"].decode("utf-8", "strict")
        if self.current_name == "video":
            if self.video_path is not None:
                raise UploadError("Exactly one video is permitted")
            name = options.get(b"filename", b"").decode("utf-8", "strict")
            # Client names never become filesystem paths, including Windows names.
            suffix = Path(name.replace("\\", "/")).suffix.lower()
            if suffix not in VIDEO_SUFFIXES:
                raise UploadError("Unsupported video suffix; expected " + ", ".join(VIDEO_SUFFIXES))
            self.video_name = name
            self.video_path = self.directory / ("original" + suffix)
            self.file = (self.directory / "upload.partial").open("xb")
            self.is_video = True
        elif self.current_name not in {"rotate", "input_mirrored", "target_fps", "timestamp_mode"}:
            raise UploadError("Unknown form field: " + self.current_name)
        elif self.current_name in self.fields or b"filename" in options:
            raise UploadError("Duplicate or file-valued configuration field")

    def part_data(self, data, start, end):
        block = data[start:end]
        if self.is_video:
            remaining = self.max_bytes - self.file_bytes
            self.file.write(block[:remaining])
            self.file_bytes += min(len(block), remaining)
            if len(block) > remaining:
                raise UploadError("Video exceeds max_upload_bytes", 413)
        else:
            if len(self.field) + len(block) > 128:
                raise UploadError("Configuration field exceeds 128 bytes")
            self.field.extend(block)

    def part_end(self):
        if self.is_video:
            self.file.close()
            self.file = None
        else:
            self.fields[self.current_name] = self.field.decode("utf-8", "strict")

    def end(self):
        self.complete = True

    def write(self, data):
        self.total_bytes += len(data)
        if self.total_bytes > self.max_bytes + 65536:
            raise UploadError("Multipart request exceeds the upload plus overhead bound", 413)
        self.parser.write(data)

    def finish(self):
        self.parser.finalize()
        if not self.complete or self.video_path is None or self.file_bytes == 0:
            raise UploadError("Upload is incomplete, empty, or missing its video field")
        (self.directory / "upload.partial").rename(self.video_path)
        return self.video_path

    def close(self):
        if self.file is not None:
            self.file.close()


def parse_parameters(fields):
    rotation = fields.get("rotate", "0")
    mirrored = fields.get("input_mirrored", "false")
    clock = fields.get("timestamp_mode", "pos-msec")
    if rotation not in {"0", "90", "180", "270"}:
        raise UploadError("rotate must be 0, 90, 180, or 270 clockwise degrees")
    if mirrored not in {"true", "false"}:
        raise UploadError("input_mirrored must be exactly true or false")
    if clock not in {"pos-msec", "frame-index"}:
        raise UploadError("timestamp_mode must be pos-msec or frame-index")
    try:
        fps = float(fields.get("target_fps", "15"))
    except (TypeError, ValueError) as error:
        raise UploadError("target_fps must be finite and in (0, 120]") from error
    if not math.isfinite(fps) or not 0 < fps <= 120:
        raise UploadError("target_fps must be finite and in (0, 120]")
    return {"rotate": int(rotation), "input_mirrored": mirrored == "true",
            "target_fps": fps, "timestamp_mode": clock}


def create_app(bundle, pose_model, hand_model, output_dir, config=None,
               max_upload_bytes=100 * 1024 * 1024, max_frames=100000,
               extract_hook=None, replay_hook=None):
    """Build the local demo app; hooks allow transport tests without detector assets."""
    from fastapi import FastAPI, Request
    from fastapi.responses import FileResponse, JSONResponse
    from starlette.concurrency import run_in_threadpool
    from vsl_streaming.config import ServerConfig, load_config
    from vsl_streaming.video import EXTRACTOR_PROFILE, extract_video
    from vsl_streaming.cli import replay

    if type(max_upload_bytes) is not int or max_upload_bytes < 1:
        raise ValueError("max_upload_bytes must be a positive integer")
    if type(max_frames) is not int or max_frames < 1:
        raise ValueError("max_frames must be a positive integer")
    settings = config if isinstance(config, ServerConfig) else load_config(config)
    bundle, pose_model, hand_model = (Path(p).resolve() for p in (bundle, pose_model, hand_model))
    if not bundle.is_dir() or not pose_model.is_file() or not hand_model.is_file():
        raise ValueError("An existing bundle directory and both detector assets are required")
    if replay_hook is None:
        from vsl_streaming.bundle import validate_bundle
        validate_bundle(bundle)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    extractor = extract_hook or extract_video
    replay_fn = replay_hook or replay
    gate = threading.Lock()
    app = FastAPI(title="VSL sequential video demo", version="1")
    app.state.job_lock = gate

    async def joined_worker(function, *args, **kwargs):
        # asyncio task cancellation can abandon an AnyIO worker despite its
        # default cancel-scope shielding. Keep the gate and evidence private
        # until the native work finishes, then propagate the cancellation.
        worker = asyncio.create_task(run_in_threadpool(function, *args, **kwargs))
        cancellation = None
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError as error:
                cancellation = error
            except Exception:
                break  # retrieve the worker exception below, also if cancelled
        try:
            result = worker.result()
        except BaseException:
            if cancellation is not None:
                raise cancellation
            raise
        if cancellation is not None:
            raise cancellation
        return result

    def artifacts(directory):
        return [{"name": path.name,
                 "url": "/v1/runs/" + directory.name + "/" + path.name,
                 "sha256": sha256(path), "bytes": path.stat().st_size}
                for path in sorted(directory.iterdir())
                if path.name in ARTIFACTS and path.is_file() and not path.is_symlink()]

    @app.get("/health")
    def health():
        return {"status": "busy" if gate.locked() else "ready", "active_jobs": int(gate.locked()),
                "extractor_profile": EXTRACTOR_PROFILE, "settings": settings.to_dict(),
                "capture_defaults": {"target_fps": 15, "rotate": 0, "input_mirrored": False,
                                     "timestamp_mode": "pos-msec"},
                "capabilities": {"video_upload": True, "sequential_jobs": 1,
                                 "max_upload_bytes": max_upload_bytes, "max_frames": max_frames,
                                 "video_suffixes": list(VIDEO_SUFFIXES)}, "scope": SCOPE}

    @app.get("/v1/runs/{run_id}/{name}")
    def download(run_id: str, name: str):
        try:
            valid_id = str(uuid.UUID(run_id)) == run_id
        except ValueError:
            valid_id = False
        if not valid_id or name not in ARTIFACTS:
            return JSONResponse({"status": "not_found"}, status_code=404)
        directory = output_dir / run_id
        path = directory / name
        if (directory.is_symlink() or path.is_symlink() or not path.is_file()
                or path.resolve().parent != directory.resolve()
                or not ((directory / "completed.json").is_file() or (directory / "failure.json").is_file())):
            return JSONResponse({"status": "not_found"}, status_code=404)
        return FileResponse(path, filename=name, headers={"X-Content-SHA256": sha256(path)})

    @app.post("/v1/video")
    async def upload(request: Request):
        if not gate.acquire(blocking=False):
            return JSONResponse({"status": "busy", "error": "One video is already being processed"},
                                status_code=409, headers={"Retry-After": "2"})
        directory = output_dir / str(uuid.uuid4())
        parser = None
        stage = "upload"
        params = None
        try:
            directory.mkdir(exist_ok=False)
            parser = MultipartUpload(request.headers.get("content-type", ""), directory, max_upload_bytes)
            async for chunk in request.stream():
                parser.write(chunk)
            video = parser.finish()
            params = parse_parameters(parser.fields)
            write_json(directory / "request.json", {"schema_version": 1, "run_id": directory.name,
                       "original_filename": parser.video_name, "parameters": params,
                       "video_sha256": sha256(video), "video_bytes": video.stat().st_size,
                       "extractor_profile": EXTRACTOR_PROFILE, "settings": settings.to_dict(),
                       "max_frames": max_frames, "scope": SCOPE})
            stage = "extraction"
            frames = directory / "frames.json"
            extracted = await joined_worker(extractor, video, pose_model, hand_model, frames,
                                            max_frames=max_frames, **params)
            stage = "replay"
            receipt = await joined_worker(replay_fn, bundle, frames, settings,
                                          batch_size=min(30, settings.max_batch_frames),
                                          capture_receipt=directory / "frames.capture.json")
            write_json(directory / "replay.json", receipt)
            events = [event for response in receipt.get("responses", []) for event in response.get("events", [])]
            result = {"status": "completed" if receipt["status"] in {"passed", "no_segments"} else "failed",
                      "run_id": directory.name, "extractor_profile": EXTRACTOR_PROFILE,
                      "decoded_frames": extracted["decoded_frames"], "emitted_frames": extracted["emitted_frames"],
                      "events": events, "replay_status": receipt["status"], "scope": SCOPE}
            if result["status"] == "failed":
                result["stage"] = stage
                result["error"] = "Replay contains rejected segments or protocol errors; inspect replay.json"
                write_json(directory / "failure.json", result)
            else:
                write_json(directory / "completed.json", result)
            result["artifacts"] = artifacts(directory)
            return JSONResponse(result, status_code=200 if result["status"] == "completed" else 422)
        except (Exception, asyncio.CancelledError) as error:
            if parser is not None:
                parser.close()
            status = error.status if isinstance(error, UploadError) else (400 if stage == "upload" else 422)
            failure = {"status": "failed", "run_id": directory.name, "stage": stage,
                       "error_type": type(error).__name__, "error": str(error) or "Client disconnected",
                       "extractor_profile": EXTRACTOR_PROFILE, "parameters": params, "scope": SCOPE}
            if parser is not None:
                failure["upload"] = {"received_request_bytes": parser.total_bytes,
                                     "retained_video_bytes": parser.file_bytes,
                                     "original_filename": parser.video_name,
                                     "fields": parser.fields, "complete": parser.complete}
            if directory.is_dir() and not (directory / "failure.json").exists():
                write_json(directory / "failure.json", failure)
            failure["artifacts"] = artifacts(directory) if directory.is_dir() else []
            if isinstance(error, asyncio.CancelledError):
                raise
            return JSONResponse(failure, status_code=status)
        finally:
            if parser is not None:
                parser.close()
            gate.release()

    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--pose-model", required=True)
    parser.add_argument("--hand-model", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18082)
    parser.add_argument("--max-upload-mib", type=int, default=100)
    parser.add_argument("--max-frames", type=int, default=100000)
    args = parser.parse_args(argv)
    try:
        import uvicorn
        import python_multipart  # fail at startup, not after accepting a user's video
        app = create_app(args.bundle, args.pose_model, args.hand_model, args.output_dir,
                         args.config, args.max_upload_mib * 1024 * 1024, args.max_frames)
    except ImportError as error:
        parser.error("Install .[server,video] and python-multipart>=0.0.20,<1: " + str(error))
    uvicorn.run(app, host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
