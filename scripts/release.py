#!/usr/bin/env python3
"""Validate and render the deterministic inputs for an lzug release."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

SEMVER_TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CHANGELOG_HEADING = re.compile(
    r"^## \[((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))\]" r" - (\d{4}-\d{2}-\d{2})$"
)


@dataclass(frozen=True)
class Release:
    """A stable SemVer release derived from a Git tag."""

    major: int
    minor: int
    patch: int

    @property
    def version(self) -> str:
        """Return the version without the Git tag prefix."""

        return f"{self.major}.{self.minor}.{self.patch}"


def parse_release_tag(tag: str) -> Release:
    """Parse the only Git tag shape accepted by the public release workflow."""

    match = SEMVER_TAG.fullmatch(tag)
    if match is None:
        raise ValueError("release tag must be a stable SemVer tag in the form vMAJOR.MINOR.PATCH")
    return Release(*(int(part) for part in match.groups()))


def image_references(repository: str, tag: str, sha: str) -> list[str]:
    """Return every required GHCR tag for one release image."""

    if REPOSITORY.fullmatch(repository) is None:
        raise ValueError("repository must have the form owner/name")
    if COMMIT_SHA.fullmatch(sha) is None:
        raise ValueError("commit SHA must contain exactly 40 lowercase hex characters")
    release = parse_release_tag(tag)
    image = f"ghcr.io/{repository.lower()}"
    return [
        f"{image}:{release.version}",
        f"{image}:{release.major}.{release.minor}",
        f"{image}:{release.major}",
        f"{image}:sha-{sha}",
    ]


def validate_source_metadata(version_file: Path, expected: str) -> None:
    """Require one version across the canonical file and package metadata."""

    source_version = version_file.read_text(encoding="utf-8").strip()
    if source_version != expected:
        raise ValueError(
            f"release tag version {expected} does not match {version_file}: {source_version}"
        )
    root = version_file.resolve().parent
    python_version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    frontend_version = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))[
        "version"
    ]
    frontend_lock = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))
    lock_versions = {
        frontend_lock["version"],
        frontend_lock["packages"][""]["version"],
    }
    if (
        python_version != source_version
        or frontend_version != source_version
        or lock_versions != {source_version}
    ):
        raise ValueError(
            "VERSION, Python metadata, and frontend package metadata must contain one version"
        )


def extract_changelog(changelog: str, version: str) -> str:
    """Extract one non-empty, uniquely versioned changelog section."""

    lines = changelog.splitlines()
    matches: list[int] = []
    for index, line in enumerate(lines):
        heading = CHANGELOG_HEADING.fullmatch(line)
        if heading is not None and heading.group(1) == version:
            matches.append(index)
    if len(matches) != 1:
        raise ValueError(f"CHANGELOG.md must contain exactly one dated section for {version}")

    start = matches[0]
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    section = "\n".join(lines[start + 1 : end]).strip()
    if not section:
        raise ValueError(f"CHANGELOG.md section for {version} must not be empty")
    return section


def validate_attestation_url(value: str) -> str:
    """Accept only GitHub HTTPS URLs emitted by the attestation action."""

    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or not parsed.path:
        raise ValueError("attestation URL must be an https://github.com URL")
    return value


def write_release_inputs(args: argparse.Namespace) -> None:
    """Validate release inputs and write release notes and expected image tags."""

    release = parse_release_tag(args.tag)
    validate_source_metadata(Path(args.version_file), release.version)
    references = image_references(args.repository, args.tag, args.sha)
    changelog = Path(args.changelog).read_text(encoding="utf-8")
    changes = extract_changelog(changelog, release.version)

    Path(args.notes).write_text(f"# lzug {release.version}\n\n{changes}\n", encoding="utf-8")
    Path(args.tags).write_text("\n".join(references) + "\n", encoding="utf-8")

    if args.github_output:
        output = Path(args.github_output)
        with output.open("a", encoding="utf-8") as stream:
            stream.write(f"version={release.version}\n")
            stream.write(f"image=ghcr.io/{args.repository.lower()}\n")
            stream.write(f"canonical_ref={references[0]}\n")


def check_image_tags(args: argparse.Namespace) -> None:
    """Fail unless generated workflow tags exactly match the release contract."""

    actual = [
        line.strip()
        for line in Path(args.tags).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected = image_references(args.repository, args.tag, args.sha)
    if actual != expected:
        raise ValueError(f"image tags do not match release contract: {actual!r}")


def finalize_release_notes(args: argparse.Namespace) -> None:
    """Add immutable supply-chain evidence to the human release notes."""

    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.digest):
        raise ValueError("image digest must be a lowercase sha256 digest")
    provenance_url = validate_attestation_url(args.provenance_url)
    sbom_url = validate_attestation_url(args.sbom_url)
    tags = [
        line.strip()
        for line in Path(args.tags).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not tags:
        raise ValueError("release must contain at least one image tag")

    base = Path(args.base).read_text(encoding="utf-8").rstrip()
    tag_list = "\n".join(f"- `{reference}`" for reference in tags)
    evidence = f"""

## Lieferkette und Verifikation

Alle folgenden Tags verweisen zum Veröffentlichungszeitpunkt auf denselben
unveränderlichen Manifest-Digest:

{tag_list}

- Image: `{args.image}@{args.digest}`
- CycloneDX-SBOM: `{args.sbom_asset}` (Release-Artefakt und signierte Attestation)
- Build-Provenance: [signierter Herkunftsnachweis]({provenance_url})
- SBOM-Attestation: [signierter SBOM-Nachweis]({sbom_url})
- Build-Lauf: [GitHub Actions]({args.run_url})

Der Herkunftsnachweis lässt sich mit GitHub CLI prüfen:

```sh
gh attestation verify "oci://{args.image}@{args.digest}" --repo {args.repository}
```

Die Referenzinstallation soll den Digest oben oder einen konkreten
`MAJOR.MINOR.PATCH`-Tag verwenden, niemals `latest`.
"""
    Path(args.output).write_text(base + evidence, encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--tag", required=True)
    prepare.add_argument("--sha", required=True)
    prepare.add_argument("--repository", required=True)
    prepare.add_argument("--changelog", required=True)
    prepare.add_argument("--version-file", default="VERSION")
    prepare.add_argument("--notes", required=True)
    prepare.add_argument("--tags", required=True)
    prepare.add_argument("--github-output")
    prepare.set_defaults(handler=write_release_inputs)

    check_tags = commands.add_parser("check-tags")
    check_tags.add_argument("--tag", required=True)
    check_tags.add_argument("--sha", required=True)
    check_tags.add_argument("--repository", required=True)
    check_tags.add_argument("--tags", required=True)
    check_tags.set_defaults(handler=check_image_tags)

    finalize = commands.add_parser("finalize")
    finalize.add_argument("--base", required=True)
    finalize.add_argument("--output", required=True)
    finalize.add_argument("--tags", required=True)
    finalize.add_argument("--image", required=True)
    finalize.add_argument("--digest", required=True)
    finalize.add_argument("--sbom-asset", required=True)
    finalize.add_argument("--provenance-url", required=True)
    finalize.add_argument("--sbom-url", required=True)
    finalize.add_argument("--run-url", required=True)
    finalize.add_argument("--repository", required=True)
    finalize.set_defaults(handler=finalize_release_notes)
    return root


def main() -> None:
    """Run the selected release command."""

    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
