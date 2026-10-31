# Sequential video demo

This optional local HTTP adapter lets a mobile client select or record a video,
upload it to a PC, and review predictions from the toolkit's existing extractor
and streaming replay. It preserves the original video, canonical observations,
capture receipt, and replay receipt in a separate directory for each request.

The desktop extractor profile is `desktop-mediapipe-tasks-pose-hands-v1`.
It uses **desktop MediaPipe Tasks Pose + Hands**, not legacy MediaPipe Holistic.
Using a PC does not by itself restore the training extractor. Compatibility with
training landmarks and parity with Android capture remain unverified. Flutter is
the user interface in this route; it does not extract or convert landmarks.

| Route | Extraction | Transport and interpretation |
| --- | --- | --- |
| Uploaded video | PC MediaPipe Tasks, with its own receipt | One complete video per HTTP request; existing toolkit replay and the selected model/configuration |
| Android live capture | Android capture profile | Canonical observations over the existing WebSocket protocol |

Both routes can use the same model bundle and segmentation configuration. Their
different capture profiles must remain visible in saved evidence. Matching point
counts, JSON schemas, or model predictions does not establish detector equivalence.

## Install and start

From the repository root, install the optional dependencies in a Python 3.11
environment. The `video` extra pins the tested desktop detector dependencies.

```powershell
python -m pip install -e ".[server,video]" "python-multipart>=0.0.20,<1"
python tools/serve_video_demo.py --bundle local_bundles/my_model --pose-model artifacts/models/pose_landmarker_lite.task --hand-model artifacts/models/hand_landmarker.task --output-dir artifacts/video-demo --config my_server.json --host 127.0.0.1 --port 18082
```

Supply your actual bundle and detector assets; the adapter does not download or
redistribute model assets, videos, or participant data. `--config` is optional
and uses the toolkit's default settings when omitted. A supplied JSON config is
loaded once at startup and passed unchanged to replay. The bundle is validated
at startup; the runtime and hash-bound capture checks run for each video.

Keep this unauthenticated demo on the local machine or an explicitly controlled
test network. The default binding is loopback. It is not a public upload service.
On Windows, [run_flutter_demo.ps1](../tools/run_flutter_demo.ps1) starts both
loopback servers with separate logs and a process manifest. For an already
installed phone app, run `./tools/run_flutter_demo.ps1 -Bundle local_bundles/my_model -Phone`.
Use the printed `-StopManifest` command to stop only that launch's recorded processes
and USB forwards. Existing listeners are left running and cause startup to stop.
For an Android phone connected by USB:

```powershell
adb reverse tcp:18082 tcp:18082
```

Then use `http://127.0.0.1:18082` as the phone's video endpoint. Live WebSocket
capture remains on its separately configured server port. Remove only this
forward when finished: `adb reverse --remove tcp:18082`.

## HTTP contract

`GET /health` returns `status` (`ready` or `busy`), `active_jobs`,
`extractor_profile`, effective toolkit `settings`, explicit `capture_defaults`,
and `capabilities` including the upload and decode bounds. This is an adapter
readiness response, not evidence of valid landmarks or model accuracy.

`POST /v1/video` accepts `multipart/form-data`:

| Field | Values | Default |
| --- | --- | --- |
| `video` | Exactly one nonempty file; `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, `.m4v` | Required |
| `rotate` | `0`, `90`, `180`, `270`; explicit clockwise degrees | `0` |
| `input_mirrored` | Literal `true` or `false`; `true` applies a horizontal flip before extraction | `false` |
| `target_fps` | Finite number greater than 0 and at most 120 | `15` |
| `timestamp_mode` | `pos-msec` or `frame-index` | `pos-msec` |

Client filenames are metadata only. Files are saved as `original.<suffix>` in
server-generated UUID directories; client paths never determine destination paths.
One request can be active at a time, including upload, extraction, and replay.
A second request receives `409` and `Retry-After: 2` without entering a queue.
The client should keep a visible processing state and use an appropriate timeout
for the clip's duration. If a response is lost, inspect saved run directories
before resubmitting; a retry creates a new run rather than overwriting evidence.
Cancellation during native extraction or replay is reported after that worker
finishes: the server keeps its single-job gate until no worker can change the
run's files. The phone's HTTP timeout does not terminate processing on the PC.

The upload limit is 100 MiB by default, configurable through
`--max-upload-mib`. Streaming multipart parsing bounds video bytes, field/header
sizes, part count, and total request overhead. The decode bound is 100,000 frames,
configurable through `--max-frames`. Use short pilot clips initially; this is a
sequential demonstration, not a throughput benchmark or a background job queue.

```powershell
curl.exe --fail-with-body -F "video=@pilot.mp4" -F "rotate=0" -F "input_mirrored=false" -F "target_fps=15" -F "timestamp_mode=pos-msec" http://127.0.0.1:18082/v1/video
```

Successful JSON has this shape; identifiers, counts, hashes, and events below are
placeholders, not research results:

```json
{
  "status": "completed",
  "run_id": "a-server-generated-uuid",
  "extractor_profile": "desktop-mediapipe-tasks-pose-hands-v1",
  "decoded_frames": 90,
  "emitted_frames": 45,
  "events": [],
  "replay_status": "no_segments",
  "artifacts": [
    {"name": "frames.json", "url": "/v1/runs/a-server-generated-uuid/frames.json", "sha256": "64-hex-characters", "bytes": 1234}
  ],
  "scope": "The returned scope describes capture and accuracy limitations."
}
```

`events` are the toolkit's actual ordered events. `replay_status` is `passed`,
`no_segments`, or `failed`. `no_segments` is a valid completed extraction/replay
with no segment emitted; it must not be displayed as a confident translation.
`passed` means replay produced predicted segments without replay rejection or
protocol error. It does not mean their labels are correct.

Status codes:

- `200`: Extraction and replay completed, including `no_segments`.
- `400`: Invalid/missing multipart data, parameters, suffix, or truncated upload.
- `409`: Another request is uploading or processing; no new run was created.
- `413`: Upload bound exceeded; the bounded partial video and failure receipt are retained.
- `422`: Extraction or replay failed, or replay rejected a segment. Available
  original/intermediate files and failure details are retained with the `run_id`.

Failure responses include `status: "failed"`, `run_id`, `stage`, and `artifacts`
when available. Exception failures additionally identify `error_type` and `error`.
Replay rejection responses retain `events` and `replay_status: "failed"`.
Do not automatically retry with different rotation, mirroring, timestamps,
thresholds, or sampling to conceal a failed interpretation.

`GET /v1/runs/<uuid>/<name>` downloads only allowlisted artifacts from a completed
or failed run. Each response includes `X-Content-SHA256`; compare it with the
artifact manifest and downloaded bytes. Allowed files are:

- `original.<suffix>` or, for an incomplete upload, `upload.partial`;
- `request.json`, recording actual input hash, declared parameters, and settings;
- `frames.json`, a JSON array of canonical observations;
- `frames.capture.json`, the extractor's hash-bound capture provenance;
- `replay.json`, the toolkit's model/configuration/capture-bound replay receipt;
- `failure.json`, when applicable.

Original video bytes are saved unchanged. Existing run directories and receipts
are never reused or overwritten. Review directory sizes and manage retained
participant data intentionally; the demo does not automatically expire evidence.

## Coordinate and clock interpretation

`rotate` applies to decoder output after requesting that OpenCV disable automatic
orientation. The receipt records whether the decoder accepted that request.
It also records whether the input was declared mirrored. Inspect orientation on
a known asymmetric sample and review `decoder_auto_rotation_disabled` before
claiming coordinate consistency; the adapter never silently chooses corrections.

Default `pos-msec` preserves decoder timestamps and rejects non-increasing time.
The explicit `frame-index` mode synthesizes timestamps from the decoder's reported
FPS; it is not evidence of original variable-frame-rate timing. Actual decoded
and emitted counts and source indices are saved in the capture receipt. Missing
pose or hands remain null observations; successful extraction can still contain
no useful landmarks, so examine detection presence before recognition evaluation.

Hand assignment uses the desktop extractor's documented visible-pose-wrist then
detector-handedness heuristic. This adapter adds no landmark conversion, cache,
index remapping, or claim that Tasks landmarks reproduce Holistic output. A paired
same-video comparison and labeled pilot remain separate validation work.

## Adapter tests

The phone is not required to reproduce inference from a saved run. Keep the same
bundle and use the exact `settings` object saved in `request.json` as the server
config. Choose a new receipt filename because the replay CLI can replace that file:

```powershell
python -m vsl_streaming.cli inspect --bundle local_bundles/my_model
python -m vsl_streaming.cli replay --bundle local_bundles/my_model --frames artifacts/video-demo/RUN_ID/frames.json --capture-receipt artifacts/video-demo/RUN_ID/frames.capture.json --config my_server.json --receipt artifacts/video-demo/RUN_ID/independent-replay.json
```

Use `--batch-size` no greater than `max_batch_frames` (the adapter uses the smaller
of 30 and that configured limit). Compare model/bundle/input/capture hashes and
settings, then ordered events excluding only measured `inference_ms`. The CLI
returns exit code 2 for `no_segments`; inspect its status instead of treating
that exit code as a detector failure. To reproduce extraction too, use
`extract-video` with the preserved original, the same detector asset hashes,
software versions, and the explicit parameters in `request.json`.

```powershell
python -m pip install -e ".[server,dev]" "python-multipart>=0.0.20,<1"
python -m unittest discover -s tests -p test_video_demo.py -v
```

The tests inject extraction/replay hooks to exercise bounds, truncated input,
parameter validation, concurrent busy rejection, filename/path isolation, hash
verification, error preservation, and forwarding of actual configuration. They
do not exercise MediaPipe inference. A real video smoke test must separately
validate decoder/detector dependencies, content presence, and replay receipts.
