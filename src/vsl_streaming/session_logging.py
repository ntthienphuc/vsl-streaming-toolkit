"""Opt-in local session evidence. Records responses, never raw input frames."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time


class SessionLogError(OSError):
    """Requested evidence could not be persisted to the configured stream."""


def canonical_sha256(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def prepare_log_directory(directory):
    if directory is None:
        return None
    path = Path(directory).resolve()
    path.mkdir(parents=True, exist_ok=True)
    # Fail before serving when the requested evidence directory is unusable.
    with tempfile.TemporaryFile(dir=path):
        pass
    return path


class SessionLog:
    def __init__(self, directory, session_id):
        self.session_id = session_id
        self.index = 0
        self.started = time.monotonic()
        try:
            self.file = (directory / (session_id + ".session.jsonl")).open("x", encoding="utf-8", newline="\n")
        except OSError as error:
            raise SessionLogError("Cannot open session evidence") from error

    def write(self, kind, **fields):
        record = {"schema_version": 1, "session_id": self.session_id,
                  "record_index": self.index, "type": kind,
                  "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                  "elapsed_ms": (time.monotonic() - self.started) * 1000, **fields}
        try:
            self.file.write(json.dumps(record, ensure_ascii=False, allow_nan=False,
                                       separators=(",", ":")) + "\n")
            self.file.flush()
        except (OSError, ValueError, TypeError) as error:
            raise SessionLogError("Cannot write session evidence") from error
        self.index += 1

    def close(self):
        try:
            self.file.close()
        except OSError as error:
            raise SessionLogError("Cannot close session evidence") from error
