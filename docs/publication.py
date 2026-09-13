#!/usr/bin/env python3
"""Build and verify the public Blowfish documentation artifact.

The build checks out one reviewed Blowfish revision, builds a static artifact and
never calls a hosting API or mutates the GitHub Wiki.
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from backend.fastapi_assembly import FastAPIConfig, create_app

BLOWFISH_REPOSITORY = "https://github.com/nunocoracao/blowfish.git"
BLOWFISH_VERSION = "v3.6.0"
BLOWFISH_REVISION = "4643c46bd5e921fee51c420575fadebf9f4b3681"
PUBLICATION_BASE_URL = "https://lzug.repertoire.papaspyrou.name"
INHERITED_PUBLIC_HOSTS = frozenset({"lxndrp.github.io", "stage.papaspyrou.name"})
MARKDOWN_LINK = re.compile(r"(?P<prefix>\[[^\]]+\]\()(?P<target>[^)]+)(?P<suffix>\))")
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


def source_url(path: Path, repository_revision: str) -> str:
    """Return the immutable repository source URL for one rendered page."""

    return f"https://github.com/lxndrp/lzug/blob/{repository_revision}/{path.as_posix()}"


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


def prepare_blowfish_checkout(destination: Path) -> None:
    local_source = os.environ.get("LZUG_BLOWFISH_SOURCE")
    if local_source:
        source = Path(local_source).resolve()
        if run("git", "rev-parse", "HEAD", cwd=source) != BLOWFISH_REVISION:
            raise ValueError("LZUG_BLOWFISH_SOURCE does not match the pinned revision")
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns("public", "resources"))
        return

    run("git", "clone", "--filter=blob:none", "--no-checkout", BLOWFISH_REPOSITORY, str(destination))
    run("git", "checkout", "--detach", BLOWFISH_REVISION, cwd=destination)
    if run("git", "rev-parse", "HEAD", cwd=destination) != BLOWFISH_REVISION:
        raise ValueError("Blowfish checkout does not match the pinned revision")


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


def configure_blowfish(
    root: Path,
    site: Path,
    base_url: str,
    demo_url: str,
    repository_revision: str,
) -> None:
    (site / "hugo.toml").write_text(
        f"baseURL = {json.dumps(base_url + '/', ensure_ascii=False)}\n"
        "title = 'lzug'\n"
        "theme = 'blowfish'\n"
        "defaultContentLanguage = 'de'\n"
        "disableHugoGeneratorInject = true\n\n"
        "[languages.de]\n  title = 'lzug'\n  languageCode = 'de-DE'\n"
        "  languageName = 'Deutsch'\n  contentDir = 'content'\n  weight = 1\n\n"
        "[params]\n  defaultAppearance = 'light'\n"
        "  autoSwitchAppearance = true\n"
        "  enableSearch = true\n"
        "  enableCodeCopy = false\n"
        "  disableImageOptimization = true\n"
        "  disableTextInHeader = false\n"
        "  fingerprintAlgorithm = 'sha512'\n"
        f"  demoURL = {json.dumps(demo_url, ensure_ascii=False)}\n"
        "  publicationProfile = 'current'\n"
        "  wikiURL = 'https://github.com/lxndrp/lzug/wiki'\n"
        "  repositoryURL = 'https://github.com/lxndrp/lzug'\n"
        "  securityURL = 'https://github.com/lxndrp/lzug/security'\n"
        "  supportURL = 'https://github.com/lxndrp/lzug/blob/master/SUPPORT.md'\n"
        "  repositoryDocumentationURL = "
        f"{json.dumps(source_url(Path('docs/developers/index.md'), repository_revision))}\n"
        "\n[params.header]\n  layout = 'basic'\n\n[params.homepage]\n  layout = 'custom'\n  showRecent = false\n\n[params.footer]\n  showMenu = true\n  showCopyright = true\n  showThemeAttribution = true\n  showAppearanceSwitcher = true\n  showScrollToTop = true\n",
        encoding="utf-8",
    )
    (site / "layouts" / "_default").mkdir(parents=True)
    (site / "layouts" / "_shortcodes").mkdir(parents=True)
    (site / "layouts" / "partials").mkdir(parents=True)
    (site / "assets" / "css").mkdir(parents=True)
    (site / "static" / "images").mkdir(parents=True)
    (site / "static" / "images" / "brand").mkdir(parents=True)
    (site / "static" / "images" / "screenshots").mkdir(parents=True)
    (site / "static" / "fonts").mkdir(parents=True)
    (site / "static" / "css").mkdir(parents=True)
    (site / "static" / "js").mkdir(parents=True)
    shutil.copyfile(
        root / "docs" / "publication" / "blowfish" / "layouts" / "_default" / "baseof.html",
        site / "layouts" / "_default" / "baseof.html",
    )
    shutil.copyfile(
        root / "docs" / "publication" / "blowfish" / "layouts" / "index.html",
        site / "layouts" / "index.html",
    )
    shutil.copyfile(
        root / "docs" / "publication" / "blowfish" / "layouts" / "_shortcodes" / "publication-scope.html",
        site / "layouts" / "_shortcodes" / "publication-scope.html",
    )
    render_hook = site / "layouts" / "_default" / "_markup" / "render-link.html"
    render_hook.parent.mkdir(parents=True)
    shutil.copyfile(
        root / "docs" / "publication" / "blowfish" / "layouts" / "_default" / "_markup" / "render-link.html",
        render_hook,
    )
    shutil.copyfile(
        root / "docs" / "publication" / "blowfish" / "assets" / "css" / "custom.css",
        site / "assets" / "css" / "custom.css",
    )
    shutil.copyfile(
        root / "docs" / "publication" / "blowfish" / "static" / "js" / "demo-warmup.js",
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
    (site / "static" / "searchindex.de.js").write_text(
        "window.searchIndex = [];\n", encoding="utf-8"
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
) -> None:
    source_routes = {"docs/portal/produkt.md": "/produkt/"}
    content = site / "content"
    (content / "produkt").mkdir(parents=True)
    (content / "referenz" / "api").mkdir(parents=True)
    (content / "referenz" / "backend").mkdir(parents=True)
    (content / "referenz" / "frontend").mkdir(parents=True)
    (content / "referenz" / "datenbank").mkdir(parents=True)
    (content / "quellen").mkdir(parents=True)
    (site / "static" / "referenz" / "api").mkdir(parents=True, exist_ok=True)

    landing = (root / "docs" / "publication" / "content" / "index.md").read_text(encoding="utf-8")
    (content / "_index.md").write_text(
        hugo_page("lzug", "Prüfungen gemeinsam verlässlich planen", landing, "home"),
        encoding="utf-8",
    )
    portal_pages = {"produkt": ("lzug", "Produktinformation und öffentlicher Einstieg")}
    for slug, (title, description) in portal_pages.items():
        source = root / "docs" / "portal" / f"{slug if slug != 'betreiben' else 'betreiben'}.md"
        body = convert_repository_links(
            source.read_text(encoding="utf-8"), source.relative_to(root), source_routes
        )
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
        "profile": "current-publication",
        "theme": "Blowfish",
        "blowfish_version": BLOWFISH_VERSION,
        "blowfish_revision": BLOWFISH_REVISION,
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
            f"- Blowfish {BLOWFISH_VERSION}: `{BLOWFISH_REVISION}`\n\n"
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
) -> None:
    destination.mkdir(parents=True)
    repository_revision = run("git", "rev-parse", "HEAD", cwd=root)
    prepare_blowfish_checkout(destination / "themes" / "blowfish")
    configure_blowfish(
        root,
        destination,
        base_url,
        demo_url,
        repository_revision,
    )
    write_content(
        root,
        destination,
        repository_revision,
    )


def verify_output(output: Path, stage: Path) -> None:
    expected = EXPECTED_OUTPUTS
    missing = [relative for relative in expected if not (output / relative).is_file()]
    if missing:
        raise ValueError(f"Publication artifact is missing: {', '.join(missing)}")
    stage_text = str(stage).encode()
    for path in output.rglob("*"):
        if path.is_file() and stage_text in path.read_bytes():
            raise ValueError(f"Generated output leaks temporary path: {path}")


def render(
    root: Path,
    site: Path,
    output: Path,
    typedoc: Path,
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
    verify_output(output, site)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "check"):
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repository_root()
    os.environ.setdefault(
        "SOURCE_DATE_EPOCH", run("git", "show", "-s", "--format=%ct", "HEAD", cwd=root)
    )
    typedoc = args.typedoc.resolve()
    base_url = publication_base_url(args.base_url)
    demo_url = public_url(args.demo_url, allow_path=False)
    with tempfile.TemporaryDirectory(prefix="lzug-publication-") as temporary:
        temporary_root = Path(temporary)
        site = temporary_root / "blowfish-site"
        prepare_site(
            root,
            site,
            base_url,
            demo_url,
        )
        if args.command == "build":
            output = ensure_safe_output(root, args.output)
            render(root, site, output, typedoc)
            print(f"Publication artifact built at {output}")
            return 0

        first = temporary_root / "first"
        second = temporary_root / "second"
        render(root, site, first, typedoc)
        render(root, site, second, typedoc)
        run("git", "diff", "--no-index", "--exit-code", "--", str(first), str(second), cwd=root)
        print("Publication artifact is reproducible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
