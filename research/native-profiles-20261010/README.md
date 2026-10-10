# Native-profile migration evidence — 10 October 2026

These receipts document a host compatibility check for version 0.2.0. The legacy owner adapters and recognition artifacts were supplied locally and are not redistributed.

- SPOTER54 and SL-GCN27 each preserved 30 of 30 segment tensors and ordered top-three predictions across three traces, comprising 3,030 frames. Maximum compared confidence difference was zero.
- Eleven generated sequence lengths per profile, 22 comparisons overall, produced identical tensors. These exercise short sequences and sampling boundaries.
- Each TCP diagnostic used the first 1,033-frame trace and returned 10 events per session, with offline agreement, different-batch agreement, exact retry handling, new connection identity and zero active sessions after disconnect.

The migration receipt identifies input/model/label hashes, profile contracts and the comparison harness. Its source digests describe working-tree bytes at that comparison; later capture/CLI changes and Git newline normalization mean it is not a digest of the final repository commit. Compare the appropriate release artifact bytes when using these hashes. The TCP files used a pre-release source import. Final installed-wheel checks are documented separately.

This establishes agreement on the tested inputs. It does not establish natural-sign accuracy, linguistic boundaries, Android extractor parity, live latency or independent adoption. No timing benchmark is inferred from the TCP diagnostic.

## Repeat with authorized inputs

Use the release environment and run `python tools/verify_native_profiles.py --help`. Supply the legacy model bundle, declared adapter sources, stream settings and authorized trace files requested by the harness. Keep private inputs and generated bundles in an ignored output directory. Then run `python tools/verify_websocket_install.py --bundle NATIVE_BUNDLE --config SERVER_CONFIG --frames TRACE --batch-size 31 --out TCP_RECEIPT.json` for each profile.

Weights, ordered labels derived from a dataset, recorded landmarks and videos require their own permissions. Hashes identify the artifacts; they do not grant redistribution rights. Public synthetic execution checks remain available without those artifacts.
