# Contributing

Open an issue describing the model/input contract, expected behavior and a small
synthetic reproduction. Submit focused pull requests with relevant test results.
Contributions are made under this repository's MIT license; keep applicable
upstream attributions and do not include source/model/data without permission.

Use `python -m pip install ".[server,export,dev]"` in a virtual environment, then
`python -m unittest discover -s tests -v`. Follow [REPRODUCE.md](REPRODUCE.md) for
wheel and transport checks. Keep protocol errors explicit and documented; preserve
atomic input validation, frame ordering, bounded state and retry semantics.

For a new adapter, specify landmark order, dimensions, sampling, normalization,
class order, supported providers and representative export checks. Matching shape
alone is insufficient. Add tests for unsupported contracts and boundary cases.
Research claims need measured evidence separate from synthetic test results.
