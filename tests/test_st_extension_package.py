import json
import subprocess
import sys
import unittest
from pathlib import Path


class StExtensionPackageTests(unittest.TestCase):
    def test_manifest_and_entrypoint_files_exist(self):
        root = Path(__file__).resolve().parents[1]
        ext_dir = root / "st-extension"
        manifest_path = ext_dir / "manifest.json"
        settings_path = ext_dir / "settings.json"

        self.assertTrue(ext_dir.exists())
        self.assertTrue(manifest_path.exists())
        self.assertTrue(settings_path.exists())

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertIn("js", manifest)
        self.assertTrue((ext_dir / manifest["js"]).exists())

    def test_validation_script_passes(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "validate_st_extension.py")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
