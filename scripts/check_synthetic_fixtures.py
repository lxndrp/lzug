#!/usr/bin/env python3
"""Validate canonical fixtures and prevent unsafe demo identities in the tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generate_synthetic_fixtures import generate, load_source  # noqa: E402

FINGERPRINTS = ROOT / "fixtures" / "blocked-fixture-fingerprints.json"
EMAIL_PATTERN = re.compile(r"[\w.%+-]+@([\w.-]+\.[A-Za-z]{2,})", re.UNICODE)
URL_PATTERN = re.compile(r"https?://[^\s'\"<>)]+")
TOKEN_PATTERN = re.compile(r"[\w@.+/-]+", re.UNICODE)
FIXTURE_URL_ROOTS = (
    "backend/tests/",
    "db/",
    "fixtures/",
    "frontend/e2e/",
    "frontend/src/app/testing/",
    "prototypes/",
)
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".scss",
    ".sql",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}
GENERATED_ARTIFACT_ROOTS = (
    ROOT / "site",
    ROOT / "frontend" / "playwright-report",
    ROOT / "frontend" / "test-results",
)


def is_reserved_domain(domain: str) -> bool:
    normalized = domain.rstrip(".").lower()
    return normalized in {
        "example.com",
        "example.net",
        "example.org",
        "localhost",
    } or normalized.endswith((".example", ".invalid", ".test"))


def normalize_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return TOKEN_PATTERN.findall(normalized)


def tracked_text_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    paths = []
    for value in output.decode("utf-8").split("\0"):
        if not value:
            continue
        path = ROOT / value
        if path.suffix.lower() in TEXT_SUFFIXES and path.is_file():
            paths.append(path)
    return paths


def validate_source() -> list[str]:
    data = load_source()
    errors = []
    conventions = data["conventions"]
    email_domain = conventions["email_domain"]
    if not is_reserved_domain(email_domain):
        errors.append("canonical email domain is not reserved")

    for group in ("committees", "members", "locations", "candidates"):
        ids = [row["id"] for row in data[group]]
        if len(ids) != len(set(ids)):
            errors.append(f"duplicate canonical IDs in {group}")

    emails = [row["email"] for row in data["members"]]
    if len(emails) != len(set(emails)):
        errors.append("canonical member emails are not unique")
    for row in data["members"]:
        if not row["email"].endswith(f"@{email_domain}"):
            errors.append(f"member {row['id']} does not use the canonical reserved domain")
        mobile = row["mobile"]
        if mobile is not None and not mobile.startswith(conventions["phone_prefix"]):
            errors.append(f"member {row['id']} does not use the synthetic phone prefix")
        if row["first_name"] != conventions["person_first_name"]:
            errors.append(f"member {row['id']} is not explicitly marked as a test person")

    exam_numbers = [row["ihk_exam_number"] for row in data["candidates"]]
    if len(exam_numbers) != len(set(exam_numbers)):
        errors.append("canonical exam numbers are not unique")
    for row in data["candidates"]:
        if row["first_name"] != conventions["candidate_first_name"]:
            errors.append(f"candidate {row['id']} is not explicitly marked as synthetic")
        if not row["ihk_exam_number"].startswith(f"{conventions['exam_number_prefix']}-"):
            errors.append(f"candidate {row['id']} does not use the synthetic exam-number prefix")
        if not row["training_company"].startswith("Testbetrieb "):
            errors.append(f"candidate {row['id']} does not use an explicit test company")

    for row in data["locations"]:
        if row["city"] != conventions["city"] or row["postal_code"] != conventions["postal_code"]:
            errors.append(f"location {row['id']} does not use the synthetic place convention")
        if "(Test)" not in row["name"] or not row["street"].startswith("Testweg "):
            errors.append(f"location {row['id']} is not explicitly marked as synthetic")
    return errors


def display_path(path: Path | str) -> str:
    if isinstance(path, Path):
        try:
            return path.relative_to(ROOT).as_posix()
        except ValueError:
            return path.as_posix()
    return path


def scan_domains(path: Path | str, text: str) -> list[str]:
    errors = []
    relative = display_path(path)
    for line_number, line in enumerate(text.splitlines(), 1):
        for match in EMAIL_PATTERN.finditer(line):
            domain = match.group(1)
            if not is_reserved_domain(domain):
                errors.append(f"{relative}:{line_number}: email uses non-reserved domain {domain}")
        if not relative.startswith(FIXTURE_URL_ROOTS):
            continue
        for match in URL_PATTERN.finditer(line):
            hostname = urlsplit(match.group(0)).hostname
            if (
                hostname
                and not is_reserved_domain(hostname)
                and hostname
                not in {
                    "127.0.0.1",
                    "::1",
                }
            ):
                errors.append(
                    f"{relative}:{line_number}: fixture URL uses non-reserved host {hostname}"
                )
    return errors


def scan_blocked_fingerprints(
    path: Path | str,
    text: str,
    fingerprint_data: dict | None = None,
) -> list[str]:
    if fingerprint_data is None:
        fingerprint_data = json.loads(FINGERPRINTS.read_text(encoding="utf-8"))
    by_size: dict[int, dict[str, str]] = defaultdict(dict)
    for item in fingerprint_data["fingerprints"]:
        by_size[item["token_count"]][item["sha256"]] = item["category"]

    tokens = normalize_tokens(text)
    relative = display_path(path)
    errors = []
    seen = set()
    for size, blocked in by_size.items():
        for index in range(0, len(tokens) - size + 1):
            candidate = " ".join(tokens[index : index + size])
            digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
            category = blocked.get(digest)
            key = (digest, category)
            if category and key not in seen:
                errors.append(f"{relative}: blocked legacy {category} fingerprint detected")
                seen.add(key)
    return errors


def scan_generated_artifacts() -> list[str]:
    errors = []
    for root in GENERATED_ARTIFACT_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in TEXT_SUFFIXES:
                text = path.read_text(encoding="utf-8", errors="ignore")
                errors.extend(scan_domains(path, text))
                errors.extend(scan_blocked_fingerprints(path, text))
            elif path.suffix.lower() == ".zip":
                with zipfile.ZipFile(path) as archive:
                    for member in archive.infolist():
                        if member.is_dir():
                            continue
                        text = archive.read(member).decode("utf-8", errors="ignore")
                        errors.extend(scan_domains(path, text))
                        errors.extend(scan_blocked_fingerprints(path, text))
            elif (
                path.suffix.lower() in {".jpeg", ".jpg", ".png", ".webp"}
                and (ROOT / "frontend" / "test-results") in path.parents
            ):
                errors.append(
                    f"{path.relative_to(ROOT)}: generated screenshot requires explicit review"
                )
    return errors


def run_checks(include_generated_artifacts: bool = False) -> list[str]:
    errors = validate_source()
    for path in generate(check=True):
        errors.append(f"outdated generated adapter: {path.relative_to(ROOT)}")
    for path in tracked_text_files():
        text = path.read_text(encoding="utf-8")
        errors.extend(scan_domains(path, text))
        errors.extend(scan_blocked_fingerprints(path, text))
    if include_generated_artifacts:
        errors.extend(scan_generated_artifacts())
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--include-generated-artifacts",
        action="store_true",
        help="also scan local documentation, Playwright reports, traces, and screenshots",
    )
    args = parser.parse_args()
    errors = run_checks(include_generated_artifacts=args.include_generated_artifacts)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("synthetic fixture policy: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
