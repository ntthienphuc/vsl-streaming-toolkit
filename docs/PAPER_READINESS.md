# Evidence checklist for a software article

The release is a reusable keypoint stream processor and ONNX classifier adapter.
Its software contribution is the specified segment-event lifecycle, model
contract, connection-local state and reproducible onboarding/replay workflow.
WebSocket transport, ONNX inference and sign-recognition models have prior art;
see [RELATED_WORK.md](RELATED_WORK.md). No new recognition algorithm is claimed.

## Evidence available to a reader

| Question | Public reproduction | What it establishes |
| --- | --- | --- |
| Does installation and export work? | CI wheel installation, synthetic demo, server-only environment | Executable software on the tested OS/Python matrix |
| Are segment events independent of batch fragmentation? | Core tests and offline/TCP replay comparison | Agreement for the included streams and segment settings |
| Are invalid or retried requests handled explicitly? | Atomic-batch, ordering, retry, capacity and malformed-JSON recovery tests | Specified protocol behavior on tested cases |
| Are model interpretation and inputs identifiable? | Bundle checksums and replay receipt hashes | Artifact integrity and association with an exact frame file |
| Is the boundary detector linguistically accurate? | Not established by the synthetic suite | Needs independently annotated sign boundaries if claimed |
| Is recognition accurate on natural signing? | Not established by fixture labels or runtime agreement | Needs labeled evaluation if claimed |
| Is deployment validated on Jetson or a live camera? | Not established by host replay | Needs target/client evidence if claimed |

Replay receipts include the input file's SHA-256, model/profile/ordered-label
hashes, configuration, Python/platform and runtime versions. Hashes establish
identity, not redistribution permission, training provenance, or a signature.
For a paper, also record the exact source commit or release tag and an environment
lock alongside each receipt. Retain original receipts when implementation changes;
do not silently reassign an earlier timing or agreement result to a newer release.

## Minimum useful application example

Include one documented, legally shareable trained classifier or a reproducible
owner-model acquisition procedure; provide the ordered labels, input contract,
frame extraction assumptions and executable adapter. Freeze representative
recorded keypoint streams with their provenance and sharing terms. Compare
direct-model and toolkit predictions for the same segments; report sample counts,
class/top-k agreement and numerical differences. A second model with a different
input layout gives stronger evidence of reuse than another demo using the same
synthetic graph. Agreement is not recognition accuracy.

## Results worth reporting

- Installation and functional outcomes, with exact source/artifact versions and
  commands a reader can execute.
- A use case from keypoint input to segment events and an explicit rejected case.
- Batch-fragmentation agreement, ordering/retry behavior, session isolation,
  gap/flush/capacity behavior and failure recovery.
- Model integration agreement, stated separately from labeled accuracy and from
  source-framework-to-ONNX export agreement.
- If reporting timing, separate preprocessing, model inference and complete
  request latency; state CPU/GPU, provider, warmup, repetitions, trace counts,
  concurrency and transport conditions. Loopback unpaced replay is not a
  live-camera or network deployment benchmark.
- Known limitations and an honest impact/reuse statement. External adoption and
  sustained overload robustness need their own evidence.

The current browser example replays keypoint files. A new mobile app, a novel
recognizer and Jetson support are not prerequisites for explaining this toolkit's
existing functionality. Their inclusion should follow the paper's actual claims
and available evidence. This checklist is project-specific preparation, not an
assertion that a journal has accepted the software or waived its requirements.

## Version 0.2.0 release gate

The current implementation includes native tensor preparation for two audited
contracts, a video-to-trace adapter, a standalone Android reference client and
an annotation-based event evaluator. These additions make the measurement path
explicit. They do not remove the need for legally accessible application inputs
and independent annotations.

| Gate | Status / required evidence |
| --- | --- |
| Software packaging | Final wheel, source archive, CI results and checksums tied to the release commit |
| Native contracts | 60 trace/model segment comparisons and 22 generated length/profile cases; host compatibility only |
| Capture provenance | Explicit detector assets, clock/orientation policies and exact frame hashes; model compatibility requires separate checking |
| Android integration | Build and transport checks; physical-device capture and network measurements remain pending |
| Event quality | Implemented evaluator and synthetic calculation tests; natural-stream annotations and results remain pending |
| Real-case reproducibility | Publicly shareable weights/data or a documented lawful acquisition route still required |
| Performance claims | Archived v0.1.2 timings retain that version; benchmark 0.2.0 separately before reporting its timing |

The article should lead with the software problem: adapting a compatible
isolated-sign recognizer into a bounded stream of auditable segment events.
Describe the contract, state transitions, reusable interfaces and failure
semantics, then present version-bound correctness and application results.
Treat the Android app as a reference integration. A new GUI, Redis replacement
or unmeasured edge target would add scope without resolving the evidence gaps.

Suggested Results order: installation and contract checks; native-profile
compatibility; offline/WebSocket event agreement; failure and cleanup behavior;
annotated stream quality; measured timing under stated conditions. Include only
completed measurements, and identify pending device work as a limitation.
The Impact section can explain reduced repeated integration work and explicit
failure handling; external adoption or productivity improvements require
independent evidence and should not be inferred from feature count.
