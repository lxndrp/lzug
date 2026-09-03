"""Validate the reproducible public-demo screenshot contract."""

from __future__ import annotations

import json
import struct
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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
    identifiers: set[str] = set()
    files: set[str] = set()
    default_viewport = contract.get("capture", {}).get("viewport", {})
    for screenshot in contract.get("screenshots", []):
        if (
            not screenshot.get("id")
            or not screenshot.get("path")
            or not screenshot.get("file")
            or not screenshot.get("alt")
        ):
            errors.append(
                "demo media: every screenshot needs id, path, file, and non-empty alt text"
            )
            continue
        if screenshot["id"] in identifiers or screenshot["file"] in files:
            errors.append("demo media: screenshot ids and files must be unique")
        identifiers.add(screenshot["id"])
        files.add(screenshot["file"])
        image = contract_path.parent / screenshot["file"]
        if not image.is_file():
            errors.append(f"demo media: screenshot file is missing: {screenshot['file']}")
            continue
        data = image.read_bytes()
        if len(data) < 24 or not data.startswith(PNG_SIGNATURE):
            errors.append(f"demo media: screenshot is not a valid PNG: {screenshot['file']}")
            continue
        actual_size = dict(zip(("width", "height"), struct.unpack(">II", data[16:24]), strict=True))
        expected_size = screenshot.get("viewport", default_viewport)
        if actual_size != expected_size:
            errors.append(
                f"demo media: {screenshot['file']} dimensions {actual_size} "
                f"must match {expected_size}"
            )
    if not contract.get("screenshots"):
        errors.append("demo media: at least one synthetic scenario screenshot is required")
    return errors


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    violations = check(root)
    if violations:
        raise SystemExit("\n".join(violations))
    print("demo media contract: ok")
