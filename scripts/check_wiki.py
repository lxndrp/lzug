#!/usr/bin/env python3
"""Check the reviewable Wiki source for structure, links, and public safety."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_ci_artifacts import SENSITIVE_PATTERNS  # noqa: E402
from scripts.check_synthetic_fixtures import scan_blocked_fingerprints, scan_domains  # noqa: E402

REQUIRED_PAGES = {
    "Home.md",
    "_Sidebar.md",
    "Fachlichkeit/index.md",
    "Fachlichkeit/Kernprozesse.md",
    "Fachlichkeit/Rollen-und-Verantwortlichkeiten.md",
    "Fachlichkeit/Glossar.md",
    "Nutzung/index.md",
    "Nutzung/Grundbegriffe.md",
    "Nutzung/Pruefungshalbjahre.md",
    "Nutzung/Stammdaten.md",
    "Nutzung/Terminplanung.md",
    "Administration/index.md",
    "Administration/Lokale-Laufzeit.md",
    "Administration/Daten-und-Zuruecksetzen.md",
    "Entwicklung/index.md",
    "Entwicklung/Einrichtung.md",
    "Entwicklung/Mitarbeit.md",
    "Entwicklung/Arbeitsprozess.md",
    "Entwicklung/Qualitaet-und-Sicherheit.md",
    "Entwicklung/Architektur.md",
    "Entwicklung/Dokumentation.md",
}
LINK_PATTERN = re.compile(r"(?<!!)(?:\[[^\]]*\])\(([^)]+)\)")
WIKI_SYNTAX_PATTERN = re.compile(r"\[\[[^\]]+\]\]|\{\{[^}]+\}\}")
MARKDOWN_SUFFIXES = {".md", ".markdown"}
ALLOWED_SECTIONS = {"Fachlichkeit", "Nutzung", "Administration", "Entwicklung"}


def relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def markdown_files(wiki_root: Path) -> list[Path]:
    return sorted(
        path for path in wiki_root.rglob("*") if path.is_file() and path.suffix in MARKDOWN_SUFFIXES
    )


def check_structure(wiki_root: Path, files: list[Path]) -> list[str]:
    actual = {path.relative_to(wiki_root).as_posix() for path in files}
    errors = [f"wiki: required page missing: {name}" for name in sorted(REQUIRED_PAGES - actual)]
    unexpected = []
    for name in sorted(actual):
        parts = Path(name).parts
        if len(parts) == 1 and name not in {"Home.md", "_Sidebar.md"}:
            unexpected.append(name)
        elif len(parts) > 1 and parts[0] not in ALLOWED_SECTIONS:
            unexpected.append(name)
    errors.extend(f"wiki: page is outside the approved structure: {name}" for name in unexpected)
    if not (wiki_root / "Home.md").is_file():
        errors.append("wiki: Home.md is required as the independent entry point")
    home = (
        (wiki_root / "Home.md").read_text(encoding="utf-8")
        if (wiki_root / "Home.md").is_file()
        else ""
    )
    for required_link in (
        "Fachlichkeit/index.md",
        "Nutzung/index.md",
        "Administration/index.md",
        "Entwicklung/index.md",
    ):
        if required_link not in home:
            errors.append(f"wiki: Home.md does not link to {required_link}")
    return errors


def check_links(wiki_root: Path, files: list[Path]) -> list[str]:
    errors = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in LINK_PATTERN.finditer(text):
            target = match.group(1).strip().strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or target.startswith("#"):
                continue
            target_path = unquote(parsed.path)
            if not target_path:
                continue
            candidate = (path.parent / target_path).resolve()
            try:
                candidate.relative_to(wiki_root.resolve())
            except ValueError:
                errors.append(f"{relative(path)}: local link leaves wiki: {target}")
                continue
            if not candidate.is_file():
                errors.append(f"{relative(path)}: local link target does not exist: {target}")
    return errors


def check_public_safety(files: list[Path]) -> list[str]:
    errors = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        display = relative(path)
        for line_number, line in enumerate(text.splitlines(), 1):
            if WIKI_SYNTAX_PATTERN.search(line):
                errors.append(
                    f"{display}:{line_number}: Gollum-specific link/template syntax is forbidden"
                )
            if any(pattern.search(line) for pattern in SENSITIVE_PATTERNS):
                errors.append(f"{display}:{line_number}: secret-like content detected")
        errors.extend(scan_domains(path, text))
        errors.extend(scan_blocked_fingerprints(path, text))
    return errors


def main() -> int:
    wiki_root = Path(sys.argv[1] if len(sys.argv) == 2 else ".").resolve()
    if not wiki_root.is_dir():
        print(f"wiki: directory does not exist: {wiki_root}")
        return 1
    files = markdown_files(wiki_root)
    errors = check_structure(wiki_root, files)
    errors.extend(check_links(wiki_root, files))
    errors.extend(check_public_safety(files))
    if errors:
        print("\n".join(errors))
        return 1
    print(f"wiki source policy: ok ({len(files)} Markdown pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
