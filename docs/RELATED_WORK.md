# Related work and the defensible scope of VSL Streaming Toolkit

Reviewed: 2026-10-03. This is a targeted primary-source review, not a systematic review or an acceptance prediction. Repository code and documentation were inspected; competing software was not installed or benchmarked. "Not established" below means the inspected material did not demonstrate the feature. It does not prove absence throughout a project or its history. No third-party implementation was copied during this review.

The proposed user workflow is: supply a compatible trained keypoint classifier and its preprocessing/labels; export or import an ONNX model bundle; validate that bundle; run a configurable self-hosted WebSocket server; receive segment-level gloss predictions. This is a credible software purpose. Each individual ingredient already has substantial prior art.

## Closest comparators

| Project | What primary material establishes | Relationship to VSL | What was not established by this review |
| --- | --- | --- | --- |
| [OpenHands](https://github.com/AI4Bharat/OpenHands), [official docs](https://openhands.ai4bharat.org/en/latest/) | Installable pose-based SLR library, dataset/model abstractions, config-driven training, pretrained models, video inference. Code identifies Apache-2.0. | Strongest established comparison for a reusable pose SLR research library. VSL cannot claim to introduce a reusable sign-recognition library. | Generic ONNX bundle export plus stateful keypoint WebSocket serving was not demonstrated by the reviewed README/docs. |
| [SignON SLR pipeline](https://github.com/signon-project/wp3-slr-pipeline), [SLR component](https://github.com/signon-project/wp3-slr-component) | Training/test/predict entry points; extensible models/datasets; checkpoints carry data-processing information. The separate Apache-2.0 component is a Docker Flask service accepting a video upload and returning JSON representations. | Closest comparison for a sign-specific path from model development to deployed service. Its documented "online" mode is a video request service; that word alone does not establish frame-by-frame streaming. | Generic ONNX export/parity and a keypoint event protocol with segmented gloss events were not established. |
| [signBridge](https://github.com/Uni-Creator/signBridge) | MIT-licensed Flutter/FastAPI application with WebSocket video input, MediaPipe processing, a 76-class video recognizer and configurable service. | Closest inspected application-level competitor for mobile-to-WebSocket recognition. A mobile demo and server integration alone offer little differentiation. | Model-independent keypoint bundle export/import and parity verification were not established. |
| [SLRT Online](https://github.com/FangyunWei/SLRT/tree/main/Online), [EMNLP 2024 paper](https://arxiv.org/abs/2401.05336) | Online CSLR from an isolated recognizer and sliding windows, with online translation extension. Official repo includes training/evaluation material and an online branch. | Closest algorithmic precedent. Sliding an isolated recognizer over continuous input is already published. This must be cited even if VSL uses a simpler motion segmenter. | General self-hosted ONNX/WebSocket toolkit for independent classifiers was not established. Main code reuse permission needs separate verification; no project-wide license was identified in the inspected top-level tree. |
| [Sign Language Translator](https://github.com/sign-language-translator/sign-language-translator) | Apache-2.0 Python framework, CLI, language abstractions, MediaPipe embeddings and concatenative text-to-sign synthesis. README marks the illustrated neural sign-to-text model as coming soon. | Prior art for extensible sign-language software, regional adapters and landmark utilities. Documented implemented features must be distinguished from goals. | A deployed generic streaming recognition backend was not established. |
| [Sign-Speak React SDK](https://github.com/Sign-Speak-Development/sign-speak-react-sdk) | A client SDK with WebSocket real-time ASL recognition and connection/recording controls. | Direct precedent for a developer-facing live sign-recognition interface. | Self-hosting the recognizer, arbitrary user-model ONNX export, and a clear reuse license were not established from the inspected README/tree. |
| [DFKI VideoProcessingTools](https://github.com/DFKI-SignLanguage/VideoProcessingTools), [2022 paper](https://www.dfki.de/fileadmin/user_upload/import/12436_Nunnari2022SLTAT_VideoProcToolkit.pdf) | Reusable Python/CLI preprocessing, video transformation and landmark extraction assembled from existing tools. Repository identifies GPL-3.0. | Clear precedent that domain-specific workflow integration can be useful software research. | Streaming classifier deployment is outside the focus described by these sources. |

The OpenASL name needs care: [chevalierNoir/OpenASL](https://github.com/chevalierNoir/OpenASL) is a dataset/preparation repository for open-domain ASL translation, not a direct generic model-serving toolkit. It states CC BY-NC-ND 4.0. Dataset terms and underlying video permissions must be checked independently of the license chosen for VSL code. Do not bundle it by assumption.

## Code-level observations that narrow the novelty claim

The inspected [signBridge handler](https://github.com/Uni-Creator/signBridge/blob/7b6aacc74a51e53047aea1b5c479e5a8ffa9ee2a/backend/app/websocket/websocket_handler.py) already implements a configuration handshake, frame validation, overlapping windows, bounded pending frames, connection-local state, shared worker pools, ordered inference results and cleanup. These are genuine existing engineering features, not just an architectural illustration. Its [processing module](https://github.com/Uni-Creator/signBridge/blob/7b6aacc74a51e53047aea1b5c479e5a8ffa9ee2a/backend/app/websocket/websocket_processing.py) works on buffered image frames and calls the model API. This differs from the proposed VSL keypoint tensor interface, but merely switching the payload to keypoints is insufficient research evidence.

SignON's [pipeline README](https://github.com/signon-project/wp3-slr-pipeline/blob/13f85a4686a71806b9b745c188127a30178bb7b9/README.md) already explains adding new model/dataset kinds and preserving processing information in checkpoints. VSL's manifest is therefore an explicit deployable contract and interoperability mechanism, not an invention of saving configuration with weights.

The [SLRT online README](https://github.com/FangyunWei/SLRT/blob/38a4f7b00da7a858d59b7fabe5093876a84db8e0/Online/README.md) explicitly describes training an isolated recognizer and applying sliding windows for online recognition. VSL should distinguish motion-gated isolated-word events from full continuous sign language recognition and translation; the former does not establish the latter.

## General infrastructure already provides many of the pieces

| Source | Existing capability | Consequence for VSL |
| --- | --- | --- |
| [MediaPipe Gesture Recognizer](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer) | Landmark/gesture processing for images, videos and live input, with model customization guidance. | Landmark extraction and live callbacks are dependencies or upstream capabilities. A task-specific temporal recognizer can build on them. |
| [ONNX Runtime Python](https://onnxruntime.ai/docs/get-started/with-python.html) | Loading and executing ONNX models, including exported PyTorch models. | ONNX inference itself is prior art. VSL's work is constraining and validating the sign-recognition interface and lifecycle. |
| [sherpa-onnx WebSocket documentation](https://k2-fsa.github.io/sherpa/onnx/websocket/index.html) | Streaming WebSocket clients/servers for ONNX speech recognition. | Exported model plus streaming server is an established adjacent-domain architecture. Avoid claiming that architecture as new. |
| [commlib-py](https://github.com/robotics-4-all/commlib-py) | A Python API over multiple messaging backends and communication patterns. | Transport adapters and broker substitution alone are generic middleware contributions already covered elsewhere. |

For the journal discussion, [AffectStream's author-institution publication record](https://pure.kaist.ac.kr/en/publications/affectstream-kafka-based-real-time-affect-monitoring-system-using/) identifies a SoftwareX 2025 framework for real-time wearable affect monitoring, with trace-based evaluations using three datasets. It supports evaluating a reusable domain pipeline with realistic traces. It does not establish a requirement for a new app, a minimum number of models, or an acceptance guarantee for VSL.

## Narrow proposed contribution

**A reusable, self-hosted runtime that connects compatible keypoint sequence classifiers to mobile or browser streams through an explicit model contract, configurable segmentation, and reproducible event-level evaluation.**

The software can contribute a coherent implementation of:

1. A model bundle tying weights to landmark ordering, coordinate convention, input layout, temporal sampling/padding, normalization, class ordering, output meaning and provenance. Reject an incompatible bundle before accepting predictions.
2. A reusable per-session segment state machine whose start/end/flush behavior is specified and replayable, with bounded memory, timestamp handling and explicit behavior for gaps and invalid input.
3. A complete import/export/validate/serve path, including numerical and class agreement on supplied representative examples, plus Python and WebSocket interfaces driven by the same core.
4. Evidence of reuse outside the original recognizer and Android client, and measurements of latency, segmentation quality, event correctness and resource use.

These are proposed software contributions, not claims of globally novel primitives. The extent implemented and the extent experimentally validated must be reported separately.

"Bring your own model" must mean **bring a model satisfying a documented interface**. Export cannot infer preprocessing from arbitrary weights, reconstruct an unknown architecture from a bare state dictionary, or automatically turn any offline video/CTC model into a segment classifier. A sensible first supported contract is a single keypoint-sequence input and a per-class score output. Other architectures need adapters and tests. The real user's ordered labels and preprocessing remain required input.

The release should describe itself as a sign-recognition streaming toolkit. Producing gloss labels does not establish natural-language translation. Showing transport tests with a toy model does not establish sign recognition accuracy.

## Evidence needed before a paper claims an advantage

| Question | Necessary evidence | Appropriate comparator |
| --- | --- | --- |
| Is integration actually reusable? | Run the original recognizer plus a second independently structured compatible model; document adapter/config work and client example. | A minimal direct ONNX Runtime + WebSocket implementation with the same models and hardware. |
| Does segmentation improve useful output? | Annotated untrimmed traces; boundary error, segment precision/recall, duplicate/missed gloss events, detection delay; tune only on a development split. | Fixed windows and the prior project segmenter. Compare to SLRT only when input, task and datasets permit a fair experiment. |
| Does export preserve behavior? | Real representative tensors from the expected preprocessing; logit tolerances, top-class agreement, changed predictions and a saved receipt. | Original framework execution using exactly the same input. |
| Does the server behave correctly? | Replay multiple interleaved sessions with gaps, invalid frames, disconnect/flush, slow clients and sustained overload. Report correctness and failures alongside p50/p95 latency and memory. | Same stream trace through the direct baseline and toolkit. |
| Is keypoint transport beneficial here? | Wire bytes, client extraction cost, server cost, device/network conditions and any accuracy change. | The same task with server-side extraction or the existing app pipeline, if feasible. |

No latency or quality superiority is asserted by this review. A simple library can be valuable when reuse and behavior are demonstrable; adding a GUI or recreating Redis does not establish those results.

## Inspection receipts and limits

GitHub API trees were queried to locate implementation and license files. Revisions observed:

- SignON pipeline: `13f85a4686a71806b9b745c188127a30178bb7b9`.
- SignON service: `1b81967978e847f06059979921abcedcdc4c4193`.
- SLRT: `38a4f7b00da7a858d59b7fabe5093876a84db8e0`.
- signBridge: `7b6aacc74a51e53047aea1b5c479e5a8ffa9ee2a`.
- Sign-Speak SDK: `768c78100101513bf56a499f597dfdb00551be22`; `src/network/websockets.ts` inspected.

Search also surfaced `signlangtk` / `ed-fish/Sign-Language-Toolkit`, but the linked GitHub README could not be retrieved during this review. It is an unresolved search lead, excluded from positive or negative feature claims. License mentions in this document identify observed upstream declarations; dependency/version-specific distribution obligations belong in the separate license audit. Public repository visibility is not itself a reuse grant.
