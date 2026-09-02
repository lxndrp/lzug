"""Validate the reproducible public-demo screenshot contract."""

from __future__ import annotations

import json
from pathlib import Path


def check(root: Path) -> list[str]:
    catalog_path = root / "fixtures" / "synthetic-fixtures.json"
    contract_path = root / "docs" / "media" / "demo-screenshots.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "fixture_catalog_version": catalog["version"],
        "fixture_catalog_revision": catalog["revision"],
        "demo_matrix_version": catalog["demo_matrix_version"],
    }
    errors = [
        f"demo media: {name} must match the synthetic fixture contract"
        for name, value in expected.items()
        if contract.get(name) != value
    ]
    for screenshot in contract.get("screenshots", []):
        if not screenshot.get("id") or not screenshot.get("path") or not screenshot.get("alt"):
            errors.append("demo media: every screenshot needs id, path, and non-empty alt text")
    if not contract.get("screenshots"):
        errors.append("demo media: at least one synthetic scenario screenshot is required")
    return errors


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    violations = check(root)
    if violations:
        raise SystemExit("\n".join(violations))
    print("demo media contract: ok")
