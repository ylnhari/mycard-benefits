from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def test_tata_benefit_detail_renders_approved_terms_count_and_claim_route() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the dependency-free benefit-detail DOM harness")

    completed = subprocess.run(
        [
            node,
            str(ROOT / "tests" / "tata_benefit_ui_harness.js"),
            str(ROOT / "src" / "mycard_benefits" / "static" / "app.js"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
