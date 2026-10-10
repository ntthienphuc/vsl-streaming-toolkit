# Offline video capture and provenance

The optional video adapter converts an authorized local video to canonical
pose/hand frames. This is a reproducible source of replay input, not a new
recognition model or evidence of Android detector equivalence.

## Installation and extraction

Use Python 3.11 for the tested optional capture environment. The base library
supports Python 3.9 and later; availability of MediaPipe wheels is platform
dependent. Keep capture separate from the lean ONNX server when deploying.

```bash
python -m pip install ".[video]"
vsl-stream extract-video --video sample.mp4 --pose-model pose_landmarker_lite.task --hand-model hand_landmarker.task --out capture/frames.json --target-fps 15
vsl-stream replay --bundle local_bundles/recognizer --frames capture/frames.json --capture-receipt capture/frames.capture.json --config server.json --receipt replay.json
```

Obtain the Tasks assets from the official [pose](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker#models)
and [hand](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker#models)
model pages, and retain the applicable model terms and download URL. Assets are
explicit inputs and are not included in the Python package. Do not infer rights
to a video, model or participant trace from this repository's source license.

## Defined capture policy

The `desktop-mediapipe-tasks-pose-hands-v1` profile uses synchronous Tasks VIDEO
mode with a CPU delegate, one pose and up to two hands. Detection, presence and
tracking thresholds are 0.5. Pose coordinates contain x, y, z and visibility;
hand coordinates use visibility 1, a placeholder rather than a measured score.
Missing detections remain null. There is no hand cache and no deletion of
missing-pose frames.

Hand assignment first uses the closest pose wrist with visibility at least 0.5
when squared normalized image distance is at most 0.08. Otherwise it uses the
detector's handedness. A collision retains the closest wrist candidate or the
first handedness-only candidate. This heuristic does not establish person
tracking; use single-person videos and assess crossed/occluded hands separately.

The default timestamp source is OpenCV's decoded `POS_MSEC`. Non-increasing or
invalid timestamps cause extraction to fail. `--timestamp-mode frame-index`
is an explicit fallback using frame index divided by reported FPS. Those
synthetic times cannot substantiate variable-frame-rate or capture latency
claims. Time-based sampling retains the actual selected timestamps. Detector
times are rounded to integer milliseconds; collisions fail rather than being
silently reordered.

Decoder auto-rotation is disabled when the backend supports it and that outcome
is recorded. `--rotate 90` applies a further clockwise rotation. Declare a
mirrored source with `--input-mirrored` to undo its horizontal mirror before
inference. Visually verify orientation for the selected decoder backend;
metadata handling varies by codec. The adapter does not guess source mirroring.

## Receipts and limits

The adjacent `.capture.json` records source-video, detector-asset and serialized
frame SHA-256 values, selected source indices, decoder/library versions,
timestamp and orientation policies, sampling counts and missing-pose counts.
The files must be new outputs. A decoding limit or declared frame-count
truncation fails without writing a completed trace. OpenCV cannot reliably
distinguish every codec failure from EOF; retain decoder diagnostics and inspect
the video when its reported frame count is unavailable or inaccurate.

`replay --capture-receipt` checks schema and the exact frame-file hash. It does
not certify that this extractor matches a checkpoint's training extractor.
Desktop and Android capture profiles deliberately have different identifiers.
The native tensor profiles lock landmark ordering and numerical transforms;
capture compatibility still requires a separately recorded comparison.

For a recognition study, retain authorized original videos and the sidecars,
annotate word intervals on the source clock, freeze source-group split roles,
and use [event evaluation](EVENT_EVALUATION.md). Synthetic blank-video checks
exercise decoding and failure handling only.
