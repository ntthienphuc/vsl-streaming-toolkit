"""Replay JSON keypoint frames with acknowledgment-based flow control."""
import argparse
import asyncio
import json
from pathlib import Path
import websockets


async def run(url, frames, batch_size):
    if batch_size < 1:
        raise ValueError("batch-size must be positive")
    async with websockets.connect(url, max_size=2_000_000) as ws:
        ready = json.loads(await ws.recv())
        if ready["type"] != "ready":
            raise RuntimeError(ready)
        batch_size = min(batch_size, ready["settings"]["max_batch_frames"])
        results = []
        for start in range(0, len(frames), batch_size):
            await ws.send(json.dumps({"type": "frames", "request_id": "example-%d" % start,
                                      "frames": frames[start:start + batch_size],
                                      "flush": start + batch_size >= len(frames)}))
            result = json.loads(await ws.recv())
            results.append(result)
            if result["type"] == "error":
                raise RuntimeError(result)
        return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="ws://127.0.0.1:8000/v1/stream")
    p.add_argument("--frames", required=True)
    p.add_argument("--batch-size", type=int, default=5)
    args = p.parse_args()
    frames = json.loads(Path(args.frames).read_text(encoding="utf-8-sig"))
    print(json.dumps(asyncio.run(run(args.url, frames, args.batch_size)), indent=2, ensure_ascii=False))
