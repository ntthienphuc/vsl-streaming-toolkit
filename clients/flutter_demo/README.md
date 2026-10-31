# VSL Toolkit — minimal Flutter research client

A small, reproducible interface for VSL Streaming Toolkit. The default workflow uploads one video to the PC, preserving its original bytes for repeated extraction and replay. Optional live capture uses the existing Android library; canonical replay is available from Evidence. Technical details expand on demand, and the live preview preserves the upright source in a 3:4 portrait frame.

| Input | Extraction | Transport and evidence |
| --- | --- | --- |
| Live | Android MediaPipe Tasks through the existing Kotlin capture library | Canonical frames over WebSocket; receipt and admitted-frame JSONL exports |
| Canonical | None: preserves an existing JSONL trace | Native replay through the same stream client |
| Video → PC | PC extractor reported by the upload service | One multipart video upload; extraction and replay artifacts with SHA-256 hashes |

Flutter is the interface, not a new landmark extractor. Android Tasks and PC extraction remain distinct profiles until a paired same-video comparison establishes compatibility. Matching point counts alone is insufficient. Model scores are displayed without a confidence threshold; they are not measured accuracy. Empty responses and rejected events clear the current prediction.

## Build and test

Tested toolchain: Flutter 3.44 / Dart 3.12, Android SDK 36, Java 21 (the Android Gradle plugin requires Java 17 or newer), and the adjacent native `clients/android/stream-client` module. Live capture also requires the detector assets documented in the Android client. From this directory:

```powershell
flutter pub get
flutter analyze
flutter test
flutter build apk --debug
```

The Android implementation is supplied in `android/`. Native channels are `vsl_streaming/bridge`, `vsl_streaming/events` and platform view `vsl_streaming/camera`. Model asset integrity and licensing follow the existing Android client documentation; Flutter introduces no bundled mascot, custom font, model or prerecorded result.

## Connect

On Windows, the helper starts both loopback services, checks their health, creates
USB forwarding for the selected phone, and opens the installed Flutter client.
Run from the repository root after installing the optional dependencies described
in [Video demo](../../docs/VIDEO_DEMO.md):

```powershell
.\tools\run_flutter_demo.ps1 -Bundle .\path\to\bundle -Config .\path\to\server.json -Phone -DeviceSerial YOUR_SERIAL
```

The output prints a manifest path and an exact stop command. Stop with that
manifest; it identifies the processes and USB forwarding created by this run.
Occupied server ports cause a preflight failure without stopping other services.
Each launch uses a new evidence directory. The bundle must already contain its
model, labels and preprocessing profile; the launcher does not download a model.

Start the toolkit WebSocket service and optional PC video service on the host. With a USB-connected Android device:

```powershell
adb reverse tcp:18081 tcp:18081
adb reverse tcp:18082 tcp:18082
```

Defaults are `ws://127.0.0.1:18081/v1/stream` and `http://127.0.0.1:18082`. For a local network connection, enter the host address in Settings. Inspect the selected service before starting. The Android debug build permits local HTTP/WebSocket transport; use a trusted development network.

## Use

For a first reviewer check, create the self-contained synthetic bundle and
canonical frames using the root README quickstart. It requires no detector
assets or participant video. Serialize the generated array as JSONL without
changing the observations, then copy it to the phone:

```powershell
python -c 'import json; from pathlib import Path; p=Path("my_demo"); frames=json.loads((p/"frames.json").read_text()); (p/"frames.jsonl").write_text("".join(json.dumps(f, separators=(",", ":"))+"\n" for f in frames), encoding="utf-8")'
adb push my_demo/frames.jsonl /sdcard/Download/vsl-synthetic.jsonl
adb reverse tcp:18081 tcp:8000
```

With the quickstart server running on its default port 8000, keep the app
WebSocket endpoint at port 18081 and use **Evidence → Replay trace**.
Expect the quickstart's synthetic labels in order; they are an integration
fixture, not natural-sign predictions. This temporary port mapping is for the
quickstart only. The two-service launcher uses host ports 18081 and 18082.

- **Session / Live:** frame face, shoulders, elbows and both hands; start; perform the planned motions; stop and wait for drain/flush completion. Stop stays available when switching tabs during a running session.
- **Evidence → Replay trace:** choose a canonical JSONL file, then start replay. Replay is acknowledgment-paced, not a claim about original camera FPS.
- **Session / Video → PC:** record or select a video, review rotation, input mirroring, target sampling FPS and timestamp mode in Settings, then upload. Requests are sequential, with a 20-minute response deadline. A client timeout does not establish that the host job stopped; inspect the host before retrying.
- **Evidence:** inspect transport counters and expandable diagnostics. Native artifacts and PC runs are identified separately: changing inputs retains previous artifacts. After live capture, export both receipt JSON and canonical JSONL, waiting for each export to finish. After canonical replay, export the receipt and retain the original selected trace. PC artifacts retain their hashes and copyable resolved URLs; the last completed PC run remains available until a newer run completes. Native receipts retain up to 500 responses and disclose omitted counts; keep the complete server log for full event comparisons.

On Android, selecting or recording a video reads its stored dimensions, duration, byte count and rotation without changing the file. Rotation defaults to the container's clockwise orientation; review or override it in Settings. If metadata cannot be read, the app explicitly asks you to check rotation. The PC extractor disables decoder autorotation and applies the submitted angle once. A portrait recording can therefore have landscape stored dimensions plus a 90/270-degree tag.

Known files above the PC limit are blocked before upload (100 MiB by default; Inspect reads a custom server limit). Start with a 3-5-second clip, since camera bitrate can make even short videos large. The original file is retained unchanged. Video timestamp values are exactly `pos-msec` (source presentation time) and `frame-index` (decoded frame index / video FPS). These settings apply to uploaded video; native capture records its own orientation and monotonic clock.

The PC interface uses `GET /health` and `POST /v1/video` with multipart fields `video`, `rotate`, `input_mirrored`, `target_fps`, `timestamp_mode`. A completed response provides `run_id`, `extractor_profile`, frame counts, events, replay status and artifact name/URL/SHA-256/byte count. `no_segments` is displayed honestly and does not invent a translation.

This client does not establish natural-sign accuracy, extractor equivalence or real-time performance. Those need the planned controlled capture and evaluation evidence.

This is one client with a common evidence contract. Video → PC is the default because the exact original input can be replayed; Live demonstrates the optional camera/transport integration. Neither Tasks extractor is automatically equivalent to the historical Holistic training pipeline. See the capture compatibility document before combining their results.

## Android test build

The package is `org.vslstream.flutterdemo`, separate from the Kotlin reference
client `org.vslstream.demo`. Installing the test APK keeps the reference app.
The test build is debug-signed and is not a Store or publication release asset.
For release builds, configure your own signing key and use HTTPS/WSS endpoints.
Native bridge limits and lifecycle details are in [BRIDGE.md](android/BRIDGE.md).
See [Capture compatibility](../../docs/FLUTTER_CAPTURE_COMPATIBILITY.md) before
combining results from live Android and uploaded PC video.
