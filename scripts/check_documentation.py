"""Check repository-specific documentation structure contracts.

The checker deliberately covers only structural invariants that standard
documentation tools do not express. MkDocs remains responsible for the
technical documentation build and its link validation; the Wiki, publication,
and generated-reference checks remain separate contracts.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT_DOCUMENT_MARKERS = {
    "README.md": (
        "nicht produktionsreif",
        "GitHub Issues",
        "GitHub Releases",
        "lzug Roadmap",
        "CONTRIBUTING.md",
        "GitHub Wiki",
    ),
    "CONTRIBUTING.md": (
        "nicht produktionsreifer",
        "GitHub Issues",
        "lzug Roadmap",
        "Entwicklerhandbuch",
        "Closes #",
    ),
    "SECURITY.md": (
        "keine Zusicherung für ungeprüfte Installationen oder produktiven Betrieb",
        "Sicherheitslücken",
        "Private Vulnerability Reporting",
        "GitHub Secret Scanning",
    ),
    "SUPPORT.md": (
        "nicht produktreifer",
        "GitHub Issue",
        "Private Vulnerability Reporting",
        "CONTRIBUTING.md",
    ),
    "CHANGELOG.md": (
        "## [Unreleased]",
        "GitHub Release",
        "Semantic Versioning",
    ),
}

ADR_PATH = Path("docs/developers/decisions")
ADR_FILENAME = re.compile(r"(?P<number>\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
DEVELOPER_PATH = Path("docs/developers")
EDITORIAL_DEVELOPER_FILES = {
    Path("architecture.md"),
    Path("components.md"),
    Path("data-and-contracts.md"),
    Path("delivery.md"),
    Path("development.md"),
    Path("index.md"),
}
GENERATED_REFERENCE_FILES = {
    Path("reference/backend.md"),
    Path("reference/frontend.md"),
    Path("reference/full-export-v1.schema.json"),
}
DEVELOPER_NAV_TARGETS = {
    "developers/architecture.md",
    "developers/components.md",
    "developers/data-and-contracts.md",
    "developers/decisions/index.md",
    "developers/delivery.md",
    "developers/development.md",
    "developers/index.md",
}
SUPERSESSION_MARKER = re.compile(r"\b(?P<kind>Supersedes|Superseded by):\s*ADR-(?P<number>\d{4})\b")
STATUS_HEADING = re.compile(r"^## Status\s*$", re.MULTILINE)
NAV_TARGET = re.compile(r"^\s*-\s+[^\n:]+:\s+(?P<target>[\w./*-]+\.md)\s*$", re.MULTILINE)
HISTORICAL_NAV_TARGET = re.compile(
    r"(?:^|/)(?:history|archive|archives)/|"
    r"(?:release-evidence|release-milestones|copilot-pilot|publication-architecture)\.md$",
    re.IGNORECASE,
)
PLANNING_HEADING = re.compile(
    r"(?:inventar|backlog|offene\s+issues?|issue[-\s]liste|pr[-\s]liste|"
    r"milestone[-\s]liste|release[-\s]liste)",
    re.IGNORECASE,
)
API_LIST_HEADING = re.compile(
    r"(?:api|openapi).*(?:route|endpoint)|(?:route|endpoint).*(?:api|openapi)",
    re.IGNORECASE,
)
SCHEMA_LIST_HEADING = re.compile(
    r"(?:schema|felder?|typen?).*(?:tabelle|liste|übersicht)|"
    r"(?:tabelle|liste|übersicht).*(?:schema|felder?|typen?)",
    re.IGNORECASE,
)
ROUTE_TOKEN = re.compile(r"[`/]api/|\b(?:GET|POST|PUT|PATCH|DELETE)\s+/", re.IGNORECASE)
SCHEMA_TOKEN = re.compile(r"\|\s*[A-Za-z_][\w-]*\s*\|.*\|", re.IGNORECASE)


def _section(document: str, heading: re.Pattern[str]) -> str | None:
    match = heading.search(document)
    if match is None:
        return None
    remainder = document[match.end() :]
    next_heading = re.search(r"^##\s+", remainder, re.MULTILINE)
    return remainder[: next_heading.start()] if next_heading else remainder


def numbered_adrs(root: Path) -> list[Path]:
    """Return numbered ADR files in deterministic order."""

    directory = root / ADR_PATH
    return sorted(
        path
        for path in directory.glob("[0-9][0-9][0-9][0-9]-*.md")
        if ADR_FILENAME.fullmatch(path.name)
    )


def check_navigation(root: Path) -> list[str]:
    """Check active navigation for forbidden targets and missing source files."""

    path = root / "mkdocs.yml"
    if not path.is_file():
        return [
            "[DOC-NAV-001] mkdocs.yml: the active navigation source is missing; "
            "restore mkdocs.yml before changing documentation navigation."
        ]

    document = path.read_text(encoding="utf-8")
    nav_match = re.search(r"^nav:\s*$", document, re.MULTILINE)
    if nav_match is None:
        return [
            "[DOC-NAV-002] mkdocs.yml: the active nav mapping is missing; "
            "keep current entry points in the MkDocs nav and validate with task docs."
        ]
    nav = document[nav_match.start() :]
    violations: list[str] = []
    targets = NAV_TARGET.findall(nav)
    for target in targets:
        if HISTORICAL_NAV_TARGET.search(target):
            violations.append(
                f"[DOC-NAV-003] mkdocs.yml: historical or archive target {target!r} is active; "
                "remove it from nav and keep history in Git, Releases, or ADR supersession markers."
            )
        elif re.match(r"^developers/decisions/\d{4}-", target):
            violations.append(
                f"[DOC-NAV-004] mkdocs.yml: individual ADR {target!r} is in the main nav; "
                "link only the decision index and keep ADR status there."
            )
        elif not (root / "docs" / target).is_file():
            violations.append(
                f"[DOC-NAV-005] mkdocs.yml: navigated page {target!r} does not exist; "
                "correct or remove the entry, then run task docs."
            )
    developer_targets = {target for target in targets if target.startswith("developers/")}
    if developer_targets != DEVELOPER_NAV_TARGETS:
        missing = sorted(DEVELOPER_NAV_TARGETS - developer_targets)
        unexpected = sorted(developer_targets - DEVELOPER_NAV_TARGETS)
        violations.append(
            "[DOC-NAV-006] mkdocs.yml: developer navigation must contain only the entry, "
            "five core areas, and ADR register; "
            f"missing={missing!r}, unexpected={unexpected!r}."
        )
    return violations


def check_developer_structure(root: Path) -> list[str]:
    """Require the consolidated editorial structure and explicit exceptions."""

    directory = root / DEVELOPER_PATH
    if not directory.is_dir():
        return [
            "[DOC-STRUCT-001] docs/developers: developer documentation is missing; "
            "restore the entry, five core areas, ADR register, and generated references."
        ]

    files = {path.relative_to(directory) for path in directory.rglob("*") if path.is_file()}
    missing_editorial = sorted(EDITORIAL_DEVELOPER_FILES - files)
    if missing_editorial:
        violations = [
            "[DOC-STRUCT-002] docs/developers: consolidated editorial files are missing; "
            f"restore {[str(path) for path in missing_editorial]!r}."
        ]
    else:
        violations = []

    allowed = (
        EDITORIAL_DEVELOPER_FILES
        | GENERATED_REFERENCE_FILES
        | {
            Path("decisions/index.md"),
            Path("decisions/TEMPLATE.md"),
        }
    )
    unexpected = []
    for path in sorted(files - allowed):
        if path.parent == Path("decisions") and ADR_FILENAME.fullmatch(path.name):
            continue
        unexpected.append(str(path))
    if unexpected:
        violations.append(
            "[DOC-STRUCT-003] docs/developers: files outside the entry, five core areas, "
            "ADR register/template/records, and generated references are forbidden; "
            f"remove {unexpected!r} instead of adding legacy, redirect, or placeholder pages."
        )

    missing_references = sorted(GENERATED_REFERENCE_FILES - files)
    if missing_references:
        violations.append(
            "[DOC-STRUCT-004] docs/developers/reference: required generated-reference "
            f"sources are missing; restore {[str(path) for path in missing_references]!r}."
        )
    return violations


def check_documentation_paths(root: Path) -> list[str]:
    """Reject repository paths that would create a second documentation archive."""

    violations: list[str] = []
    for relative in (Path("docs/history"), Path("docs/archive"), Path("docs/archives")):
        if (root / relative).exists():
            violations.append(
                f"[DOC-PATH-001] {relative}: archive directories are forbidden; "
                "delete the replacement archive and rely on Git history or ADR "
                "supersession markers."
            )
    return violations


def _headings(document: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*$", document, re.MULTILINE))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else None
        sections.append((match.group("title"), document[match.end() : end]))
    return sections


def check_redundant_inventories(root: Path) -> list[str]:
    """Reject obvious planning and complete API/schema inventories in prose."""

    violations: list[str] = []
    for path in sorted((root / "docs").rglob("*.md")):
        document = path.read_text(encoding="utf-8")
        for title, section in _headings(document):
            compact_title = " ".join(title.split())
            if PLANNING_HEADING.search(compact_title) and re.search(
                r"(?:#\d{2,}|/issues/\d+|/pull/\d+|Milestone|Issue|Pull Request)",
                section,
                re.IGNORECASE,
            ):
                violations.append(
                    f"[DOC-CONTENT-001] {path.relative_to(root)}: heading "
                    f"{compact_title!r} introduces a planning inventory; "
                    "move current planning to GitHub Issues, Milestones, or Project fields."
                )
            if API_LIST_HEADING.search(compact_title) and len(ROUTE_TOKEN.findall(section)) >= 3:
                violations.append(
                    f"[DOC-CONTENT-002] {path.relative_to(root)}: API route list "
                    "duplicates the executable HTTP contract; "
                    "link OpenAPI or the generated reference instead of maintaining a second list."
                )
            if (
                SCHEMA_LIST_HEADING.search(compact_title)
                and len(SCHEMA_TOKEN.findall(section)) >= 3
            ):
                violations.append(
                    f"[DOC-CONTENT-003] {path.relative_to(root)}: schema/field table "
                    "duplicates an executable source; "
                    "link the ORM, db/schema.sql, migration, or generated reference instead."
                )
    return violations


def check_adrs(root: Path) -> list[str]:
    """Check ADR structure, status markers, and index coverage."""

    violations: list[str] = []
    adrs = numbered_adrs(root)
    known_numbers = {ADR_FILENAME.fullmatch(path.name).group("number") for path in adrs}
    relationships: dict[str, set[tuple[str, str]]] = {}
    index_path = root / ADR_PATH / "index.md"
    index = index_path.read_text(encoding="utf-8") if index_path.is_file() else ""

    if not index_path.is_file():
        violations.append(
            "[DOC-ADR-001] docs/developers/decisions/index.md: ADR index is missing; "
            "restore it and link every numbered ADR exactly once."
        )

    for path in adrs:
        relative = path.relative_to(root)
        document = path.read_text(encoding="utf-8")
        match = ADR_FILENAME.fullmatch(path.name)
        assert match is not None
        number = match.group("number")
        if not re.search(rf"^# ADR-{number}:", document, re.MULTILINE):
            violations.append(
                f"[DOC-ADR-002] {relative}: heading must identify ADR-{number}; "
                "copy the document shape from docs/developers/decisions/TEMPLATE.md."
            )

        status_matches = list(STATUS_HEADING.finditer(document))
        if len(status_matches) != 1:
            violations.append(
                f"[DOC-ADR-003] {relative}: expected exactly one '## Status' section; "
                "copy the status section from docs/developers/decisions/TEMPLATE.md."
            )
            continue

        status = _section(document, STATUS_HEADING)
        assert status is not None
        first_paragraph = next((line.strip() for line in status.splitlines() if line.strip()), "")
        if not re.match(r"^(Vorgeschlagen|Akzeptiert|Abgelehnt)\b", first_paragraph):
            violations.append(
                f"[DOC-ADR-004] {relative}: status must start with Vorgeschlagen, "
                "Akzeptiert, or Abgelehnt; "
                "record the decision state in the Status section."
            )

        all_markers = list(SUPERSESSION_MARKER.finditer(document))
        status_markers = list(SUPERSESSION_MARKER.finditer(status))
        if len(all_markers) != len(status_markers):
            violations.append(
                f"[DOC-ADR-005] {relative}: Supersedes/Superseded by may occur only in Status; "
                "use ordinary context or references for non-superseding relationships."
            )
        for marker in status_markers:
            relationships.setdefault(number, set()).add(
                (marker.group("kind"), marker.group("number"))
            )
            if marker.group("number") not in known_numbers:
                violations.append(
                    f"[DOC-ADR-006] {relative}: {marker.group(0)!r} points to a missing ADR; "
                    "correct the target or remove the supersession marker."
                )

        if index_path.is_file():
            index_links = re.findall(rf"\[[^]]*\]\((?:[^)]*/)?{re.escape(path.name)}\)", index)
            if len(index_links) != 1:
                violations.append(
                    f"[DOC-ADR-007] {relative}: ADR must occur exactly once in the decision index; "
                    "add or remove the index entry without adding a second inventory."
                )

    for number, markers in relationships.items():
        for kind, target in markers:
            inverse_kind = "Superseded by" if kind == "Supersedes" else "Supersedes"
            if (inverse_kind, number) not in relationships.get(target, set()):
                violations.append(
                    f"[DOC-ADR-008] ADR-{number}: {kind} ADR-{target} has no inverse "
                    "status marker; add the matching marker to both ADR Status "
                    "sections or remove the relationship."
                )

    return violations


def check_root_documents(root: Path) -> list[str]:
    """Ensure root documents retain their small, distinct responsibility markers."""

    violations: list[str] = []
    for filename, markers in ROOT_DOCUMENT_MARKERS.items():
        path = root / filename
        if not path.is_file():
            violations.append(
                f"[DOC-ROOT-001] {filename}: canonical root document is missing; "
                "restore the document instead of moving its responsibility into docs/."
            )
            continue
        document = path.read_text(encoding="utf-8")
        document = re.sub(r"[*_>`]", "", document)
        document = " ".join(document.split())
        for marker in markers:
            if marker not in document:
                violations.append(
                    f"[DOC-ROOT-002] {filename}: missing canonical boundary marker {marker!r}; "
                    "restore the concise product, release, security, or support "
                    "statement and keep details in its canonical source."
                )
    return violations


def check(root: Path) -> list[str]:
    """Return all structural documentation contract violations."""

    return [
        *check_documentation_paths(root),
        *check_developer_structure(root),
        *check_navigation(root),
        *check_redundant_inventories(root),
        *check_adrs(root),
        *check_root_documents(root),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    violations = check(root)
    if violations:
        print("documentation structure: failed")
        print("\n".join(violations))
        return 1
    print(f"documentation structure: ok ({len(numbered_adrs(root))} ADRs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
