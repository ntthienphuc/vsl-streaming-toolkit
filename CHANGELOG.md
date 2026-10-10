# Changelog

## 0.2.0 — 2026-10-10

- Add native SPOTER-54 legacy and SL-GCN-27 bone preprocessing profiles with
  explicit tensor, temporal-sampling and landmark-order contracts. Preserve
  the historical SPOTER hand ordering for checkpoint compatibility; retain
  upstream Apache-2.0 attribution and license for the derived implementation.
- Add optional offline MediaPipe video capture, asset/video/frame hashes,
  explicit timestamp and orientation policies, and JSON array/JSONL replay.
- Add a standalone Android capture/file-replay reference client with a reusable
  WebSocket transport, bounded queuing, correlated acknowledgments and stop
  drain/flush behavior. Physical-device validation remains a separate phase.
- Add annotated event evaluation for temporal matching, missed/extra intervals,
  boundary errors, gloss edits and rejected/forced-closure events. Public
  fixtures are synthetic and do not establish recognition accuracy.
- Add model-profile initialization, capture-receipt checks and an evaluation
  CLI; expand release verification, third-party notices and journal guidance.
- Normalize literal malformed Unicode in the public protocol decoder into the
  same bounded validation-error path as malformed JSON strings.

The frozen `study-20261009` results evaluate v0.1.2. They are not measurements of
the new capture client or native profiles in this release.

## 0.1.2 — 2026-10-09

- Keep parser-error responses bounded and valid UTF-8 even when malformed JSON
  contains duplicate surrogate keys; the WebSocket connection remains usable.
- Bind replay receipts to the exact input bytes and all three model bundle
  artifacts, and record the Python/platform/direct runtime versions.
- Add regressions for malformed-message recovery and identical model graphs
  interpreted with different ordered label lists.
- Include the SoftwareX filename `Licence.txt`, byte-identical to `LICENSE.txt`,
  in source and wheel distributions, with a packaging synchronization check.
- Add a claim-oriented software-paper evidence checklist.

## 0.1.1 — 2026-10-05

First public release; 0.1.0 was a local development snapshot.

- MIT source license with explicit third-party boundaries and software citation.
- Isolated-session keypoint segmentation, ordering and atomic batch validation.
- Fixed-window and signing-space modes with specified gaps, flush and capacity behavior.
- Bundle validation, trusted preprocessing adapters and ONNX export/import commands.
- Representative-tensor export parity checks and explicit rejected segment events.
- Configurable WebSocket server, browser file replay and Python client.
- Public synthetic reproduction procedure and continuous integration.

No trained VSL weights, recorded participant traces or legacy recognizer source
are included. Publication of this code does not establish their redistribution rights.
