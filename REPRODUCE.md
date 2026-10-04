# Reproduce the public release

Run from a fresh checkout using Python 3.9+. Commands below use `python` and
`vsl-stream` from an activated virtual environment. Windows can instead use
`.venv\Scripts\python.exe` and `.venv\Scripts\vsl-stream.exe` directly.

```sh
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install ".[server,export,dev]"
python -m unittest discover -s tests -v
python -m build
vsl-stream demo --out demo_run
vsl-stream inspect --bundle demo_run/bundle
python tools/verify_websocket_install.py --bundle demo_run/bundle --config demo_run/server.json --frames demo_run/frames.json --batch-size 5 --out demo_run/tcp_receipt.json
vsl-stream serve --bundle demo_run/bundle --config demo_run/server.json
```

Open http://127.0.0.1:8000/, load `demo_run/frames.json` and replay. Expected labels:
`SYNTHETIC_NEGATIVE`, then `SYNTHETIC_POSITIVE`. The demo destination must not
already exist. Generated files are ignored by Git.

## Expected checks

- The unit suite passes with no skips when server/export/dev dependencies are installed.
- The demo checks those two fixture labels and records three export parity probes.
- The TCP tool starts its own server on a temporary port and terminates it afterwards.
- It checks exact retry, new connection identities, agreement across two batch sizes,
  offline/WebSocket event agreement and zero active sessions after disconnect.
- `python -m pip check` reports no dependency conflicts.

To verify the actual built wheel, install the file listed in `dist/` into a new
virtual environment, with its `server` extra. Do not add `src/` to PYTHONPATH.
Run the TCP tool against the existing generated demo. Export-time PyTorch is not
needed in that server environment. CI performs tests against the installed wheel
and checks absence of PyTorch in a separate server-only environment.

`requirements-tested.txt` lists direct versions exercised on the original host;
it is not a transitive or cross-platform lock. CI records resolved environment
versions with the validation artifacts. Tests and fixture labels establish software
behavior, not sign recognition accuracy, field usability or Jetson performance.
