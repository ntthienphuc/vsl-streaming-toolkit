# Software metadata

| Item | Value |
| --- | --- |
| Software name | VSL Streaming Toolkit |
| Released software version | 0.2.1 |
| Version-specific release link | https://github.com/ntthienphuc/vsl-streaming-toolkit/tree/v0.2.1 |
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

Use the v0.2.1 tag and its release assets to identify this version. At the
11 October 2026 audit the tag resolves to commit
`eace06d35b8b130a48f98140af353b4f598e3d24`. Documentation changes on main
after that freeze are not changes to the tagged release. The release
validation receipt records the artifact hashes and completed software checks;
verify the checksums on downloaded files before an experimental campaign.
See [SOFTWAREX_SUBMISSION.md](SOFTWAREX_SUBMISSION.md) for remaining gates.

## SoftwareX code metadata

These values use the exact C1–C8 labels of the official Original Software
Publication Word template, Version 6 (March 2026), retrieved and inspected on
11 October 2026. Keep its first two columns unchanged when filling the Word
file; this Markdown table supplies values, not the submission layout. The supplied
34-page Guide for Authors requires a version-specific GitHub retrieval URL,
README.md, LICENSE.txt and source in repo/src (p. 30). This repository has those
paths. Preserve the combined source license and third-party notices when making
the final submission archive.

| Nr | Code metadata description | Metadata |
| --- | --- | --- |
| C1 | Current code version | 0.2.1 |
| C2 | Permanent link to code/repository used for this code version | https://github.com/ntthienphuc/vsl-streaming-toolkit/tree/v0.2.1 |
| C3 | Legal code license | MIT AND Apache-2.0; original source MIT, native preprocessing Apache-2.0; see THIRD_PARTY_NOTICES.md |
| C4 | Code versioning system used | Git |
| C5 | Software code languages, tools and services used | Python, NumPy, ONNX, ONNX Runtime; optional FastAPI, Uvicorn, websockets, PyTorch, MediaPipe and OpenCV; Kotlin, CameraX and OkHttp for Android |
| C6 | Compilation requirements, operating environments and dependencies | Python >=3.9; no source compilation step for the toolkit; CI specifies Windows/Ubuntu CPU environments; optional Android build requires Java 17 and Android SDK 36, with minimum device API 26 |
| C7 | If available, link to developer documentation/manual | https://github.com/ntthienphuc/vsl-streaming-toolkit/tree/v0.2.1/docs and tagged README/REPRODUCE |
| C8 | Support email for questions | Author must supply a monitored correspondence/support email. Supplementary support: https://github.com/ntthienphuc/vsl-streaming-toolkit/issues |

The submitting author must supply a monitored correspondence email on the
title page, as required by the supplied guide (p. 16), and resolve the support
email field in the actual template. A GitHub noreply commit address is not a
monitored support address. No DOI/archive identifier is assigned by this
metadata. The guide prefers a software persistent identifier but permits a URL
when no PID exists (p. 28); absence of a DOI is not itself a verified submission
prohibition.

Use the tagged source and its release checksums when linking results to this
version. A mutable `main` branch is useful for development but does not identify
the source used in a particular experiment. Private earlier results retain their
original artifact hashes and must not be reassigned to this version without
checking the relevant source/model changes.

The source license `MIT AND Apache-2.0` does not grant rights to third-party
model weights, detector assets, or participant traces, and is separate from the
article's eventual publishing license. At submission the author must provide a
data-availability statement: deposit and cite/link supporting research data, or
explain why sharing is not possible (Option C, guide p. 22). Public synthetic
fixtures, restricted real inputs and future uncollected Results must be described
separately. See [submission preparation](SOFTWAREX_SUBMISSION.md) for the supplied
guide's hash/page-reference convention and remaining author-controlled fields.
