"""Real ASGI WebSocket contracts using a deterministic injected recognizer."""
import json
import unittest

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from vsl_streaming.config import ServerConfig
from vsl_streaming.core import StreamConfig
from vsl_streaming.server import create_app


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
