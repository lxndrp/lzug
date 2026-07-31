#!/usr/bin/env python3
"""Validate a reviewable GitHub Wiki source and derive its public sitemap."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from xml.etree.ElementTree import Element, ElementTree, SubElement

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_ci_artifacts import SENSITIVE_PATTERNS  # noqa: E402

DEFAULT_WIKI_BASE_URL = "https://github.com/lxndrp/lzug/wiki"
LINK_PATTERN = re.compile(r"(?<!!)(?:\[[^\]]*\])\(([^)]+)\)")
MARKDOWN_SUFFIXES = {".md", ".markdown"}
SIDEBAR_FILENAME = "_Sidebar.md"
WIKI_SYNTAX_PATTERN = re.compile(r"\[\[[^\]]+\]\]|\{\{[^}]+\}\}")


def relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def markdown_files(wiki_root: Path) -> list[Path]:
    return sorted(
        path for path in wiki_root.rglob("*") if path.is_file() and path.suffix in MARKDOWN_SUFFIXES
    )


def local_link_target(target: str) -> str | None:
    parsed = urlsplit(target.strip().strip("<>"))
    if parsed.scheme or parsed.netloc or not parsed.path or target.startswith("#"):
        return None
    return unquote(parsed.path)


def sidebar_targets(sidebar: Path) -> tuple[list[str], list[str]]:
    targets = []
    errors = []
    text = sidebar.read_text(encoding="utf-8")
    for match in LINK_PATTERN.finditer(text):
        line_number = text.count("\n", 0, match.start()) + 1
        target = match.group(1).strip().strip("<>")
        local_target = local_link_target(target)
        if local_target is None:
            continue
        parsed = urlsplit(target)
        if parsed.query or parsed.fragment:
            errors.append(
                f"{sidebar.name}:{line_number}: sidebar page target must not use a query or "
                "fragment: "
                f"{target}"
            )
        targets.append(local_target)
    return targets, errors


def check_structure(wiki_root: Path, files: list[Path]) -> list[str]:
    actual = {path.relative_to(wiki_root).as_posix() for path in files}
    errors = []
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
    sidebar = wiki_root / SIDEBAR_FILENAME
    if not sidebar.is_file():
        errors.append("wiki: _Sidebar.md is required as the canonical page list")
        return errors

    targets, sidebar_errors = sidebar_targets(sidebar)
    errors.extend(sidebar_errors)
    content_pages = {
        path.stem
        for path in files
        if path.parent == wiki_root and path.name != SIDEBAR_FILENAME and path.suffix == ".md"
    }
    target_counts = Counter(targets)
    errors.extend(
        f"wiki: sidebar target is duplicated: {target}"
        for target, count in sorted(target_counts.items())
        if count > 1
    )
    errors.extend(
        f"wiki: sidebar target must be an extensionless flat page: {target}"
        for target in sorted(target_counts)
        if target.endswith(tuple(MARKDOWN_SUFFIXES))
        or "/" in target
        or target.startswith((".", "/"))
    )
    errors.extend(
        f"wiki: sidebar target does not exist: {target}"
        for target in sorted(set(targets) - content_pages)
    )
    errors.extend(
        f"wiki: content page is missing from _Sidebar.md: {page}"
        for page in sorted(content_pages - set(targets))
    )
    return errors


def check_internal_wiki_route_syntax(files: list[Path]) -> list[str]:
    """Keep raw Markdown paths out of Wiki links; Lychee checks their reachability."""
    errors = []
    for path in files:
        for match in LINK_PATTERN.finditer(path.read_text(encoding="utf-8")):
            target = match.group(1).strip().strip("<>")
            local_target = local_link_target(target)
            if local_target is None:
                continue
            if local_target.endswith(tuple(MARKDOWN_SUFFIXES)):
                errors.append(
                    f"{relative(path)}: internal wiki link must be extensionless: {target}"
                )
            elif "/" in local_target or local_target.startswith((".", "/")):
                errors.append(
                    f"{relative(path)}: internal wiki link must target a flat page: {target}"
                )
    return errors


def check_public_safety(files: list[Path]) -> list[str]:
    errors = []
    for path in files:
        display = relative(path)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if WIKI_SYNTAX_PATTERN.search(line):
                errors.append(
                    f"{display}:{line_number}: Gollum-specific link/template syntax is forbidden"
                )
            if any(pattern.search(line) for pattern in SENSITIVE_PATTERNS):
                errors.append(f"{display}:{line_number}: secret-like content detected")
    return errors


def write_sitemap(sitemap: Path, pages: set[str], wiki_base_url: str) -> None:
    base_url = wiki_base_url.rstrip("/")
    urlset = Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for page in sorted(pages):
        location = base_url if page == "Home" else f"{base_url}/{quote(page)}"
        url = SubElement(urlset, "url")
        SubElement(url, "loc").text = location
    sitemap.parent.mkdir(parents=True, exist_ok=True)
    ElementTree(urlset).write(sitemap, encoding="utf-8", xml_declaration=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wiki_root", nargs="?", default=".")
    parser.add_argument("--sitemap", type=Path, required=True, help="temporary sitemap output path")
    parser.add_argument("--wiki-base-url", default=DEFAULT_WIKI_BASE_URL)
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()
    if not wiki_root.is_dir():
        print(f"wiki: directory does not exist: {wiki_root}")
        return 1
    files = markdown_files(wiki_root)
    errors = check_structure(wiki_root, files)
    errors.extend(check_internal_wiki_route_syntax(files))
    errors.extend(check_public_safety(files))
    if errors:
        print("\n".join(errors))
        return 1

    pages, _ = sidebar_targets(wiki_root / SIDEBAR_FILENAME)
    write_sitemap(args.sitemap, set(pages), args.wiki_base_url)
    print(f"wiki source policy: ok ({len(pages)} content pages; sitemap: {args.sitemap})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
