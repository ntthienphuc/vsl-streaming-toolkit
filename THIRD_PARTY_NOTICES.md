# Third-party notices

Original toolkit source is MIT, copyright 2026 Nguyễn Trần Thiên Phúc.
`src/vsl_streaming/native_profiles.py` is Apache-2.0 and retains the SPOTER
normalization lineage (copyright 2021–2022 Matyáš Boháček). The combined source
license expression is **MIT AND Apache-2.0**. See the retained full
[Apache license](third_party/SPOTER_LICENSE.txt) and module attribution.
The compatibility implementation was modified for the owner's deployment
contract; it is not an unmodified upstream model or a distribution of weights.
The audited upstream [SPOTER revision](https://github.com/matyasbohacek/spoter/tree/0f909bf92690772f43f0062be41860ed85b461ad)
identifies the normalization lineage. No other cited competing toolkit is vendored.

Dependencies are installed separately; the toolkit license does not replace
their terms. Preserve applicable license and notice files when redistributing
an assembled environment, Android APK or container.

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

No Redis installation is required or distributed. Optional MediaPipe and OpenCV
packages perform extraction; their code licenses do not automatically cover
all downloadable detector assets, videos or recognition weights. Those assets
must be obtained separately, with their own provenance and terms retained.
The asset download helper is a convenience, not a new license grant.

Pretrained recognition architectures, VSL training datasets and human keypoint
recordings are not distributed. A separately supplied owner-model adapter is
subject to its source and asset terms. The legacy bridge executes a trusted
owner checkout; the built-in profiles remove that dependency only for their
two declared numerical contracts.

[Related work](docs/RELATED_WORK.md) cites inspected upstream tools for comparison.
Their implementations are not vendored. The synthetic fixture generator and
protocol/segmentation implementation are part of this toolkit's MIT source.

## Optional research tools

The separate research/host-replay-20261009 capsule uses psutil 7.2.2 (BSD-3-Clause) as a resource observer and optional Playwright 1.62.0 (Apache-2.0) for desktop-browser checks. Distribution declarations are recorded in its RESEARCH_DEPENDENCY_LICENSES.json. They are installed separately; preserve their native/transitive notices when redistributing an environment. The capsule contains authored harness code and numeric observations, without model weights, human landmarks or external recognizer implementations.

## Optional capture and Android direct dependencies

| Component | Declared upstream code license | Role |
| --- | --- | --- |
| [MediaPipe](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE) | Apache-2.0 | Python Tasks and Android Tasks Vision; downloaded detector assets have their own applicable terms |
| [OpenCV](https://github.com/opencv/opencv/blob/4.x/LICENSE) | Apache-2.0 | Optional decoded-video input; binary distributions include additional notices |
| [AndroidX](https://android.googlesource.com/platform/frameworks/support/+/androidx-main/LICENSE.txt) | Apache-2.0 | CameraX and activity integration |
| [OkHttp](https://github.com/square/okhttp/blob/master/LICENSE.txt) | Apache-2.0 | Android WebSocket transport |
| [Gson](https://github.com/google/gson/blob/main/LICENSE) | Apache-2.0 | Android JSON serialization |
| [Guava](https://github.com/google/guava/blob/master/LICENSE) | Apache-2.0 | Android asynchronous utilities |
| [Kotlin](https://github.com/JetBrains/kotlin/blob/master/license/LICENSE.txt) | Apache-2.0 | Android language/runtime tooling |
| [Gradle](https://github.com/gradle/gradle/blob/master/LICENSE) | Apache-2.0 | Included build wrapper and build tooling |
| [JUnit 4](https://github.com/junit-team/junit4/blob/main/LICENSE-junit.txt) | EPL-1.0 | Android local test dependency; not an application runtime dependency |

The pinned direct Android versions are declared in `clients/android/*/build.gradle.kts`.
Python capture versions are declared by the `video` extra in `pyproject.toml`.
This inventory does not replace notices for resolved transitive/native code.
The Android guide records build and asset preparation; obtain and retain any
asset-specific license information before redistributing an asset-bearing APK.
