# Release validation — 10 October 2026

`receipt.json` records the installed-wheel host checks for v0.2.0 and local Android compilation. Its archive digests bind the downloadable release files. The recognition models and participant inputs are not included. Historical host replay performance remains in the separate v0.1.2 capsule.

## Reproduce public checks

Create an environment, install the release with server/export/dev extras and CPU PyTorch as described in the root README, then run:

```sh
python -m unittest discover -s tests -v
python -m pip check
vsl-stream demo --out demo_run
python tools/verify_websocket_install.py --bundle demo_run/bundle --config demo_run/server.json --frames demo_run/frames.json --batch-size 5 --out demo_run/tcp_receipt.json
python -m venv .venv-server
python tools/check_server_only.py --venv .venv-server --demo demo_run
```

The server-only check expects exactly one wheel in `dist/`. Copy the selected release wheel there. It installs server extras in the supplied clean environment and verifies absence of PyTorch. The TCP check compares events excluding inference timing, reconnect identity, retries and cleanup.

For browser checks install Playwright and Chromium, then run `python tools/verify_browser.py --server-python PATH_TO_SERVER_PYTHON --bundle demo_run/bundle --frames demo_run/frames.json --config demo_run/server.json --out artifacts/browser-check`. Timeout scenarios shorten only the application test timers to 80 ms; production limits are 10 s and 30 s.

Android build and five transport tests are documented in `docs/ANDROID_CLIENT.md`. CI compilation intentionally omits detector assets. The local camera APK was built with downloaded assets and remains outside public release files pending asset redistribution review. No physical-phone run is reported.

## Interpretation

The Python suite ran 88 tests: 87 passed and one optional owner-source test was skipped. A separate native-profile campaign tested the actual supplied owner artifacts. Public fixtures are synthetic. A generated 12-frame blank MJPG file also exercised the actual CPU MediaPipe extractor, emitting six missing-pose observations. This is execution evidence, not landmark accuracy.

All timing fields from the small TCP diagnostics are omitted here because they are not a controlled performance campaign. Natural-sign boundary and gloss quality, Android/desktop extractor compatibility, real network behavior and physical-device performance remain separate measurements. Run the prospective measurement protocol before extending those claims.
