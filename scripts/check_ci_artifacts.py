#!/usr/bin/env python3
"""Reject generated CI artifacts that contain credentials or unsafe test data."""

# The repository-local fixture guard is imported after adding the project root.
# ruff: noqa: E402

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_synthetic_fixtures import (
    scan_blocked_fingerprints,
    scan_domains,
)

SENSITIVE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"(?i)['\"]?(?:authorization|proxy-authorization)['\"]?\s*:\s*" r"(?:bearer|basic)\s+\S+"
    ),
    re.compile(r"(?i)['\"]?(?:cookie|set-cookie)['\"]?\s*:\s*['\"]?[^\s<]+"),
    re.compile(
        r"(?i)['\"]?(?:api[_-]?key|access[_-]?token|client[_-]?secret)['\"]?" r"\s*[:=]\s*['\"]?\S+"
    ),
)
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".json",
    ".js",
    ".mjs",
    ".scss",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
    ".zip",
}


def scan_text(path: Path, text: str) -> list[str]:
    errors = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(line):
                errors.append(f"{path}:{line_number}: sensitive CI artifact content detected")
                break
    errors.extend(scan_domains(path, text))
    errors.extend(scan_blocked_fingerprints(path, text))
    return errors


def scan_file(path: Path) -> list[str]:
    if path.suffix.lower() != ".zip":
        return scan_text(path, path.read_text(encoding="utf-8", errors="ignore"))

    errors = []
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            text = archive.read(member).decode("utf-8", errors="ignore")
            errors.extend(scan_text(path, text))
    return errors


def main() -> int:
    roots = [Path(value).resolve() for value in sys.argv[1:]]
    errors = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                errors.extend(scan_file(path))
    if errors:
        for error in errors:
            print(error)
        return 1
    print("CI artifact policy: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
