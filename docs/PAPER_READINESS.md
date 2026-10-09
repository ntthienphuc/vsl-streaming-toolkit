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
