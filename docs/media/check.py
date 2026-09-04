"""Check metadata for screenshots captured by the Playwright demo test."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


def _image_dimensions(path: Path) -> dict[str, int] | None:
    try:
        result = subprocess.run(
            ["file", "-b", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError, subprocess.CalledProcessError:
        return None
    match = re.search(r"PNG image data, (\d+) x (\d+)", result.stdout)
    if match is None:
        return None
    return {"width": int(match.group(1)), "height": int(match.group(2))}


def check(root: Path) -> list[str]:
    contract_path = root / "docs/media/demo-screenshots.json"
    fixture_path = root / "fixtures/synthetic-fixtures.json"
    if not contract_path.is_file() or not fixture_path.is_file():
        return ["demo media: screenshot or fixture contract is missing"]

    contract: dict[str, Any] = json.loads(contract_path.read_text(encoding="utf-8"))
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    violations: list[str] = []
    fixture_fields = {
        "fixture_catalog_version": "version",
        "fixture_catalog_revision": "revision",
        "demo_matrix_version": "demo_matrix_version",
    }
    for contract_field, fixture_field in fixture_fields.items():
        if contract.get(contract_field) != fixture.get(fixture_field):
            violations.append(
                f"demo media: {contract_field} does not match the synthetic fixture contract"
            )

    default_viewport = contract.get("capture", {}).get("viewport", {})
    identifiers: set[str] = set()
    files: set[str] = set()
    for screenshot in contract.get("screenshots", []):
        if not all(screenshot.get(field) for field in ("id", "path", "file", "alt")):
            violations.append(
                "demo media: every screenshot needs id, path, file, and non-empty alt text"
            )
            continue
        if screenshot["id"] in identifiers or screenshot["file"] in files:
            violations.append("demo media: screenshot ids and files must be unique")
        identifiers.add(screenshot["id"])
        files.add(screenshot["file"])
        image = contract_path.parent / screenshot["file"]
        if not image.is_file():
            violations.append(f"demo media: screenshot file is missing: {screenshot['file']}")
            continue
        actual = _image_dimensions(image)
        expected = screenshot.get("viewport", default_viewport)
        if actual != expected:
            violations.append(
                f"demo media: {screenshot['file']} dimensions {actual} must match {expected}"
            )
    if not contract.get("screenshots"):
        violations.append("demo media: at least one synthetic scenario screenshot is required")
    return violations


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    violations = check(root)
    if violations:
        raise SystemExit("\n".join(violations))
    print("demo media contract: ok")
