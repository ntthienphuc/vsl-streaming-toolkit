# Third-party notices

Toolkit source is MIT, copyright 2026 Nguyễn Trần Thiên Phúc. Dependencies are
installed separately; the toolkit license does not replace their terms.

| Dependency | Upstream license | Role / upstream source |
| --- | --- | --- |
| NumPy | BSD-3-Clause, bundled notices | [Tensor preparation](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| ONNX Runtime | MIT, third-party notices | [Execution](https://github.com/microsoft/onnxruntime/blob/main/LICENSE) |
| ONNX | Apache-2.0 | [Graph validation](https://github.com/onnx/onnx/blob/main/LICENSE) |
| FastAPI | MIT | [Optional server](https://github.com/fastapi/fastapi/blob/master/LICENSE) |
| Starlette | BSD-3-Clause | [ASGI dependency](https://github.com/Kludex/starlette/blob/main/LICENSE.md) |
| Pydantic | MIT | [Configuration dependency](https://github.com/pydantic/pydantic/blob/main/LICENSE) |
| Uvicorn | BSD-3-Clause | [ASGI serving](https://github.com/Kludex/uvicorn/blob/main/LICENSE.md) |
| websockets | BSD-3-Clause | [Transport and client](https://github.com/python-websockets/websockets/blob/main/LICENSE) |
| PyTorch | BSD-3-Clause, bundled notices | [Optional export](https://github.com/pytorch/pytorch/blob/main/LICENSE) |
| HTTPX | BSD-3-Clause | [Development tests](https://github.com/encode/httpx/blob/master/LICENSE.md) |
| build / setuptools / wheel | MIT | [Packaging tools](https://packaging.python.org/en/latest/key_projects/) |

Installed distributions contain their own full license/notice files. Preserve
these when redistributing an environment or container. This table summarizes
upstream declarations and does not substitute for version-specific full texts
or a complete native/transitive notice inventory.

Redis server/client, MediaPipe, OpenCV, pretrained recognition architectures,
VSL training datasets and recorded keypoints are not distributed here. No Redis
installation is needed. A separately provided model, dataset or owner-code
adapter remains subject to its own terms. The optional legacy adapter calls an
owner checkout and does not copy its implementation or grant its redistribution.

[Related work](docs/RELATED_WORK.md) cites inspected upstream tools for comparison.
Their implementations are not vendored. The synthetic fixture generator and
protocol/segmentation implementation are part of this toolkit's MIT source.
