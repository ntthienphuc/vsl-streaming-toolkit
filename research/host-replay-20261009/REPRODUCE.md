# Host replay study and phone preparation — 9 October 2026

This authored study capsule evaluates installed VSL Streaming Toolkit 0.1.2.
The runtime is frozen at f2410017a5273ecf3158f7971f31c4b484d2e9dd, not at whichever
main branch a reader has checked out. Study tools are frozen separately by tag
study-20261009. Toolkit source and the authored tools are MIT.

## What was measured

Three recorded keypoint files contain 1,033, 998 and 999 frames. Default signing-space
segmentation produced ten segments per file. All 30 batch-fragmentation checks
passed across signing-space/fixed-window modes and chunks of 1/4/19/31/120 frames.
Each owner-provided SPOTER and SL-GCN ONNX model produced the same ordered top
three as its direct owner runtime on all 30 segments. Both paths use the same
owner preprocessing; this is an integration comparison, not an independent
validation of the transform, export or recognition accuracy.

The CPU loopback load study used 31-frame acknowledged requests, 1/4/8 concurrent
sessions, three files and two repeated waves per condition. Across both backends:
36 measured waves, 156 connections, 5,200 requests and 1,560 predicted events.
Every event matched offline replay; no measured request error or segment reject
occurred; active sessions returned to zero after every wave. These unpaced tests
exclude camera/extractor cost. Timing repeats are not independent signs or people.

The evidence directory includes raw numeric timing observations and resources,
pooled load summaries, exact runtime/input/model identities, and synthetic/browser
checks. It excludes class strings, model weights, raw human landmarks and owner
source paths. The private receipt hash identifies the original full receipt but
does not make that receipt publicly available.

## Public reproduction

Use a clean Python 3.11 environment for the measured toolchain; Python >=3.9 is
the package contract. From a checkout containing this capsule:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r research/host-replay-20261009/requirements-host-frozen.txt
.\.venv\Scripts\vsl-stream.exe demo --out demo_check
.\.venv\Scripts\vsl-stream.exe inspect --bundle demo_check/bundle
.\.venv\Scripts\vsl-stream.exe replay --bundle demo_check/bundle --frames demo_check/frames.json --config demo_check/server.json --receipt demo_check/replay.json
.\.venv\Scripts\python.exe research/host-replay-20261009/readiness/host_readiness.py --out readiness_check
```

The public demo's labels are synthetic, not signs. Its deterministic input,
model and expected outputs reproduce software behavior without private data.
The arithmetic readiness fixture is a separate synthetic Python recognizer,
not a trained ONNX checkpoint. All 30 real-TCP expected fault outcomes passed.
Twelve malformed messages are expected errors, not a success-path error rate.
Five excess connections received code 1013 with capacity set to two.

For the browser checks, install the optional research tool separately:

```powershell
.\.venv\Scripts\python.exe -m pip install playwright==1.62.0
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe research/host-replay-20261009/readiness/check_browser.py
```

The browser check uses desktop Chromium at width 320px. Its 8/8 passing checks
do not constitute a physical phone test.

## Private real-model route

The case-study models, recorded human traces and original preprocessing checkout
are not distributed. Their redistribution/participant permissions have not been
established here. A public repository license does not grant those rights.
Use this route only with artifacts you are authorized to use and trusted owner
Python source; the external adapter imports it as executable code.

The owner server checkout must contain gloss.csv, pipelines/spoter_onnx_inference.py,
pipelines/slgcn_onnx_inference.py, utils/constants.py, and the two named ONNX files
under models/. Exact evaluated hashes are in evidence/aggregate_receipt.json.
The trace directory must contain three run*_keypoints_15fps.json files, each
with a frames array. The full command creates private bundles and receipts:

```powershell
.\.venv\Scripts\python.exe research/host-replay-20261009/validate_host.py --release-source . --owner-root OWNER_SERVER --trace-dir AUTHORIZED_TRACES --out-root PRIVATE_OUTPUT --check-only
.\.venv\Scripts\python.exe research/host-replay-20261009/validate_host.py --release-source . --owner-root OWNER_SERVER --trace-dir AUTHORIZED_TRACES --out-root PRIVATE_OUTPUT
```

The parameterized runner is derived from the original measured runner. Its
preflight has been executed; the new source hash differs from the original
harness hash in the aggregate. The archived measurements were not rerun or
silently reassigned to this new harness. The original source stays local.
The runner verifies the evaluated installed-wheel module byte hashes and
Git content after CRLF-to-LF normalization. The checked release wheel has CRLF
in two Python files while Git normalizes them to LF.

Paths and declared source dependencies are embedded in external preprocessing
profiles. Moving a checkout can therefore change profile byte hashes even when
its semantic preprocessing is unchanged. Keep the original profile identity in
reports, and record a new profile for the relocated run. Bundle manifest hashes
cover actual bundled files; registration-input hashes cover separate input
JSON files with potentially different whitespace/newline serialization.

An independent reader can reproduce the public fixture today. Complete public
reproduction of these particular human recordings remains unavailable until a
lawful artifact access route and provenance/consent statement are provided.
Supplying another authorized model or trace creates a new study, not replication
of the archived numeric measurements.

## Timing interpretation and limits

Two warmup and five timed passes over 30 segments yield 150 observations per
layer and backend. Median/p95 values use NumPy percentiles. Component percentiles
are not additive. The completed-run receipt records equal ORT_SEQUENTIAL,
intra-op 1 and inter-op 1 settings for owner and toolkit sessions. Paired
differences compare complete calls including postprocessing; they do not isolate
wrapper overhead. This wording was clarified on 10 October; frozen observations,
the historical study tag and its archive remain unchanged.

Request RTT starts after client payload construction and includes socket send,
server waiting/processing/encoding, receive and client response parsing. This
differs from the phone page's timing boundary, which includes its serialization.
Event-bearing RTT and all-request RTT are separately reported. Throughput is
aggregate replayed frames per whole-wave elapsed time, not live camera FPS.
RSS is summed over the owned process tree and sampled at 100 ms; it can miss
short peaks and double-count shared pages.

A finite 24-request paused-reader test completed all 24 ordered responses. It
does not prove a transport-memory bound or sustained overload tolerance.
Started inference completed after disconnect in another fixture check; a
client timeout/disconnect does not imply cancellation. Retries are bounded
and connection-local. Default service admission is 32 sessions; the measured
load reaches eight, not a proven universal maximum.

## Phone later

```powershell
research/host-replay-20261009/readiness/Start-Readiness.ps1 -Python .\.venv\Scripts\python.exe
```

Open http://127.0.0.1:8766/readiness on the host. The page has a permission
confirmation, a built-in fixture, JSON replay, reset/reconnect and receipt
download. To test a phone on an authorized LAN later, explicitly choose
BindAddress 0.0.0.0 and the host LAN URL. No firewall is changed automatically.
See readiness/PHONE_TEST_PROTOCOL.md for fields and expected outcomes.
Camera capture/landmark extraction is an external client and is not implemented
by this page. Physical-phone and Jetson tests are pending.

## Dependency terms

Runtime dependency notices remain in the root THIRD_PARTY_NOTICES.md. Research
observer psutil 7.2.2 identifies BSD-3-Clause and optional browser tool Playwright
1.62.0 identifies Apache-2.0 in their distribution metadata. They are installed
separately; their native/transitive notices remain applicable. No Redis server
or client is required. No third-party recognizer implementation is vendored.
