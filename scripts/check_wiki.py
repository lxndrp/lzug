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
    "Fachlichkeit.md",
    "Fachlichkeit-Kernprozesse.md",
    "Fachlichkeit-Rollen-und-Verantwortlichkeiten.md",
    "Fachlichkeit-Glossar.md",
    "Prozess-Pruefungshalbjahr-planen.md",
    "Prozess-Zulassung-und-Antraege-bewerten.md",
    "Prozess-Schriftliche-Pruefungen-organisieren.md",
    "Prozess-Muendliche-Pruefung-planen-und-durchfuehren.md",
    "Prozess-Pruefungsleistungen-bewerten.md",
    "Prozess-Ergebnis-feststellen-und-bekanntgeben.md",
    "User-Journey-Pruefungshalbjahr-planen.md",
    "User-Journey-Verfuegbarkeit-melden.md",
    "User-Journey-Muendlichen-Pruefungstag-vorbereiten-und-durchfuehren.md",
    "User-Journey-Dokumentation-individuell-bewerten.md",
    "User-Journey-Praesentation-und-Fachgespraech-bewerten.md",
    "User-Journey-Ergebnis-gemeinsam-feststellen.md",
    "Entscheidungsmatrix-Besetzung-und-Planbarkeit.md",
    "Entscheidungsmatrix-Ausfall-und-Ersatzbesetzung.md",
    "Nutzung.md",
    "Nutzung-Grundbegriffe.md",
    "Nutzung-Pruefungshalbjahre.md",
    "Nutzung-Stammdaten.md",
    "Nutzung-Terminplanung.md",
    "Administration.md",
    "Administration-Lokale-Laufzeit.md",
    "Administration-Daten-und-Zuruecksetzen.md",
    "Entwicklung.md",
    "Entwicklung-Einrichtung.md",
    "Entwicklung-Arbeitsprozess.md",
    "Entwicklung-Qualitaet-und-Sicherheit.md",
    "Entwicklung-Architektur.md",
    "Entwicklung-Dokumentation.md",
}
LINK_PATTERN = re.compile(r"(?<!!)(?:\[[^\]]*\])\(([^)]+)\)")
WIKI_SYNTAX_PATTERN = re.compile(r"\[\[[^\]]+\]\]|\{\{[^}]+\}\}")
MARKDOWN_SUFFIXES = {".md", ".markdown"}
REQUIRED_HOME_LINKS = {"Fachlichkeit", "Nutzung", "Administration", "Entwicklung"}
REQUIRED_SIDEBAR_LINKS = REQUIRED_HOME_LINKS | {"Home"}


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
    nested = sorted(name for name in actual if len(Path(name).parts) != 1)
    errors.extend(f"wiki: page must be flat: {name}" for name in nested)
    non_md = sorted(name for name in actual if Path(name).suffix != ".md")
    errors.extend(f"wiki: page must use the .md extension: {name}" for name in non_md)
    stems: dict[str, list[str]] = {}
    for name in sorted(actual):
        stems.setdefault(Path(name).stem, []).append(name)
    errors.extend(
        f"wiki: page name is not unique: {', '.join(names)}"
        for names in stems.values()
        if len(names) > 1
    )
    if not (wiki_root / "Home.md").is_file():
        errors.append("wiki: Home.md is required as the independent entry point")
    if not (wiki_root / "_Sidebar.md").is_file():
        errors.append("wiki: _Sidebar.md is required")
    for filename, required_links in (
        ("Home.md", REQUIRED_HOME_LINKS),
        ("_Sidebar.md", REQUIRED_SIDEBAR_LINKS),
    ):
        path = wiki_root / filename
        if not path.is_file():
            continue
        linked = local_link_targets(path.read_text(encoding="utf-8"))
        for required_link in sorted(required_links - linked):
            errors.append(f"wiki: {filename} does not link to {required_link}")
    return errors


def local_link_targets(text: str) -> set[str]:
    targets = set()
    for match in LINK_PATTERN.finditer(text):
        target = match.group(1).strip().strip("<>")
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or parsed.path == "" or target.startswith("#"):
            continue
        targets.add(unquote(parsed.path))
    return targets


def check_links(wiki_root: Path, files: list[Path]) -> list[str]:
    errors = []
    page_stems = {path.stem for path in files if path.parent == wiki_root and path.suffix == ".md"}
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
            if target_path.endswith(tuple(MARKDOWN_SUFFIXES)):
                errors.append(
                    f"{relative(path)}: internal wiki link must be extensionless: {target}"
                )
                continue
            if "/" in target_path or target_path.startswith((".", "/")):
                errors.append(
                    f"{relative(path)}: internal wiki link must target a flat page: {target}"
                )
                continue
            if target_path not in page_stems:
                errors.append(f"{relative(path)}: local wiki page does not exist: {target}")
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
