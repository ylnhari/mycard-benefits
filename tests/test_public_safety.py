from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_claude_adapter_is_exact() -> None:
    assert (ROOT / "CLAUDE.md").read_text(encoding="utf-8").strip() == "@AGENTS.md"


def test_tracked_source_tree_has_no_machine_path_or_runtime_identity() -> None:
    forbidden = ("C:\\Users\\", "BEGIN PRIVATE KEY")
    for folder in (ROOT / "src", ROOT / "catalog", ROOT / "docs", ROOT / "samples"):
        for path in folder.rglob("*"):
            if not path.is_file() or path.suffix in {".pyc"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in forbidden:
                assert marker not in text, f"{path} contains forbidden marker {marker!r}"
