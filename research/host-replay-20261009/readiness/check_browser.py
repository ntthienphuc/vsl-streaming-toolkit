"""Local Chromium smoke test; explicitly not an actual smartphone measurement."""
import argparse
import sys
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
DEFAULT_PYTHON = sys.executable


def main(python):
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    checks, errors = [], []
    with (results / "browser_server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([python, str(ROOT / "host_readiness.py"), "--serve", "--port", str(port)],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen("http://127.0.0.1:%d/health" % port, timeout=1) as r:
                        if json.load(r)["status"] == "ready":
                            break
                except OSError:
                    time.sleep(.05)
            else:
                raise RuntimeError("fixture server startup timeout")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 320, "height": 740})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto("http://127.0.0.1:%d/readiness" % port)
                page.locator("#connect").click()
                page.wait_for_function("document.getElementById('output').textContent.includes('Confirm permission')")
                checks.append({"case": "permission_required", "pass": True})
                page.locator("#permission").check()
                page.locator("#connect").click()
                page.wait_for_function("document.getElementById('status').textContent.startsWith('Connected:')")
                first_session = page.locator("#status").inner_text()
                checks.append({"case": "ready_handshake", "pass": True})
                page.locator("#replay").click()
                page.wait_for_function("document.getElementById('status').textContent.startsWith('Replay complete:')")
                summary = json.loads(page.locator("#output").inner_text())
                observed = {key: summary[key] for key in ("frames", "requests", "predictions", "rejected")}
                expected = {"frames": 8, "requests": 3, "predictions": 3, "rejected": 0}
                checks.append({"case": "synthetic_replay", "expected": expected, "observed": observed, "pass": observed == expected})
                page.locator("#reset").click()
                page.wait_for_function("document.getElementById('output').textContent.includes('received_frames')")
                reset = json.loads(page.locator("#output").inner_text())
                checks.append({"case": "reset_clears_state", "pass": reset["response"]["state"]["received_frames"] == 0})
                page.locator("#disconnect").click()
                page.locator("#connect").click()
                page.wait_for_function("document.getElementById('status').textContent.startsWith('Connected:')")
                checks.append({"case": "reconnect_new_id", "pass": page.locator("#status").inner_text() != first_session})
                overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth")
                checks.append({"case": "320px_no_horizontal_overflow", "pass": not overflow})
                with page.expect_download() as event:
                    page.locator("#export").click()
                event.value.save_as(results / "browser_download_receipt.json")
                downloaded = json.loads((results / "browser_download_receipt.json").read_text())
                checks.append({"case": "receipt_download", "pass": downloaded["schema"] == "vsl-phone-readiness-1" and len(downloaded["rows"]) >= 7})
                checks.append({"case": "no_javascript_exceptions", "pass": not errors})
                page.screenshot(path=str(results / "browser_320px.png"), full_page=True)
                browser.close()
        finally:
            process.terminate()
            process.wait(timeout=10)
    receipt = {"scope": "desktop Chromium at 320px; no physical phone or Wi-Fi test", "checks": checks,
               "checks_total": len(checks), "checks_passed": sum(c["pass"] for c in checks), "javascript_errors": errors}
    (results / "browser_smoke_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if all(c["pass"] for c in checks) and len(checks) == 8 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-python", default=DEFAULT_PYTHON)
    raise SystemExit(main(parser.parse_args().server_python))
