# Native bridge contract

The host is `org.vslstream.flutterdemo.MainActivity`, a `FlutterFragmentActivity`.
It links the existing `clients/android/stream-client` Gradle module directly.
`LandmarkCapture` and `StreamSession` are not copied or modified. The capture
profile remains `android-mediapipe-tasks-pose-hands-v1`; it is distinct from
desktop extraction and does not establish model compatibility.

## Channels and view

- Methods: `vsl_streaming/bridge`.
- Events: `vsl_streaming/events`. Each event is a map with a `type` string.
- Platform view: `vsl_streaming/camera`, a CameraX `PreviewView` using the front
  camera and a fitted preview. Creating the view does not request permission
  or begin capture.

| Method | Arguments | Return |
| --- | --- | --- |
| `inspect` | `endpoint` | Parsed `/v1/config` map; also emits `config` |
| `inspectVideo` | local cached file `path` from `image_picker` | Integer `width`, `height`, `rotation`, `duration_ms`, `bytes` |
| `startLive` | `endpoint`, integer `targetFps` (1–30) | Current snapshot; permission may still be pending |
| `stop` | none | Current snapshot; drain/flush completes asynchronously |
| `selectReplay` | none | null; native SAF selection emits `selection` |
| `startReplay` | `endpoint` | Current snapshot |
| `exportReceipt` | none | null; native SAF picker and export events |
| `exportFrames` | none | null; native SAF picker and export events |
| `snapshot` | none | Current snapshot |

Endpoints must be `ws://` or `wss://` URLs ending in `/v1/stream` without
credentials, query parameters or fragments. Debug builds allow cleartext LAN;
release builds require WSS. The scaffold's debug signing configuration is for
local demonstration, not a production signing setup.

Snapshots contain `phase`, `message`, `active`, `previewReady`, `replayName`,
`selecting`, `exporting`, `hasReceipt`, `hasFrames`, and `diagnostics`.
They restore the current activity's state when Dart reconnects; no session is
restored after Android process death.

`inspectVideo` reads metadata with Android `MediaMetadataRetriever` on the IO
executor and releases the retriever before completing the method on the UI
thread. It does not decode/transform pixels, change capture settings, or modify
the file. Missing/unreadable/empty files, missing required metadata, invalid
dimensions/duration or unsupported rotation return `video_inspect_failed`;
rotation is never silently guessed. Width and height describe stored video
dimensions; the caller can swap the displayed upright dimensions for 90/270
degrees. Duration is milliseconds and bytes is the current local file length.

Android's [retriever metadata contract](https://github.com/aosp-mirror/platform_frameworks_base/blob/master/media/java/android/media/MediaMetadataRetriever.java)
defines rotation values 0, 90, 180 and 270 degrees. Its
[video orientation contract](https://github.com/aosp-mirror/platform_frameworks_base/blob/master/media/java/android/media/MediaMuxer.java)
defines the composition-matrix playback rotation clockwise, without rotating
stored pixels. Pass that rotation to the PC extraction setting when decoder
autorotation is disabled; do not apply it twice. Metadata inspection does not
validate the visual correctness of a file's orientation tag.

## Events

- `status`: `phase`, `message`, `active`. Phases are `idle`,
  `awaiting_permission`, `connecting`, `capturing`, `replaying`, `stopping`,
  `completed`, or `failed`.
- `cameraPreviewReady`: `ready` means the native preview view exists, not that
  the camera or model is validated or a stream handshake has succeeded.
- `config`, `ready`, `result`, `diagnostics`: `data` contains a decoded map.
  `ready` is exclusively the actual WebSocket handshake. `result` preserves
  the complete protocol response, including empty and rejected events.
  `diagnostics` additionally has `finalized`: export is available only after
  finalization, not merely because transport has become terminal.
- `selection`: `name`, `selecting`; completion also includes `cancelled`.
- `export`: `kind` (`receipt` or `frames`), `status` (`choosing`, `writing`,
  `completed`, `cancelled`, `failed`), and `message`.

Model predictions use `label`, `confidence`, and `top_k`; they are not the old
app's `gloss`/`score` schema. The bridge performs no score filtering, speech,
transparent retry or HTTP inference fallback.

## Evidence and lifecycle

Live diagnostics expose transport counters. After terminal finalization,
diagnostics contain the stable receipt with capture provenance, exact admitted
JSONL SHA-256, source failure, server handshake and response history. The
transport ledger is the unchanged native module's ledger, including admitted,
acknowledged, dropped, rejected, aborted and uncertain frames. Flush success
does not establish successful inference, complete source capture or recognition
accuracy. Completion reports socket closure requested, not observed.

Replay input and captured JSONL are limited to 20 MiB; responses are capped at
500 entries with `response_log_omitted`. Replay is acknowledgement paced and
uses `replay_input_unspecified` provenance, without importing a sidecar.

Export opens separate SAF destinations named `vsl-capture-receipt.json` and
`vsl-capture.jsonl`. The selected final artifact is frozen before its picker
opens; session starts are blocked until selection/export completes or cancels.
Errors may leave an incomplete destination and are surfaced explicitly.
Temporary traces are not durable experiment storage: export before another
session or leaving the activity.

Backgrounding the activity or disposing the live preview stops admission,
drains accepted frames and requests flush. The source executor drains before
the detector closes and the final trace hash/receipt are published.

## Assets

The host pins AGP 8.11.1, Kotlin 2.2.20 and Gradle 8.14 (with the native
wrapper's distribution SHA-256). These versions match the unchanged native
module; the initial Flutter scaffold's AGP 9/Kotlin 2.3 combination rejected
that module's existing Gradle DSL. This host does not migrate the baseline.

The app's asset source set points to `clients/android/app/src/main/assets`.
Run the existing `clients/android/fetch_assets.py` to obtain the two pinned
MediaPipe task files. Their SHA-256 is checked by `LandmarkCapture` at startup.
Review `clients/android/THIRD_PARTY.md` before redistribution. A build without
the task assets can compile but cannot perform live extraction.
