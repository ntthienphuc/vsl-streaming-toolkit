# Validation scope

## Publicly reproducible checks

The public release includes core, protocol, bundle, adapter and server tests,
a generated two-class model, a browser replay interface, and an installed-package
TCP check. [REPRODUCE.md](../REPRODUCE.md) states inputs and expected outcomes.
CI exposes logs and generated receipts for the evaluated commit.

The synthetic model classifies the sign of generated point values. It is a
software fixture, not a trained sign-language recognizer. Numerical export
agreement is checked on specified probes; adding representative user tensors
extends that tested input set but does not certify all inputs.

## Earlier private integration work

Separate local development work compared owner-supplied SPOTER and SL-GCN
preprocessing and inference on recorded keypoints. Those models, owner source,
participant traces, labels, machine paths and local audit receipts are excluded
from this repository. Those checks should be presented with their own artifact
identities and evidence in a manuscript, rather than treated as reproduced by
this public synthetic release. No accuracy number is claimed here.

## Remaining experiments

Independent annotated continuous traces, boundary/event metrics, segmenter
baselines, controlled latency/resource measurements, sustained overload and
slow-client tests, independent reuse, a live camera client and Jetson execution
require separate evidence. The included browser is a frame-file replay client;
the existing Android application is not part of this package. One process owns
connection-local state; reconnect resumes neither state nor durable retries.

## Repository structure precedents

The release organization was informed by
[EmbedKD v0.1.5](https://github.com/hublinhdn/embedkd/tree/v0.1.5), with packaging,
reproduction instructions, citation and tests, and
[AffectStream's SoftwareX repository](https://github.com/ElsevierSoftwareX/SOFTX-D-25-00173),
with code structure, local setup and deployment examples. These are organizational
comparators, not competing software benchmark results or an acceptance guarantee.
No implementation from these repositories was copied.

For a claim-oriented inventory of public checks, application examples and
remaining evidence, see [PAPER_READINESS.md](PAPER_READINESS.md).
