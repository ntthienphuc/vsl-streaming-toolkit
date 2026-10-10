# Evaluation scope and application clients

Documentation audit: 10 October 2026. This page is a clarification, not a new
model or device benchmark. The evaluated runtime remains 0.1.2 at
`f2410017a5273ecf3158f7971f31c4b484d2e9dd`; the original research capsule remains
frozen separately by `study-20261009`. Existing tags/assets are not replaced.

## What the public distribution contains

The public project contains a Python library, CLI, ONNX onboarding commands,
self-hosted WebSocket server, Python client and browser keypoint-file replay
page. It does not contain a native Android/Flutter application. The browser
does not capture camera video or extract landmarks. An existing external app
must be adapted and tested against `/v1/stream` before claiming compatibility.

The current API accepts a compatible single-input keypoint classifier with one
raw-logit output; it cannot infer training preprocessing or class order from a
checkpoint. Model/labels/preprocessing remain explicit developer inputs.

## Evidence already available

The October 9 study reports integration around two owner-provided ONNX models,
three recorded keypoint traces, chunk replay and unpaced loopback load. Across
both backends it measured 36 waves, 156 connections, 5,200 requests and 1,560
predicted events. Load was tested at 1/4/8 concurrent sessions. These are repeated
executions of recorded inputs, not independent participants or a live-camera
evaluation. Models and human coordinates are not redistributed by this project.

Public numeric observations reproduce all six archived load-summary rows within
`1e-9` in the October 10 reanalysis. This verifies summary arithmetic; it does
not run the original models again. Thirty synthetic readiness checks and eight
desktop-browser checks are separate from the real-model study and phone tests.

The direct/toolkit comparison preserves ordered top-three predictions on the
30 segments per backend. It compares their returned top-three probability
scores, not every raw logit or task accuracy. Both paths share owner
preprocessing. Source-framework export parity, linguistic boundary quality,
recognition accuracy, live phone capture, LAN device timing and Jetson runtime
performance remain outside the measured results.

## Thread-option correction

The completed-run receipt records `ORT_SEQUENTIAL`, intra-op threads `1` and
inter-op threads `1` for **both** owner and toolkit sessions in **both** backends.
A local working manuscript and supplement previously described different
inter-op settings. Those sentences were corrected on October 10 without
changing the original observations or receipt. The paired timing differences
still compare complete calls, including postprocessing; they do not isolate
pure wrapper overhead. The original research summary wording is clarified on
the current branch; the historical study tag and downloadable archive retain
their original bytes.

## Before making mobile or capacity claims

Measure phone browser replay, native-app file replay and live extraction as
separate stages. Preserve original frame-relative time across batching and
record acquired, dropped, queued, sent and accepted frame counts. A narrow
desktop viewport is not a physical-phone result. A default admission limit of
32 connections is not a measured sustainable capacity of 32 clients.

See [the next measurement protocol](REMEASUREMENT_PLAN.md),
[the model contract](MODEL_CONTRACT.md), [the wire protocol](../README.md#websocket-protocol-and-configuration), and
the [frozen study](../research/host-replay-20261009/REPRODUCE.md). New campaign
results require their own run ID, environment, artifact hashes and receipts.

## Python for the research tools

The runtime package supports Python >=3.9; the frozen host study used Python
3.11. Optional Playwright 1.62 requires Python >=3.10. On a host where `python`
resolves to Python 3.9, invoke the study virtual environment explicitly; the
interpreter difference does not require changing the archived package versions.
Reproducing an installed environment's inventory is distinct from proving a
fresh installation of the entire locked toolchain.
