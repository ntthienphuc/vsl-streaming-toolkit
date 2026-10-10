# Evaluation scope and application clients

Documentation audit: 10 October 2026. The current release is 0.2.0. Archived
October 9 load and integration results remain attached to runtime **0.1.2** at
`f2410017a5273ecf3158f7971f31c4b484d2e9dd` and the separate
`study-20261009` capsule. Existing tags and assets are not replaced.

## What the public distribution contains

The public project contains a Python library, CLI, ONNX onboarding commands,
self-hosted WebSocket server, Python client and browser keypoint-file replay
page. Version 0.2.0 adds native `spoter54-legacy-v1` and `slgcn27-bone-v1`
preprocessing, optional CPU video extraction, annotation-based event evaluation,
and a standalone Kotlin Android capture/replay reference client with reusable
transport. The original Flutter application remains separate. The browser
replays frame files and does not extract landmarks from a camera.

Android compilation and host transport tests are preparation for physical-device
testing. They do not establish camera quality, phone energy consumption,
network robustness, end-to-end latency or participant usability. Desktop and
Android extraction use distinct profile identifiers. A capture receipt checks
provenance and trace integrity; it does not prove training-extractor equivalence.

The current API accepts a compatible single-input keypoint classifier with one
raw-logit output; it cannot infer training preprocessing or class order from a
checkpoint. Model/labels/preprocessing remain explicit developer inputs.

## Frozen v0.1.2 evidence

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

## Native profile migration evidence for 0.2.0

An independent numerical comparison used the same three owner-authorized
keypoint traces and the same ONNX weights and ordered labels, while replacing
the legacy external preparation adapter with each native profile. All 30
segments per model had bit-identical prepared tensors and identical ordered
top-three predictions: 60 model-segment comparisons, with maximum reported
score difference 0. A further 22 generated length/profile cases had bit-identical
tensors across lengths 1, 2, 29, 30, 69, 70, 71, 149, 150, 151 and 301 for each
profile. These inputs probe temporal contract boundaries; they do not represent
22 independent natural-sign examples.

This is **host compatibility evidence**, not source-framework export validation,
natural-sign accuracy, independent model training or Android parity. Native
profiles deliberately preserve historical transform conventions, including the
SPOTER hand-index quirk documented in PREPROCESSING_PROFILES.md. Replacing that
behavior requires a new profile and a newly validated model contract.

The optional public verifier requires authorized external model/trace/adapter
inputs. Those inputs are not distributed. Public synthetic checks are fully
self-contained; private natural-trace checks are not independently reproducible
from the public repository alone. Exact test totals and build outcomes belong
to the release validation receipt and CI run for the final commit.

## Remaining evidence for application claims

1. Establish a shareable real-model acquisition and trace route with explicit
   model/data terms, labels, extraction contract and split roles.
2. Annotate natural streams independently and freeze validation/test roles;
   report interval precision/recall, boundary errors, misses/extras, gloss edit
   counts and rejected events. The evaluator supplies calculations, not labels.
3. Measure the Android path on a physical device, including orientation,
   missing-hand/pose behavior, timestamps, reconnects and overload counters.
4. If reporting 0.2.0 latency or capacity, rerun its locked release and disclose
   hardware, provider, warmup, trace pacing, concurrency and error counts.

A functional toolkit and a measured recognition system support different
claims. The release is prepared for those experiments; it does not substitute
protocol parity or artifact hashes for the missing application evidence.
