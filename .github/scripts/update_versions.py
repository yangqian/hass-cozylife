#!/usr/bin/env python3
"""Utility to sync version metadata for HACS."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "custom_components" / "cozylife" / "manifest.json"
HACS_JSON_PATH = ROOT / "hacs.json"


def update_json(path: Path, version: str) -> None:
    data = json.loads(path.read_text())
    data["version"] = version
    path.write_text(json.dumps(data, indent=2) + "\n")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: update_versions.py <version>", file=sys.stderr)
        return 1

    version = sys.argv[1]

    update_json(MANIFEST_PATH, version)

    if HACS_JSON_PATH.exists():
        update_json(HACS_JSON_PATH, version)

    return 0


if __name__ == "__main__":
    sys.exit(main())
