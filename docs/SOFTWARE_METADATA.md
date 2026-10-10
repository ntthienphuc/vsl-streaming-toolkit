# Software metadata

| Item | Value |
| --- | --- |
| Software name | VSL Streaming Toolkit |
| Current version | 0.2.1 |
| Permanent version link | https://github.com/ntthienphuc/vsl-streaming-toolkit/tree/v0.2.1 |
| Source repository | https://github.com/ntthienphuc/vsl-streaming-toolkit |
| Release artifacts | https://github.com/ntthienphuc/vsl-streaming-toolkit/releases/tag/v0.2.1 |
| Source license | MIT AND Apache-2.0; copyright 2026 Nguyễn Trần Thiên Phúc |
| Language | Python; Kotlin/Android reference client; PowerShell demonstration launcher |
| Main requirements | Python >=3.9, NumPy, ONNX, ONNX Runtime |
| Optional server / export | FastAPI, Uvicorn, websockets / PyTorch; optional video extraction uses MediaPipe and OpenCV |
| Installation | Repository checkout or release wheel; server/export/video extras |
| User documentation | README.md, REPRODUCE.md, MODEL_CONTRACT.md, SEGMENTATION.md |
| Support | GitHub Issues |
| Citation | CITATION.cff |
| Software DOI | Not assigned |
| Journal publication | Not asserted by this release |

Use the v0.2.1 tag and its release assets to identify this version. The release
validation receipt records the artifact hashes and completed software checks;
verify the checksums on downloaded files before an experimental campaign.
See [SOFTWAREX_SUBMISSION.md](SOFTWAREX_SUBMISSION.md) for remaining gates.

## SoftwareX code metadata

| Code | Item | Value |
| --- | --- | --- |
| C1 | Current code version | 0.2.1 |
| C2 | Permanent repository link for this version | https://github.com/ntthienphuc/vsl-streaming-toolkit/tree/v0.2.1 |
| C3 | Legal code license | MIT AND Apache-2.0; original source MIT, native preprocessing Apache-2.0; see THIRD_PARTY_NOTICES.md |
| C4 | Code versioning system used | Git |
| C5 | Software languages, tools and services used | Python, NumPy, ONNX, ONNX Runtime; optional FastAPI, Uvicorn, websockets, PyTorch, MediaPipe and OpenCV; Kotlin, CameraX and OkHttp for Android |
| C6 | Compilation requirements, operating environments and dependencies | Python >=3.9; no source compilation step for the toolkit; CI specifies Windows/Ubuntu CPU environments; optional Android build requires Java 17 and Android SDK 36, with minimum device API 26 |
| C7 | Link to developer documentation/manual | https://github.com/ntthienphuc/vsl-streaming-toolkit/tree/v0.2.1/docs and tagged README/REPRODUCE |
| C8 | Support email for questions | Author must supply a monitored correspondence/support email. Supplementary support: https://github.com/ntthienphuc/vsl-streaming-toolkit/issues |

The submitting author must supply a real correspondence email if requested by
the manuscript template; a GitHub noreply commit address is not a monitored
support address. A DOI/archive identifier is not assigned by this metadata.

Use the tagged source and its release checksums when linking results to this
version. A mutable `main` branch is useful for development but does not identify
the source used in a particular experiment. Private earlier results retain their
original artifact hashes and must not be reassigned to this version without
checking the relevant source/model changes.
