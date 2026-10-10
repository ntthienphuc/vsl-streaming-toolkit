# Contributing

Open an issue describing the model/input contract, expected behavior and a small
synthetic reproduction. Submit focused pull requests with relevant test results.
New original toolkit contributions use MIT; modifications to the Apache-2.0
native preprocessing module retain Apache-2.0 and its upstream notices. The
combined distribution uses `MIT AND Apache-2.0`; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Do not include source, model weights, recordings, traces or session logs without
appropriate redistribution permission. Use synthetic inputs in public bug reports.

Use `python -m pip install ".[server,export,dev]"` in a virtual environment, then
`python -m unittest discover -s tests -v`. Follow [REPRODUCE.md](REPRODUCE.md) for
wheel and transport checks. Keep protocol errors explicit and documented; preserve
atomic input validation, frame ordering, bounded state and retry semantics.

For a new adapter, specify landmark order, dimensions, sampling, normalization,
class order, supported providers and representative export checks. Matching shape
alone is insufficient. Add tests for unsupported contracts and boundary cases.
Research claims need measured evidence separate from synthetic test results.
