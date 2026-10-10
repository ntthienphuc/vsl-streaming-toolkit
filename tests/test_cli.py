"""CLI JSON must remain usable with Vietnamese paths under redirected output."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CLIEncodingTests(unittest.TestCase):
    def test_redirected_json_uses_utf8_with_legacy_environment_encoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "tổ hợp"
            result = subprocess.run(
                [sys.executable, "-m", "vsl_streaming.cli", "init", "--out", str(output)],
                env={**os.environ, "PYTHONIOENCODING": "cp1252"},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            data = json.loads(result.stdout.decode("utf-8"))
            self.assertEqual(data["directory"], str(output.resolve()))
            self.assertTrue((output / "profile.json").is_file())


if __name__ == "__main__":
    unittest.main()
