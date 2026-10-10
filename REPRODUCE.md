# Reproduce the public release

Run from a fresh checkout using Python 3.9+. Commands below use `python` and
`vsl-stream` from an activated virtual environment. Windows can instead use
`.venv\Scripts\python.exe` and `.venv\Scripts\vsl-stream.exe` directly.

```sh
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install ".[server,export,dev]"
python -m unittest discover -s tests -v
python -m build
vsl-stream demo --out demo_run
vsl-stream inspect --bundle demo_run/bundle
python tools/verify_websocket_install.py --bundle demo_run/bundle --config demo_run/server.json --frames demo_run/frames.json --batch-size 5 --out demo_run/tcp_receipt.json
vsl-stream serve --bundle demo_run/bundle --config demo_run/server.json
```

Open http://127.0.0.1:8000/, load `demo_run/frames.json` and replay. Expected labels:
`SYNTHETIC_NEGATIVE`, then `SYNTHETIC_POSITIVE`. The demo destination must not
already exist. Generated files are ignored by Git.

## Expected checks

- Public unit checks should pass. Optional video and owner-asset checks may skip when their dependencies or authorized inputs are absent; record each skip and its reason.
- The demo checks those two fixture labels and records three export parity probes.
- The TCP tool starts its own server on a temporary port and terminates it afterwards.
- It checks exact retry, new connection identities, agreement across two batch sizes,
  offline/WebSocket event agreement and zero active sessions after disconnect.
- It also writes per-session evidence beside the TCP receipt and checks model/
  configuration hashes, complete send records, retry deduplication and drained
  terminal state. Choose a new receipt path for each run to preserve the logs.
- `python -m pip check` reports no dependency conflicts.

To verify the actual built wheel, install the file listed in `dist/` into a new
virtual environment, with its `server` extra. Do not add `src/` to PYTHONPATH.
Run the TCP tool against the existing generated demo. Export-time PyTorch is not
needed in that server environment. CI performs tests against the installed wheel
and checks absence of PyTorch in a separate server-only environment.

`requirements-tested.txt` lists direct versions exercised on the original host;
it is not a transitive or cross-platform lock. CI records resolved environment
versions with the validation artifacts. Tests and fixture labels establish software
behavior, not sign recognition accuracy, field usability or Jetson performance.

## Version 0.2.0 capture and event tools

For the optional video path, use Python 3.11 and install `.[video]`. Follow
[VIDEO_CAPTURE.md](docs/VIDEO_CAPTURE.md) to obtain detector assets separately,
extract a new trace and validate its capture receipt during replay. Run
`python -m unittest discover -s tests -p test_capture.py -v` to check capture
contracts. Generated blank videos exercise decoding and missing detections;
they do not establish capture quality for signing participants.

Create a predictions JSON object mapping each recording ID to its replay
receipt or canonical event array. Evaluate it with independently prepared
annotations:

```sh
vsl-stream evaluate --annotations examples/event_annotations.json --predictions examples/event_predictions.json --out event_report.json
```

The bundled annotations are synthetic. Use [EVENT_EVALUATION.md](docs/EVENT_EVALUATION.md)
for research annotation, time alignment, split roles and metrics. Run
`python -m unittest discover -s tests -p test_evaluation.py -v` for the evaluator's
synthetic calculation checks.

The bundled predictions intentionally contain temporal and gloss errors; see
the guide for exact expected metrics. This command runs from a fresh checkout
without private data or a recognizer. For a real recording, supply new
independent annotations and its own predictions instead.

## Version 0.2.1 session evidence

Enable `serve --session-log-dir artifacts/device-test/server-logs` before a
phone campaign. Follow [SESSION_LOGGING.md](docs/SESSION_LOGGING.md) to retain
the whole server response sequence and check session completion. Local session
logs are not automatically public research assets. The client ACK ledger and
capture receipt remain necessary for a whole-trace parity claim.

Patch validation belongs to v0.2.1. The v0.2.0 native-migration and host software
receipts remain historical records and are not relabeled or extended by a new
build. Phone, natural-sign accuracy and performance Results remain prospective.

The [Android guide](docs/ANDROID_CLIENT.md) provides separate build, asset and
physical-device steps. The server package does not require Android tooling.
The browser only replays frame files, and does not extract camera landmarks.

## Native preprocessing migration

`tools/verify_native_profiles.py` compares the native SPOTER/SL-GCN contracts
against an authorized legacy adapter using supplied traces and models. It does
not download private inputs. Its output includes private bundle copies and must
remain outside public release assets unless redistribution is authorized.
Call it with `--help` for its required paths. The recorded migration comparison
contains 60 trace/model segment cases and 22 generated length/profile cases;
see [EVALUATION_SCOPE.md](docs/EVALUATION_SCOPE.md) for their interpretation.

The research capsule under `research/host-replay-20261009` remains a **v0.1.2**
study. Use its frozen instructions and versions to reproduce its timing table.
Do not assign those measurements to this release without a new run.
