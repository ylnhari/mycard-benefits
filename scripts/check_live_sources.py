"""Guard the intentionally separate, opt-in live-source-check entry point.

No network adapter is registered in this repository today. The script exists
solely so a future live adapter cannot be added to fixture CI by accident.
It does not send a request; a future implementation must keep the explicit
environment gate and supply its own reviewed source-admission checks.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).parents[1]


def main() -> None:
    if os.environ.get("MYCARD_BENEFITS_ENABLE_LIVE_CHECKS") != "1":
        raise SystemExit(
            "Live source checks are disabled; set MYCARD_BENEFITS_ENABLE_LIVE_CHECKS=1."
        )
    admissions = sorted((ROOT / "sources" / "admissions").glob("*.json"))
    print(
        "No live source adapter is registered; no network request was made "
        f"for {len(admissions)} admitted-source records."
    )


if __name__ == "__main__":
    main()
