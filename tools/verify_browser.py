"""Chromium replay and failure smoke checks against a real local server.

Install Playwright and its Chromium browser in the runner environment. The
separate server Python must have vsl-streaming-toolkit[server] installed.
Use a synthetic demo bundle; this is browser/protocol validation, not accuracy.
"""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.request

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-python", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--frames", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    settings = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
    settings["max_sessions"] = 1
    config = out / "browser-server.json"
    config.write_text(json.dumps(settings), encoding="utf-8")
    frames = json.loads(Path(args.frames).read_text(encoding="utf-8-sig"))
    frame_array = out / "frames.json"
    frame_array.write_text(json.dumps(frames), encoding="utf-8")
    frame_lines = out / "frames.jsonl"
    frame_lines.write_text("\n".join(json.dumps(f) for f in frames), encoding="utf-8")
    with socket.socket() as selection:
        selection.bind(("127.0.0.1", 0))
        port = selection.getsockname()[1]
    url = "http://127.0.0.1:%d" % port
    checks = []
    with (out / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([
            args.server_python, "-m", "vsl_streaming.cli", "serve",
            "--bundle", str(Path(args.bundle).resolve()), "--config", str(config),
            "--host", "127.0.0.1", "--port", str(port),
        ], stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    with urllib.request.urlopen(url + "/health", timeout=1):
                        break
                except OSError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Server failed to start; inspect server.log")
                    time.sleep(.1)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                errors = []
                page = browser.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(url)
                observed = []
                for path in (frame_array, frame_lines):
                    page.locator("#file").set_input_files(str(path))
                    page.locator("#run").click()
                    page.wait_for_function("!document.querySelector('#run').disabled")
                    assert page.locator("#status").inner_text().startswith("Replayed ")
                    responses = json.loads(page.locator("#output").inner_text())
                    events = [event for response in responses for event in response["events"]]
                    assert events and all(event["status"] == "predicted" for event in events)
                    observed.append([{key: value for key, value in event.items()
                                      if key != "inference_ms"} for event in events])
                    checks.append("replay_" + path.suffix[1:])
                assert observed[0] == observed[1], "JSON and JSONL replay differ"
                page.screenshot(path=str(out / "replay.png"), full_page=True)

                assert page.evaluate("ws === null && pending.size === 0")
                checks.append("completed_replay_closes_socket")
                # Keep one explicit idle connection to exercise capacity rejection.
                page.evaluate("connect()")
                excess = browser.new_page()
                excess.goto(url)
                excess.locator("#reset").click()
                excess.wait_for_function("!document.querySelector('#reset').disabled")
                assert "1013" in excess.locator("#output").inner_text()
                checks.append("capacity_close_before_ready")
                excess.close()
                page.close()

                oversized = browser.new_page()
                oversized.goto(url)
                oversized.locator("#file").set_input_files({
                    "name": "oversized.json", "mimeType": "application/json",
                    "buffer": b" " * (10 * 1024 * 1024 + 1)})
                oversized.locator("#run").click()
                oversized.wait_for_function("!document.querySelector('#run').disabled")
                assert "10 MiB" in oversized.locator("#output").inner_text()
                assert oversized.evaluate("ws === null && counter === 0")
                checks.append("oversized_file_rejected_before_connect")
                oversized.close()

                for mode in ("byte_limit", "history_limit"):
                    bounded = browser.new_page()
                    bounded.add_init_script("""window.sentPayloads=[];
                    const originalSend=WebSocket.prototype.send;
                    WebSocket.prototype.send=function(data){
                        window.sentPayloads.push(data);return originalSend.call(this,data);};""")
                    def config_route(route, current=mode):
                        response = route.fetch()
                        body = response.json()
                        if current == "byte_limit":
                            body["settings"]["max_message_bytes"] = 1000
                        else:
                            body["settings"]["max_batch_frames"] = 1
                        route.fulfill(response=response, json=body)
                    bounded.route("**/v1/config", config_route)
                    bounded.goto(url)
                    bounded.locator("#file").set_input_files(str(frame_array))
                    bounded.locator("#run").click()
                    bounded.wait_for_function("!document.querySelector('#run').disabled")
                    status = bounded.locator("#status").inner_text()
                    assert status.startswith("Replayed %d/%d" % (len(frames), len(frames))), status
                    payloads = bounded.evaluate("window.sentPayloads")
                    requests = [json.loads(raw) for raw in payloads if json.loads(raw)["type"] == "frames"]
                    assert [frame for request in requests for frame in request["frames"]] == frames
                    assert bounded.evaluate("ws === null && pending.size === 0")
                    responses = json.loads(bounded.locator("#output").inner_text())
                    if mode == "byte_limit":
                        assert all(len(raw.encode("utf-8")) <= 1000 for raw in payloads)
                        assert len(requests) > 1
                        events = [event for response in responses for event in response["events"]]
                        actual = [{key: value for key, value in event.items() if key != "inference_ms"} for event in events]
                        assert actual == observed[0], "Byte-aware batches changed predictions"
                        checks.append("byte_limited_batches_preserve_events")
                    else:
                        assert len(frames) > 20, "History-bound fixture needs more than 20 frames"
                        assert len(responses) == 20
                        assert "omitted %d" % (len(frames) - 20) in status
                        checks.append("history_bounded_with_visible_omitted_count")
                    bounded.close()

                # Only shorten the two application timers. Browser/Playwright
                # internal timers and the production HTML remain unchanged.
                shorten = """const originalTimeout = window.setTimeout;
                window.setTimeout = (fn, ms, ...args) => originalTimeout(fn,
                    (ms === 10000 || ms === 30000) ? 80 : ms, ...args);"""
                for mode in ("handshake", "acknowledgement"):
                    context = browser.new_context()
                    context.add_init_script(shorten)
                    sent = []
                    def socket_handler(route, current=mode):
                        route.on_message(lambda message: sent.append(message))
                        if current == "acknowledgement":
                            route.send(json.dumps({"type": "ready", "session_id": "test-stall"}))
                    context.route_web_socket("**/v1/stream", socket_handler)
                    stalled = context.new_page()
                    stalled.on("pageerror", lambda error: errors.append(str(error)))
                    stalled.goto(url)
                    stalled.locator("#reset").click()
                    stalled.wait_for_function("!document.querySelector('#reset').disabled")
                    message = stalled.locator("#output").inner_text()
                    assert "timed out" in message, message
                    assert len(sent) == (1 if mode == "acknowledgement" else 0)
                    assert stalled.evaluate("ws === null && pending.size === 0")
                    checks.append(mode + "_timeout_no_auto_retry")
                    context.close()
                browser.close()
                assert not errors, errors
            deadline = time.monotonic() + 5
            while True:
                with urllib.request.urlopen(url + "/health") as response:
                    active = json.load(response)["active_sessions"]
                if active == 0:
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("Sessions did not clean up")
                time.sleep(.05)
            receipt = {"status": "passed", "scope": "synthetic browser replay and transport failure handling",
                       "browser": "Chromium", "checks": checks,
                       "json_jsonl_events_identical_excluding_inference_ms": True,
                       "frames": len(frames), "events_per_replay": len(observed[0]),
                       "page_errors": errors, "active_sessions_after": active,
                       "timeout_test_ms": 80,
                       "production_handshake_timeout_ms": 10000,
                       "production_request_timeout_ms": 30000}
            (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(receipt, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
