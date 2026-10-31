# Flutter capture and model compatibility

Flutter supplies the application interface. It does not define a landmark
detector, coordinate system, or recognition model. The intended application has
two modes, with independently identified capture profiles and a shared canonical
landmark contract. Matching that contract does **not** prove detector parity or
compatibility with the data used to train a particular checkpoint.

## One application, two capture modes

| Mode | Extraction and transport | Evidence to retain |
| --- | --- | --- |
| Live landmarks | Flutter controls a native bridge to the existing Android `LandmarkCapture` and `StreamSession`; the phone sends canonical frames over WebSocket | Original trace, final capture/transport receipt, server session log, bundle hashes and settings |
| Video for PC processing | The application records or selects a video; PC extraction uses the existing desktop Tasks extractor, then canonical frames enter the same toolkit | Original video hash, decoder/timestamp/rotation settings, detector asset hashes, extracted frames and capture receipt |

The live bridge must reuse the Android library's extraction and session logic.
It must not implement a second detector, hand assignment, or normalization in
Dart. Flutter may transform coordinates for a mirrored/cropped preview overlay;
those display coordinates must never replace the canonical observations.
The PC path currently uses **MediaPipe Tasks Pose + Hand**, not historical
MediaPipe Holistic. Its profile must remain separately identified.

## Confirmed extraction differences

The following describes the inspected implementations; it is not a parity claim.

| Property | Android library | Desktop `video.py` |
| --- | --- | --- |
| Profile | `android-mediapipe-tasks-pose-hands-v1` | `desktop-mediapipe-tasks-pose-hands-v1` |
| Detector | Separate Tasks Pose and Hand landmarkers | Separate Tasks Pose and Hand landmarkers |
| Execution | CPU, VIDEO, one pose, two hands, 0.5 thresholds | CPU, VIDEO, one pose, two hands, 0.5 thresholds |
| Runtime/assets | Tasks 0.10.26.1; two required asset SHA-256 values | Optional Python dependency pins MediaPipe 0.10.21; supplied asset hashes recorded |
| Hand geometry | Centroid of all 21 detected hand points | Detected hand wrist, point 0 |
| Assignment | Globally sorted wrist-distance candidates; greedy unique hand/side matching | Each hand selects its nearest visible pose wrist; closest candidate retained per side |
| Distance boundary | Candidate accepted when squared distance **< 0.08** | Wrist candidate accepted when squared distance **<= 0.08** |
| Fallback | Remaining unused hands use Tasks handedness verbatim if side vacant | Handedness used when no acceptable wrist candidate; first fallback retained unless replaced by closer wrist candidate |
| Missing groups | Retained as null; no hand cache | Retained as null; no hand cache |
| Hand visibility | Optional detector visibility, otherwise 1 | Explicitly 1 |
| Time | Monotonic analyzer-arrival milliseconds; ties advance by 1 ms | Decoder timestamps, or explicit frame-index/FPS synthesis; millisecond collisions rejected |
| Frame selection | Rate gate and CameraX KEEP_ONLY_LATEST | Time-based sampling over decoded frames |

Both association implementations use pose wrists 15/16 with visibility at least
0.5. Their candidate geometry, collision resolution, and boundary condition are
different. Identical settings and model assets do not remove these differences.
Any future policy alignment requires an explicit profile/version decision and
regression fixtures; historical receipts must continue to describe their actual
algorithm. Tasks tracking also makes frame history part of the experiment.

Android rotates pixels using `ImageProxy.imageInfo.rotationDegrees`; its front
preview is mirrored while inference is unmirrored. Desktop extraction attempts
to disable decoder auto-rotation and records whether that succeeds, then applies
explicit rotation and an optional declared mirrored-input correction. Inspect
that receipt rather than assuming the decoder honored the orientation setting.
Normalized image x/y/z are preserved without clipping to the image boundary.
Image coordinates and world coordinates are distinct outputs and not exchangeable.

The previous translator's Flutter interface can inform the visual design, but
its extraction path is not a drop-in replacement. Its native implementation has
a hand cache below 150 ms, GPU-to-CPU fallback, and wall-clock timestamps. Its
Dart path drops pose-null observations and uses another centroid assignment.
The retained ML Kit path supplies pose only, clips normalized x/y, and keeps
pixel-scale z. Reusing those paths would change the capture contract.

## Canonical observations and model tensors

Canonical frames retain sequence/time and nullable arrays of 33 pose points,
21 left-hand points and 21 right-hand points. Each point carries x/y/z/visibility.
The server owns point selection, missing-value handling and model preprocessing.
Do not mirror, reorder, clamp, normalize, interpolate or fill observations in Dart.

| Profile | Tensor | Temporal and channel semantics |
| --- | --- | --- |
| `spoter54-legacy-v1` | float32 `1 x 70 x 54 x 2`, BTVC | x/y; cycle shorter sequences, otherwise 70 endpoint-inclusive linspace indices rounded down |
| `slgcn27-bone-v1` | float32 `1 x 3 x 150 x 27 x 1`, BCTVM | Bone x/y and edge confidence; expand sequences shorter than 30, normalize, then cycle or retain prefix to 150 |

SPOTER selects 12 body slots, including a zero neck, then 21 points per hand.
Its exact body order is `(0,-1,5,2,8,7,12,11,14,13,16,15)`; hand order is
`(0,8,7,6,5,12,11,10,9,16,15,14,13,20,19,18,17,4,3,2,1)`.
The historical alternating-name hand normalization and final subtraction of
0.5 are deliberately preserved. SPOTER validates z but does not use it.
SL-GCN selects pose `(0,11,12,13,14,15,16)` and ten points per hand, with
confidence 1 for present hands. Its third channel is **confidence, not depth**.
See [Preprocessing profiles](PREPROCESSING_PROFILES.md) for complete details.

The local 400-class SPOTER bundle inspected for this integration declares
`poses` input, `logits` output, and the 70-frame SPOTER profile above. Its manifest
records source-framework/export parity as unverified. A model filename, archived
accuracy table, or valid tensor shape must not override that evidence boundary.

## Training-extractor uncertainty

The previous server contains Holistic extraction with detection confidence 0.8;
tracking confidence is 0.5 in its CLI/inference paths and 0.6 in another endpoint.
Thus even the historical server does not identify a single extraction setting.
Archived minimal model code calls `pose_format.utils.holistic.load_holistic`,
but its requirements leave `pose-format` unpinned and bound MediaPipe only by
`<0.10.30`. Exact training-extractor reconstruction is not established.
An archived generic SPOTER transform also uses prefix truncation, unlike the
current deployment profile's linspace selection for long sequences. Bind code,
dependency versions, extraction cache and preprocessing configuration to the
exact checkpoint before making a training-equivalence claim or changing it.

Holistic uses a coordinated graph with pose-guided regions and hand recropping.
Two independently invoked Tasks detectors do not reproduce that graph merely
because their final arrays have the same lengths. Current preprocessing checks
establish a deployment-transform contract, not original training equivalence.

## Validation protocol

1. **Bridge fidelity:** inject asymmetric canonical observations, null groups,
   out-of-image finite coordinates and distinct left/right hands. Verify that
   bridge serialization preserves point order, values, nulls and timestamps.
2. **Same decoded inputs:** decode a consented reference clip once to lossless
   RGB frames with index, dimensions, pixel hash and timestamp manifest. Feed
   identical pixels/times in the same order to freshly initialized Android and
   desktop VIDEO detectors. Pin assets, options, runtime and delegate. Retain raw
   candidate hands and handedness before assignment. Test historical Holistic
   only as a separately configured third profile.
3. **Measure differences:** compare missingness, independently annotated
   anatomical handedness, distances on jointly present points, selected temporal
   indices, model tensors, segmentation and output. Establish detector tolerances
   from repeat runs; do not demand unjustified bitwise detector equality.
4. **Labelled pilot:** use a signer-reviewed protocol and reference annotations
   for recognition/segmentation metrics. A UI smoke run is not such a pilot.

Generated fixtures and replayed traces are engineering checks. Replaying one
saved trace tests deterministic downstream behavior, not detector parity.
Two separately recorded live sessions are not the same-input experiment.
The existing 182-frame camera trace contains observations but no original video
or raw pre-assignment candidates; it cannot resolve detector or training parity.

## Source evidence and official documentation

- [`video.py`](../src/vsl_streaming/video.py): desktop extraction, assignment and provenance.
- [`LandmarkCapture.kt`](../clients/android/stream-client/src/main/java/org/vslstream/client/LandmarkCapture.kt): native extraction and receipt.
- [`StreamSession.kt`](../clients/android/stream-client/src/main/java/org/vslstream/client/StreamSession.kt): native transport lifecycle.
- [`native_profiles.py`](../src/vsl_streaming/native_profiles.py): tensor contracts and historical transforms.
- Previous translator: `android/app/src/main/kotlin/com/example/vsl_translator/MainActivity.kt`, `lib/features/camera/camera_screen.dart`, `vsl_server/tools/extract_keypoints.py`, `vsl_server/app.py`.
- Archived minimal code: `E:/Paper/MultiModel Paper/paper_results/01_sign_vsl400_5models/02_rgb_results_and_code/02_minimal_code_cache/minimal_code/features/transforms/base.py` and `pipelines/spoter_graph_classification.py`; this is a local audit pointer, not a public dependency.
- [Google Hand Landmarker guide](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python): modes, tracking, timestamps and coordinate outputs.
- [Google Pose Landmarker guide](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python): pose options and execution modes.
- [MediaPipe Holistic documentation](https://chuoling.github.io/mediapipe/solutions/holistic.html): coordinated pipeline, recropping and historical options.
