"""Refresh catalog benefit quantities and their honest coverage report."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from mycard_benefits.catalog.quantities import (
    QUANTITY_BASES,
    QUANTITY_METRICS,
    QUANTITY_PERIODS,
    QUANTITY_SCOPES,
    QUANTITY_UNITS,
    project_benefit_record,
)


def main() -> None:
    root = Path(__file__).parents[1]
    benefits_dir = root / "catalog" / "benefits"
    coverage_dir = root / "catalog" / "coverage"
    mapped_keys: set[str] = set()
    all_keys: set[str] = set()
    unmapped: Counter[tuple[str, str]] = Counter()
    benefits_with_quantities = 0
    quantity_count = 0

    for path in sorted(benefits_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        projection = project_benefit_record(record)
        record["quantities"] = list(projection.quantities)
        path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        allowance = record.get("allowance")
        if isinstance(allowance, dict):
            all_keys.update(allowance)
        if "not_claimed" in record:
            all_keys.add("not_claimed")
        mapped_keys.update(projection.mapped_keys)
        unmapped.update(projection.unmapped)
        quantity_count += len(projection.quantities)
        benefits_with_quantities += bool(projection.quantities)

    unmapped_rows = [
        {"key": key, "reason": reason, "count": count}
        for (key, reason), count in sorted(unmapped.items())
    ]
    unmapped_keys = {row["key"] for row in unmapped_rows}
    report: dict[str, Any] = {
        "report_version": "1",
        "source": "catalog/benefits/*.json",
        "benefit_count": len(list(benefits_dir.glob("*.json"))),
        "benefits_with_quantities": benefits_with_quantities,
        "quantity_count": quantity_count,
        "distinct_allowance_keys": len(all_keys),
        "mapped_key_count": len(mapped_keys),
        "unmapped_key_count": len(unmapped_keys),
        "keys_with_mapped_and_unmapped_observations": len(mapped_keys & unmapped_keys),
        "mapped_keys": sorted(mapped_keys),
        "unmapped_keys": unmapped_rows,
        "vocabularies": {
            "metric": sorted(QUANTITY_METRICS),
            "unit": sorted(QUANTITY_UNITS),
            "basis": sorted(QUANTITY_BASES),
            "scope": sorted(QUANTITY_SCOPES),
            "period": sorted(QUANTITY_PERIODS),
        },
    }
    coverage_dir.mkdir(exist_ok=True)
    (coverage_dir / "quantities.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
