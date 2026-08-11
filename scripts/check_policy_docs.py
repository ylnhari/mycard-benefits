"""Verify required no-force-push and independent-review policy text exists."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIREMENTS = {
    "CONTRIBUTING.md": ("cannot approve its own", "private records"),
    "docs/RELEASE-GOVERNANCE.md": ("Force-pushes", "independent", "exact commit range"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="validate only local policy files using the Python standard library",
    )
    parser.parse_args()
    findings: list[str] = []
    for filename, markers in REQUIREMENTS.items():
        path = Path(filename)
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            findings.append(f"missing policy document: {filename}")
            continue
        for marker in markers:
            if marker.casefold() not in content.casefold():
                findings.append(f"{filename}: missing policy marker {marker!r}")
    if findings:
        for finding in findings:
            print(f"FAIL {finding}")
        return 1
    print("PASS no-force-push and independent-review policy documentation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
