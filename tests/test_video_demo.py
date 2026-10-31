"""HTTP/evidence tests use synthetic bytes and hooks, never claim detector parity."""
import hashlib
import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from vsl_streaming.config import ServerConfig
from vsl_streaming.core import StreamConfig

HAS_HTTP = all(importlib.util.find_spec(name) is not None
               for name in ("fastapi", "httpx", "python_multipart"))
SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "serve_video_demo.py"
spec = importlib.util.spec_from_file_location("video_demo", SCRIPT)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


@unittest.skipUnless(HAS_HTTP, "optional HTTP demo dependencies are not installed")
class VideoDemoTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Windows runners may expose TEMP through an 8.3 alias; the app resolves it.
        self.root = Path(self.temp.name).resolve()
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        self.pose, self.hands = self.root / "pose.task", self.root / "hands.task"
        self.pose.write_bytes(b"pose test asset")
        self.hands.write_bytes(b"hand test asset")
        self.runs = self.root / "runs"
        self.settings = ServerConfig(stream=StreamConfig(angle_threshold=125), max_batch_frames=7, top_k=2)
        self.extract = Mock(side_effect=self.extract_fixture)
        self.replay = Mock(return_value={"status": "no_segments", "responses": [{"events": []}]})
        self.app = demo.create_app(self.bundle, self.pose, self.hands, self.runs, self.settings,
                                   max_upload_bytes=32, max_frames=125,
                                   extract_hook=self.extract, replay_hook=self.replay)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    @staticmethod
    def extract_fixture(video, pose, hands, frames, **params):
        frames.write_text("[]\n", encoding="utf-8")
        frames.with_suffix(".capture.json").write_text("{}\n", encoding="utf-8")
        return {"decoded_frames": 10, "emitted_frames": 5}

    def post(self, data=None, name="demo.mp4", video=b"synthetic bytes"):
        return self.client.post("/v1/video", data=data or {}, files={"video": (name, video, "video/mp4")})

    def test_no_segments_and_exact_artifacts_configuration(self):
        response = self.post({"rotate": "90", "input_mirrored": "true", "target_fps": "7.5",
                              "timestamp_mode": "frame-index"}, name="../../private\\escape.MP4")
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual((result["status"], result["replay_status"], result["events"]),
                         ("completed", "no_segments", []))
        run = self.runs / result["run_id"]
        self.assertEqual([p.name for p in self.runs.iterdir()], [result["run_id"]])
        self.assertNotEqual(result["run_id"], "00000000-0000-0000-0000-000000000000")
        for receipt_name in ("request.json", "completed.json"):
            receipt = json.loads((run / receipt_name).read_text(encoding="utf-8"))
            self.assertEqual(receipt["run_id"], result["run_id"])
        self.assertEqual((run / "original.mp4").read_bytes(), b"synthetic bytes")
        self.assertEqual(self.extract.call_args.kwargs, {"rotate": 90, "input_mirrored": True,
                         "target_fps": 7.5, "timestamp_mode": "frame-index", "max_frames": 125})
        self.assertEqual(self.replay.call_args.args, (self.bundle, run / "frames.json", self.settings))
        self.assertEqual(self.replay.call_args.kwargs, {"batch_size": 7,
                         "capture_receipt": run / "frames.capture.json"})
        for artifact in result["artifacts"]:
            self.assertEqual(artifact["url"], "/v1/runs/" + result["run_id"] + "/" + artifact["name"])
            saved = self.client.get(artifact["url"])
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(len(saved.content), artifact["bytes"])
            self.assertEqual(hashlib.sha256(saved.content).hexdigest(), artifact["sha256"])
            self.assertEqual(saved.headers["X-Content-SHA256"], artifact["sha256"])
        self.assertEqual(self.client.get("/health").json()["settings"], self.settings.to_dict())

    def test_oversize_retains_bounded_partial_and_releases_gate(self):
        response = self.post(video=b"x" * 33)
        self.assertEqual(response.status_code, 413, response.text)
        run = self.runs / response.json()["run_id"]
        self.assertEqual((run / "upload.partial").read_bytes(), b"x" * 32)
        self.assertTrue((run / "failure.json").exists())
        self.extract.assert_not_called()
        self.assertEqual(self.post().status_code, 200)

    def test_truncated_upload_never_becomes_completed_original(self):
        body = b'--demo\r\nContent-Disposition: form-data; name="video"; filename="demo.mp4"\r\n\r\npartial bytes'
        response = self.client.post("/v1/video", content=body,
                                    headers={"Content-Type": "multipart/form-data; boundary=demo"})
        self.assertEqual(response.status_code, 400, response.text)
        run = self.runs / response.json()["run_id"]
        self.assertEqual((run / "upload.partial").read_bytes(), b"partial bytes")
        self.assertFalse((run / "original.mp4").exists())
        self.extract.assert_not_called()

    def test_parameter_errors_retain_original_and_do_not_extract(self):
        for field, values in {"target_fps": ["nan", "inf", "-1", "121", "oops"],
                              "rotate": ["-90", "90.0"], "input_mirrored": ["1", "True"],
                              "timestamp_mode": ["auto"]}.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    response = self.post({field: value})
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assertTrue((self.runs / response.json()["run_id"] / "original.mp4").exists())
        self.extract.assert_not_called()

    def test_invalid_suffix_and_duplicate_video_rejected(self):
        self.assertEqual(self.post(name="evil.exe").status_code, 400)
        response = self.client.post("/v1/video", files=[("video", ("a.mp4", b"one")),
                                                      ("video", ("b.mp4", b"two"))])
        self.assertEqual(response.status_code, 400)
        self.extract.assert_not_called()

    def test_busy_rejects_without_creating_second_run(self):
        entered, finish = threading.Event(), threading.Event()
        original = self.extract_fixture

        def blocking(*args, **kwargs):
            entered.set()
            if not finish.wait(10):
                raise RuntimeError("Test did not release job")
            return original(*args, **kwargs)

        self.extract.side_effect = blocking
        replies = []
        worker = threading.Thread(target=lambda: replies.append(self.post()))
        worker.start()
        try:
            self.assertTrue(entered.wait(5))
            busy = self.post()
            self.assertEqual(busy.status_code, 409)
            self.assertEqual(self.client.get("/health").json()["active_jobs"], 1)
            self.assertEqual(len(list(self.runs.iterdir())), 1)
        finally:
            finish.set()
            worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(replies[0].status_code, 200)
        self.assertEqual(self.client.get("/health").json()["active_jobs"], 0)

    def test_extraction_failure_is_downloadable_and_next_run_works(self):
        self.extract.side_effect = ValueError("nonmonotonic decoder timestamp")
        response = self.post()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["stage"], "extraction")
        failure = next(a for a in response.json()["artifacts"] if a["name"] == "failure.json")
        self.assertIn("nonmonotonic", self.client.get(failure["url"]).json()["error"])
        self.replay.assert_not_called()
        self.extract.side_effect = self.extract_fixture
        self.assertEqual(self.post().status_code, 200)

    def test_rejected_replay_is_preserved_and_not_called_success(self):
        self.replay.return_value = {"status": "failed", "responses": [{"events": [{"status": "rejected"}]}]}
        response = self.post()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["stage"], "replay")
        self.assertEqual(response.json()["replay_status"], "failed")
        self.assertEqual(response.json()["events"], [{"status": "rejected"}])
        self.assertIn("replay.json", [a["name"] for a in response.json()["artifacts"]])

    def test_download_does_not_expose_unlisted_files_or_traversal(self):
        result = self.post().json()
        run = self.runs / result["run_id"]
        (run / "private.txt").write_text("private", encoding="utf-8")
        for suffix in ("private.txt", "completed.json", "..%2F..%2Fpose.task", "%2e%2e%5cpose.task"):
            self.assertEqual(self.client.get("/v1/runs/" + result["run_id"] + "/" + suffix).status_code, 404)
        self.assertEqual(self.client.get("/v1/runs/not-a-uuid/original.mp4").status_code, 404)

    def test_cancel_waits_for_worker_before_releasing_gate_or_finalizing_failure(self):
        import httpx
        entered, finish, written = threading.Event(), threading.Event(), threading.Event()

        def blocking(*args, **kwargs):
            entered.set()
            if not finish.wait(5):
                raise RuntimeError("Cancellation test did not release worker")
            result = self.extract_fixture(*args, **kwargs)
            written.set()
            return result

        async def scenario():
            self.extract.side_effect = blocking
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                task = asyncio.create_task(client.post("/v1/video", files={"video": ("a.mp4", b"first")}))
                try:
                    for _ in range(200):
                        if entered.is_set():
                            break
                        await asyncio.sleep(.005)
                    self.assertTrue(entered.is_set())
                    task.cancel()
                    await asyncio.sleep(.02)
                    self.assertFalse(written.is_set())
                    self.assertTrue(self.app.state.job_lock.locked())
                    self.assertFalse(any(self.runs.glob("*/failure.json")))
                    busy = await client.post("/v1/video", files={"video": ("b.mp4", b"second")})
                    self.assertEqual(busy.status_code, 409)
                finally:
                    finish.set()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                self.assertTrue(written.is_set())
                self.assertFalse(self.app.state.job_lock.locked())
                failure_path = next(self.runs.glob("*/failure.json"))
                failure = json.loads(failure_path.read_text(encoding="utf-8"))
                self.assertEqual(failure["error_type"], "CancelledError")
                self.assertTrue((failure_path.parent / "frames.json").is_file())
                self.replay.assert_not_called()
                self.extract.side_effect = self.extract_fixture
                retry = await client.post("/v1/video", files={"video": ("b.mp4", b"second")})
                self.assertEqual(retry.status_code, 200)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
