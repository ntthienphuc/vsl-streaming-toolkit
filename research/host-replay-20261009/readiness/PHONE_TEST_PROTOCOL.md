# Phone evaluation protocol — pending actual device

Status: no physical smartphone test has been performed. This document is a prospective protocol. Host receipts and desktop browser checks cannot fill phone result cells.

## Record the test identity

Record date/operator, consent or authority for the selected data, phone make/model/OS/browser versions, host CPU/OS/power state, installed toolkit version, checkpoint SHA-256, bundle profile/config hashes, execution provider, landmark extractor version, LAN topology and access-point model/band, approximate distance, and whether VPN/client isolation is present. Use coded participant IDs if human data is later authorized. Do not put identifiable videos or private landmark traces in a public paper repository; establish retention, access and withdrawal arrangements before capture.

| Run | Device/browser | Input artifact and hash | Bundle/config hashes | Route | Batch size | Sent frames | Responses | Predicted/rejected | RTT p50/p95/max | Status |
|---|---|---|---|---|---|---:|---:|---|---|---|
| H | Host browser, loopback | known permitted replay | record | loopback | record | pending | pending | pending | pending | pending |
| P | Physical phone | same replay | identical | phone to LAN host | identical | pending | pending | pending | pending | pending |
| C | Phone camera, future client | permissioned capture | record | phone to LAN host | record | pending | pending | pending | pending | NOT IMPLEMENTED |

## Transport replay sequence

1. Start the optional LAN fixture as documented in README. From the phone verify `/health` and `/v1/config`, then open `/readiness`. Record actual host address, port and successful/failed connection. Do not alter firewall rules as part of this protocol automatically.
2. Confirm permission and run the built-in synthetic 8-frame fixture. With batch size 3 expect three responses and three predicted events (3, 3, 2 frames). Export the phone receipt. This checks browser transport only.
3. Repeat on the host browser with the same fixture and settings. Then use a known, permitted real replay and exact matching model/config on both devices. For real replay, record actual expected event counts from the frozen offline reference; do not assume the synthetic 3-event count applies.
4. Compare event IDs, reasons, boundaries, labels, and scores with the reference, excluding timing fields. Repeat using at least two batch sizes and final flush. Record any discrepancy. A complete event match supports replay consistency, not natural signing accuracy.
5. Reset: confirm state counters clear. Flush: verify remaining valid segments are emitted and short candidates are accounted for as configured. Flush preserves ordering. Reconnect: expect a new session and empty state; replay all desired data from its beginning. A cached request retry is connection-local, bounded by cache retention, and not durable across reconnects.
6. Intentionally pause reading or switch the browser briefly to background, then resume. Record elapsed time, response/frame counts, close codes and timeouts. Mobile background throttling may change behavior. A timeout means unknown completion until reconciled; it does not cancel server work. Disconnecting during a pending request can leave inference already running.

## Coordinate and capture contract gate

Before any actual camera study, implement and audit a separate capture/extraction path against the bundle contract. Record and verify all of the following:

- Source frame resolution/orientation, camera facing, rotation/crop/resize, and whether preview mirroring changes coordinates. CSS preview mirroring must not silently swap anatomical left/right.
- Exact landmark order (pose/left hand/right hand), channel order, point count, x/y/z meaning and scale, visibility, missing-hand and missing-pose convention, and any already applied centering/scaling. Do not normalize twice. The server contract, profile and adapter decide input requirements; there is no universal 2×2 or normalized-coordinate assumption.
- Use monotonic capture-relative timestamps in milliseconds and strictly increasing sequence IDs. Preserve acquisition time across batching; do not replace it with upload time. Record dropped frames and sequence jumps. Monotonic timestamps from phone and host cannot be directly subtracted without clock synchronization.
- Check the active `max_gap_ms`, `max_batch_frames`, `max_message_bytes`, `min_segment_frames`, window/segmentation mode, final flush policy, and buffer settings. A gap can close an old segment; it must remain visible in results. Show both missing-data events and rejected segments in reports.
- Start/end gesture handling, trailing inactive frames, explicit flush before normal close, reset between recordings, and recovery after network loss. Obtain capture and data-use permission before recording; keep raw video optional and separately controlled.

## Timing and recognition claims

Browser RTT measures send to matching response on one clock. It contains browser scheduling, serialization/transfer, server gate waiting, processing and return transfer. `processing_ms` begins inside message processing and excludes semaphore wait and transport. `inference_ms` measures the model call for a particular segment. RTT minus these values is not an isolated Wi-Fi latency measure.

Report host loopback and phone-to-host LAN RTT separately, with input size, batch sizes, concurrency, request counts, warm-up policy and rejected/error/timeout counts. Report any camera/extractor time separately once implemented. To estimate network-only RTT, use a separately defined echo measurement; this implementation does not provide one. Keep one-way latency unavailable unless clock synchronization and uncertainty are documented.

Phone capture accuracy, WER/top-1/F1, signer-independent generalization and real-time deployment require permissioned labeled capture data and a prespecified evaluation protocol. No such metric is inferred from replay agreement or synthetic transport success. All physical phone measurements and camera-based tests remain pending.
