"""Real TCP/WebSocket check of an installed package and supplied bundle.

Run with the clean server environment's Python. The process started here is
always terminated on exit; an existing server is never stopped or reused.
"""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import websockets


async def replay(port, frames, batch_size):
    events = []
    latencies = []
    async with websockets.connect("ws://127.0.0.1:%d/v1/stream" % port, max_size=2_000_000) as ws:
        ready = json.loads(await ws.recv())
        if ready["type"] != "ready":
            raise RuntimeError("Missing ready handshake")
        responses = [ready]
        for offset in range(0, len(frames), batch_size):
            request = {"type": "frames", "request_id": "network-%d" % offset,
                       "frames": frames[offset:offset + batch_size], "flush": offset + batch_size >= len(frames)}
            started = time.perf_counter()
            await ws.send(json.dumps(request))
            response = json.loads(await ws.recv())
            responses.append(response)
            latencies.append((time.perf_counter() - started) * 1000)
            if response["type"] != "result":
                raise RuntimeError(response)
            if any(event["status"] != "predicted" for event in response["events"]):
                raise RuntimeError("Rejected network event: " + str(response["events"]))
            events.extend(response["events"])
            if offset == 0:
                await ws.send(json.dumps(request))
                repeated = json.loads(await ws.recv())
                responses.append(repeated)
                if not repeated["replayed"] or repeated["events"] != response["events"]:
                    raise RuntimeError("Exact retry behavior differs over network")
        return {"session_id": ready["session_id"], "events": events, "latencies_ms": latencies,
                "responses": responses}

def verify_session_logs(directory, sessions, bundle, settings, public_profile, package_version):
    """Check persisted server evidence against replies actually received over TCP."""
    from vsl_streaming.evaluation import events_from_responses
    paths = [directory / (session["session_id"] + ".session.jsonl") for session in sessions]
    # Health cleanup and the final log write occur in the same server teardown;
    # tolerate observing the former just before the final JSONL record arrives.
    for _ in range(30):
        try:
            records = [[json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                       for path in paths]
            if all(rows and rows[-1]["type"] == "session_end" for rows in records):
                break
        except (OSError, json.JSONDecodeError):
            pass
        time.sleep(0.05)
    else:
        raise RuntimeError("Missing completed session evidence")
    if set(directory.glob("*.session.jsonl")) != set(paths):
        raise RuntimeError("Unexpected session logs in this diagnostic")
    manifest = json.loads((Path(bundle) / "manifest.json").read_text(encoding="utf-8"))
    settings_hash = hashlib.sha256(json.dumps(settings, sort_keys=True, separators=(",", ":"),
                                               ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    def contains_raw_frames(value):
        if isinstance(value, dict):
            return any(key in ("frames", "pose_landmarks", "left_hand_landmarks", "right_hand_landmarks", "points")
                       or contains_raw_frames(item) for key, item in value.items())
        return isinstance(value, list) and any(contains_raw_frames(item) for item in value)
    counts = []
    for session, rows in zip(sessions, records):
        if ([row["record_index"] for row in rows] != list(range(len(rows)))
                or any(row["schema_version"] != 1 or row["session_id"] != session["session_id"] for row in rows)):
            raise RuntimeError("Session log identity or record ordering differs")
        kinds = [row["type"] for row in rows]
        if (kinds[0] != "session_start" or kinds[-1] != "session_end"
                or kinds.count("session_start") != 1 or kinds.count("session_end") != 1):
            raise RuntimeError("Session lifecycle evidence differs")
        start, end = rows[0], rows[-1]
        if (start["software_version"] != package_version or start["protocol_version"] != 1
                or start["settings"] != settings or start["settings_sha256"] != settings_hash
                or start["profile"] != public_profile or start["bundle_sha256"] != manifest["sha256"]
                or start["provider"] != settings["provider"] or not start["active_providers"]):
            raise RuntimeError("Session model/configuration provenance differs")
        response_rows = [row for row in rows if row["type"] == "response"]
        send_rows = [row for row in rows if row["type"] == "send_complete"]
        indices = list(range(len(response_rows)))
        if ([row["response_index"] for row in response_rows] != indices
                or [row["response_index"] for row in send_rows] != indices
                or kinds[1:-1] != ["response", "send_complete"] * len(response_rows)):
            raise RuntimeError("Response/send completion evidence is incomplete or out of order")
        responses = [row["response"] for row in response_rows]
        if responses != session["responses"]:
            raise RuntimeError("Persisted responses differ from live WebSocket replies")
        converted = events_from_responses(responses)
        if (converted != events_from_responses(session["responses"])
                or len(converted) != len(session["events"])
                or sum(reply.get("replayed", False) for reply in responses) != 1):
            raise RuntimeError("Logged event reconstruction or cached retry accounting differs")
        if (end["reason"] not in ("client_disconnect", "connection_lost")
                or end["buffered_frames_abandoned"] != 0 or end["state"]["buffered_frames"] != 0
                or end["state"] != responses[-1]["state"]):
            raise RuntimeError("Session ended with incomplete processing evidence")
        if contains_raw_frames(rows):
            raise RuntimeError("Session evidence unexpectedly contains raw input frames")
        counts.append(len(response_rows))
    return {"status": "passed", "directory": str(directory.resolve()), "completed_sessions": len(records),
            "response_counts": counts, "model_config_provenance": True, "contiguous_indices": True,
            "live_response_agreement": True, "cached_retry_deduplicated": True,
            "send_complete_for_each_response": True, "buffered_frames_abandoned": 0,
            "raw_input_frames_recorded": False,
            "delivery_scope": "ASGI send completion checked against this diagnostic client; not a production client acknowledgement"}


def check(bundle, config, frame_file, output, batch_size=31):
    # Import local example adapters for the reference replay too. Adding the
    # project root does not add src, so the installed wheel remains under test.
    project = Path(__file__).resolve().parents[1]
    if str(project) not in sys.path:
        sys.path.insert(0, str(project))
    from vsl_streaming.cli import replay as local_replay
    from vsl_streaming.config import load_config
    import vsl_streaming
    from vsl_streaming.capture import load_frames
    try:
        data = json.loads(Path(frame_file).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        data = load_frames(frame_file)
    recorded = isinstance(data, dict) and "frames" in data
    if isinstance(data, dict) and not recorded:
        data = load_frames(frame_file)
    frames = [dict(frame, seq=index) for index, frame in enumerate(data["frames"])] if recorded else data
    with socket.socket() as selection:
        selection.bind(("127.0.0.1", 0))
        port = selection.getsockname()[1]
    env = dict(os.environ)
    # Keep example adapter importable; avoid importing src instead of the wheel.
    env["PYTHONPATH"] = str(project)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    session_log_dir = Path(output).with_suffix(".sessions").resolve()
    session_log_dir.mkdir(parents=True, exist_ok=True)
    if any(session_log_dir.glob("*.session.jsonl")):
        raise RuntimeError("Use a new output path; session evidence already exists")
    log_path = Path(output).with_suffix(".server.log")
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-m", "vsl_streaming.cli", "serve", "--bundle", str(Path(bundle).resolve()),
                                    "--config", str(Path(config).resolve()), "--port", str(port),
                                    "--session-log-dir", str(session_log_dir)],
                                   cwd=project, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            health_url = "http://127.0.0.1:%d/health" % port
            for _ in range(150):
                if process.poll() is not None:
                    raise RuntimeError("Server exited; see " + str(log_path))
                try:
                    with urllib.request.urlopen(health_url, timeout=1) as result:
                        if json.load(result)["status"] == "ready":
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Server startup timed out")
            first = asyncio.run(replay(port, frames, batch_size))
            second = asyncio.run(replay(port, frames, max(1, batch_size - 12)))
            def stable(events):
                return [{key: value for key, value in event.items() if key != "inference_ms"} for event in events]
            if stable(first["events"]) != stable(second["events"]):
                raise RuntimeError("Reconnected session / changed batches produce different events")
            if first["session_id"] == second["session_id"]:
                raise RuntimeError("Reconnect reused a connection identity")
            for _ in range(30):
                with urllib.request.urlopen(health_url, timeout=1) as result:
                    cleanup = json.load(result)
                if cleanup["active_sessions"] == 0:
                    break
                time.sleep(0.05)
            if cleanup["active_sessions"] != 0:
                raise RuntimeError("Disconnected session remained active")
            with urllib.request.urlopen("http://127.0.0.1:%d/v1/config" % port, timeout=1) as result:
                public_configuration = json.load(result)
            session_logging = verify_session_logs(session_log_dir, [first, second], bundle,
                                                  load_config(config).to_dict(),
                                                  public_configuration["profile"], vsl_streaming.__version__)
            # Local replay same installed runtime, preserving all frame content.
            adapted = Path(output).with_suffix(".frames.json")
            adapted.write_text(json.dumps(frames), encoding="utf-8")
            reference = local_replay(bundle, adapted, load_config(config), batch_size)
            adapted.unlink()
            offline_events = [event for response in reference["responses"] for event in response["events"]]
            if stable(offline_events) != stable(first["events"]):
                raise RuntimeError("WebSocket events differ from installed-library replay")
            latencies = sorted(first["latencies_ms"])
            receipt = {"status": "passed", "scope": "local TCP integration diagnostic, not a deployment benchmark or recognition accuracy",
                       "python": sys.version, "package_path": vsl_streaming.__file__,
                       "server_has_torch": importlib.util.find_spec("torch") is not None,
                       "versions": {name: importlib.metadata.version(name) for name in
                                    ("vsl-streaming-toolkit", "onnxruntime", "numpy", "fastapi", "uvicorn", "websockets")},
                       "input_frames": len(frames), "events_per_session": len(first["events"]),
                       "new_session_id_on_reconnect": True, "batch_fragmentation_agreement": True,
                       "offline_websocket_agreement": True, "exact_retry": True, "active_sessions_after_disconnect": 0,
                       "session_logging": session_logging,
                       "batch_sizes": [batch_size, max(1, batch_size - 12)],
                       "diagnostic_rtt_p50_ms": latencies[len(latencies) // 2],
                       "diagnostic_rtt_max_ms": max(latencies)}
            Path(output).write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
            return receipt
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--frames", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--batch-size", type=int, default=31)
    args = parser.parse_args()
    print(json.dumps(check(args.bundle, args.config, args.frames, args.out, args.batch_size), indent=2))
