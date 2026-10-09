"""Synthetic real-TCP fault checks against the installed VSL package.

No trained checkpoint or human trace is used. This intentionally tiny arithmetic
recognizer tests software behavior; its timings are not model performance.
"""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import socket
import sys
import threading
import time
import urllib.request

import uvicorn
import websockets
from websockets.exceptions import ConnectionClosed
import vsl_streaming
from vsl_streaming.config import ServerConfig
from vsl_streaming.core import StreamConfig
from vsl_streaming.server import create_app

ROOT = Path(__file__).resolve().parent


class SyntheticArithmeticRecognizer:
    labels = ["synthetic_sum"]
    profile = {"name": "synthetic-2x2-arithmetic-only", "trained": False,
               "input": "2x2 points", "claim": "software fault fixture only"}

    def __init__(self):
        self.lock = threading.Lock()
        self.delay = 0.0
        self.calls = []
        self.completed = 0
        self.active = 0
        self.peak = 0

    def predict_segment(self, frames):
        with self.lock:
            self.calls.append([f["seq"] for f in frames])
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.delay)
            return {"label": "synthetic_sum", "score": 1.0,
                    "sum": sum(sum(sum(row) for row in f["points"]) for f in frames),
                    "seqs": [f["seq"] for f in frames]}
        finally:
            with self.lock:
                self.completed += 1
                self.active -= 1

    def snapshot(self):
        with self.lock:
            return {"started": len(self.calls), "completed": self.completed,
                    "active": self.active, "peak_concurrency": self.peak}


def settings():
    return ServerConfig(stream=StreamConfig(mode="fixed_window", window_frames=3,
                        min_segment_frames=2, min_up_frames=1, max_buffer_frames=6,
                        max_gap_ms=100), max_sessions=2, max_batch_frames=8,
                        max_message_bytes=4096, request_cache_size=8,
                        inference_concurrency=1)


def frame(seq):
    return {"seq": seq, "timestamp_ms": seq * 20, "points": [[seq, 0], [1, seq]]}


def batch(start=0, count=3, request_id="batch", flush=False):
    return {"type": "frames", "request_id": request_id, "flush": flush,
            "frames": [frame(i) for i in range(start, start + count)]}


def http_json(port, route):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, route), timeout=3) as response:
        return json.load(response)


def make_app(model):
    app = create_app(config=settings(), recognizer=model)
    from fastapi.responses import HTMLResponse

    @app.get("/readiness", response_class=HTMLResponse)
    async def readiness_page():
        return (ROOT / "phone_replay.html").read_text(encoding="utf-8")

    return app


class Harness:
    def __init__(self, port, model):
        self.port, self.model = port, model
        self.rows, self.wire = [], []
        self.case = "startup"

    def check(self, name, expected, observed):
        self.rows.append({"case": name, "expected": expected, "observed": observed,
                          "pass": expected == observed})

    async def connect(self, **kwargs):
        ws = await websockets.connect("ws://127.0.0.1:%d/v1/stream" % self.port, **kwargs)
        ready = json.loads(await asyncio.wait_for(ws.recv(), 5))
        self.wire.append({"case": self.case, "direction": "ready", "message": ready})
        return ws, ready

    async def request(self, ws, message):
        raw = message if isinstance(message, (str, bytes)) else json.dumps(message)
        self.wire.append({"case": self.case, "direction": "sent",
                          "message": repr(raw) if isinstance(raw, bytes) else raw})
        await ws.send(raw)
        result = json.loads(await asyncio.wait_for(ws.recv(), 5))
        self.wire.append({"case": self.case, "direction": "received", "message": result})
        return result

    async def cleanup(self):
        for _ in range(100):
            health = http_json(self.port, "/health")
            if health["active_sessions"] == 0:
                return 0
            await asyncio.sleep(.02)
        return health["active_sessions"]

    async def run(self):
        self.case = "malformed_and_limits"
        ws, ready = await self.connect()
        self.check("advertised_settings", settings().to_dict(), ready["settings"])
        cases = [(b"binary", "text_required"), ("{", "invalid_json"),
                 ('{"x":NaN}', "invalid_json"), ('{"x":1e309}', "invalid_json"),
                 ('{"x":1,"x":2}', "invalid_json"), ('{"x":"\\ud800"}', "invalid_json"),
                 ("[]", "invalid_message"), ({"type": "status"}, "invalid_request_id"),
                 ({"type": "status", "request_id": "unknown", "extra": 1}, "unknown_field"),
                 ({"type": "wrong", "request_id": "wrong"}, "invalid_type"),
                 ({"padding": "x" * 4096}, "message_too_large"),
                 (batch(count=9, request_id="oversized-batch"), "batch_too_large")]
        errors = []
        for index, (raw, expected) in enumerate(cases):
            response = await self.request(ws, raw)
            observed = response.get("error", {}).get("code")
            errors.append(observed)
            self.check("malformed_%02d" % index, expected, observed)
        state = (await self.request(ws, {"type": "status", "request_id": "after-errors"}))["state"]
        self.check("malformed_no_frames_applied", 0, state["received_frames"])
        self.check("malformed_rejection_count", 12, len(errors))
        self.case = "late_invalid_atomicity"
        invalid = batch(count=4, request_id="late-invalid")
        invalid["frames"][-1]["points"] = [[1], [2, 3]]
        before = self.model.snapshot()["started"]
        result = await self.request(ws, invalid)
        state = (await self.request(ws, {"type": "status", "request_id": "after-invalid"}))["state"]
        self.check("late_invalid_batch", {"code": "invalid_points", "received": 0, "inferences": 0},
                   {"code": result.get("error", {}).get("code"), "received": state["received_frames"],
                    "inferences": self.model.snapshot()["started"] - before})
        self.case = "retry_and_conflict"
        request = batch(request_id="first")
        original = await self.request(ws, request)
        repeat = await self.request(ws, request)
        self.check("exact_retry", {"replayed": True, "equal_events": True, "inferences": 1},
                   {"replayed": repeat["replayed"], "equal_events": repeat["events"] == original["events"],
                    "inferences": self.model.snapshot()["started"] - before})
        conflict = await self.request(ws, batch(start=3, request_id="first"))
        recovery = await self.request(ws, batch(start=3, request_id="second"))
        self.check("conflict_then_recovery", {"code": "request_id_conflict", "received": 6, "seqs": [3,4,5]},
                   {"code": conflict.get("error", {}).get("code"), "received": recovery["state"]["received_frames"],
                    "seqs": recovery["events"][0]["prediction"]["seqs"]})
        ordering = await self.request(ws, batch(start=5, request_id="backwards"))
        self.check("ordering_rejected", "out_of_order_seq", ordering.get("error", {}).get("code"))
        await ws.close()
        self.check("cleanup_after_correctness", 0, await self.cleanup())
        self.case = "reconnect_and_gap_flush"
        ws, new_ready = await self.connect()
        new = await self.request(ws, batch(request_id="first", count=2))
        self.check("reconnect_fresh_session", {"new_id": True, "received": 2, "replayed": False},
                   {"new_id": ready["session_id"] != new_ready["session_id"],
                    "received": new["state"]["received_frames"], "replayed": new["replayed"]})
        gap = await self.request(ws, batch(start=8, count=2, request_id="gap", flush=True))
        self.check("gap_then_flush", {"reasons": ["gap", "flush"], "counts": [2,2], "gaps": 1, "buffered": 0},
                   {"reasons": [e["reason"] for e in gap["events"]], "counts": [e["frame_count"] for e in gap["events"]],
                    "gaps": gap["state"]["gap_resets"], "buffered": gap["state"]["buffered_frames"]})
        await ws.close()
        await self.cleanup()
        self.case = "session_capacity"
        first, _ = await self.connect()
        second, _ = await self.connect()
        codes = []
        for _ in range(5):
            excess = await websockets.connect("ws://127.0.0.1:%d/v1/stream" % self.port)
            try:
                await asyncio.wait_for(excess.recv(), 5)
                codes.append("unexpected_message")
            except ConnectionClosed as error:
                codes.append(error.rcvd.code if error.rcvd else None)
            finally:
                await excess.close()
        self.check("capacity_2_admitted_5_excess", {"active": 2, "close_codes": [1013]*5},
                   {"active": http_json(self.port, "/health")["active_sessions"], "close_codes": codes})
        self.model.delay = .04
        concurrent = await asyncio.gather(self.request(first, batch(request_id="concurrent-1")),
                                          self.request(second, batch(request_id="concurrent-2")))
        self.check("global_inference_gate", {"responses": 2, "predictions": 2, "peak": 1},
                   {"responses": len(concurrent), "predictions": sum(len(r["events"]) for r in concurrent),
                    "peak": self.model.snapshot()["peak_concurrency"]})
        await first.close()
        await second.close()
        self.check("capacity_cleanup", 0, await self.cleanup())
        replacement, _ = await self.connect()
        self.check("capacity_slot_reusable", 1, http_json(self.port, "/health")["active_sessions"])
        await replacement.close()
        await self.cleanup()
        self.case = "paused_reader_bounded_burst"
        self.model.delay = .02
        slow, _ = await self.connect(max_queue=1)
        before = self.model.snapshot()["completed"]
        burst_started = time.perf_counter()
        for i in range(24):
            await slow.send(json.dumps(batch(start=i*3, request_id="burst-%d" % i)))
        await asyncio.sleep(.65)
        before_read = self.model.snapshot()["completed"] - before
        responses = [json.loads(await asyncio.wait_for(slow.recv(), 5)) for _ in range(24)]
        elapsed = time.perf_counter() - burst_started
        counts = {"sent": 24, "responses": len(responses),
                  "predictions": sum(len(r.get("events", [])) for r in responses),
                  "errors": sum(r["type"] == "error" for r in responses),
                  "final_received_frames": responses[-1]["state"]["received_frames"],
                  "inferences": self.model.snapshot()["completed"] - before,
                  "ordered_ids": [r["request_id"] for r in responses] == ["burst-%d" % i for i in range(24)]}
        self.check("paused_reader_24_request_burst", {"sent":24,"responses":24,"predictions":24,"errors":0,
                   "final_received_frames":72,"inferences":24,"ordered_ids":True}, counts)
        self.wire.append({"case": self.case, "pause_seconds": .65,
                          "completed_before_application_read": before_read, "elapsed_seconds": elapsed,
                          "responses": responses, "scope": "small finite burst; does not establish transport queue memory bound"})
        await slow.close()
        self.check("paused_reader_cleanup", 0, await self.cleanup())
        self.case = "disconnect_during_inference"
        self.model.delay = .2
        departing, _ = await self.connect()
        before = self.model.snapshot()
        await departing.send(json.dumps(batch(request_id="disconnect-inflight")))
        for _ in range(100):
            if self.model.snapshot()["started"] > before["started"]:
                break
            await asyncio.sleep(.005)
        seen_active = self.model.snapshot()["active"]
        await departing.close()
        cleaned = await self.cleanup()
        self.check("disconnect_does_not_cancel_started_inference",
                   {"active_at_disconnect": 1, "started": 1, "completed": 1, "sessions_after": 0},
                   {"active_at_disconnect": seen_active,
                    "started": self.model.snapshot()["started"] - before["started"],
                    "completed": self.model.snapshot()["completed"] - before["completed"], "sessions_after": cleaned})
        self.model.delay = 0


def config_checks(h):
    invalid = [{"max_sessions": 0}, {"max_batch_frames": 0}, {"max_message_bytes": 0},
               {"request_cache_size": 0}, {"inference_concurrency": 0}, {"top_k": True},
               {"unknown": 1}, {"stream": {"mode": "fixed_window", "window_frames": 301}},
               {"stream": {"max_gap_ms": 0}}]
    rejected = []
    for value in invalid:
        try:
            ServerConfig.from_dict(value)
            rejected.append(False)
        except (ValueError, TypeError):
            rejected.append(True)
    h.check("invalid_configuration_rejection", [True]*9, rejected)
    h.wire.append({"case": "invalid_configuration_rejection", "inputs": invalid, "rejected": rejected})


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    model = SyntheticArithmeticRecognizer()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(make_app(model), host="127.0.0.1", port=port,
                            log_level="warning", ws="websockets", ws_max_size=65536, ws_max_queue=8))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    h = Harness(port, model)
    failure = None
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        if not server.started:
            raise RuntimeError("server did not start")
        config_checks(h)
        asyncio.run(h.run())
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error), "case": h.case}
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    receipt = {"status": "passed" if failure is None and all(r["pass"] for r in h.rows) else "failed",
               "scope": "synthetic arithmetic fixture, installed package, real loopback TCP/WebSocket; no phone or natural recognition evidence",
               "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "python": sys.version,
               "platform": platform.platform(), "package_path": vsl_streaming.__file__,
               "versions": {k: importlib.metadata.version(k) for k in
                            ("vsl-streaming-toolkit", "fastapi", "uvicorn", "websockets")},
               "settings": settings().to_dict(), "uvicorn_ws_max_size": 65536, "uvicorn_ws_max_queue": 8,
               "checks_total": len(h.rows), "checks_passed": sum(r["pass"] for r in h.rows),
               "error": failure, "synthetic_model_counts": model.snapshot(), "server_thread_stopped": not thread.is_alive(),
               "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "checks": h.rows,
               "limitations": ["Finite paused-reader burst does not prove memory bounds for transport queues or sustained overload.",
                               "Client receive timeouts do not cancel server work; started inference completed after disconnect in this test.",
                               "No trained-model latency, recognition accuracy, Wi-Fi, smartphone capture, or production robustness claim."]}
    (output / "host_readiness_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    (output / "wire_transcript.json").write_text(json.dumps(h.wire, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] == "passed" and receipt["server_thread_stopped"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--serve", action="store_true", help="serve synthetic fixture plus /readiness browser page")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if args.serve:
        uvicorn.run(make_app(SyntheticArithmeticRecognizer()), host=args.host, port=args.port,
                    ws_max_size=65536, ws_max_queue=8)
    else:
        raise SystemExit(run(args.out))
