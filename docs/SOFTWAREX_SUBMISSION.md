# SoftwareX submission preparation and unresolved gates

Reviewed on 11 October 2026 against the author-supplied SoftwareX Guide for
Authors PDF (34 pages). Software target: **v0.2.1**.
This is a project preparation record, not an editorial decision or a declaration
that the paper is ready to submit. Real Results are deliberately reserved for the
next experimental phase.

## Verified guide and official original-software template

The source is a supplied print-to-PDF of the
[SoftwareX Guide for Authors](https://www.sciencedirect.com/journal/softwarex/publish/guide-for-authors),
SHA-256 `104317c56d7d0b1b364863842b18fc7c34e5ea43e9776264aebe4718edd19cab`.
Page references below use that PDF's 1-based page order. The full text was read;
the earlier inability to retrieve the webpage no longer leaves these rules
unverified. The official Word template was also downloaded and inspected on
11 October 2026: **Version 6 (March 2026)**, SHA-256
`9fcf40ede96a2f188ee4ef77134e0596d01e1b65fd9db63f2874d29f2ecb916d`.
The LaTeX template was not inspected; the project uses the Word submission route.

| Requirement | Verified guide pages | Submission action |
| --- | --- | --- |
| Descriptive software paper plus open-source distribution/support material | 3–4 | Explain scientific use and reuse; preserve an executable public software package. |
| Maximum 4,000 words and six figures | 30 | Count abstract, running text, captions and footnotes; exclude title, authors, affiliations, references and metadata tables. Keep Results space without substituting a 3,000-word journal limit. |
| Exact journal template | 4, 23–24, 30–31 | Use the original-software template without changing its format settings. A new software version alone does not qualify as a Software Update article; that article type is for software previously published in SoftwareX. |
| Editable manuscript source | 15, 23, 31 | Submit single-column Word .doc/.docx; for the Word submission route upload .docx. A PDF alone is insufficient. LaTeX needs the review PDF and the complete source ZIP. |
| Figures and tables | 4, 18–20, 23–24 | Embed figures in the Word .docx and supply separately numbered artwork/source files with captions. Keep tables and equations editable; check artwork resolution, fonts and legibility. |
| Abstract and keywords | 16–17; Word template v6 | Guide ceiling: 250 words and 1–7 keywords. Follow the template's narrower target: abstract about 100 words and at most six keywords. |
| Highlights and graphical abstract | 17 | Both are encouraged, not mandatory. If included: highlights in a separate editable file, 3–5 bullets of at most 85 characters each including spaces; graphical abstract in a separate file meeting the stated size/format rules. |
| Public code repository | 4, 30 | Use GitHub with README.md, LICENSE.txt and source under repo/src; put the version-specific retrieval URL in the template metadata. The journal archives accepted code, not an unaccepted development snapshot. |
| Research data and availability statement | 22 | Under Option C, deposit research data and cite/link it, or explain why sharing is not possible. State availability at submission; restricted data must not be silently omitted or described as public. |
| References | 26–28 | Use numbered citations in order, resolve every citation/reference pair, and cite software with its version and retrievable identifier. A DOI is preferred; the guide permits a software URL when no PID exists. |

The [official original-software Word template](https://legacyfileshare.elsevier.com/promis_misc/softwarex-osp-template.docx)
was successfully retrieved. Its fixed C1–C8 metadata labels and five main
sections were inspected. The template targets six pages for Sections 1–5,
excluding metadata, tables, figures and references, and gives priority to the
4,000-word limit over page count. Preserve its styles and page settings when
filling the Word file. Template inspection does not close the remaining author,
study or final-document verification gates.

## Concrete readiness matrix

“Prepared” describes a document or implementation, not a successful experiment.

| Area | Present preparation | Remaining gate |
| --- | --- | --- |
| Software purpose | README and model/stream contracts describe reusable isolated-sign classifier deployment. | Demonstrate a permissioned natural-sign application; do not claim a new recognizer. |
| Related software | [RELATED_WORK.md](RELATED_WORK.md) links inspected immutable sources, including Signa, signBridge, OpenHands and SignON. | Keep source-inspection comparisons distinct from measured baselines; no blanket feature-absence claims. |
| Versioned source | Git repository, changelog, citation metadata and v0.2.1 release identifiers. | Use the release validation receipt, matching CI and verified downloaded checksums; freeze identities before collecting Results. These later documentation edits on main do not alter the v0.2.1 tag/assets. |
| Licensing | MIT AND Apache-2.0 source expression and SPOTER notice/lineage retained. | Check final wheel/source notices; separately document every model, detector and recording access condition. |
| Installation | Public synthetic path, optional server/export/video groups and Android instructions. | Validate the final installed artifacts on the stated environments; disclose skipped platform/device checks. |
| Illustrative examples | Synthetic demo and event-evaluation example are independently runnable. | Add lawful acquisition steps for the eventual real model/trace example; synthetic labels do not establish sign accuracy. |
| Article architecture | New draft should describe native profiles, optional capture, Android transport and the evaluator together. | Preserve v0.1.2 draft/study as an archive. Never silently migrate its numbers to v0.2.1. |
| Results | Evaluation interfaces and prospective protocol are prepared; a limited local physical-phone engineering smoke has occurred. | Article Results remain pending: natural-sign annotations, useful landmark capture, recognition/event measurements and defined timing/network/device campaigns. Local smoke is not public journal Results. |
| Impact | Documented interoperability and diagnostic use cases. | External reuse, reduced effort and usability claims require evidence; describe intended impact until measured. |
| Code metadata | [SOFTWARE_METADATA.md](SOFTWARE_METADATA.md) supplies the inspected template's C1–C8 values and labels. | Author supplies a monitored support email; corresponding-author email is required on the title page (p. 16). An issue URL is supplementary support. |
| Authorship/declarations | Explicit author-supplied fields preserve uncertainty. | Confirm authors/order/approval, full affiliations and correspondence (pp. 5–7, 15–16), CRediT (p. 25), funding/sponsor role and declarations-tool Word output (pp. 7–8), and applicable participant consent/ethics or justified exemption (pp. 13–14). |
| Availability | Public code/synthetic data versus restricted real artifacts are distinguished. | Prepare the required availability statement and deposit/citation or specific restriction explanation (p. 22); provide lawful acquisition steps where available. Hashes alone do not grant access. |
| Submission format | Guide and official Word template v6 inspected; five-part article preparation uses that template. | Verify the final filled DOCX, embedded/separate figures, word/figure limits and all upload items after Results and author declarations are complete. This checklist is not a completed submission package. |

## Article structure and claim discipline

Retain the template's five required main sections: Motivation and significance;
Software description; Illustrative examples; Impact; Conclusions. Put pending
measurements in a clearly marked Results subsection under Illustrative examples.
The inspected Word template, rather than the guide alone, establishes this
section list. Documentation
can carry detailed protocol schemas and installation commands so the article can
explain scientific utility and evidence.

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

## Disclosure, figures and author decisions

The supplied guide requires a manuscript-preparation AI disclosure before the
references at first submission when such tools were used (pp. 9–10). Name the
actual tool/service and purpose; describe human review and responsibility only
after the authors have performed that review. The guide exempts basic
grammar/spelling/reference checks and accessibility-only assistive features.
It does not allow AI tools as authors. Record research/software assistance
accurately where relevant to reproducible methods; do not invent tool versions,
funding, conflicts, consent, exemption or author approval.

Page 20 permits AI-supported explanatory diagrams and data visualizations
derived from underlying data through reproducible methods. It does not permit
creating or altering primary observed/experimental images in the prohibited
ways described there. AI-generated manuscript images need disclosure in each
caption and in the general AI statement. Page 17 refers graphical abstracts
to Elsevier's AI policy; it does not itself state a blanket permission or ban.
Use an editable, author-checked architecture diagram and retain its source;
use recorded data and plotting code for future result figures.

Complete the declarations tool and upload its .doc/.docx output even when
there are no competing interests (p. 8). The authors must also settle CRediT,
funding and sponsor role, approvals/consent when applicable, copyright
permissions, and the submission declaration. Confirm APC responsibility and any
institutional coverage without inventing a fee (p. 29). Highlights or a graphical
abstract can improve presentation but are not substitutes for these requirements.

## Local physical-phone smoke boundary

The local report and structured receipt from 11 October 2026 were inspected.
Four successful sessions acknowledged 205 frames: two 24-frame synthetic
replays and camera traces of 106 and 51 frames. All 157 camera trace frames had
null pose and hand landmark groups. This supports the exercised capture,
missing-detection transport, stop/flush/export and cleanup paths; it does not
establish useful landmark detection, camera recognition, boundary quality,
recognition accuracy, deployment latency or sustained performance.

These are local engineering observations, not public article Results. Raw
device identifiers and private traces are not included here. The receipt binds
the tested checkout to `bee6fb25697ec3a9fa90c446000727ede938c817` and identifies
the selected v0.2.1 APK separately. The release tag resolves to
`eace06d35b8b130a48f98140af353b4f598e3d24`; a later main checkout is not the tag.
Do not transfer archived v0.2.0 compatibility counts or v0.1.2 timings to this
local smoke or to a new v0.2.1 scientific experiment.

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
