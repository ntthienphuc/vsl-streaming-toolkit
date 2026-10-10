# SoftwareX submission preparation and unresolved gates

Reviewed on 10 October 2026. Software target: **v0.2.1**.
This is a project preparation record, not an editorial decision or a declaration
that the paper is ready to submit. Real Results are deliberately reserved for the
next experimental phase.

## Primary-source access and limits

| Source | Access result and use |
| --- | --- |
| [Elsevier Research Elements](https://www.elsevier.com/researcher/author/tools-and-resources/research-elements-journals) | Read on 2026-10-10. Identifies SoftwareX as a research-software journal, describes application/reproducibility aims, and links its guide and template. |
| [SoftwareX Guide for Authors](https://www.sciencedirect.com/journal/softwarex/publish/guide-for-authors) | Direct web and HTTPS retrieval returned HTTP 403. Current detailed submission rules could not be verified from the primary page in this audit. |
| [Official original-software Word template](https://legacyfileshare.elsevier.com/promis_misc/softwarex-osp-template.docx) | Exact URL extracted from the live Elsevier page. Download returned HTTP 403 locally; the web reader could not parse its content type. This establishes the official link, not that the current template was reviewed. |
| [Elsevier AI policy](https://www.elsevier.com/about/policies-and-standards/generative-ai-policies-for-journals) | Read on 2026-10-10; page states updated June 2026. Informs the disclosure and figure preparation actions below. |

Do not turn third-party summaries or a previously saved template into a claim
that the current web guide was verified. The older manuscript's preparation note
records a version-6 template and a 4,000-word body target; other search leads
conflict. For this project, use a **conservative 3,000-word planning budget**,
including abstract and captions, and keep room for results. This is an editorial
preparation choice while direct verification remains unresolved, not a verified
current journal limit. Recheck the official guide/template before submission,
including word/figure limits, metadata labels and required upload items.

## Concrete readiness matrix

“Prepared” describes a document or implementation, not a successful experiment.

| Area | Present preparation | Remaining gate |
| --- | --- | --- |
| Software purpose | README and model/stream contracts describe reusable isolated-sign classifier deployment. | Demonstrate a permissioned natural-sign application; do not claim a new recognizer. |
| Related software | [RELATED_WORK.md](RELATED_WORK.md) links inspected immutable sources, including Signa, signBridge, OpenHands and SignON. | Keep source-inspection comparisons distinct from measured baselines; no blanket feature-absence claims. |
| Versioned source | Git repository, changelog, citation metadata and v0.2.1 release identifiers. | Use the release validation receipt, matching CI and verified downloaded checksums; freeze these identities before collecting Results. |
| Licensing | MIT AND Apache-2.0 source expression and SPOTER notice/lineage retained. | Check final wheel/source notices; separately document every model, detector and recording access condition. |
| Installation | Public synthetic path, optional server/export/video groups and Android instructions. | Validate the final installed artifacts on the stated environments; disclose skipped platform/device checks. |
| Illustrative examples | Synthetic demo and event-evaluation example are independently runnable. | Add lawful acquisition steps for the eventual real model/trace example; synthetic labels do not establish sign accuracy. |
| Article architecture | New draft should describe native profiles, optional capture, Android transport and the evaluator together. | Preserve v0.1.2 draft/study as an archive. Never silently migrate its numbers to v0.2.1. |
| Results | Evaluation interfaces and prospective protocol are prepared. | Intentionally pending: annotations, device campaign, timing and real-stream outcomes. |
| Impact | Documented interoperability and diagnostic use cases. | External reuse, reduced effort and usability claims require evidence; describe intended impact until measured. |
| Code metadata | [SOFTWARE_METADATA.md](SOFTWARE_METADATA.md) supplies C1–C8 software values. | Author supplies a real support email and verifies final template labels; an issue URL is supplementary support. |
| Authorship/declarations | Explicit author-supplied fields preserve uncertainty. | Confirm affiliation, correspondence, CRediT, funding, competing interests and applicable participant/ethics statements. |
| Availability | Public code/synthetic data versus restricted real artifacts are distinguished. | Provide an actionable lawful acquisition route or state restrictions plainly; hashes alone do not grant access. |
| Submission format | Short five-part article is planned. | Apply the freshly obtained official template, check rendering and upload requirements, and review the final package. |

## Article structure and claim discipline

Retain the established working structure: motivation and significance; software
description; illustrative examples; impact; conclusions. Put pending measurements
in a clearly marked Results subsection under the illustrative examples until the
final template is checked. Documentation can carry detailed protocol schemas and
installation commands so the article can explain scientific utility and evidence.

The central proposition is that explicit classifier interpretation and observable
stream behavior support reproducible integration. It is testable through
onboarding, deterministic replay, failure handling and actual application studies.
Do not describe ONNX serving, motion gating, mobile capture or reusable SLR
libraries as new in themselves.

A reviewer should be able to trace each factual statement to one of:

- Released code and a documented contract.
- A final-artifact validation receipt with exact environment and source identity.
- A completed, version-bound measurement using permissioned inputs.
- A cited upstream source with a bounded comparison.
- An explicitly prospective goal or limitation.

No numerical placeholder should resemble a real result. Keep old results attached
to their original release even when a later compatibility check succeeds. Compile
and transport tests do not validate a physical camera, linguistic boundaries or
signer-independent accuracy.

## Disclosure and figures

The verified Elsevier policy requires a manuscript-preparation disclosure for
substantive AI assistance, naming the tool and purpose with author oversight.
Research use, including AI-assisted coding, belongs in the Methods description.
Record actual assistance; do not fabricate author review, declarations or tool
versions. The final author must check the references and accept responsibility.

The same policy permits AI-assisted explanatory diagrams with caption/general
disclosure and data visualizations faithfully produced by reproducible methods
from actual data. It prohibits general-purpose generative image tools for
graphical abstracts. For this project, retain editable architecture-diagram
source and use plotting code tied to recorded data for future result figures.
An attractive figure cannot replace an unperformed experiment.

## Freeze before the real campaign

Record the source commit and installed artifact hash; environment and runtime
provider; model/label/profile identities; detector asset hashes and capture clock
policy; annotation version and source-group split; segmentation/evaluation
settings; measurement boundaries and exclusion rules. Preserve raw observations,
errors, rejections and incomplete sessions. Use a development set for tuning and
keep evaluation inputs distinct.

The minimal next study should answer the manuscript's integration questions
before expanding features: compatible model onboarding; agreement on identical
prepared inputs; annotated event behavior; and a measured capture-to-display or
explicitly narrower host path. The exact design belongs in the prospective
measurement plan. This checklist creates no experiment outcomes and promises no
acceptance probability.
