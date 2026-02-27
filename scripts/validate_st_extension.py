from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
EXT_DIR = ROOT / "st-extension"
MANIFEST = EXT_DIR / "manifest.json"

REQUIRED_MANIFEST_KEYS = {
    "name",
    "display_name",
    "author",
    "version",
    "js",
}


def main() -> int:
    if not EXT_DIR.exists():
        print("st-extension directory is missing")
        return 1

    if not MANIFEST.exists():
        print("manifest.json is missing")
        return 1

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))

    missing = sorted(REQUIRED_MANIFEST_KEYS - set(data.keys()))
    if missing:
        print(f"manifest.json missing keys: {', '.join(missing)}")
        return 1

    js_file = EXT_DIR / data["js"]
    if not js_file.exists():
        print(f"entrypoint referenced by manifest not found: {data['js']}")
        return 1

    settings_file = EXT_DIR / "settings.json"
    if not settings_file.exists():
        print("settings.json is missing")
        return 1

    print("ST extension package validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
