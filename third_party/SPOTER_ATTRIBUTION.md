# SPOTER normalization attribution

The body and hand normalization behavior in
`src/vsl_streaming/native_profiles.py` is adapted from SPOTER by Matyáš Boháček
and Marek Hrúz, specifically `spoter/utils/normalization.py` at revision
`0f909bf92690772f43f0062be41860ed85b461ad`:

https://github.com/maty-bohacek/spoter/tree/0f909bf92690772f43f0062be41860ed85b461ad

The upstream implementation is licensed under Apache License 2.0. The full
license is preserved in [SPOTER_LICENSE.txt](SPOTER_LICENSE.txt). No upstream
NOTICE file was found in the inspected revision. This document records
attribution and changes; it is not an upstream NOTICE file.

Changes in this distribution: normalization is implemented in NumPy within a
versioned model-input profile, combined with explicit frame/landmark selection,
shape and finite-value validation, and legacy temporal preparation. The
`spoter54-legacy-v1` profile preserves the owner pipeline's historical hand-layout
behavior for checkpoint compatibility. It should not be silently substituted
for another SPOTER training pipeline. See `docs/PREPROCESSING_PROFILES.md`.

The toolkit's original code remains MIT licensed. The adapted normalization is
subject to Apache-2.0; distribution therefore includes both licenses. This
attribution conveys no permission for pretrained weights, datasets, recordings,
or the personal likeness of signers.
