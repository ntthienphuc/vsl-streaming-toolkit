"""Evaluate authorized, annotated recordings; the bundled example is synthetic."""
import argparse
import hashlib
import json
from pathlib import Path

from vsl_streaming.evaluation import evaluate_events, events_from_responses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", required=True)
    parser.add_argument("--predictions", required=True,
                        help="JSON object mapping recording ID to canonical events or replay receipt")
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    paths = [Path(args.annotations), Path(args.predictions)]
    documents = [json.loads(p.read_text(encoding="utf-8-sig")) for p in paths]
    if not isinstance(documents[1], dict):
        parser.error("predictions document must map recording IDs to events or receipts")
    predictions = {}
    for rid, value in documents[1].items():
        if isinstance(value, dict) and "responses" in value:
            value = events_from_responses(value)
        elif isinstance(value, list) and value and isinstance(value[0], dict) and "type" in value[0]:
            value = events_from_responses(value)
        predictions[rid] = value
    report = evaluate_events(documents[0], predictions, args.iou_threshold)
    report["inputs"] = {name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                        for name, path in zip(("annotations", "predictions"), paths)}
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    print(str(target))


if __name__ == "__main__":
    main()
