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
| Is deployment validated on Jetson or useful live-camera landmarks? | Not established by public host replay; limited local phone smoke is described below | Needs target-specific evidence; camera frames with null landmarks do not establish recognition |

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

## Archived version 0.2.0 compatibility gate

The v0.2.0 implementation introduced native tensor preparation for two audited
contracts, a video-to-trace adapter, a standalone Android reference client and
an annotation-based event evaluator. These additions make the measurement path
explicit. They do not remove the need for legally accessible application inputs
and independent annotations.

The following table records historical v0.2.0 preparation and checks. It is not
a new v0.2.1 experiment or the current manuscript's Results. Keep the original
receipts and evaluated model/source identities with those counts.

| Gate | Status / required evidence |
| --- | --- |
| Software packaging | Final wheel, source archive, CI results and checksums tied to the release commit |
| Native contracts | Archived v0.2.0: 60 trace/model segment comparisons and 22 generated length/profile cases; host compatibility only, not new v0.2.1 results |
| Capture provenance | Explicit detector assets, clock/orientation policies and exact frame hashes; model compatibility requires separate checking |
| Android integration | At the v0.2.0 gate: build and transport checks; physical-device capture and network measurements were pending |
| Event quality | Implemented evaluator and synthetic calculation tests; natural-stream annotations and results remain pending |
| Real-case reproducibility | Publicly shareable weights/data or a documented lawful acquisition route still required |
| Performance claims | Archived v0.1.2 timings retain that version; any later timing requires a separately identified measurement |

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


## Pre-results preparation, updated 11 October 2026

Version 0.2.1 hardens the 0.2.0 feature set. The
[submission matrix](SOFTWAREX_SUBMISSION.md) separates completed preparation
from author-supplied information, final template application and future results.
Journal fit is a reason to prepare a careful submission, not an acceptance
prediction.

Preserve the archived v0.1.2 manuscript and host study as versioned history.
A new candidate manuscript must update the license, native profiles, optional
capture adapters, Android client and evaluator together. Keep its Results
subsection explicitly pending. Do not transfer v0.1.2 host timings, private-model
agreement counts or v0.2.0 checks to a changed binary without identifying the
original evaluated version and justifying applicability.

Before the real experiment, freeze the source commit, release and environment;
the acquisition policy and detector assets; ordered labels and model contracts;
the development/evaluation split; and the annotation and event-matching rules.
Select baselines to answer a stated question, not to maximize a favorable
difference. Report all emitted, rejected, missed and extra events under the
predeclared rule. These are project-specific safeguards for interpretable
results; they do not assert an unverified journal-mandated experiment count.

The current unresolved evidence gates remain permissioned real-case access,
independent natural-stream annotations, useful physical-device landmark capture,
measurements supporting the exact phone/network/timing claim, and Results bound
to the measured version. They remain for the next experimental phase. A software
release may be usable before the associated article is ready for submission.

## Local phone smoke is not scientific Results

The local 11 October report and structured receipt establish a limited
engineering smoke: 205 acknowledged frames across four completed sessions
(24 + 24 synthetic replay; 106 + 51 camera frames). All 157 camera trace frames
had null pose and hand landmarks. Missing-detection frame capture, transport,
stop/flush, export and cleanup were exercised; recognition on camera input,
landmark quality, natural-sign boundaries and accuracy were not established.
This evidence remains local and is not presented as public journal Results.
It also does not validate Wi-Fi/LAN, WSS/TLS, long captures or deployment latency.
The receipt identifies a later checkout and the selected APK separately from
the frozen v0.2.1 tag; preserve those identities rather than treating main as the
release. Private traces and raw device identifiers are not included here.

## Verified journal format and author gates

The complete supplied SoftwareX Guide for Authors PDF was reviewed on
11 October; [SOFTWAREX_SUBMISSION.md](SOFTWAREX_SUBMISSION.md) records its hash
and page convention. The descriptive paper has a **4,000-word maximum** including
abstract, running text, captions and footnotes, excluding title, authors,
affiliations, references and metadata tables, with at most six figures (p. 30).
Use the exact journal template (pp. 4, 23–24, 30–31), an editable single-column
Word source (p. 15), figures embedded in .docx and supplied separately as artwork
and source files (pp. 4, 18, 23–24). A prepared draft does not establish that the
format has been preserved. The official Word template was separately retrieved
and inspected on 11 October 2026: Version 6 (March 2026). It requires the five
main sections and fixed C1–C8 metadata labels, targets an approximately 100-word
abstract and allows at most six keywords. Apply those template constraints
alongside the guide's broader abstract/keyword ceilings.

The guide permits at most 250 abstract words and 1–7 English keywords
(pp. 16–17); use the narrower Word-template targets above for this submission.
Highlights and a graphical abstract are encouraged, not mandatory (p. 17).
Supply the required data-availability statement and either deposit/cite/link
supporting research data or explain why sharing is impossible (p. 22). An
unconditional promise to publish restricted participant traces would not satisfy
the project's permissions constraints.

Authors still need to confirm author order/approval, full affiliation and
correspondence, CRediT roles, funding/sponsor role, the competing-interest
declaration-tool output, and any applicable ethics/consent or justified exemption
(pp. 5–8, 13–16, 25). Declare actual manuscript-preparation AI assistance before
references when applicable (pp. 9–10), and AI-generated images in their captions
as well as the general disclosure (p. 20). Keep statements awaiting author
confirmation visibly unresolved; do not infer approval from software tests.
