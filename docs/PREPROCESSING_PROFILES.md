# Versioned preprocessing profiles

The built-in profiles convert a completed sequence of canonical MediaPipe-style
landmark records into the tensor expected by a declared model. Their purpose is
to make model input preparation reproducible without requiring an external
application checkout. They do not train, download, or redistribute a recognizer.

The names below specify two particular deployment contracts. A checkpoint with
the same architecture name is not sufficient evidence of compatibility. Model
owners must verify ordered labels, coordinate conventions, extraction settings,
training transforms, and source-framework/exported outputs for their checkpoint.

## Supported contracts

| Profile | Tensor shape | Coordinate channels | Temporal contract |
| --- | --- | --- | --- |
| `spoter54-legacy-v1` | `1 × 70 × 54 × 2` (`BTVC`) | x, y after historical body/hand normalization and shift | Cycle a short sequence to 70 frames; for length ≥70 use 70 equally spaced endpoint-inclusive indices rounded down |
| `slgcn27-bone-v1` | `1 × 3 × 150 × 27 × 1` (`BCTVM`) | normalized bone x, normalized bone y, edge confidence | Expand sequences shorter than 30 frames, then normalize, then cycle to 150 frames or retain the first 150 |

Both profiles require `preprocessing.config` to be `{}`. Their dimensions,
layout, and temporal behavior are fixed; conflicting profile fields are rejected
before model execution. The canonical temporal identifiers are
`repeat-or-linspace-floor-v1` and `linear-min30-repeat-or-prefix-v1`, respectively.
The 49-point shoulder profile is a separate contract and cannot replace these
profiles without revalidating or retraining a model.

```json
{
  "schema_version": 1,
  "input_name": "poses",
  "output_name": "logits",
  "layout": "BTVC",
  "num_frames": 70,
  "num_points": 54,
  "num_channels": 2,
  "temporal_sampling": "repeat-or-linspace-floor-v1",
  "preprocessing": {"name": "spoter54-legacy-v1", "config": {}}
}
```

Input and output tensor names must match the actual ONNX graph. The native
profile validates layout and dimensions, not the semantic correctness of an
arbitrary model file that happens to accept that shape.

## Landmark input

Each frame uses `pose_landmarks` (33 points), `left_hand_landmarks` (21 points),
and `right_hand_landmarks` (21 points). A component may be `null`; omitted
components are treated as missing. At least one canonical component field must
be present, even if its value is `null`. Point arrays and alternate field names
are rejected by these native profiles to prevent accidental contract changes.

Each point is an object with finite `x` and `y`. Optional `z` must be finite but
is not consumed by either transform. `visibility` is constrained to [0, 1] and
defaults to 1, consistently with the public wire protocol. Neither profile
clamps x/y to [0, 1]. A coordinate on an image boundary therefore remains a
valid numeric input, although the historical SPOTER convention treats x=0 as
missing during normalization.

Sequence numbers and timestamps, when supplied to the standalone preprocessing
API, must increase strictly. The WebSocket protocol additionally requires these
ordering fields. The profile resamplers operate on frame index, not elapsed
time: equal sequence length at different capture rates does not imply equal
motion duration. Capture FPS and timestamp policy belong in the experiment
record. Extraction settings cannot be inferred from a tensor shape.

## SPOTER54 compatibility details

Pose selection is `(0, -1, 5, 2, 8, 7, 12, 11, 14, 13, 16, 15)`, where `-1`
inserts a zero neck placeholder. Each hand is selected in the order
`(0, 8, 7, 6, 5, 12, 11, 10, 9, 16, 15, 14, 13, 20, 19, 18, 17, 4, 3, 2, 1)`.
The selected tensor initially contains 12 body points, all 21 left-hand points,
and all 21 right-hand points. Computation uses float64 before the final float32
cast to match the inspected deployment source.

The body normalization derives a box from the shoulders, dummy neck, and left
eye. Its bounds are clipped below at zero. Missing anchor points reuse the last
available box; frames before any valid box and frames with zero box dimensions
retain their raw body values. A final subtraction of 0.5 applies to every
coordinate, including missing zeros.

**The `legacy` suffix is intentional.** The historical application concatenates
left/right hand blocks, then interprets their names in an alternating order.
Consequently, hand normalization operates on indices `12,14,...,52` and
`13,15,...,53`, rather than two anatomical hand blocks. This implementation
preserves that behavior for compatibility. Silently correcting it changes model
inputs; a corrected anatomical variant would need a new profile identifier and
an independently evaluated training/deployment contract.

For each historical hand group, nonzero x and y extrema define a square bounding
box with a margin equal to 10% of the larger span. Points with x=0 remain
unchanged until the final shift. A nonempty group with zero area is rejected:
the original transform could produce NaN/Inf in this case. A fully missing
component remains representable. An entirely missing frame becomes -0.5 after
the final shift; this is numerical compatibility, not evidence that the frame
contains a recognizable sign. Input-quality decisions belong upstream.

## SL-GCN27 compatibility details

Pose indices are `(0, 11, 12, 13, 14, 15, 16)`. Each hand uses
`(0, 4, 5, 8, 9, 12, 13, 16, 17, 20)`. The selected channels are x, y, and
confidence. Pose confidence comes from visibility; a detected hand has
confidence 1 regardless of its point visibility field. Missing components and
pose points with nonpositive confidence are zeroed. The third channel is
**confidence, not MediaPipe depth**.

For a sequence shorter than 30 frames, x/y are linearly interpolated in index
space to 30 positions. Confidence is sampled at the nearest original index
using NumPy round-to-even; x/y are zeroed where the resulting confidence is
nonpositive. Interpolation may span a missing observation, as in the original
deployment code; this profile does not introduce a new missing-data estimator.

Each joint's x/y distribution is standardized over its positive-confidence
observations using population standard deviation. A standard deviation ≤1e-7
maps that channel to zero. This normalization uses the full expanded sequence
**before** repetition or prefix truncation to 150 frames. Changing that order
changes the tensor.

The fixed directed skeleton has 26 parent-to-child edges over 27 joints. Each
target stores target-minus-source normalized x/y and the minimum endpoint
confidence. The root has no incoming edge and remains zero. The historical
root-centering operation is retained; it is a no-op for this bone stream.
Output is contiguous float32 in `BCTVM` order. Motion differencing and DSTA are
not part of this profile. Coordinates that overflow float32, or operations that
produce a nonfinite final tensor, are rejected before inference.

## Validation and evidence boundary

`tests/test_native_profiles.py` provides 12 public analytic tests covering shape
and option rejection, temporal selection, dummy-neck and missing-mask behavior,
historical hand grouping, confidence semantics, pre-truncation normalization,
input immutability, malformed order/coordinates, and degenerate/overflow cases.
An additional optional test compares both profiles with the separately
installed owner transforms using generated landmarks only. It requires no
model weights or signer recordings.

On 2026-10-10, the optional comparison passed exact float32 array equality for
both profiles at lengths 1, 2, 29, 30, 69, 70, 71, 149, 150, 151, and 301
(22 tensor comparisons; maximum absolute difference 0). Fixtures include
deterministic missing-pose and missing-hand patterns. The comparison was run
under Python 3.9 in the local development environment. The compared source
SHA-256 values were:

| Owner source relative to `vsl_server` | SHA-256 |
| --- | --- |
| `pipelines/spoter_onnx_inference.py` | `60e4d449909baf409be301e400e90cfd93115688bf08ad33b660bb64b66c303a` |
| `pipelines/slgcn_onnx_inference.py` | `7e554defecaa45fe4fe5002eccc26aba4d99bc645f5bbb5bfbca783552aa633e` |
| `utils/constants.py` | `a71244ba7139f0ab54c198497cc3be567849346abc18f5b195562bc6de9ebb3a` |

The owner comparison is supplementary development evidence; it skips in public
CI when the owner checkout is absent. Public analytic tests remain runnable
from the released source. Exact equality on these generated inputs does not
establish a mathematical proof for every input, recognition accuracy, detector
equivalence, mobile performance, or a new natural-stream evaluation. The frozen
2026-10-09 host replay continues to describe its original external adapter;
these new profiles do not retroactively change its tested artifact.

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p test_native_profiles.py -v
# Optional: only with a separately authorized original source checkout.
$env:VSL_OWNER_SERVER_ROOT = "C:\path\to\original\vsl_server"
python -m unittest discover -s tests -p test_native_profiles.py -v
```

## Source attribution and distribution

The implementation follows the owner's deployment transform contracts. SPOTER
body/hand normalization has upstream lineage in Matyáš Boháček and Marek Hrúz,
*Sign Pose-Based Transformer for Word-Level Sign Language Recognition*, WACV
Workshops 2022, pp. 182–191. The inspected upstream revision is
[`0f909bf92690772f43f0062be41860ed85b461ad`](https://github.com/maty-bohacek/spoter/tree/0f909bf92690772f43f0062be41860ed85b461ad).
Its [Apache-2.0 license](https://github.com/maty-bohacek/spoter/blob/0f909bf92690772f43f0062be41860ed85b461ad/LICENSE)
includes copyright 2021–2022 Matyáš Boháček. No upstream `NOTICE` file was present
in the inspected tree. The full license is retained at
[`third_party/SPOTER_LICENSE.txt`](../third_party/SPOTER_LICENSE.txt).

`native_profiles.py` is explicitly marked Apache-2.0 and identifies the new
NumPy compatibility implementation, fixed schemas, historical ordering,
validation, and finite-input safeguards as modifications. This exception is
retained alongside the toolkit's own MIT source license. No SPOTER/SL-GCN neural
architecture, upstream dataset, or pretrained checkpoint is redistributed by
this module. Permission to distribute source code does not establish permission
to redistribute a particular model or a participant's recordings. The original
SPOTER repository lists separate dataset terms; those datasets are not included.
