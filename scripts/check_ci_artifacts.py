#!/usr/bin/env python3
"""Reject generated CI artifacts that contain credentials."""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path
from zipfile import ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]

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
    ".jsonl",
    ".js",
    ".log",
    ".mjs",
    ".ndjson",
    ".network",
    ".har",
    ".map",
    ".svg",
    ".scss",
    ".stacks",
    ".trace",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
ARCHIVE_SUFFIXES = {".zip"}
MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 2_000
MAX_ARCHIVE_DEPTH = 3


class ScanBudget:
    def __init__(self) -> None:
        self.remaining = MAX_ARCHIVE_BYTES

    def reserve(self, size: int) -> bool:
        if size > self.remaining:
            return False
        self.remaining -= size
        return True


def display_path(path: Path | str) -> str:
    if isinstance(path, Path):
        try:
            return path.relative_to(ROOT).as_posix()
        except ValueError:
            return path.as_posix()
    return path


def member_suffix(name: str) -> str:
    return Path(name.replace("\\", "/")).suffix.lower()


def is_text_member(name: str) -> bool:
    return member_suffix(name) in TEXT_SUFFIXES


def is_archive_member(name: str) -> bool:
    return member_suffix(name) in ARCHIVE_SUFFIXES


def member_path(archive_path: Path | str, name: str) -> str:
    # Member names are only used for diagnostics; never extract or resolve them.
    safe_name = name.replace("\x00", "").replace("\\", "/")
    return f"{display_path(archive_path)}!/{safe_name}"


def decode_text(data: bytes, path: Path | str) -> tuple[str | None, list[str]]:
    if b"\x00" in data[:4096]:
        return None, [f"{display_path(path)}: text artifact contains binary data"]
    try:
        return data.decode("utf-8-sig"), []
    except UnicodeDecodeError:
        return None, [f"{display_path(path)}: text artifact is not valid UTF-8"]


def scan_text(path: Path | str, text: str) -> list[str]:
    errors = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(line):
                errors.append(f"{path}:{line_number}: sensitive CI artifact content detected")
                break
    return errors


def read_text_file(path: Path) -> list[str]:
    if path.stat().st_size > MAX_TEXT_BYTES:
        return [f"{display_path(path)}: text artifact exceeds scan size limit"]
    text, errors = decode_text(path.read_bytes(), path)
    if text is not None:
        errors.extend(scan_text(path, text))
    return errors


def read_archive_member(
    archive: ZipFile,
    member: ZipInfo,
    path: str,
    budget: ScanBudget,
) -> tuple[bytes | None, list[str]]:
    if member.file_size > MAX_ARCHIVE_MEMBER_BYTES:
        return None, [f"{path}: archive member exceeds scan size limit"]
    if not budget.reserve(member.file_size):
        return None, [f"{path}: archive scan size limit exceeded"]
    try:
        with archive.open(member) as stream:
            data = stream.read(MAX_ARCHIVE_MEMBER_BYTES + 1)
    except (KeyError, OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
        return None, [f"{path}: unable to read archive member ({error.__class__.__name__})"]
    if len(data) > MAX_ARCHIVE_MEMBER_BYTES:
        return None, [f"{path}: archive member exceeds scan size limit"]
    return data, []


def scan_archive(
    archive: ZipFile,
    archive_path: Path | str,
    budget: ScanBudget,
    depth: int,
) -> list[str]:
    if depth > MAX_ARCHIVE_DEPTH:
        return [f"{display_path(archive_path)}: archive nesting limit exceeded"]

    members = archive.infolist()
    if len(members) > MAX_ARCHIVE_MEMBERS:
        return [f"{display_path(archive_path)}: archive member limit exceeded"]

    errors = []
    for member in members:
        if member.is_dir():
            continue
        path = member_path(archive_path, member.filename)
        if not is_text_member(member.filename) and not is_archive_member(member.filename):
            continue
        data, read_errors = read_archive_member(archive, member, path, budget)
        errors.extend(read_errors)
        if data is None:
            continue
        if is_archive_member(member.filename):
            if depth >= MAX_ARCHIVE_DEPTH:
                errors.append(f"{path}: archive nesting limit exceeded")
                continue
            try:
                with ZipFile(io.BytesIO(data)) as nested_archive:
                    errors.extend(scan_archive(nested_archive, path, budget, depth + 1))
            except zipfile.BadZipFile:
                errors.append(f"{path}: invalid nested ZIP archive")
            continue
        text, decode_errors = decode_text(data, path)
        errors.extend(decode_errors)
        if text is not None:
            errors.extend(scan_text(path, text))
    return errors


def scan_archive_file(path: Path) -> list[str]:
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        return [f"{display_path(path)}: archive exceeds scan size limit"]
    try:
        with ZipFile(path) as archive:
            return scan_archive(archive, path, ScanBudget(), 0)
    except zipfile.BadZipFile:
        return [f"{display_path(path)}: invalid ZIP archive"]


def scan_file(path: Path) -> list[str]:
    if path.is_symlink() or not path.is_file():
        return []
    suffix = path.suffix.lower()
    if suffix in ARCHIVE_SUFFIXES:
        return scan_archive_file(path)
    if suffix in TEXT_SUFFIXES:
        return read_text_file(path)
    return []


def main() -> int:
    roots = [Path(value).resolve() for value in sys.argv[1:]]
    errors = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and (
                path.suffix.lower() in TEXT_SUFFIXES or path.suffix.lower() in ARCHIVE_SUFFIXES
            ):
                errors.extend(scan_file(path))
    if errors:
        for error in errors:
            print(error)
        return 1
    print("CI artifact policy: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
