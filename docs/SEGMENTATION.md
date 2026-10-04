# Stream segmentation contract

`StreamSession` is an in-memory, dependency-free state machine for one ordered
stream. A caller must serialize calls on each session. Different sessions do not
share buffers. Results depend on frame order and timestamps, not batch boundaries.

Every frame has a nonnegative integer `seq` and a finite, nonnegative
`timestamp_ms`. Both strictly increase, including after `flush()`. A full batch
is validated and copied before state changes. Rejected batches leave state
unchanged and raise `ProtocolError`, whose `code` identifies the failure.
`reset()` clears buffers, ordering, counters, and the representation contract.

`StreamConfig` defaults:

| Setting | Default | Meaning |
| --- | ---: | --- |
| `mode` | `signing_space` | Geometry heuristic or `fixed_window` |
| `window_frames` | 60 | Non-overlapping window length in fixed mode |
| `angle_threshold` | 140 | Maximum active elbow angle in degrees |
| `visibility_threshold` | 0.5 | Minimum visibility of required landmarks |
| `min_up_frames` | 4 | Consecutive active frames confirming onset |
| `min_down_frames` | 4 | Consecutive inactive frames required to end |
| `min_down_ms` | 300 | Elapsed time since first inactive frame required to end |
| `min_segment_frames` | 6 | Minimum retained frames for an emitted segment |
| `max_gap_ms` | 1000 | Maximum interval between adjacent observations |
| `max_buffer_frames` | 300 | Maximum pending segment size |

## Signing-space mode

Frames use `pose_landmarks` (33 objects), `left_hand_landmarks` and
`right_hand_landmarks` (21 objects each). Each field may be omitted or null.
Landmarks require finite `x`, `y`; `z` defaults to zero and `visibility` to one.
Visibility must lie in [0, 1]. Coordinates use MediaPipe normalized image axes;
the API permits coordinates outside [0, 1] for off-screen estimates.

An arm is active when its visible shoulder, elbow, and wrist form an elbow angle
strictly between zero and `angle_threshold`. A straight arm can also be active
when its detected hand wrist is visible and the pose wrist is sufficiently above
the hip: margin = max(0.04, 0.12 * vertical torso height). If the hip is not
visible, the wrist must be above shoulder y + 0.30. Either arm activates the
shared segment. Missing or low-visibility pose is inactive; prior geometry is
never reused.

The onset debounce retains all consecutive candidate frames. Once active,
inactive frames are retained until **both** the frame-count and time thresholds
are met. Brief dropout therefore stays inside a segment. This is a heuristic
for pauses between signs, not a validated general continuous-language boundary
detector. Its behavior is independently implemented and has not been shown
equivalent to the legacy VSL segmenter.

## Fixed-window mode

Use this mode to connect a trained clip classifier without a signing-space
assumption. A frame can contain `points`, a finite, nonempty rectangular N by C
matrix, or the MediaPipe fields above. Representation and points shape must
remain consistent until reset. Consecutive frames form non-overlapping windows;
there is no activity gate. `min_segment_frames <= window_frames <=
max_buffer_frames` is required. The model's preprocessing adapter owns tensor
packing, sampling, and normalization.

This is windowed classification. It does not convert a clip classifier into a
causal model or establish that windows coincide with individual signs.

## End conditions and observability

`push_batch()` returns **all** completed segments in order. Segment fields are
`id`, `frames`, `start_ms`, `end_ms`, and `reason`. IDs increase within a session
and restart after reset. `to_dict(include_frames=False)` returns metadata and
`frame_count` without the frame payload.

| Reason | Condition |
| --- | --- |
| `inactive` | Signing-space down debounce completes |
| `window` | A fixed window fills |
| `capacity` | Signing-space buffer fills; continued activity starts the next chunk |
| `gap` | Sequence number skips or elapsed frame interval exceeds `max_gap_ms` |
| `flush` | Caller explicitly ends pending work |

A gap closes eligible work before processing the new frame and clears debounce.
A buffer limit can split a long sign; downstream consumers should inspect
`reason`. A candidate without confirmed onset, or a chunk shorter than
`min_segment_frames`, is discarded. `status()` exposes discarded candidate frame
count, gaps, emitted segments, received frames, last sequence and time, current
buffer size, and debounce counts. Idle observations are not counted as discarded
candidate frames. Capacity limits pending segment storage; callers should also
limit batch size to bound validation memory.
