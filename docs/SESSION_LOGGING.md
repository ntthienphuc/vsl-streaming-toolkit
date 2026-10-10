# Local session response evidence

Enable complete server response logging for an approved capture session:

```sh
vsl-stream serve --bundle my_bundle --config server.json --session-log-dir session_logs
```

Logging is off by default. Each accepted connection creates a distinct
`<session UUID>.session.jsonl` file. The directory is checked before serving;
unwritable storage prevents startup. A later log-open or write failure closes
that connection with code 1011 and releases its session slot. A response that
could not be recorded is not sent; processing may already have happened. Do
not automatically retry in a new connection as if the outcome were known.

Each line contains schema version 1, session ID, contiguous zero-based
`record_index`, UTC recording time, and monotonic elapsed milliseconds:

- `session_start`: toolkit version, server settings and their canonical JSON
  SHA-256, public preprocessing profile, bundle artifact hashes when present,
  requested provider and active ONNX providers. Injected test recognizers may
  have no bundle hashes or provider identity.
- `response`: complete ready, result or protocol-error response and zero-based
  `response_index`. Text requests include a SHA-256 of exact UTF-8 wire text,
  including whitespace; ready and binary-rejection records have no request hash.
- `send_complete`: response index after ASGI send returns. This is transport
  submission evidence, **not a client acknowledgement**.
- `session_end`: reason, observed disconnect code, final stream counters and
  `buffered_frames_abandoned`. Disconnect never automatically flushes or
  classifies the remainder. Explicitly flush and receive its response before
  ending a planned capture.

Responses are written before sending, one flushed JSON line at a time. Memory
does not grow with session duration, but disk usage does. Flush is not fsync:
process or machine failure may leave a partial final line or lose recent writes.
Missing end/send records, a noncontiguous index, an evidence failure, or nonzero
abandoned buffer makes the relevant evidence incomplete. Logs are not a durable
queue, reconnect state, exactly-once guarantee or authenticity proof. Preserve
hashes alongside the experiment manifest.

The logger omits incoming raw frames, adapter arguments and local dependency
paths. Predictions, request IDs and model error messages remain potentially
identifying research information. Store locally under approved retention/access
rules; do not publish natural-session logs by default. Custom recognizers
control their own response fields and must avoid returning raw inputs or
secrets. Public `/v1/config` does not expose the log-directory path.

For event evaluation, JSONL records are an evidence envelope, not prediction
JSON accepted directly by `vsl-stream evaluate`. After checking one start/end,
contiguous record/response indices, send completion, end reason and abandoned
buffers, assign the approved recording ID. Extract the `response` object
from each `type == "response"` row into
`{"recording_id": [response, ...]}`. Keep ready and cached retry responses:
the evaluator checks the session boundary and deduplicates cached events.
Do not silently discard unsent responses, errors, reset boundaries or
unflushed tails to improve metrics. Preserve the log hash and document
inclusion/exclusion decisions. See [event evaluation](EVENT_EVALUATION.md).

The browser replay page limits uploads to 10 MiB, displays only the latest
20 responses and closes its socket when an action ends. It adapts batch size
to both frame and byte limits. Use this server log or the Python client for
complete evidence; browser output is a bounded preview.
