"""Distribution metadata required to identify and reuse a research release."""
from importlib.metadata import distribution
from pathlib import Path
import unittest


class PackagingTests(unittest.TestCase):
    def test_softwarex_license_copy_and_wheel_notices_match_source(self):
        root = Path(__file__).resolve().parents[1]
        canonical = (root / "LICENSE.txt").read_bytes()
        self.assertEqual((root / "Licence.txt").read_bytes(), canonical)
        package = distribution("vsl-streaming-toolkit")
        for name in ("LICENSE.txt", "Licence.txt", "THIRD_PARTY_NOTICES.md"):
            files = [path for path in package.files
                     if str(path).endswith(".dist-info/licenses/" + name)]
            # A source/editable run checks the source; an installed wheel must
            # actually carry both license spellings and the dependency notices.
            if any(str(path).endswith(".dist-info/WHEEL") for path in package.files):
                self.assertEqual(len(files), 1, name)
                self.assertEqual(Path(package.locate_file(files[0])).read_bytes(),
                                 (root / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
