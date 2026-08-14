#!/usr/bin/env python3
"""Build and verify the local Relearn publication architecture spike.

The spike checks out one reviewed Relearn revision, builds a static artifact and
never calls a hosting API or mutates the GitHub Wiki.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from backend.openapi import spec as openapi_spec

RELEARN_REPOSITORY = "https://github.com/McShelby/hugo-theme-relearn.git"
RELEARN_REVISION = "8bb66fa674351f3a0b0917a7552caac686eca920"
MARKDOWN_LINK = re.compile(r"(?P<prefix>\[[^\]]+\]\()(?P<target>[^)]+)(?P<suffix>\))")
EXPECTED_OUTPUTS = (
    "index.html",
    "handbuch/index.html",
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


def source_revision(source: Path) -> str:
    if (source / ".git").exists():
        if run("git", "status", "--porcelain", cwd=source):
            raise ValueError(f"Wiki source must be clean: {source}")
        return run("git", "rev-parse", "HEAD", cwd=source)

    digest = hashlib.sha256()
    for path in sorted(source.glob("*.md")):
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"fixture-sha256:{digest.hexdigest()}"


def wiki_slug(target: str) -> str:
    return "index" if target == "Home" else target.lower()


def convert_wiki_links(markdown: str, known_pages: set[str]) -> str:
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
            raise ValueError(f"Unknown extensionless Wiki target: {target}")
        converted = "/handbuch/" if target == "Home" else f"/handbuch/{wiki_slug(target)}/"
        if separator:
            converted += f"#{fragment}"
        return f"{match.group('prefix')}{converted}{match.group('suffix')}"

    return MARKDOWN_LINK.sub(replace, markdown)


def hugo_page(title: str, description: str, body: str, page_type: str | None = None) -> str:
    frontmatter = {
        "title": title,
        "description": description,
        "draft": False,
    }
    if page_type:
        frontmatter["type"] = page_type
    return f"---\n{json.dumps(frontmatter, ensure_ascii=False)}\n---\n\n{body.rstrip()}\n"


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


def configure_relearn(root: Path, site: Path) -> None:
    (site / "hugo.toml").write_text(
        "baseURL = 'https://lxndrp.github.io/lzug/'\n"
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
        "  [[params.themeVariant]]\n    identifier = 'relearn-light'\n    name = 'Hell'\n"
        "  [[params.themeVariant]]\n    identifier = 'relearn-dark'\n    name = 'Dunkel'\n",
        encoding="utf-8",
    )
    (site / "layouts" / "home").mkdir(parents=True)
    (site / "layouts" / "partials").mkdir(parents=True)
    (site / "assets" / "css").mkdir(parents=True)
    shutil.copyfile(
        root / "prototypes" / "publication" / "relearn" / "layouts" / "home" / "article.html",
        site / "layouts" / "home" / "article.html",
    )
    shutil.copyfile(
        root / "prototypes" / "publication" / "relearn" / "assets" / "css" / "custom.css",
        site / "assets" / "css" / "custom.css",
    )
    repository_revision = run("git", "rev-parse", "HEAD", cwd=root)
    (site / "layouts" / "partials" / "assetbusting.gotmpl").write_text(
        f'{{{{- return "?{repository_revision[:12]}" }}}}\n', encoding="utf-8"
    )


def write_content(root: Path, wiki_root: Path, site: Path, repository_revision: str) -> None:
    wiki_files = sorted(path for path in wiki_root.glob("*.md") if path.name != "_Sidebar.md")
    if (
        not wiki_files
        or not (wiki_root / "Home.md").is_file()
        or not (wiki_root / "_Sidebar.md").is_file()
    ):
        raise ValueError("Wiki source must contain Home.md, _Sidebar.md, and content")

    wiki_revision = source_revision(wiki_root)
    known_pages = {path.stem for path in wiki_files}
    content = site / "content"
    (content / "handbuch").mkdir(parents=True)
    (content / "referenz" / "api").mkdir(parents=True)
    (content / "referenz" / "backend").mkdir(parents=True)
    (content / "referenz" / "frontend").mkdir(parents=True)
    (content / "referenz" / "datenbank").mkdir(parents=True)
    (content / "quellen").mkdir(parents=True)
    (site / "static" / "referenz" / "api").mkdir(parents=True, exist_ok=True)

    landing = (root / "prototypes" / "publication" / "content" / "index.md").read_text(
        encoding="utf-8"
    )
    (content / "_index.md").write_text(
        hugo_page("lzug", "Prüfungen gemeinsam verlässlich planen", landing, "home"),
        encoding="utf-8",
    )
    for wiki_file in wiki_files:
        body = convert_wiki_links(wiki_file.read_text(encoding="utf-8"), known_pages)
        canonical = f"https://github.com/lxndrp/lzug/wiki/{wiki_file.stem}"
        provenance = (
            f"> Generierte Projektion der [kanonischen Wiki-Seite]({canonical}) "
            f"aus Wiki-Commit `{wiki_revision}`.\n\n"
        )
        title = "Handbuch" if wiki_file.stem == "Home" else wiki_file.stem
        name = "_index.md" if wiki_file.stem == "Home" else f"{wiki_slug(wiki_file.stem)}.md"
        (content / "handbuch" / name).write_text(
            hugo_page(title, f"Öffentliche Wiki-Projektion: {title}", provenance + body),
            encoding="utf-8",
        )

    backend = (root / "docs" / "developers" / "reference" / "backend.md").read_text(
        encoding="utf-8"
    )
    (content / "referenz" / "backend" / "_index.md").write_text(
        hugo_page(
            "Python-Backend",
            "Aus Python-Docstrings erzeugte Backend-Referenz",
            f"> Generiert aus Hauptrepository-Commit `{repository_revision}`.\n\n{backend}",
        ),
        encoding="utf-8",
    )

    api_document = openapi_spec()
    (site / "static" / "referenz" / "api" / "openapi.json").write_text(
        json.dumps(api_document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (content / "referenz" / "api" / "_index.md").write_text(
        hugo_page(
            "API-Referenz",
            "Aus dem OpenAPI-Vertrag erzeugte API-Referenz",
            f"> Generiert aus Hauptrepository-Commit `{repository_revision}`.\n\n"
            "Der Spike exportiert den Vertrag als [OpenAPI-JSON](/referenz/api/openapi.json). "
            "Die produktive Pipeline bündelt daraus eine gelockte Redoc-Ausgabe.",
        ),
        encoding="utf-8",
    )

    schema = (root / "db" / "schema.sql").read_text(encoding="utf-8")
    (content / "referenz" / "datenbank" / "_index.md").write_text(
        hugo_page(
            "Datenbankschema",
            "Deterministische Ansicht des kanonischen Datenbankschemas",
            f"> Generiert aus Hauptrepository-Commit `{repository_revision}`.\n\n"
            f"```sql\n{schema.rstrip()}\n```",
        ),
        encoding="utf-8",
    )
    (content / "referenz" / "frontend" / "_index.md").write_text(
        hugo_page(
            "TypeScript-Frontend",
            "Aus TSDoc erzeugte Frontend-Referenz",
            "TypeDoc ersetzt diese Seite im Zielartefakt.",
        ),
        encoding="utf-8",
    )
    (content / "referenz" / "_index.md").write_text(
        hugo_page(
            "Technische Referenz",
            "Revisionsgebundene technische Referenzen",
            "Die Generatoren schreiben unabhängig und werden erst im Zielartefakt zusammengeführt.",
        ),
        encoding="utf-8",
    )

    manifest = {
        "relearn_revision": RELEARN_REVISION,
        "repository": "https://github.com/lxndrp/lzug",
        "repository_revision": repository_revision,
        "wiki": "https://github.com/lxndrp/lzug.wiki.git",
        "wiki_revision": wiki_revision,
    }
    (site / "static" / "quellen.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (content / "quellen" / "_index.md").write_text(
        hugo_page(
            "Quellen und Versionen",
            "Revisionsidentität der erzeugten Ausgabe",
            f"- Hauptrepository: `{repository_revision}`\n"
            f"- GitHub Wiki: `{wiki_revision}`\n"
            f"- Relearn: `{RELEARN_REVISION}`\n\n"
            "[Maschinenlesbare Fassung](/quellen.json)",
        ),
        encoding="utf-8",
    )


def prepare_site(root: Path, wiki_root: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    prepare_relearn_checkout(destination / "themes" / "relearn")
    configure_relearn(root, destination)
    write_content(root, wiki_root, destination, run("git", "rev-parse", "HEAD", cwd=root))


def verify_output(output: Path, stage: Path) -> None:
    missing = [relative for relative in EXPECTED_OUTPUTS if not (output / relative).is_file()]
    if missing:
        raise ValueError(f"Publication spike is missing: {', '.join(missing)}")
    stage_text = str(stage).encode()
    for path in output.rglob("*"):
        if path.is_file() and stage_text in path.read_bytes():
            raise ValueError(f"Generated output leaks temporary path: {path}")


def render(root: Path, site: Path, output: Path, typedoc: Path) -> None:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "check"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--wiki-root", type=Path, required=True)
        subparser.add_argument("--typedoc", type=Path, required=True)
        if command == "build":
            subparser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repository_root()
    os.environ.setdefault(
        "SOURCE_DATE_EPOCH", run("git", "show", "-s", "--format=%ct", "HEAD", cwd=root)
    )
    wiki_root = args.wiki_root.resolve()
    typedoc = args.typedoc.resolve()
    with tempfile.TemporaryDirectory(prefix="lzug-publication-spike-") as temporary:
        site = Path(temporary) / "relearn-site"
        prepare_site(root, wiki_root, site)
        if args.command == "build":
            output = ensure_safe_output(root, args.output)
            render(root, site, output, typedoc)
            print(f"Publication spike built at {output}")
            return 0

        first = Path(temporary) / "first"
        second = Path(temporary) / "second"
        render(root, site, first, typedoc)
        render(root, site, second, typedoc)
        first_digest = tree_digest(first)
        second_digest = tree_digest(second)
        if first_digest != second_digest:
            differences = ", ".join(differing_files(first, second))
            raise ValueError(
                f"Publication builds differ: {first_digest} != {second_digest}; {differences}"
            )
        print(f"Publication spike is reproducible: sha256:{first_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
