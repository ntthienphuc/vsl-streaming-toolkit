"""Exercise a built Docker server image with the generated synthetic fixture."""
import argparse
import asyncio
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
from verify_websocket_install import replay


def check(image, demo):
    demo = demo.resolve()
    with socket.socket() as selection:
        selection.bind(("127.0.0.1", 0))
        port = selection.getsockname()[1]
    identifier = subprocess.check_output([
        "docker", "run", "--rm", "-d", "-p", "127.0.0.1:%d:8000" % port,
        "-v", "%s:/models:ro" % demo, "-v", "%s:/config:ro" % demo, image,
    ], text=True).strip()
    try:
        url = "http://127.0.0.1:%d/health" % port
        for _ in range(200):
            try:
                with urllib.request.urlopen(url, timeout=1) as result:
                    if json.load(result)["status"] == "ready":
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Container did not become ready")
        frames = json.loads((demo / "frames.json").read_text(encoding="utf-8"))
        network = asyncio.run(replay(port, frames, 5))
        labels = [event["prediction"]["label"] for event in network["events"]]
        if labels != ["SYNTHETIC_NEGATIVE", "SYNTHETIC_POSITIVE"]:
            raise RuntimeError("Unexpected fixture outputs: " + str(labels))
        for _ in range(30):
            with urllib.request.urlopen(url, timeout=1) as result:
                health = json.load(result)
            if health["active_sessions"] == 0:
                break
            time.sleep(0.05)
        if health["active_sessions"] != 0:
            raise RuntimeError("Container retained disconnected session")
        receipt = {"status": "passed", "scope": "synthetic container execution, not recognition accuracy",
                   "image": image, "fixture_labels_match": True, "exact_retry": True,
                   "events": len(labels), "active_sessions_after_disconnect": 0,
                   "server_version": health["version"]}
        (demo / "container_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(receipt))
    except Exception:
        subprocess.run(["docker", "logs", identifier], check=False)
        raise
    finally:
        subprocess.run(["docker", "stop", identifier], check=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--demo", type=Path, required=True)
    args = parser.parse_args()
    check(args.image, args.demo)
