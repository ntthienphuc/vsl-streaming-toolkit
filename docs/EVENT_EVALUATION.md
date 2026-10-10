# Annotation-based event evaluation

`vsl_streaming.evaluation` measures whether emitted intervals correspond to annotated signs and whether their gloss labels agree. It is an offline evaluator implemented with the Python standard library. It does not obtain ground truth from model outputs or from the segmentation heuristic. The bundled example is synthetic; its scores validate calculations, not recognition performance.

## Annotation contract

Use the structure in [`examples/event_annotations.json`](../examples/event_annotations.json). Each document declares `schema_version: 1`, `scope: synthetic|research`, and a `recordings` array. Each recording has:

| Field | Meaning |
|---|---|
| `recording_id` | Unique join key linking annotations to predictions |
| `split_role` | `train`, `validation`, `test`, or `demo`; tune thresholds on validation only |
| `source_group` | Original recording/acquisition group, preserved across derived clips |
| `speaker_identity` | `{"status":"unverified"}` unless identity has been independently established |
| `annotations` | Chronological, nonoverlapping `{start_ms, end_ms, label}` intervals |

Verified speaker identity requires `{"status":"verified", "id":"pseudonymous-id", "evidence":"verification record reference"}`. The library validates these fields; it cannot independently authenticate an identity assertion. It does not infer speaker identity from a filename or source group. A source group occurring in multiple split roles is rejected. Verified speaker overlap between roles is reported because speaker-dependent and speaker-independent study designs have different requirements. Unverified identities do not establish speaker independence.

Annotation intervals require finite nonnegative start times and strictly later end times. Empty annotation lists are valid for negative/no-sign recordings. Labels are compared exactly, including case, diacritics, and Unicode representation; freeze a shared ordered vocabulary and normalization convention before annotation and inference. Overlapping reference signs are outside this single-track word-event schema. Document how annotators defined preparation, meaningful movement, holds and retraction, how disagreements were adjudicated, and the timing uncertainty. The JSON schema alone does not establish annotation quality.

Annotations and emitted intervals must use the **same recording time origin and clock units**. Do not compare video-relative milliseconds with a phone's uptime or wall-clock milliseconds without an explicit recorded offset. Event boundaries are the first and last retained sample timestamps, so frame sampling contributes timing uncertainty.

## Prediction input

The evaluator accepts a dictionary mapping recording IDs to lists of canonical events:

```json
{
  "synthetic-demo": [
    {"start_ms": 10, "end_ms": 510, "label": "SYNTHETIC_NEGATIVE", "status": "predicted", "reason": "inactive"},
    {"start_ms": 710, "end_ms": 1210, "label": "SYNTHETIC_POSITIVE", "status": "predicted", "reason": "flush"}
  ]
}
```

`status` defaults to `predicted`; `reason` defaults to `unspecified`; `quality_flags` defaults to an empty list. A rejected inference is represented by `status: rejected` and `label: null`. Unknown flags remain visible in the report. A zero-duration predicted interval is legal (for example, one retained frame) but its temporal IoU is zero. Reversed, nonfinite or out-of-order intervals are rejected. Equal start times and overlapping predictions are retained so duplicate/split detections are measurable. The evaluator does not sort malformed logs or collapse repeated glosses.

`events_from_responses(responses)` converts ordered `/v1/stream` result messages or the `responses` member of an offline replay receipt. It includes rejected events and skips an explicit `replayed: true` cached reply only when a matching original result is present. Protocol errors, inconsistent cached replies and duplicate uncached request IDs raise. Pass one recording/session at a time. This prevents a partial, error-containing response log from silently becoming a complete accuracy result; report transport failures separately.

Missing prediction keys are treated as zero emitted events and listed in `missing_prediction_recordings`. Thus a missing recording counts toward misses and deletions. Unknown recording IDs are rejected rather than excluded. Do not use missing keys as a substitute for diagnosing a failed run.

## Matching and metrics

Matching uses temporal overlap alone; gloss labels do not influence pairing. An edge is eligible when `temporal_iou >= iou_threshold`, with a required threshold in `(0, 1]` and default `0.5`. Continuous-time IoU is intersection duration divided by union duration. The algorithm uses unit-capacity min-cost maximum flow with negative-IoU costs. It first maximizes the number of one-to-one matches and then maximizes their summed IoU. Reference order, prediction order and strict shortest-path updates make ties deterministic; cost improvements smaller than `1e-12` are treated as ties. It is an offline algorithm for moderate recording-level event lists, not the real-time inference path.

For `N` reference signs, `M` emitted intervals and `K` matches, the report contains:

- Interval precision `K/M`, recall `K/N`, and F1 `2K/(N+M)`; missed signs `N-K` and extra intervals `M-K`.
- Mean temporal IoU for matched intervals.
- Signed onset/end errors (`predicted - reference`) and their mean and median absolute errors in milliseconds, for matched intervals only. These describe boundary placement, **not capture-to-display latency**.
- Matched-gloss accuracy: correctly labeled temporal matches divided by all temporal matches. A temporally matched rejected inference is an incorrect label outcome. This conditional measure must accompany missed/extra counts; by itself it can hide segmentation failures.
- Full recording gloss-sequence Levenshtein distance, substitutions, deletions and insertions. All predicted labels are retained in chronological event order, including unmatched and repeated labels. Rejected events have no output token. This sequence metric is independent of temporal matching and can be perfect despite poor boundaries. Unit edit costs are used; optimal-alignment ties prefer substitution, then deletion, then insertion after an exact diagonal match.
- Closure-reason, event-status and quality-flag counts, per recording and overall.

`error_rate = (S+D+I)/N_tokens`; insertions can make it exceed 1. An empty denominator produces JSON `null`, never a fabricated zero or perfect score. Counts are always available. Empty reference and hypothesis sequences have edit distance 0 and undefined normalized error rate. F1 is undefined only when both reference and emitted interval counts are zero. No confidence intervals or significance tests are generated.

All emitted intervals contribute to primary detection metrics, including `flush`, `gap`, `capacity`, and inference rejection. These closure reasons are implementation events, not independent evidence of complete linguistic signs. A capacity split can create extra intervals; a flush can close a partial sign. If the study needs a secondary analysis excluding a predeclared class of closures, report it alongside the primary result with explicit denominators. The evaluator intentionally provides no silent exclusion switch.

## Reproduction

Python API:

```python
import json
from vsl_streaming.evaluation import evaluate_events, events_from_responses

annotations = json.load(open("annotations.json", encoding="utf-8"))
receipt = json.load(open("replay_receipt.json", encoding="utf-8"))
events = events_from_responses(receipt)
report = evaluate_events(annotations, {"recording-001": events}, iou_threshold=0.5)
```

After installing the toolkit, the standalone command supports either canonical event lists or response lists/receipts mapped by recording ID:

```bash
python examples/evaluate_events.py --annotations examples/event_annotations.json --predictions predictions.json --iou-threshold 0.5 --out event_report.json
```

The command stores SHA-256 hashes of its two input files. Archive the model bundle, ordered labels, extraction/preprocessing profiles, stream configuration, recordings/trace hashes and software version alongside the report. Input hashes bind files; they do not prove rights, annotation correctness, or split independence.

Totals are micro-aggregated across supplied recordings. Run train/validation/test roles separately for paper results; do not present a pooled total containing training recordings as held-out performance. When comparing segmentation configurations, use the same recordings, vocabulary and recognizer, freeze the chosen threshold before test evaluation, and retain no-sign clips and failures. Repeat the evaluation on each capture profile separately before claiming Android and desktop extraction equivalence.

Unit tests include known boundary offsets, empty and rejected cases, source-group leakage, edit counts, cached-response accounting, a case in which greedy IoU matching loses a valid match, and exhaustive matching checks over small synthetic graphs. These are software tests. Real annotated recording results remain a separate measurement requirement; transport parity and unannotated host replay cannot supply them.
