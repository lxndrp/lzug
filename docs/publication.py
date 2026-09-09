#!/usr/bin/env python3
"""Build and verify the public Relearn documentation artifact.

The build checks out one reviewed Relearn revision, builds a static artifact and
never calls a hosting API or mutates the GitHub Wiki.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from backend.fastapi_assembly import FastAPIConfig, create_app

RELEARN_REPOSITORY = "https://github.com/McShelby/hugo-theme-relearn.git"
RELEARN_REVISION = "8bb66fa674351f3a0b0917a7552caac686eca920"
PUBLICATION_BASE_URL = "https://lzug.repertoire.papaspyrou.name"
WIKI_BASE_URL = "https://github.com/lxndrp/lzug/wiki"
INHERITED_PUBLIC_HOSTS = frozenset({"lxndrp.github.io", "stage.papaspyrou.name"})
MARKDOWN_LINK = re.compile(r"(?P<prefix>\[[^\]]+\]\()(?P<target>[^)]+)(?P<suffix>\))")
CHANGELOG_RELEASE = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+)\] - ", re.MULTILINE)
MARKDOWN_SUFFIXES = (".md", ".markdown")
WIKI_REQUIRED_PAGES = frozenset({"Home", "_Sidebar", "Versionshinweise"})
WIKI_DEVELOPER_PREFIX = "Entwicklung"
PUBLICATION_FRAGMENT_REMAP = {
    "vollstandige-qualitat": "vollständige-qualität",
    "lokaler-admin-und-artefaktvertrag": "lokaler-admin--und-artefaktvertrag",
}
EXPECTED_OUTPUTS = (
    "index.html",
    "images/favicon.svg",
    "images/screenshots/demo-scenarios-desktop.png",
    "images/screenshots/demo-scenarios-mobile.png",
    "js/demo-warmup.js",
    "produkt/index.html",
    "nutzen/index.html",
    "betreiben/index.html",
    "entwickeln/index.html",
    "handbuch/index.html",
    "referenz/index.html",
    "referenz/api/index.html",
    "referenz/api/openapi.json",
    "referenz/backend/index.html",
    "referenz/frontend/index.html",
    "referenz/datenbank/index.html",
    "entwickeln/reference/full-export-v1.schema.json",
    "quellen/index.html",
    "quellen.json",
    "searchindex.de.js",
    ".nojekyll",
)
PAGES_CANDIDATE_EXPECTED_OUTPUTS = (
    "index.html",
    "images/favicon.svg",
    "images/screenshots/demo-scenarios-desktop.png",
    "images/screenshots/demo-scenarios-mobile.png",
    "js/demo-warmup.js",
    "produkt/index.html",
    "referenz/index.html",
    "referenz/api/index.html",
    "referenz/api/openapi.json",
    "referenz/backend/index.html",
    "referenz/frontend/index.html",
    "referenz/datenbank/index.html",
    "quellen/index.html",
    "quellen.json",
    "searchindex.de.js",
    ".nojekyll",
)
PAGES_CANDIDATE_FORBIDDEN_PATHS = (
    "handbuch",
    "fachlichkeit",
    "nutzen",
    "betreiben",
    "entwickeln",
)


def run(*command: str, cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as error:
        details = "\n".join(part for part in (error.stdout, error.stderr) if part)
        raise RuntimeError(f"Command failed: {' '.join(command)}\n{details}") from error
    return completed.stdout.strip()


def repository_root() -> Path:
    return Path(run("git", "rev-parse", "--show-toplevel")).resolve()


def ensure_safe_output(root: Path, output: Path) -> Path:
    resolved = output.resolve()
    allowed_roots = ((root / "build").resolve(), Path(tempfile.gettempdir()).resolve())
    if not any(resolved == allowed or allowed in resolved.parents for allowed in allowed_roots):
        raise ValueError("output must be below build/ or the system temp directory")
    return resolved


def convert_handbook_links(markdown: str, known_pages: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_target = match.group("target")
        target, separator, fragment = raw_target.partition("#")
        if (
            not target
            or target.startswith(("http://", "https://", "mailto:", "/"))
            or "/" in target
            or Path(target).suffix
        ):
            return match.group(0)
        if target not in known_pages:
            raise ValueError(f"Unknown extensionless handbook target: {target}")
        converted = known_pages[target]
        if separator:
            converted += f"#{fragment}"
        return f"{match.group('prefix')}{converted}{match.group('suffix')}"

    return MARKDOWN_LINK.sub(replace, markdown)


def convert_repository_links(markdown: str, source: Path, source_routes: dict[str, str]) -> str:
    """Rewrite Markdown source links to their one generated public route."""

    def replace(match: re.Match[str]) -> str:
        raw_target = match.group("target")
        target, separator, fragment = raw_target.partition("#")
        if not target or target.startswith(("http://", "https://", "mailto:", "/")):
            return match.group(0)
        relative = posixpath.normpath((source.parent / target).as_posix())
        route = source_routes.get(relative)
        if route is None:
            return match.group(0)
        if separator:
            route += f"#{PUBLICATION_FRAGMENT_REMAP.get(fragment, fragment)}"
        return f"{match.group('prefix')}{route}{match.group('suffix')}"

    return MARKDOWN_LINK.sub(replace, markdown)


def candidate_product_content(markdown: str, repository_revision: str) -> str:
    """Route prospective Pages hand-offs to their future canonical surfaces."""

    replacements = {
        "/nutzen/": f"{WIKI_BASE_URL}/Nutzung",
        "/betreiben/": f"{WIKI_BASE_URL}/Administration",
        "/entwickeln/": source_url(Path("docs/developers/index.md"), repository_revision),
    }
    for old, new in replacements.items():
        markdown = markdown.replace(f"]({old})", f"]({new})")
    return markdown


def source_url(path: Path, repository_revision: str) -> str:
    """Return the immutable repository source URL for one rendered page."""

    return f"https://github.com/lxndrp/lzug/blob/{repository_revision}/{path.as_posix()}"


def handbook_route(path: Path) -> str:
    """Return the public route for one migrated handbook source page."""

    stem = path.stem.lower()
    if path.name == "Home.md":
        return "/handbuch/"
    if stem.startswith("administration"):
        return f"/betreiben/{stem.removeprefix('administration-')}/"
    if stem.startswith("nutzung"):
        return f"/nutzen/{stem.removeprefix('nutzung-')}/"
    if stem.startswith("entwicklung"):
        return f"/entwickeln/{stem.removeprefix('entwicklung-')}/"
    return f"/fachlichkeit/{stem}/"


def handbook_file(route: str) -> Path:
    """Convert a public handbook route into its generated Hugo content path."""

    parts = [part for part in route.strip("/").split("/") if part]
    if route == "/handbuch/":
        return Path("handbuch/_index.md")
    return Path(*parts) / "_index.md"


def stable_version(root: Path) -> str:
    """Return the newest released version recorded in the canonical changelog."""

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = CHANGELOG_RELEASE.search(changelog)
    if match is None:
        raise ValueError("CHANGELOG.md does not contain a released semantic version")
    return match.group("version")


def wiki_source_files(root: Path) -> list[Path]:
    """Return current editorial sources that belong in the Wiki candidate."""

    handbook = root / "docs" / "handbook"
    return sorted(
        path
        for path in handbook.glob("*.md")
        if path.name != "_Sidebar.md" and not path.stem.startswith(WIKI_DEVELOPER_PREFIX)
    )


def markdown_title(path: Path) -> str:
    """Read the first level-one heading used as a sidebar label."""

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    raise ValueError(f"Wiki source has no level-one heading: {path}")


def wiki_home(markdown: str, version: str) -> str:
    """Adapt the current repository source to the prospective Wiki contract."""

    source_statement = (
        "Dieses Handbuch ist die vollständige und kanonische\n"
        "redaktionelle Handbuchquelle für Fachlichkeit, Nutzung und Administration."
    )
    candidate_statement = (
        "Dieses Wiki ist das vollständige und kanonische redaktionelle Handbuch\n"
        "für Fachlichkeit, Nutzung und Administration."
    )
    if source_statement not in markdown:
        raise ValueError("Handbook Home no longer contains the expected source statement")
    markdown = markdown.replace(source_statement, candidate_statement, 1)
    heading = "## Einstieg"
    version_statement = (
        f"**Stand:** Dieses Wiki beschreibt grundsätzlich den aktuellen stabilen Stand "
        f"lzug {version}.\n\n"
    )
    if heading not in markdown:
        raise ValueError("Handbook Home no longer contains the expected entry section")
    return markdown.replace(heading, version_statement + heading, 1)


def rewrite_wiki_candidate_links(
    markdown: str,
    candidate_pages: set[str],
    repository_revision: str,
) -> str:
    """Keep Wiki links extensionless and route developer links to the repository."""

    developer_url = source_url(Path("docs/developers/index.md"), repository_revision)

    def replace(match: re.Match[str]) -> str:
        raw_target = match.group("target").strip().strip("<>")
        parsed = urlparse(raw_target)
        if parsed.scheme or parsed.netloc or raw_target.startswith(("/", "#")):
            return match.group(0)
        target = unquote(parsed.path)
        if target.startswith(WIKI_DEVELOPER_PREFIX):
            replacement = developer_url
            if parsed.fragment:
                replacement += f"#{parsed.fragment}"
            return f"{match.group('prefix')}{replacement}{match.group('suffix')}"
        if target in candidate_pages:
            replacement = target
            if parsed.fragment:
                replacement += f"#{parsed.fragment}"
            return f"{match.group('prefix')}{replacement}{match.group('suffix')}"
        return match.group(0)

    return MARKDOWN_LINK.sub(replace, markdown)


def wiki_sidebar(sources: list[Path]) -> str:
    """Create one complete, deterministic sidebar from current source headings."""

    groups = (
        ("Einstieg", ("Home", "Versionshinweise")),
        (
            "Fachlichkeit",
            ("Fachlichkeit", "Prozess-", "User-Journey-", "Entscheidungsmatrix-"),
        ),
        ("Nutzung", ("Nutzung",)),
        ("Betrieb", ("Administration",)),
    )
    labels = {path.stem: markdown_title(path) for path in sources}
    labels["Versionshinweise"] = "Versionshinweise"
    remaining = set(labels)
    lines = ["# Navigation", ""]
    for title, prefixes in groups:
        pages = sorted(page for page in remaining if page.startswith(prefixes))
        if not pages:
            continue
        lines.extend((f"## {title}", ""))
        for page in pages:
            lines.append(f"- [{labels[page]}]({page})")
            remaining.remove(page)
        lines.append("")
    if remaining:
        raise ValueError(f"Wiki pages have no sidebar group: {sorted(remaining)!r}")
    return "\n".join(lines).rstrip() + "\n"


def wiki_versions(version: str) -> str:
    """Create the version contract without adding a second maintained source."""

    return (
        "# Versionshinweise\n\n"
        f"Dieses Wiki beschreibt grundsätzlich den aktuellen stabilen Stand lzug {version}.\n"
        "Redaktionelle Klarstellungen ohne abweichendes Produktverhalten erhalten keine eigene "
        "Versionsmarkierung.\n"
        "Wenn sich beschriebenes Verhalten zwischen unterstützten Versionen unterscheidet, "
        "steht der Hinweis unmittelbar an der betroffenen Stelle.\n\n"
        "Veröffentlichte Produktstände und Änderungen sind im "
        "[Changelog](https://github.com/lxndrp/lzug/blob/master/CHANGELOG.md) und in den "
        "[GitHub Releases](https://github.com/lxndrp/lzug/releases) nachvollziehbar.\n"
    )


def build_wiki_candidate(root: Path, output: Path, repository_revision: str) -> None:
    """Build a flat Wiki candidate from the still-canonical repository sources."""

    output = ensure_safe_output(root, output)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    sources = wiki_source_files(root)
    if not sources or not any(path.name == "Home.md" for path in sources):
        raise ValueError("Wiki candidate sources must include docs/handbook/Home.md")
    pages = {path.stem for path in sources} | {"Versionshinweise"}
    version = stable_version(root)
    for source in sources:
        markdown = source.read_text(encoding="utf-8")
        if source.name == "Home.md":
            markdown = wiki_home(markdown, version)
        markdown = rewrite_wiki_candidate_links(markdown, pages, repository_revision)
        (output / source.name).write_text(markdown.rstrip() + "\n", encoding="utf-8")
    (output / "Versionshinweise.md").write_text(wiki_versions(version), encoding="utf-8")
    (output / "_Sidebar.md").write_text(wiki_sidebar(sources), encoding="utf-8")
    errors = check_wiki_candidate(output, version)
    if errors:
        raise ValueError("Invalid Wiki candidate:\n" + "\n".join(errors))


def local_markdown_target(raw_target: str) -> tuple[str, str, str] | None:
    """Parse a local Markdown page target into path, query, and fragment."""

    target = raw_target.strip().strip("<>")
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or target.startswith("#") or not parsed.path:
        return None
    return unquote(parsed.path), parsed.query, parsed.fragment


def sidebar_targets(sidebar: Path) -> tuple[list[str], list[str]]:
    """Return extensionless page targets from the canonical sidebar."""

    targets: list[str] = []
    errors: list[str] = []
    text = sidebar.read_text(encoding="utf-8")
    for match in MARKDOWN_LINK.finditer(text):
        parsed = local_markdown_target(match.group("target"))
        if parsed is None:
            continue
        target, query, fragment = parsed
        line = text.count("\n", 0, match.start()) + 1
        if query or fragment:
            errors.append(
                f"_Sidebar.md:{line}: page target must not use a query or fragment: {target}"
            )
        targets.append(target)
    return targets, errors


def check_wiki_candidate(wiki_root: Path, version: str | None = None) -> list[str]:
    """Validate flat pages, sidebar completeness, and all internal Wiki links."""

    errors: list[str] = []
    files = sorted(
        path
        for path in wiki_root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(wiki_root).parts
    )
    names = [path.relative_to(wiki_root).as_posix() for path in files]
    errors.extend(f"wiki: page must be flat: {name}" for name in names if "/" in name)
    errors.extend(
        f"wiki: page must use the .md extension: {name}"
        for name in names
        if Path(name).suffix.lower() != ".md"
    )
    stems = [Path(name).stem for name in names if Path(name).suffix.lower() == ".md"]
    folded = Counter(stem.casefold() for stem in stems)
    errors.extend(
        f"wiki: page name is not globally unique: {stem}"
        for stem in sorted(stems)
        if folded[stem.casefold()] > 1
    )
    missing = sorted(WIKI_REQUIRED_PAGES - set(stems))
    errors.extend(f"wiki: required page is missing: {page}.md" for page in missing)
    errors.extend(
        f"wiki: developer page must remain in the repository: {stem}.md"
        for stem in stems
        if stem.startswith(WIKI_DEVELOPER_PREFIX)
    )
    sidebar = wiki_root / "_Sidebar.md"
    if not sidebar.is_file():
        return errors
    targets, sidebar_errors = sidebar_targets(sidebar)
    errors.extend(sidebar_errors)
    counts = Counter(targets)
    errors.extend(
        f"wiki: sidebar target is duplicated: {target}"
        for target, count in sorted(counts.items())
        if count > 1
    )
    content_pages = set(stems) - {"_Sidebar"}
    for target in sorted(counts):
        if target.endswith(MARKDOWN_SUFFIXES) or "/" in target or target.startswith((".", "/")):
            errors.append(f"wiki: sidebar target must be an extensionless flat page: {target}")
        elif target not in content_pages:
            errors.append(f"wiki: sidebar target does not exist: {target}")
    errors.extend(
        f"wiki: content page is missing from _Sidebar.md: {page}"
        for page in sorted(content_pages - set(targets))
    )
    for path in files:
        if path.suffix.lower() != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            parsed = local_markdown_target(match.group("target"))
            if parsed is None:
                continue
            target, query, _fragment = parsed
            line = text.count("\n", 0, match.start()) + 1
            if query:
                errors.append(f"{path.name}:{line}: internal Wiki target must not use a query")
            if target.endswith(MARKDOWN_SUFFIXES) or "/" in target or target.startswith((".", "/")):
                errors.append(
                    f"{path.name}:{line}: internal Wiki target must be extensionless and flat: "
                    f"{target}"
                )
            elif target not in content_pages:
                errors.append(f"{path.name}:{line}: internal Wiki target does not exist: {target}")
    if version:
        marker = f"aktuellen stabilen Stand lzug {version}"
        for required in ("Home.md", "Versionshinweise.md"):
            candidate = wiki_root / required
            if candidate.is_file() and marker not in candidate.read_text(encoding="utf-8"):
                errors.append(f"wiki: {required} does not identify stable version {version}")
    return errors


def write_wiki_routes(wiki_root: Path, output: Path, base_url: str) -> None:
    """Create a temporary Lychee input from the checked sidebar routes."""

    targets, errors = sidebar_targets(wiki_root / "_Sidebar.md")
    if errors:
        raise ValueError("Invalid Wiki sidebar:\n" + "\n".join(errors))
    base = public_url(base_url, allow_path=True)
    routes = [base if page == "Home" else f"{base}/{quote(page)}" for page in targets]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(f"- <{route}>\n" for route in routes), encoding="utf-8")


class RejectRedirects(HTTPRedirectHandler):
    """Turn redirects into inspectable HTTP errors."""

    def redirect_request(self, request, response, code, msg, headers, new_url):
        return None


def check_published_wiki(wiki_root: Path, base_url: str) -> list[str]:
    """Read every sidebar route and reject redirects or non-HTML responses."""

    targets, errors = sidebar_targets(wiki_root / "_Sidebar.md")
    if errors:
        return errors
    base = public_url(base_url, allow_path=True)
    opener = build_opener(RejectRedirects)
    for page in targets:
        url = base if page == "Home" else f"{base}/{quote(page)}"
        request = Request(url, headers={"User-Agent": "lzug-wiki-post-publish-check"})
        try:
            response = opener.open(request, timeout=20)
        except HTTPError as error:
            location = error.headers.get("Location", "")
            errors.append(
                f"{page}: expected direct HTTP 200, got {error.code}"
                + (f" redirecting to {location}" if location else "")
            )
            continue
        status = getattr(response, "status", response.getcode())
        content_type = response.headers.get_content_type()
        final_url = response.geturl()
        response.close()
        if status != 200:
            errors.append(f"{page}: expected HTTP 200, got {status}")
        if content_type != "text/html":
            errors.append(f"{page}: expected Content-Type text/html, got {content_type}")
        if "raw.githubusercontent.com" in final_url:
            errors.append(f"{page}: resolved to raw content: {final_url}")
    return errors


def hugo_page(
    title: str,
    description: str,
    body: str,
    page_type: str | None = None,
    provenance: str | None = None,
) -> str:
    frontmatter = {
        "title": title,
        "description": description,
        "draft": False,
    }
    if page_type:
        frontmatter["type"] = page_type
    prefix = f"> {provenance}\n\n" if provenance else ""
    return f"---\n{json.dumps(frontmatter, ensure_ascii=False)}\n---\n\n{prefix}{body.rstrip()}\n"


def prepare_relearn_checkout(destination: Path) -> None:
    local_source = os.environ.get("LZUG_RELEARN_SOURCE")
    if local_source:
        source = Path(local_source).resolve()
        if run("git", "rev-parse", "HEAD", cwd=source) != RELEARN_REVISION:
            raise ValueError("LZUG_RELEARN_SOURCE does not match the pinned revision")
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns("public", "resources"))
        return

    run("git", "clone", "--filter=blob:none", "--no-checkout", RELEARN_REPOSITORY, str(destination))
    run("git", "checkout", "--detach", RELEARN_REVISION, cwd=destination)
    if run("git", "rev-parse", "HEAD", cwd=destination) != RELEARN_REVISION:
        raise ValueError("Relearn checkout does not match the pinned revision")


def public_url(value: str, *, allow_path: bool) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
        or "*" in value
        or parsed.hostname.lower() in INHERITED_PUBLIC_HOSTS
        or (not allow_path and parsed.path not in {"", "/"})
    ):
        raise ValueError(
            "public URLs must be absolute HTTPS URLs without credentials, query, or fragment"
        )
    normalized_path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{normalized_path}"


def publication_base_url(value: str) -> str:
    normalized = public_url(value, allow_path=True)
    if normalized != PUBLICATION_BASE_URL:
        raise ValueError(
            f"publication base URL must be the canonical HTTPS origin {PUBLICATION_BASE_URL}"
        )
    return normalized


def configure_relearn(
    root: Path,
    site: Path,
    base_url: str,
    demo_url: str,
    repository_revision: str,
    *,
    pages_candidate: bool = False,
) -> None:
    (site / "hugo.toml").write_text(
        f"baseURL = {json.dumps(base_url + '/', ensure_ascii=False)}\n"
        "title = 'lzug'\n"
        "theme = 'relearn'\n"
        "defaultContentLanguage = 'de'\n"
        "disableHugoGeneratorInject = true\n\n"
        "[languages.de]\n  title = 'lzug'\n  languageCode = 'de-DE'\n"
        "  languageName = 'Deutsch'\n  contentDir = 'content'\n  weight = 1\n\n"
        "[params]\n  disableLandingPageButton = true\n"
        "  disableLanguageSwitchingButton = true\n"
        "  disableThemeSwitchingButton = false\n"
        "  linkTitle = 'lzug'\n"
        f"  demoURL = {json.dumps(demo_url, ensure_ascii=False)}\n"
        "  [[params.themeVariant]]\n    identifier = 'relearn-light'\n    name = 'Hell'\n"
        "  [[params.themeVariant]]\n    identifier = 'relearn-dark'\n    name = 'Dunkel'\n",
        encoding="utf-8",
    )
    (site / "layouts" / "home").mkdir(parents=True)
    (site / "layouts" / "partials").mkdir(parents=True)
    (site / "assets" / "css").mkdir(parents=True)
    (site / "static" / "images").mkdir(parents=True)
    (site / "static" / "images" / "brand").mkdir(parents=True)
    (site / "static" / "images" / "screenshots").mkdir(parents=True)
    (site / "static" / "fonts").mkdir(parents=True)
    (site / "static" / "css").mkdir(parents=True)
    (site / "static" / "js").mkdir(parents=True)
    home_layout = (
        root / "docs" / "publication" / "relearn" / "layouts" / "home" / "article.html"
    ).read_text(encoding="utf-8")
    if pages_candidate:
        home_layout = (
            home_layout.replace(
                '<a href="{{ relURL "nutzen/" }}">nächsten fachlich zulässigen Schritt</a>',
                f'<a href="{WIKI_BASE_URL}/Nutzung">Nutzerhandbuch im GitHub Wiki</a>',
            )
            .replace(
                '<a href="{{ relURL "betreiben/" }}">Self-Hosting, Bootstrap, Diagnose und '
                "erstes Backup</a>",
                f'<a href="{WIKI_BASE_URL}/Administration">Betreiberhandbuch im GitHub Wiki</a>',
            )
            .replace(
                '<a href="{{ relURL "entwickeln/" }}">Architektur, Entwicklung, Referenzen und '
                "ADRs</a>",
                '<a href="'
                + source_url(Path("docs/developers/index.md"), repository_revision)
                + '">Entwicklerdokumentation im Hauptrepository</a>',
            )
        )
    (site / "layouts" / "home" / "article.html").write_text(home_layout, encoding="utf-8")
    shutil.copyfile(
        root / "docs" / "publication" / "relearn" / "layouts" / "partials" / "favicon.html",
        site / "layouts" / "partials" / "favicon.html",
    )
    shutil.copyfile(
        root / "docs" / "publication" / "relearn" / "assets" / "css" / "custom.css",
        site / "assets" / "css" / "custom.css",
    )
    shutil.copyfile(
        root / "docs" / "publication" / "relearn" / "static" / "js" / "demo-warmup.js",
        site / "static" / "js" / "demo-warmup.js",
    )
    for name in (
        "favicon.svg",
        "key-visual-dark.svg",
        "key-visual-light.svg",
        "logo-horizontal-dark.svg",
        "logo-horizontal-light.svg",
    ):
        shutil.copyfile(
            root / "brand" / "derived" / name,
            site / "static" / "images" / "brand" / name,
        )
    if not pages_candidate:
        schema_source = root / "docs" / "developers" / "reference" / "full-export-v1.schema.json"
        schema_target = site / "static" / "entwickeln" / "reference" / schema_source.name
        schema_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(schema_source, schema_target)
    shutil.copyfile(
        root / "brand" / "derived" / "favicon.svg",
        site / "static" / "images" / "favicon.svg",
    )
    for screenshot in (root / "docs" / "media").glob("*.png"):
        shutil.copyfile(screenshot, site / "static" / "images" / "screenshots" / screenshot.name)
    shutil.copyfile(
        root / "brand" / "tokens.css",
        site / "static" / "css" / "brand-tokens.css",
    )
    shutil.copyfile(
        root / "docs" / "publication" / "public-font.css",
        site / "static" / "css" / "brand-font.css",
    )
    for subset in ("latin", "greek", "greek-ext"):
        shutil.copyfile(
            root
            / "frontend"
            / "node_modules"
            / "@fontsource-variable"
            / "inter"
            / "files"
            / f"inter-{subset}-wght-normal.woff2",
            site / "static" / "fonts" / f"inter-{subset}-wght-normal.woff2",
        )
    (site / "layouts" / "partials" / "assetbusting.gotmpl").write_text(
        f'{{{{- return "?{repository_revision[:12]}" }}}}\n', encoding="utf-8"
    )


def write_content(
    root: Path,
    site: Path,
    repository_revision: str,
    *,
    pages_candidate: bool = False,
) -> None:
    handbook_root = root / "docs" / "handbook"
    handbook_files = sorted(
        path for path in handbook_root.glob("*.md") if path.name != "_Sidebar.md"
    )
    if not handbook_files or not (handbook_root / "Home.md").is_file():
        raise ValueError("Repository handbook must contain Home.md and migrated content")

    known_pages = {path.stem: handbook_route(path) for path in handbook_files}
    developer_files = sorted((root / "docs" / "developers").rglob("*.md"))
    source_routes = {
        **{path.relative_to(root).as_posix(): handbook_route(path) for path in handbook_files},
        "docs/portal/produkt.md": "/produkt/",
        "docs/portal/nutzen.md": "/nutzen/",
        "docs/portal/betreiben.md": "/betreiben/",
        **{
            path.relative_to(root).as_posix(): "/entwickeln/"
            + path.relative_to(root / "docs" / "developers")
            .with_suffix("")
            .as_posix()
            .replace("/index", "")
            + "/"
            for path in developer_files
        },
        "docs/developers/reference/backend.md": "/referenz/backend/",
        "docs/developers/reference/frontend.md": "/referenz/frontend/",
        "docs/developers/reference/cli.md": "/referenz/cli/",
        "docs/developers/reference/full-export-v1.schema.json": (
            "/entwickeln/reference/full-export-v1.schema.json"
        ),
    }
    source_routes["docs/developers/index.md"] = "/entwickeln/"
    source_routes["docs/developers/decisions/index.md"] = "/entwickeln/entscheidungen/"
    content = site / "content"
    (content / "produkt").mkdir(parents=True)
    if not pages_candidate:
        (content / "handbuch").mkdir(parents=True)
        (content / "nutzen").mkdir(parents=True)
        (content / "betreiben").mkdir(parents=True)
        (content / "entwickeln").mkdir(parents=True)
    (content / "referenz" / "api").mkdir(parents=True)
    (content / "referenz" / "backend").mkdir(parents=True)
    (content / "referenz" / "frontend").mkdir(parents=True)
    (content / "referenz" / "datenbank").mkdir(parents=True)
    (content / "quellen").mkdir(parents=True)
    (site / "static" / "referenz" / "api").mkdir(parents=True, exist_ok=True)

    landing = (root / "docs" / "publication" / "content" / "index.md").read_text(encoding="utf-8")
    if pages_candidate:
        landing = landing.replace(
            "Alle Produkt-, Nutzer-, Betreiber- und Entwicklerdokumentation stammt aus "
            "derselben Repository-Revision.",
            "Produktseite und technische Referenzen stammen aus derselben Repository-Revision. "
            "Redaktionelle Handbücher werden im GitHub Wiki geführt; technische "
            "Entwicklerdokumentation bleibt im Hauptrepository.",
        )
    (content / "_index.md").write_text(
        hugo_page("lzug", "Prüfungen gemeinsam verlässlich planen", landing, "home"),
        encoding="utf-8",
    )
    portal_pages = {"produkt": ("lzug", "Produktinformation und öffentlicher Einstieg")}
    if not pages_candidate:
        portal_pages.update(
            {
                "nutzen": ("Nutzung", "Erste fachliche Schritte und Nutzerhandbuch"),
                "betreiben": ("Self-Hosting", "Installation, Bootstrap und Betrieb"),
            }
        )
    for slug, (title, description) in portal_pages.items():
        source = root / "docs" / "portal" / f"{slug if slug != 'betreiben' else 'betreiben'}.md"
        body = convert_repository_links(
            source.read_text(encoding="utf-8"), source.relative_to(root), source_routes
        )
        if pages_candidate and slug == "produkt":
            body = candidate_product_content(body, repository_revision)
        (content / slug / "_index.md").write_text(
            hugo_page(
                title,
                description,
                body,
                provenance=(
                    f"Quelle: [{source.relative_to(root)}]"
                    f"({source_url(source.relative_to(root), repository_revision)}) · "
                    f"Revision `{repository_revision}`."
                ),
            ),
            encoding="utf-8",
        )
    if not pages_candidate:
        developer_source = root / "docs" / "developers" / "index.md"
        (content / "entwickeln" / "_index.md").write_text(
            hugo_page(
                "Entwicklung",
                "Architektur, Entwicklung, Referenzen und Entscheidungen",
                convert_repository_links(
                    developer_source.read_text(encoding="utf-8"),
                    developer_source.relative_to(root),
                    source_routes,
                ),
                provenance=(
                    f"Quelle: [{developer_source.relative_to(root)}]"
                    f"({source_url(developer_source.relative_to(root), repository_revision)}) · "
                    f"Revision `{repository_revision}`."
                ),
            ),
            encoding="utf-8",
        )
        for developer_source in developer_files:
            if developer_source == root / "docs" / "developers" / "index.md":
                continue
            relative = developer_source.relative_to(root)
            route = source_routes[relative.as_posix()]
            target = content / Path(*route.strip("/").split("/")) / "_index.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                hugo_page(
                    developer_source.stem,
                    f"Kanonische Entwicklerdokumentation: {developer_source.stem}",
                    convert_repository_links(
                        developer_source.read_text(encoding="utf-8"),
                        relative,
                        source_routes,
                    ),
                    provenance=(
                        f"Quelle: [{relative}]({source_url(relative, repository_revision)}) · "
                        f"Revision `{repository_revision}`."
                    ),
                ),
                encoding="utf-8",
            )
        for handbook_source in handbook_files:
            relative = handbook_source.relative_to(root)
            route = handbook_route(handbook_source)
            body = convert_handbook_links(handbook_source.read_text(encoding="utf-8"), known_pages)
            body = convert_repository_links(body, relative, source_routes)
            target = content / handbook_file(route)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                hugo_page(
                    handbook_source.stem if handbook_source.name != "Home.md" else "Handbuch",
                    f"Kanonisches Repository-Handbuch: {handbook_source.stem}",
                    body,
                    provenance=(
                        f"Quelle: [{relative}]({source_url(relative, repository_revision)}) · "
                        f"Revision `{repository_revision}`."
                    ),
                ),
                encoding="utf-8",
            )

    backend = (root / "docs" / "developers" / "reference" / "backend.md").read_text(
        encoding="utf-8"
    )
    (content / "referenz" / "backend" / "_index.md").write_text(
        hugo_page(
            "Python-Backend",
            "Aus Python-Docstrings erzeugte Backend-Referenz",
            backend,
            provenance=f"Revision `{repository_revision}`.",
        ),
        encoding="utf-8",
    )

    api_document = create_app(
        FastAPIConfig(db_path=Path(":memory:"), session_cookie_name="__Host-lzug_session")
    ).openapi()
    (site / "static" / "referenz" / "api" / "openapi.json").write_text(
        json.dumps(api_document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (content / "referenz" / "api" / "_index.md").write_text(
        hugo_page(
            "API-Referenz",
            "Aus dem OpenAPI-Vertrag erzeugte API-Referenz",
            "Der Publikationsaufbau exportiert den Vertrag als "
            "[OpenAPI-JSON](/referenz/api/openapi.json). "
            "Die produktive Pipeline bündelt daraus eine gelockte Redoc-Ausgabe.",
            provenance=f"Revision `{repository_revision}`.",
        ),
        encoding="utf-8",
    )

    schema = (root / "backend" / "db" / "schema.sql").read_text(encoding="utf-8")
    (content / "referenz" / "datenbank" / "_index.md").write_text(
        hugo_page(
            "Datenbankschema",
            "Deterministische Ansicht des kanonischen Datenbankschemas",
            f"```sql\n{schema.rstrip()}\n```",
            provenance=f"Revision `{repository_revision}`.",
        ),
        encoding="utf-8",
    )
    (content / "referenz" / "frontend" / "_index.md").write_text(
        hugo_page(
            "TypeScript-Frontend",
            "Aus TSDoc erzeugte Frontend-Referenz",
            "TypeDoc ersetzt diese Seite im Zielartefakt.",
            provenance=f"Revision `{repository_revision}`.",
        ),
        encoding="utf-8",
    )
    (content / "referenz" / "_index.md").write_text(
        hugo_page(
            "Technische Referenz",
            "Revisionsgebundene technische Referenzen",
            "Die Generatoren schreiben unabhängig und werden erst im Zielartefakt zusammengeführt.",
            provenance=f"Revision `{repository_revision}`.",
        ),
        encoding="utf-8",
    )

    manifest = {
        "profile": "reduced-pages-candidate" if pages_candidate else "current-publication",
        "relearn_revision": RELEARN_REVISION,
        "repository": "https://github.com/lxndrp/lzug",
        "repository_revision": repository_revision,
    }
    (site / "static" / "quellen.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (content / "quellen" / "_index.md").write_text(
        hugo_page(
            "Quellen und Versionen",
            "Revisionsidentität der erzeugten Ausgabe",
            f"- Hauptrepository: `{repository_revision}`\n"
            f"- Relearn: `{RELEARN_REVISION}`\n\n"
            "[Maschinenlesbare Fassung](/quellen.json)",
            provenance=f"Revision `{repository_revision}`.",
        ),
        encoding="utf-8",
    )


def prepare_site(
    root: Path,
    destination: Path,
    base_url: str,
    demo_url: str,
    *,
    pages_candidate: bool = False,
) -> None:
    destination.mkdir(parents=True)
    repository_revision = run("git", "rev-parse", "HEAD", cwd=root)
    prepare_relearn_checkout(destination / "themes" / "relearn")
    configure_relearn(
        root,
        destination,
        base_url,
        demo_url,
        repository_revision,
        pages_candidate=pages_candidate,
    )
    write_content(
        root,
        destination,
        repository_revision,
        pages_candidate=pages_candidate,
    )


def verify_output(output: Path, stage: Path, *, pages_candidate: bool = False) -> None:
    expected = PAGES_CANDIDATE_EXPECTED_OUTPUTS if pages_candidate else EXPECTED_OUTPUTS
    missing = [relative for relative in expected if not (output / relative).is_file()]
    if missing:
        raise ValueError(f"Publication artifact is missing: {', '.join(missing)}")
    if pages_candidate:
        unexpected = [
            relative for relative in PAGES_CANDIDATE_FORBIDDEN_PATHS if (output / relative).exists()
        ]
        if unexpected:
            raise ValueError(
                "Reduced Pages candidate still contains handbook or developer routes: "
                + ", ".join(unexpected)
            )
    stage_text = str(stage).encode()
    for path in output.rglob("*"):
        if path.is_file() and stage_text in path.read_bytes():
            raise ValueError(f"Generated output leaks temporary path: {path}")


def render(
    root: Path,
    site: Path,
    output: Path,
    typedoc: Path,
    *,
    pages_candidate: bool = False,
) -> None:
    if output.exists():
        shutil.rmtree(output)
    run("hugo", "--minify", "--gc", "--destination", str(output), cwd=site)
    if not typedoc.is_file():
        raise ValueError(f"TypeDoc is missing: {typedoc}; run task setup:frontend")
    run(
        str(typedoc),
        "--treatWarningsAsErrors",
        "--entryPointStrategy",
        "expand",
        "--entryPoints",
        "src/app",
        "--out",
        str(output / "referenz" / "frontend"),
        cwd=root / "frontend",
    )
    (output / ".nojekyll").write_text("", encoding="utf-8")
    verify_output(output, site, pages_candidate=pages_candidate)


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def differing_files(first: Path, second: Path) -> list[str]:
    paths = {path.relative_to(first).as_posix() for path in first.rglob("*") if path.is_file()} | {
        path.relative_to(second).as_posix() for path in second.rglob("*") if path.is_file()
    }
    return [
        path
        for path in sorted(paths)
        if not (first / path).is_file()
        or not (second / path).is_file()
        or (first / path).read_bytes() != (second / path).read_bytes()
    ]


def publication_inventory(root: Path, repository_revision: str) -> list[dict[str, str]]:
    """Create the one-time source/target/decision inventory in generated evidence."""

    inventory: list[dict[str, str]] = []
    for source in sorted((root / "docs" / "handbook").glob("*.md")):
        relative = source.relative_to(root).as_posix()
        if source.stem.startswith(WIKI_DEVELOPER_PREFIX):
            inventory.append(
                {
                    "source": relative,
                    "current_route": handbook_route(source),
                    "target": source_url(Path("docs/developers/index.md"), repository_revision),
                    "decision": "repository-entry; do not copy into the Wiki",
                }
            )
        else:
            page = source.stem
            inventory.append(
                {
                    "source": relative,
                    "current_route": handbook_route(source),
                    "target": WIKI_BASE_URL if page == "Home" else f"{WIKI_BASE_URL}/{quote(page)}",
                    "decision": (
                        "Wiki candidate; remove repository source only after public acceptance"
                    ),
                }
            )
    for source in sorted((root / "docs" / "portal").glob("*.md")):
        relative = source.relative_to(root).as_posix()
        if source.stem == "produkt":
            target = f"{PUBLICATION_BASE_URL}/produkt/"
            decision = "Pages product source"
        elif source.stem == "nutzen":
            target = f"{WIKI_BASE_URL}/Nutzung"
            decision = "replace Pages entry with labelled Wiki hand-off after public acceptance"
        else:
            target = f"{WIKI_BASE_URL}/Administration"
            decision = "replace Pages entry with labelled Wiki hand-off after public acceptance"
        inventory.append(
            {
                "source": relative,
                "current_route": f"/{source.stem}/",
                "target": target,
                "decision": decision,
            }
        )
    for source in sorted((root / "docs" / "developers").rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(root)
        inventory.append(
            {
                "source": relative.as_posix(),
                "current_route": "repository and current Pages projection",
                "target": source_url(relative, repository_revision),
                "decision": "repository canonical; remove only the Pages projection",
            }
        )
    inventory.extend(
        (
            {
                "source": "backend OpenAPI assembly",
                "current_route": "/referenz/api/",
                "target": "/referenz/api/",
                "decision": "Pages generated reference",
            },
            {
                "source": "backend/src/backend Python docstrings",
                "current_route": "/referenz/backend/",
                "target": "/referenz/backend/",
                "decision": "Pages generated reference",
            },
            {
                "source": "frontend/src/app TSDoc",
                "current_route": "/referenz/frontend/",
                "target": "/referenz/frontend/",
                "decision": "Pages generated reference",
            },
            {
                "source": "backend/db/schema.sql",
                "current_route": "/referenz/datenbank/",
                "target": "/referenz/datenbank/",
                "decision": "Pages generated reference",
            },
        )
    )
    for source in (
        "README.md",
        "CONTRIBUTING.md",
        "docs/index.md",
        "frontend/src/app/auth/auth-flow.component.html",
        "frontend/src/app/about/about.component.html",
        "frontend/src/app/dashboard/dashboard.component.ts",
    ):
        inventory.append(
            {
                "source": source,
                "current_route": "controlled entry point",
                "target": "Wiki, Pages, or repository according to audience",
                "decision": "update only after public Wiki acceptance in #740",
            }
        )
    return inventory


def write_candidate_evidence(root: Path, output: Path, repository_revision: str) -> None:
    """Write generated review evidence without adding a maintained migration record."""

    output = ensure_safe_output(root, output)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    inventory = publication_inventory(root, repository_revision)
    evidence = {
        "schema_version": 1,
        "repository_revision": repository_revision,
        "stable_version": stable_version(root),
        "inventory_count": len(inventory),
        "inventory": inventory,
        "rollback_contract": {
            "pages": (
                "dispatch Public site from master with the full repository_revision of a "
                "previous successful artifact; the github-pages Environment remains mandatory"
            ),
            "wiki": (
                "record the previous Wiki commit before activation and restore its tree as a "
                "new reviewed commit; never force-push"
            ),
            "required_cutover_evidence": [
                "repository_revision",
                "wiki_revision",
                "Pages workflow run and artifact availability",
                "artifact digest",
            ],
        },
    }
    (output / "inventory.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_full_revision(value: str, label: str) -> None:
    """Require an explicit immutable lower-case Git SHA."""

    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError(f"{label} must be a full lower-case 40-character Git SHA")


def validate_rollback_candidate(
    root: Path,
    pages_root: Path,
    repository_revision: str,
    wiki_root: Path,
    wiki_revision: str,
) -> str:
    """Bind preserved Pages and Wiki data to concrete immutable revisions."""

    validate_full_revision(repository_revision, "repository revision")
    validate_full_revision(wiki_revision, "Wiki revision")
    run("git", "cat-file", "-e", f"{repository_revision}^{{commit}}", cwd=root)
    resolved_wiki = run("git", "rev-parse", f"{wiki_revision}^{{commit}}", cwd=wiki_root)
    if resolved_wiki != wiki_revision:
        raise ValueError(f"Wiki revision resolves to {resolved_wiki}, not {wiki_revision}")
    wiki_files = run("git", "ls-tree", "-r", "--name-only", wiki_revision, cwd=wiki_root)
    if not wiki_files:
        raise ValueError("Wiki rollback revision has no files")
    manifest_path = pages_root / "quellen.json"
    if not manifest_path.is_file():
        raise ValueError("Pages rollback artifact has no quellen.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("repository_revision") != repository_revision:
        raise ValueError(
            "Pages rollback artifact revision does not match the requested repository revision"
        )
    missing = [relative for relative in EXPECTED_OUTPUTS if not (pages_root / relative).is_file()]
    if missing:
        raise ValueError(f"Pages rollback artifact is incomplete: {', '.join(missing)}")
    return (
        "Rollback candidate is bound and complete: "
        f"repository={repository_revision}, wiki={wiki_revision}, "
        f"pages=sha256:{tree_digest(pages_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "check", "candidate", "candidate-check"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--typedoc", type=Path, required=True)
        subparser.add_argument(
            "--base-url",
            default=os.environ.get("PUBLICATION_BASE_URL", PUBLICATION_BASE_URL),
        )
        subparser.add_argument(
            "--demo-url",
            default=os.environ.get("DEMO_URL", "https://demo.example.invalid"),
        )
        if command == "build":
            subparser.add_argument("--output", type=Path, required=True)
        elif command == "candidate":
            subparser.add_argument("--pages-output", type=Path, required=True)
            subparser.add_argument("--wiki-output", type=Path, required=True)
            subparser.add_argument("--evidence-output", type=Path, required=True)
    wiki_build = subparsers.add_parser("wiki-build")
    wiki_build.add_argument("--output", type=Path, required=True)
    wiki_check = subparsers.add_parser("wiki-check")
    wiki_check.add_argument("--wiki-root", type=Path, required=True)
    wiki_routes = subparsers.add_parser("wiki-routes")
    wiki_routes.add_argument("--wiki-root", type=Path, required=True)
    wiki_routes.add_argument("--output", type=Path, required=True)
    wiki_routes.add_argument("--wiki-base-url", default=WIKI_BASE_URL)
    wiki_post_publish = subparsers.add_parser("wiki-post-publish")
    wiki_post_publish.add_argument("--wiki-root", type=Path, required=True)
    wiki_post_publish.add_argument("--wiki-base-url", default=WIKI_BASE_URL)
    rollback = subparsers.add_parser("rollback-check")
    rollback.add_argument("--pages-root", type=Path, required=True)
    rollback.add_argument("--repository-revision", required=True)
    rollback.add_argument("--wiki-root", type=Path, required=True)
    rollback.add_argument("--wiki-revision", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repository_root()
    repository_revision = run("git", "rev-parse", "HEAD", cwd=root)
    if args.command == "wiki-build":
        build_wiki_candidate(root, args.output, repository_revision)
        print(f"Wiki candidate built at {args.output.resolve()}")
        return 0
    if args.command == "wiki-check":
        errors = check_wiki_candidate(args.wiki_root.resolve(), stable_version(root))
        if errors:
            raise ValueError("Invalid Wiki candidate:\n" + "\n".join(errors))
        targets, _ = sidebar_targets(args.wiki_root.resolve() / "_Sidebar.md")
        print(f"Wiki candidate is valid: {len(targets)} content pages")
        return 0
    if args.command == "wiki-routes":
        errors = check_wiki_candidate(args.wiki_root.resolve())
        if errors:
            raise ValueError("Invalid Wiki candidate:\n" + "\n".join(errors))
        write_wiki_routes(args.wiki_root.resolve(), args.output.resolve(), args.wiki_base_url)
        print(f"Wiki route list written to {args.output.resolve()}")
        return 0
    if args.command == "wiki-post-publish":
        errors = check_wiki_candidate(args.wiki_root.resolve())
        errors.extend(check_published_wiki(args.wiki_root.resolve(), args.wiki_base_url))
        if errors:
            raise ValueError("Published Wiki check failed:\n" + "\n".join(errors))
        targets, _ = sidebar_targets(args.wiki_root.resolve() / "_Sidebar.md")
        print(f"Published Wiki is valid: {len(targets)} direct HTML routes")
        return 0
    if args.command == "rollback-check":
        print(
            validate_rollback_candidate(
                root,
                args.pages_root.resolve(),
                args.repository_revision,
                args.wiki_root.resolve(),
                args.wiki_revision,
            )
        )
        return 0

    os.environ.setdefault(
        "SOURCE_DATE_EPOCH", run("git", "show", "-s", "--format=%ct", "HEAD", cwd=root)
    )
    typedoc = args.typedoc.resolve()
    base_url = publication_base_url(args.base_url)
    demo_url = public_url(args.demo_url, allow_path=False)
    with tempfile.TemporaryDirectory(prefix="lzug-publication-") as temporary:
        temporary_root = Path(temporary)
        site = temporary_root / "relearn-site"
        pages_candidate = args.command in {"candidate", "candidate-check"}
        prepare_site(
            root,
            site,
            base_url,
            demo_url,
            pages_candidate=pages_candidate,
        )
        if args.command == "build":
            output = ensure_safe_output(root, args.output)
            render(root, site, output, typedoc)
            print(f"Publication artifact built at {output}")
            return 0
        if args.command == "candidate":
            pages_output = ensure_safe_output(root, args.pages_output)
            wiki_output = ensure_safe_output(root, args.wiki_output)
            evidence_output = ensure_safe_output(root, args.evidence_output)
            render(root, site, pages_output, typedoc, pages_candidate=True)
            build_wiki_candidate(root, wiki_output, repository_revision)
            write_candidate_evidence(root, evidence_output, repository_revision)
            print(
                "Publication candidates built: "
                f"pages={pages_output}, wiki={wiki_output}, evidence={evidence_output}"
            )
            return 0

        first = temporary_root / "first"
        second = temporary_root / "second"
        render(root, site, first, typedoc, pages_candidate=pages_candidate)
        render(root, site, second, typedoc, pages_candidate=pages_candidate)
        compared = [("Pages", first, second)]
        if args.command == "candidate-check":
            first_wiki = temporary_root / "first-wiki"
            second_wiki = temporary_root / "second-wiki"
            first_evidence = temporary_root / "first-evidence"
            second_evidence = temporary_root / "second-evidence"
            build_wiki_candidate(root, first_wiki, repository_revision)
            build_wiki_candidate(root, second_wiki, repository_revision)
            write_candidate_evidence(root, first_evidence, repository_revision)
            write_candidate_evidence(root, second_evidence, repository_revision)
            compared.extend(
                (
                    ("Wiki", first_wiki, second_wiki),
                    ("evidence", first_evidence, second_evidence),
                )
            )
        digests = []
        for label, first_tree, second_tree in compared:
            first_digest = tree_digest(first_tree)
            second_digest = tree_digest(second_tree)
            if first_digest != second_digest:
                differences = ", ".join(differing_files(first_tree, second_tree))
                raise ValueError(
                    f"{label} candidates differ: {first_digest} != {second_digest}; {differences}"
                )
            digests.append(f"{label}=sha256:{first_digest}")
        print("Publication artifact is reproducible: " + ", ".join(digests))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
