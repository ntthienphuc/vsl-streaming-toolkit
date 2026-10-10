# Android integration and device evaluation

The Android client is an optional integration example. It contains a reusable `stream-client` module and a minimal `app` module; the Python library and WebSocket server remain usable independently. This is a new native Kotlin client, not a repackaging of the historical Flutter application. The v0.2.1 Android extractor has not been validated on a physical phone.

## Reproduce the build

See [client build instructions](../clients/android/README.md). Build with JDK 17, SDK 36, Gradle 8.14, Android Gradle Plugin 8.11.1, and Kotlin 2.2.20. The app supports API 26 and above. Run the JVM transport tests before installing the APK. Downloaded detector assets are checksum-pinned and excluded from Git; the CI build omits them and is compile/replay-only.

From the repository root, install the Python server dependencies and start a validated bundle:
```sh
python -m pip install '.[server]'
vsl-stream serve --bundle /path/to/bundle --host 0.0.0.0 --port 8000
adb reverse tcp:8000 tcp:8000
adb install -r clients/android/app/build/outputs/apk/debug/app-debug.apk
```

Use `ws://127.0.0.1:8000/v1/stream` over USB reverse, `ws://10.0.2.2:8000/v1/stream` in an emulator, or the host LAN address. Debug builds permit cleartext development traffic; release builds require WSS. Configure authentication and network access outside this research example before exposing a server.

## Capture contract

Profile `android-mediapipe-tasks-pose-hands-v1` uses MediaPipe Tasks Vision 0.10.26.1 with CPU VIDEO mode, one pose and at most two hands. Detection, presence and tracking thresholds are 0.5. Coordinates are normalized, unclamped x/y/z/visibility. Hand visibility defaults to 1 when absent; it is not calibrated confidence. Missing landmarks remain null and are never replaced by cached hands.

CameraX rotates pixels using ImageProxy rotation metadata. The front preview is mirrored; inference pixels are unmirrored. Hand assignment greedily matches hand centroids to visible pose wrists within squared normalized distance 0.08, then uses Tasks handedness verbatim for unmatched hands. This differs from the desktop wrist-based association and must not be described as extractor parity.

Timestamps come from `SystemClock.elapsedRealtimeNanos` at analyzer arrival. Millisecond ties advance by one millisecond and are counted. This is neither a sensor exposure clock nor a clock synchronized with the server. The 1-30 FPS control is a target admission rate. CameraX KEEP_ONLY_LATEST may replace upstream frames without exposing their count; diagnostics report this as unknown, not zero.
## Transport and receipts

The transport has a 120-frame queue, at most one outstanding request, batches of at most five frames subject to advertised server limits, and a 30-second request timeout. Admission preserves source sequence numbers and timestamps, including gaps from dropped offers. Stop immediately wakes a blocked replay producer, drains accepted frames, waits for flush acknowledgment, and then requests socket closure. Disconnects never trigger transparent replay into a new session. Unacknowledged frames submitted to the WebSocket remain explicitly uncertain; frames that fail local size checks before submission are aborted, not uncertain. A matching request ID alone is insufficient: the result must contain an events array and state object.

Camera export writes only frames admitted to the transport queue as UTF-8 JSONL. Its receipt binds exact file bytes by SHA-256 and records detector asset hashes, software versions, coordinate policy, clock policy, processed/admitted counts, queue drops, acknowledged/rejected/uncertain frames, and flush completion. It also preserves the server ready response and separates `source_failure` from transport failure: a successful flush does not erase a camera, replay or file-writing failure. Check `trace_matches_admitted_frames`, the byte hash and both ledgers before comparing offline replay with server responses. Admitted does not mean acknowledged. File replay is always marked `replay_input_unspecified` and does not import a capture sidecar; retain the original sidecar separately. Replay diagnostics are not a capture provenance certificate.

The `android_client` object records app version/build and device model, manufacturer, Android release and API level for both replay and capture. Record the installed APK SHA-256 separately. At terminal completion, `queued` and `in_flight` must be zero, and `enqueued` must equal acknowledged + server-rejected + aborted + uncertain frames. Successful inference is a separate event-level outcome; acknowledged input may produce rejected inference events.

The response log is capped at 500 entries and records omissions. Export full server-side responses for longer evaluations. Input files and captured traces are limited to 20 MiB; capture stops before admitting a frame that would exceed this replay limit. Longer experiments need explicitly planned session boundaries. Each camera session uses a distinct temporary cache file, and export snapshots are bound when the picker opens. Export runs off the UI thread, and I/O errors remain visible; a failed destination may contain partial bytes and must be exported again. Cache files are not permanent storage, so export the trace and receipt before starting another session or leaving the app. The example has no account system, persistent background camera service, automatic reconnection, on-device recognizer, or sentence translation. Camera pixels remain local; landmarks and gloss results cross the configured network connection.

## Physical-device acceptance sequence

1. Record phone model, Android version, APK SHA-256, server commit, bundle hashes, ordered labels, configuration, detector hashes, and connection route. Keep source permission and annotation records with the experiment.
2. Replay a fixed synthetic trace from the phone. Compare events and gloss order with host replay using exactly the same bundle and segmentation settings. Confirm zero omitted responses, drained queue, acknowledged flush and server session cleanup.
3. Exercise denied camera permission, unavailable front camera, missing/corrupt detector assets, invalid file ordering, wrong endpoint, server rejection, and network disconnect. Verify visible failure and consistent final ledgers without hidden fallback.
4. Capture separate left/right hand movement, crossed hands, missing hands, missing pose, rotations and lighting changes. Visually verify anatomical assignment and normalization. Schema compatibility alone does not establish compatibility with recognition training.
5. Export each captured JSONL and its final receipt. Replay the identical admitted trace offline, accounting for transport rejection or uncertainty before expecting parity. Annotate natural signing independently and report boundary misses, extra segments, gloss errors and rejection rates.
6. Measure extraction duration, admitted FPS, queue loss, round-trip latency and total user-observed delay separately. Repeat sustained sessions and interruption/resume tests; report device temperature, power mode and network. Compare models only with matched input and settings.

These are prospective device checks. JVM tests cover bounded admission, invalid ordering, drain/flush ordering, disconnect uncertainty and response correlation. They do not replace physical-device or human-signing evaluation. Historical host replay results belong to their frozen release and must not be relabeled as Android measurements.
