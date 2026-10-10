# Next VSL measurement campaign

Status: **prospective protocol, not executed results**. Proposed on 10 October
2026 after reanalysing the frozen October 9 study. The choices below are study
design recommendations, not SoftwareX requirements or universal performance
thresholds. Freeze choices and a new harness hash before collecting new data.

## F0: artifacts and installation

Use a new output directory and run ID. Record wheel/commit/module hashes,
model graph, manifest, labels in training order, preprocessing profile and
declared adapter dependencies, stream/server configuration and actual session
options. Distinguish original input hashes from canonical-frame/tensor hashes.
Record host, interpreter, provider, package inventory, power mode and timestamps.

In a new Python 3.11 virtual environment install the frozen wheel and declared
dependencies, run `pip check`, verify site-packages imports, and run the public
synthetic demo/inspect/replay against expected outputs. Keep resolver failures.
The study lock is Windows/Python 3.11-specific; generic runtime support does not
promise that every study observer works under Python 3.9 or Jetson ARM.

Artifact integrity does not establish correct training semantics or permission
to distribute models/human traces. A full real-case reproduction additionally
needs lawful artifact access and documented preprocessing provenance.

## F1: staged direct/model integration

On exactly the same emitted segment frames compare:

1. Canonical frames and segment membership.
2. Prepared tensor shape/dtype/values.
3. All raw logits, every-class probabilities and class ranking.
4. Ordered label mapping and delivered predictions/rejections.

Both sessions must have equal provider/thread/execution settings, verified from
the initialized sessions. Proposed criteria: exact tensor equality for the same
deterministic CPU adapter; finite outputs; full-logit `allclose(atol=1e-5,
rtol=1e-4)`; maximum probability difference `2e-6`; unchanged top-1/ordered top-3
on the declared cases. Record margins and tie-breaking; do not change tolerance
after seeing an inconvenient difference. Report the first stage that differs.

The previous `2e-6` comparison covered returned top-three probabilities only.
Sharing preprocessing establishes integration agreement, not independent
transform correctness. Add independently specified tensor fixtures. Validate
PyTorch-to-ONNX separately when architecture/checkpoint rights permit it.

## F2: protocol and session correctness

Compare offline and socket events at chunks 1/4/19/31/120 and one seeded variable
chunk pattern, separately for signing-space and fixed-window modes. Preserve
event IDs, sequence/time bounds, counts, closure reasons, rejection reasons and
all class outputs; remove timing fields only.

Create a request/event ledger. Test invalid-last-frame batch atomicity, order
and timestamp faults, nonfinite landmarks, point-count errors, missing pose,
gap/onset/closure thresholds, minimum segment length, buffer closure, flush,
reset, retries/conflicting IDs/eviction, disconnect and fresh reconnect.
Test concurrent isolation, admission saturation and reusable connection slots.
Started inference is not guaranteed to cancel on disconnect; evaluate actual
completion/cleanup semantics. Proposed cleanup deadline is five seconds after
all in-flight work finishes, with work completion recorded separately.

## F3: timing

Measure client JSON encode, send/response RTT, server parse/validation,
inference-gate wait, segmentation, preprocessing, ONNX execution, ranking,
response serialization and client parse on defined clocks. Do not subtract
unsynchronized phone/host timestamps or combine component percentiles.

Proposed repetitions: ten warmup passes, three fresh-process campaigns, ten
timed passes over thirty segments/backend/campaign. Alternate or seed-randomize
path order. Report raw observations, p50/p95/max, denominators and campaign
variation. Repeated calls are technical repeats, not additional signs/speakers.
No simultaneous browser rendering, CI or other benchmarks during these runs.
Keep cold-start timing separate and predefine rerun/outlier rules.

## F4: paced and sustained load

Keep the unpaced acknowledged-request baseline separate. Add source-time paced
replay near 15 fps at batch sizes 1/4/31 and concurrency 1/4/8. Account for
batching delay: accumulating 31 frames at 15 fps holds early frames for about
two seconds before sending them. RTT alone excludes that delay.

Use a bounded producer queue to separate generation from acknowledgment-driven
sending. Report offered/sent/accepted/completed rates, queue age/occupancy,
drops, event rates, RTT and event-bearing p95, timeouts, protocol errors,
segment rejects and admission rejects. Do not label the old closed-loop harness
an open-loop producer.

Proposed campaign: fifteen-minute steady-state steps at 1/4/8 sessions; explore
16/32 only after documenting earlier steps; thirty-minute soak at the proposed
demo envelope. Stop on a declared queue/memory budget, persistent timeout or
process failure and keep the failed condition. A proposed engineering goal for
the chosen demo profile is event-bearing client RTT p95 <=1,000 ms without
growing queue age, protocol loss/duplicates or session contamination. This is
a prospective host goal, not live capture latency or linguistic accuracy.

Sample RSS/private bytes when available, CPU time, threads, handles, queues and
active sessions. Run thirty connect/replay/disconnect cycles and observe
quiescent baselines. RSS allocator retention alone is not proof of a leak;
summed process-tree RSS may double-count shared pages. The previous finite
paused-reader burst does not prove sustained overload bounds.

## F5: lawful scientific case

Provide an accessible model/ordered labels/preprocessing/trace workflow with
clear terms. An alternative public model/trace is a new demonstration, not an
exact replication of the private case. Keep models, datasets and participant
permissions separate from the toolkit's MIT AND Apache-2.0 source license.

Only compute recognition or boundary metrics against actual reference labels
and boundaries. Prompts are not annotations. Preserve missed/merged/fragmented
and false-positive events; predefine temporal matching and report denominators.
Separate ground-truth-segment classification from end-to-end segmentation plus
recognition. Source groups without verified signer IDs are not independent
signers. Integration-only evidence must retain the narrower conclusion.

## F6/F7: mobile and Jetson later

The released Android reference client implements `/v1/stream`; before claiming
physical-device behavior, validate ready,
frames/request IDs, sequence/time, canonical pose/hand order, event parsing,
flush/reset/status, fresh reconnect and bounded queues. Audit mirror/rotation,
handedness, visibility and sampling against training semantics.

Separate phone-browser LAN replay, native-app replay of the same file and new
camera/extractor streams. Log acquired/extracted/dropped/queued/sent/accepted
counts. Measure capture-to-display on the client's own monotonic clock.
Physical-device receipts remain pending until actually executed.

For Jetson first establish actual board/JetPack/runtime/provider compatibility;
the Windows lock is not an ARM deployment promise. Compare tensors/outputs
before timing. Record CPU fallback, conversion failures, thermal/power mode and
sustained behavior; do not describe generic CPU checks as GPU/TensorRT results.

## Delivery and publication

Keep each campaign's raw numeric observations, config, hashes, request/event
ledger, summary code and failures. Generate Results/Impact from receipts, and
label pending device or scientific-quality metrics explicitly. The paper's
initial supported scope can remain library/server replay while mobile and edge
claims await their own experiments. See [evaluation scope](EVALUATION_SCOPE.md).
