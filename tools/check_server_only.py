"""Install the built wheel with server extras into an existing clean venv."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


def run(venv, demo):
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    wheels = list(Path("dist").glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Expected exactly one built wheel")
    subprocess.check_call([str(python), "-m", "pip", "install", str(wheels[0].resolve()) + "[server]"])
    subprocess.check_call([str(python), "-m", "pip", "check"])
    subprocess.check_call([str(python), "-c", "import importlib.util; assert importlib.util.find_spec('torch') is None, 'Server must not require Torch'"])
    receipt = demo / "server_only_receipt.json"
    subprocess.check_call([str(python), "tools/verify_websocket_install.py", "--bundle", str(demo / "bundle"),
                           "--config", str(demo / "server.json"), "--frames", str(demo / "frames.json"),
                           "--batch-size", "5", "--out", str(receipt)])
    result = json.loads(receipt.read_text(encoding="utf-8"))
    if result["status"] != "passed" or result["server_has_torch"]:
        raise RuntimeError("Server-only verification failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--demo", type=Path, required=True)
    args = parser.parse_args()
    run(args.venv, args.demo)
