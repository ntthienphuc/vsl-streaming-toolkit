"""Fetch exact upstream MediaPipe task assets; weights are not stored in Git.

Review THIRD_PARTY.md and the upstream model documentation before use.
This downloader verifies identity, not ownership or fitness for a model task.
"""
import hashlib
from pathlib import Path
from urllib.request import urlopen

ASSETS = {
    "pose_landmarker_lite.task": (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
        "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a",
    ),
    "hand_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
        "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1",
    ),
}

def main():
    target = Path(__file__).parent / "app/src/main/assets"
    target.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in ASSETS.items():
        dest = target / name
        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == expected:
            print(f"Verified existing {name}")
            continue
        with urlopen(url, timeout=120) as response:
            data = response.read(30_000_001)
        if len(data) > 30_000_000 or hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f"Asset checksum/size mismatch: {name}; no file installed")
        staged = dest.with_suffix(".download")
        staged.write_bytes(data)
        staged.replace(dest)
        print(f"Downloaded and SHA-256 verified {name}")

if __name__ == "__main__":
    main()
