#!/usr/bin/env python3
"""Validate lzug's Wiki sidebar invariant and derive its public routes."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

from scripts.wiki_routes import wiki_source_url

DEFAULT_WIKI_BASE_URL = "https://github.com/lxndrp/lzug/wiki"
LINK_PATTERN = re.compile(r"(?<!!)(?:\[[^\]]*\])\(([^)]+)\)")
MARKDOWN_SUFFIXES = {".md", ".markdown"}
SIDEBAR_FILENAME = "_Sidebar.md"


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


def check_sidebar_routes(wiki_root: Path, files: list[Path]) -> tuple[set[str], list[str]]:
    """Check that the flat content pages and canonical sidebar agree."""
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
        return set(), errors

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
    return set(targets), errors


def write_routes(routes: Path, pages: set[str], wiki_base_url: str) -> None:
    """Write a temporary Markdown input that Lychee can check directly."""
    base_url = wiki_base_url.rstrip("/")
    urls = [f"- <{wiki_source_url(page, base_url)}>" for page in sorted(pages)]
    routes.parent.mkdir(parents=True, exist_ok=True)
    routes.write_text("\n".join(urls) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wiki_root", nargs="?", default=".")
    parser.add_argument("--routes", type=Path, help="temporary Markdown route-list output path")
    parser.add_argument("--wiki-base-url", default=DEFAULT_WIKI_BASE_URL)
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()
    if not wiki_root.is_dir():
        print(f"wiki: directory does not exist: {wiki_root}")
        return 1
    files = markdown_files(wiki_root)
    pages, errors = check_sidebar_routes(wiki_root, files)
    if errors:
        print("\n".join(errors))
        return 1

    if args.routes:
        write_routes(args.routes, pages, args.wiki_base_url)
    print(f"wiki sidebar routes: ok ({len(pages)} content pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
