# Model interface and reproducibility contract

V1 supports **isolated-segment keypoint classifiers**. It requires a single
float32 input and a float32 raw-logit output `[1,K]`, with K unique ordered gloss
labels. This interface describes interoperability, not a new recognition
algorithm. A clip classifier used on continuous input still needs evaluated
segmentation and cannot be assumed to become a continuous-language recognizer.

## Shapes and profile

`profile.json` has exactly these fields:

```json
{
  "schema_version": 1,
  "input_name": "keypoints",
  "output_name": "logits",
  "layout": "BTVC",
  "num_frames": 60,
  "num_points": 49,
  "num_channels": 2,
  "temporal_sampling": "uniform-nearest-v1",
  "preprocessing": {"name": "mediapipe49-shoulder-v1", "config": {}}
}
```

BTVC packs `[1,T,V,C]`; BCTVM packs `[1,C,T,V,1]`. Batch size is one. Graphs
may declare dynamic dimensions, but each bundle fixes T,V,C for preparation and
validation. Input/output names must match. Extra graph outputs may exist, but
the declared logits output must be executable and correctly shaped. External
ONNX data files are unsupported; provide a single-file model.

Labels are a JSON list, e.g. `["hello","thank_you"]`. List position is class
index. The toolkit checks uniqueness and count, not whether the author supplied
the actual training class order. Duplicate labels require disambiguation by the
model owner before packaging; changing label order after packaging is detected
as an artifact edit.

## Temporal preparation

For `identity-v1` and `mediapipe49-shoulder-v1` with `uniform-nearest-v1`,
S accepted frames and target length T use sampling indexes
`floor(linspace(0,S-1,T)+0.5)`. Endpoints are retained and short sequences repeat
nearest frames. The rule is deterministic and independent of batch boundaries.
It is not cyclic padding or timestamp-based interpolation. **Train with this
same rule**, or supply already prepared points and a compatible adapter. For
identity mode with S=T, every frame is preserved.

## Preprocessing profiles

`identity-v1` accepts per-frame `points` as finite `[V,C]`. It performs no
spatial normalization, landmark extraction, bone/motion construction or
imputation. The model owner controls their meaning and order. The caller must
already use the coordinate/channel conventions required by training.

`mediapipe49-shoulder-v1` accepts the canonical server fields
`pose_landmarks` (33), `left_hand_landmarks` (21), `right_hand_landmarks` (21).
The Python preparation function also accepts legacy short field aliases, but
the WebSocket protocol uses the canonical names. Points are ordered as pose
indices `[0,11,12,13,14,15,16]`, then the 21 left-hand indices in MediaPipe
order, then the 21 right-hand indices. It uses xy channels only. For each frame:

- Center = midpoint of pose shoulders 11 and 12.
- Scale = Euclidean xy distance between those shoulders.
- Each detected xy point becomes `(point-center)/scale`.
- A missing hand remains 21 zero points, rather than transformed zeros.
- Missing pose or shoulder width <=1e-6 rejects the segment. This version does
  not independently threshold pose visibility during spatial normalization.

There are no configurable hidden variants; `preprocessing.config` must be `{}`.
The geometry segmenter separately uses configured visibility thresholds. This
new 49-point profile is **not** the historical 54-point SPOTER transform or
27-point SL-GCN/DSTA bone/motion transform. Do not switch an existing checkpoint
to it without retraining or establishing a separately specified adapter.

### Native compatibility profiles (0.2.0)

`spoter54-legacy-v1` fixes BTVC shape `[1,70,54,2]` and
`repeat-or-linspace-floor-v1`: cycle short sequences, otherwise retain
endpoint-inclusive, equally spaced indices rounded down. It preserves the
historical hand-index normalization convention deliberately.

`slgcn27-bone-v1` fixes BCTVM shape `[1,3,150,27,1]` and
`linear-min30-repeat-or-prefix-v1`: expand short sequences to 30 frames,
normalize, then cycle to 150 frames or retain the first 150. The three channels
are bone x, bone y and confidence, not xyz.

Both native profiles require empty `preprocessing.config` and reject conflicting
layout, dimensions or sampling identifiers. They prepare tensors without an
external owner checkout. Their precise ordering, missing-point behavior and
numerical conventions are specified in [PREPROCESSING_PROFILES.md](PREPROCESSING_PROFILES.md).
They are checkpoint-specific compatibility contracts, not automatic support for
all models with those architecture names. The generic uniform-nearest rule
above does not apply to these profiles or to an external Python profile.

## Export and import

Models with another established preprocessing pipeline can use
`external-python-v1`. Its `config` contains exactly `factory` (`module:function`),
`source_sha256` (hash of the defining module file), `kwargs` (JSON arguments),
and `source_dependencies` (declared local source-file paths mapped to hashes).
Its `temporal_sampling` is also `external-python-v1`; the owner function controls
sampling/normalization. The function accepts `(frames, profile, **kwargs)` and
returns the complete finite float32 tensor with the declared shape. The runtime
checks declared source files at startup and retains the callable. Restart after
changing code; hashes do not monitor process memory or every transitive import.

External factories execute trusted local Python. Import itself can execute
package code before the defining file is checked; this is not a sandbox or an
authenticity signature. Install the owner's code separately, keep the declared
dependencies and versions, and review its rights. Source hashes only cover the
declared files. `/v1/config` omits external kwargs/local dependency paths.

`examples/legacy_model_preprocessor.py` demonstrates delegating to the existing
owner checkout for SPOTER and SL-GCN. It copies no normalization implementation
or model architecture. The profile keeps the 54-point SPOTER and 27-point
SL-GCN contracts separately. The owner's existing source is required at runtime;
the example does not clear its license or make the bundle self-contained.

`export_pytorch()` imports a trusted `module:function`, constructs the declared
architecture, loads a weights-only state dictionary strictly, switches to CPU
evaluation mode and exports with ONNX opset 17. A factory is executable local
Python; use code whose provenance you know. A checkpoint may be a state
dictionary directly or contain `state_dict`. Tuple/dict outputs need a wrapper
returning just the selected logits tensor. Unsupported ONNX operations fail
export explicitly.

Three fixed synthetic tensors are compared between PyTorch and ONNX Runtime.
Optional `--validation-tensors real_inputs.npz` adds representative samples.
The NPZ must contain exactly `inputs`, float32 shaped `[N,T,V,C]` for BTVC or
`[N,C,T,V,1]` for BCTVM, N between 1 and 10000, already prepared exactly as in
training. Finite logits, `allclose(atol=1e-5,rtol=1e-4)`, and identical argmax
are required for every sample. The receipt records sample-file hash, counts,
tolerances, versions and maximum absolute error. An argmax tie that changes
class is rejected under this conservative rule.

These checks establish numerical agreement on tested inputs, not accuracy,
linguistic validity, calibrated confidence or agreement on all possible inputs.
User samples should come from a held-out representative trace set. The toolkit
does not certify their provenance or prevent development-set reuse.

`register_onnx()` checks graph/schema/execution but lacks framework outputs, so
its manifest marks parity `unverified`. Do not relabel import as tested export.
Bundle publishing uses a temporary directory and checks the complete artifact
before renaming into place. Existing outputs require explicit `--overwrite`;
arbitrary existing directories cannot be overwritten as bundles.

## Runtime behavior

Runtime validates artifact hashes, labels, profile and executable shape/class
compatibility before accepting predictions. An unavailable execution provider
is rejected. It does not silently select a different requested provider.
Returned `confidence` and `top_k` values are softmax class scores; they are not
calibrated uncertainty, open-set detection, or evidence that a sign is valid.
Prediction events identify a segment's start/end and completion reason.

SHA-256 binds saved bytes against accidental changes. Anyone who can replace
both the artifact and manifest can recompute hashes; this is not signed model
authenticity. Identical shapes cannot establish semantic compatibility. The
training owner remains responsible for the profile, class order and model/data
rights. Include a model card with those details before distributing weights.
