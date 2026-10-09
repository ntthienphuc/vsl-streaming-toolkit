# Deployment

## Local server

Install `.[server]` into a virtual environment and provide a validated bundle:

```sh
vsl-stream inspect --bundle my_bundle
vsl-stream serve --bundle my_bundle --config server.json
```

The default interface is http://127.0.0.1:8000/. The browser replays a keypoint
JSON file; it does not extract landmarks from a camera. A Python client is in
`examples/websocket_client.py`. Connect client applications to `/v1/stream`.
`/health` exposes readiness and active connection count; `/v1/config` exposes
the public contract without owner adapter arguments or local dependency paths.

Use `vsl-stream init --out my_settings` to create editable profile, labels,
factory arguments and server settings. Training must agree with that profile;
editing the template alone does not make an existing checkpoint compatible.

## Container

Generate the demo outside Docker as in REPRODUCE.md; the container needs no Torch.
With Docker Engine running, use the following Bash commands from the checkout:

```sh
docker build -t vsl-streaming-toolkit:0.1.2 .
docker run --rm -p 127.0.0.1:8000:8000 \
  -v "$PWD/demo_run:/models:ro" \
  -v "$PWD/demo_run:/config:ro" \
  vsl-streaming-toolkit:0.1.2
```

The image's defaults load `/models/bundle` and `/config/server.json`. For another
model, mount its parent directory under `/models` and the settings directory
under `/config`, or supply `--bundle` and `--config` arguments after the image
name. External Python adapters require their owner code to be installed in the
image separately; an ONNX graph alone does not supply that preprocessing.

For a public endpoint, configure the operator's reverse proxy, TLS and access
controls. This release supplies a single-process service with bounded sessions,
message/batch limits and inference concurrency. Redis, shared worker state,
durable reconnect continuation and built-in authentication are outside this
version. Requested providers must actually be installed; there is no silent
provider fallback. Generic CPU container checks do not validate Jetson GPU,
TensorRT, live capture or production-scale latency.
