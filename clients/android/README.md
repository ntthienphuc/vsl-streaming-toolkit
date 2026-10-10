# Android capture and replay example

A thin Android integration for VSL Streaming Toolkit. The reusable `stream-client` module extracts canonical landmarks and sends them to the Python WebSocket server; `app` provides a small camera/file-replay interface. Recognition and segmentation run on the server.

## Build

Use JDK 17, Android SDK 36, and the checked-in Gradle 8.14 wrapper. The minimum Android version is 8.0 (API 26).

```sh
python fetch_assets.py
./gradlew :stream-client:testDebugUnitTest :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

On Windows use `gradlew.bat`. `fetch_assets.py` downloads two pinned upstream MediaPipe task files and verifies SHA-256. Read [third-party terms](THIRD_PARTY.md) before redistributing assets. Weights are excluded from Git. Without this download the APK compiles and supports file replay, but camera initialization fails with an explicit missing-asset error. CI builds that omit the download are compile/replay artifacts, not camera-ready packages.

## Connect

Start the toolkit server with a validated model bundle. For a USB-connected physical phone use `adb reverse tcp:8000 tcp:8000` and enter `ws://127.0.0.1:8000/v1/stream`. For the Android emulator use `ws://10.0.2.2:8000/v1/stream`. A LAN connection requires a reachable server address and port. Debug builds allow cleartext traffic for local testing; release builds require WSS.

Choose a canonical JSON/JSONL trace to test transport before enabling the front camera. Stop drains the bounded queue, waits for the flush response, then closes the connection. Export diagnostics and the admitted camera frames after completion. File replay preserves timestamps but is acknowledgment-paced rather than real-time playback.

See the [complete integration and physical-device test plan](../../docs/ANDROID_CLIENT.md). JVM transport tests and a successful APK build do not establish camera correctness, device performance, recognition accuracy, or compatibility with the historical Android extractor.
