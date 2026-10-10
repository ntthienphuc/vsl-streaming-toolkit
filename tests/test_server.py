"""Real ASGI WebSocket contracts using a deterministic injected recognizer."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from vsl_streaming.config import ServerConfig
from vsl_streaming.core import StreamConfig
from vsl_streaming.server import create_app
from vsl_streaming.session_logging import SessionLog, SessionLogError, canonical_sha256


class FakeRecognizer:
    profile = {"adapter": "test-only"}
    labels = ["example"]

    def __init__(self, invalid_output=False):
        self.calls = []
        self.invalid_output = invalid_output

    def predict_segment(self, frames):
        seqs = [f["seq"] for f in frames]
        self.calls.append(seqs)
        return {"label": "example", "score": float("nan") if self.invalid_output else 0.95,
                "seqs": seqs}


def config(**overrides):
    return ServerConfig(stream=StreamConfig(mode="fixed_window", window_frames=3,
                                           min_segment_frames=2, min_up_frames=1), **overrides)


def message(start=0, count=3, request_id="r1", flush=False):
    return {"type": "frames", "request_id": request_id, "flush": flush,
            "frames": [{"seq": i, "timestamp_ms": i * 20,
                        "points": [[i, 0], [1, i]]} for i in range(start, start + count)]}


class WebSocketServerTests(unittest.TestCase):
    def test_session_log_records_full_responses_retry_and_unflushed_disconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            model = FakeRecognizer()
            app = create_app(config=config(), recognizer=model, session_log_dir=directory)
            with TestClient(app) as client:
                self.assertNotIn(directory, client.get("/v1/config").text)
                with client.websocket_connect("/v1/stream") as ws:
                    ready = ws.receive_json()
                    ws.send_json(message(count=5))
                    result = ws.receive_json()
                    ws.send_json(message(count=5))
                    retry = ws.receive_json()
                    ws.send_text("{")
                    invalid = ws.receive_json()
                self.assertEqual(client.get("/health").json()["active_sessions"], 0)
            records = [json.loads(line) for line in (Path(directory) / (ready["session_id"] + ".session.jsonl")).read_text(encoding="utf-8").splitlines()]
            self.assertEqual([r["record_index"] for r in records], list(range(len(records))))
            start, end = records[0], records[-1]
            self.assertEqual(start["type"], "session_start")
            self.assertEqual(start["settings_sha256"], canonical_sha256(config().to_dict()))
            self.assertIsNone(start["bundle_sha256"])
            responses = [r for r in records if r["type"] == "response"]
            self.assertEqual([r["response"] for r in responses], [ready, result, retry, invalid])
            self.assertEqual(responses[1]["request_sha256"], responses[2]["request_sha256"])
            self.assertEqual([r["response_index"] for r in records if r["type"] == "send_complete"], [0, 1, 2, 3])
            self.assertEqual(end["type"], "session_end")
            self.assertEqual(end["reason"], "client_disconnect")
            self.assertEqual(end["buffered_frames_abandoned"], 2)
            self.assertEqual(end["state"]["received_frames"], 5)
            self.assertEqual(model.calls, [[0, 1, 2]])
            self.assertNotIn('"points"', (Path(directory) / (ready["session_id"] + ".session.jsonl")).read_text())

    def test_logging_disabled_does_not_open_evidence(self):
        with patch("vsl_streaming.server.SessionLog", side_effect=AssertionError("unexpected logging")):
            with TestClient(create_app(config=config(), recognizer=FakeRecognizer())) as client:
                with client.websocket_connect("/v1/stream") as ws:
                    self.assertEqual(ws.receive_json()["type"], "ready")

    def test_unusable_log_directory_fails_before_serving(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "file"
            path.write_text("occupied")
            with self.assertRaises(OSError):
                create_app(config=config(), recognizer=FakeRecognizer(), session_log_dir=path)

    def test_log_open_failure_closes_without_ready_or_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            model = FakeRecognizer()
            app = create_app(config=config(), recognizer=model, session_log_dir=directory)
            with patch("vsl_streaming.server.SessionLog", side_effect=SessionLogError("unavailable")):
                with TestClient(app) as client:
                    with client.websocket_connect("/v1/stream") as ws:
                        with self.assertRaises(WebSocketDisconnect) as caught:
                            ws.receive_json()
                    self.assertEqual(caught.exception.code, 1011)
                    self.assertEqual(client.get("/health").json()["active_sessions"], 0)
            self.assertEqual(model.calls, [])

    def test_response_log_failure_stops_acknowledgement_and_releases_session(self):
        original = SessionLog.write
        def fail_response(log, kind, **fields):
            if kind == "response" and fields["response"]["type"] == "result":
                raise SessionLogError("disk full")
            return original(log, kind, **fields)
        with tempfile.TemporaryDirectory() as directory:
            model = FakeRecognizer()
            app = create_app(config=config(), recognizer=model, session_log_dir=directory)
            with patch.object(SessionLog, "write", fail_response):
                with TestClient(app) as client:
                    with client.websocket_connect("/v1/stream") as ws:
                        ready = ws.receive_json()
                        ws.send_json(message())
                        with self.assertRaises(WebSocketDisconnect) as caught:
                            ws.receive_json()
                    self.assertEqual(caught.exception.code, 1011)
                    self.assertEqual(client.get("/health").json()["active_sessions"], 0)
            records = [json.loads(line) for line in (Path(directory) / (ready["session_id"] + ".session.jsonl")).read_text().splitlines()]
            self.assertEqual(records[-1]["reason"], "evidence_log_failed")
            self.assertEqual(records[-1]["state"]["received_frames"], 3)
            self.assertEqual(len(model.calls), 1)
            self.assertEqual(len([r for r in records if r["type"] == "response"]), 1)

    def test_adapter_exception_is_bounded_utf8_and_connection_recovers(self):
        model = FakeRecognizer()
        def broken(frames):
            raise ValueError("\ud800" + "x" * 3000)
        model.predict_segment = broken
        app = create_app(config=config(), recognizer=model)
        with TestClient(app) as client:
            with client.websocket_connect("/v1/stream") as ws:
                ws.receive_json()
                ws.send_json(message())
                response = ws.receive_json()
                event = response["events"][0]
                self.assertEqual(event["status"], "rejected")
                self.assertEqual(len(event["error"]["message"]), 2000)
                event["error"]["message"].encode("utf-8")
                ws.send_json({"type": "status", "request_id": "after-failure"})
                self.assertEqual(ws.receive_json()["type"], "result")

    def test_health_config_demo_and_ready(self):
        app = create_app(config=config(), recognizer=FakeRecognizer())
        with TestClient(app) as client:
            self.assertEqual(client.get("/health").json()["active_sessions"], 0)
            self.assertEqual(client.get("/v1/config").json()["settings"]["stream"]["mode"], "fixed_window")
            self.assertIn("text/html", client.get("/").headers["content-type"])
            with client.websocket_connect("/v1/stream") as ws:
                ready = ws.receive_json()
                self.assertEqual(ready["type"], "ready")
                self.assertEqual(ready["protocol_version"], 1)
                self.assertTrue(ready["session_id"])
                self.assertEqual(client.get("/health").json()["active_sessions"], 1)
            self.assertEqual(client.get("/health").json()["active_sessions"], 0)
        self.assertEqual(len(app.state.active_sessions), 0)

    def test_multiple_windows_flush_retry_and_disconnect_cleanup(self):
        model = FakeRecognizer()
        app = create_app(config=config(), recognizer=model)
        with TestClient(app) as client:
            with client.websocket_connect("/v1/stream") as ws:
                ws.receive_json()
                request = message(count=8, flush=True)
                ws.send_json(request)
                result = ws.receive_json()
                self.assertEqual([e["reason"] for e in result["events"]], ["window", "window", "flush"])
                self.assertEqual(model.calls, [[0, 1, 2], [3, 4, 5], [6, 7]])
                self.assertEqual(result["state"]["buffered_frames"], 0)
                ws.send_json(request)
                retry = ws.receive_json()
                self.assertTrue(retry["replayed"])
                self.assertEqual(retry["events"], result["events"])
                self.assertEqual(len(model.calls), 3)
            self.assertEqual(client.get("/health").json()["active_sessions"], 0)

    def test_simultaneous_clients_isolate_ids_and_buffers(self):
        model = FakeRecognizer()
        app = create_app(config=config(), recognizer=model)
        with TestClient(app) as client:
            with client.websocket_connect("/v1/stream") as first:
                first_ready = first.receive_json()
                first.send_json(message(count=2))
                self.assertEqual(first.receive_json()["events"], [])
                with client.websocket_connect("/v1/stream") as second:
                    second_ready = second.receive_json()
                    self.assertNotEqual(first_ready["session_id"], second_ready["session_id"])
                    self.assertEqual(client.get("/health").json()["active_sessions"], 2)
                    second.send_json(message())
                    result = second.receive_json()
                    self.assertFalse(result["replayed"])
                    self.assertEqual(result["events"][0]["prediction"]["seqs"], [0, 1, 2])
                    first.send_json({"type": "flush", "request_id": "flush"})
                    result = first.receive_json()
                    self.assertEqual(result["events"][0]["prediction"]["seqs"], [0, 1])
                self.assertEqual(client.get("/health").json()["active_sessions"], 1)
            self.assertEqual(client.get("/health").json()["active_sessions"], 0)

    def test_capacity_closes_excess_client_and_slot_recovers(self):
        app = create_app(config=config(max_sessions=1), recognizer=FakeRecognizer())
        with TestClient(app) as client:
            with client.websocket_connect("/v1/stream") as first:
                first.receive_json()
                with self.assertRaises(WebSocketDisconnect) as caught:
                    with client.websocket_connect("/v1/stream") as second:
                        second.receive_json()
                self.assertEqual(caught.exception.code, 1013)
                self.assertEqual(client.get("/health").json()["active_sessions"], 1)
                first.send_json({"type": "status", "request_id": "still-alive"})
                self.assertEqual(first.receive_json()["type"], "result")
            with client.websocket_connect("/v1/stream") as third:
                self.assertEqual(third.receive_json()["type"], "ready")
            self.assertEqual(client.get("/health").json()["active_sessions"], 0)

    def test_binary_invalid_json_and_oversize_errors_recover(self):
        model = FakeRecognizer()
        app = create_app(config=config(max_message_bytes=500), recognizer=model)
        with TestClient(app) as client:
            with client.websocket_connect("/v1/stream") as ws:
                ws.receive_json()
                ws.send_bytes(b"binary")
                self.assertEqual(ws.receive_json()["error"]["code"], "text_required")
                for raw in ('{', '{"x":NaN}', '{"x":1e309}', '{"x":1,"x":2}', '{"x":"\\ud800"}'):
                    ws.send_text(raw)
                    result = ws.receive_json()
                    self.assertEqual(result["error"]["code"], "invalid_json")
                    self.assertIsNone(result["request_id"])
                ws.send_text(json.dumps({"padding": "x" * 600}))
                self.assertEqual(ws.receive_json()["error"]["code"], "message_too_large")
                ws.send_json(message())
                result = ws.receive_json()
                self.assertEqual(result["type"], "result")
                self.assertEqual(result["state"]["received_frames"], 3)
                self.assertEqual(model.calls, [[0, 1, 2]])

    def test_duplicate_surrogate_json_key_returns_error_and_recovers(self):
        app = create_app(config=config(), recognizer=FakeRecognizer())
        with TestClient(app) as client:
            with client.websocket_connect("/v1/stream") as ws:
                ws.receive_json()
                ws.send_text('{"\\ud800":1,"\\ud800":2}')
                response = ws.receive_json()
                self.assertEqual(response["error"]["code"], "invalid_json")
                response["error"]["message"].encode("utf-8")
                ws.send_json(message())
                response = ws.receive_json()
                self.assertEqual(response["type"], "result")
                self.assertEqual(response["state"]["received_frames"], 3)

    def test_duplicate_conflict_is_recoverable_and_atomic(self):
        model = FakeRecognizer()
        app = create_app(config=config(), recognizer=model)
        with TestClient(app) as client:
            with client.websocket_connect("/v1/stream") as ws:
                ws.receive_json()
                ws.send_json(message())
                ws.receive_json()
                ws.send_json(message(start=3))
                self.assertEqual(ws.receive_json()["error"]["code"], "request_id_conflict")
                ws.send_json(message(start=3, request_id="r2"))
                result = ws.receive_json()
                self.assertEqual(result["events"][0]["prediction"]["seqs"], [3, 4, 5])
                self.assertEqual(len(model.calls), 2)

    def test_nonfinite_prediction_is_rejected_without_killing_connection(self):
        app = create_app(config=config(), recognizer=FakeRecognizer(invalid_output=True))
        with TestClient(app) as client:
            with client.websocket_connect("/v1/stream") as ws:
                ws.receive_json()
                ws.send_json(message())
                result = ws.receive_json()
                self.assertEqual(result["events"][0]["status"], "rejected")
                self.assertNotIn("prediction", result["events"][0])
                ws.send_json({"type": "status", "request_id": "status"})
                self.assertEqual(ws.receive_json()["type"], "result")


if __name__ == "__main__":
    unittest.main()
