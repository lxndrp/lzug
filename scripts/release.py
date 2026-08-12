#!/usr/bin/env python3
"""Validate and render the deterministic inputs for an lzug release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.build_metadata import COMMIT_SHA, SEMVER_TAG, BuildMetadata  # noqa: E402
from scripts.build_cli_release import (  # noqa: E402
    CLI_TARGETS,
    archive_name,
    checksums_name,
    sbom_name,
)
from scripts.build_metadata import verify_tag_target  # noqa: E402

REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CHANGELOG_HEADING = re.compile(
    r"^## \[((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)(?:-rc\.(?:0|[1-9][0-9]*))?)\] - (\d{4}-\d{2}-\d{2})$"
)


@dataclass(frozen=True)
class Release:
    """A SemVer release derived from a Git tag."""

    major: int
    minor: int
    patch: int
    release_candidate: int | None = None

    @property
    def version(self) -> str:
        """Return the version without the Git tag prefix."""

        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.release_candidate is not None:
            return f"{version}-rc.{self.release_candidate}"
        return version


def parse_release_tag(tag: str) -> Release:
    """Parse the SemVer tag shapes accepted by the release contract."""

    match = SEMVER_TAG.fullmatch(tag)
    if match is None:
        raise ValueError(
            "release tag must be SemVer in the form "
            "vMAJOR.MINOR.PATCH or vMAJOR.MINOR.PATCH-rc.N"
        )
    major, minor, patch, release_candidate = match.groups()
    return Release(
        int(major),
        int(minor),
        int(patch),
        int(release_candidate) if release_candidate is not None else None,
    )


def image_references(repository: str, tag: str, sha: str) -> list[str]:
    """Return every required GHCR tag for one release image."""

    if REPOSITORY.fullmatch(repository) is None:
        raise ValueError("repository must have the form owner/name")
    if COMMIT_SHA.fullmatch(sha) is None:
        raise ValueError("commit SHA must contain exactly 40 lowercase hex characters")
    release = parse_release_tag(tag)
    image = f"ghcr.io/{repository.lower()}"
    references = [f"{image}:{release.version}"]
    if release.release_candidate is None:
        references.extend([f"{image}:{release.major}.{release.minor}", f"{image}:{release.major}"])
    references.append(f"{image}:sha-{sha}")
    return references


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


def validate_github_url(value: str) -> str:
    """Accept only a concrete GitHub HTTPS URL."""

    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or not parsed.path:
        raise ValueError("GitHub URL must be an https://github.com URL")
    return value


def asset_hashes(root: Path) -> dict[str, str]:
    """Return stable SHA-256 hashes for every qualified extension asset."""

    if not root.is_dir():
        raise ValueError("release assets path must be a directory")
    hashes: dict[str, str] = {}
    for path in sorted(entry for entry in root.rglob("*") if entry.is_file()):
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        hashes[relative] = digest.hexdigest()
    return hashes


def cli_asset_paths(version: str) -> tuple[list[str], list[str], str]:
    """Return the exact archive, SBOM, and checksum paths for one release."""

    archives = [
        f"cli/{archive_name(version, goos, goarch, extension)}"
        for goos, goarch, extension in CLI_TARGETS
    ]
    sboms = [
        f"cli/{sbom_name(version, goos, goarch, extension)}"
        for goos, goarch, extension in CLI_TARGETS
    ]
    return archives, sboms, f"cli/{checksums_name(version)}"


def cli_checksum_content(root: Path, version: str) -> str:
    """Render the deterministic checksum file for all CLI archives and SBOMs."""

    archives, sboms, _ = cli_asset_paths(version)
    paths = [root / path for path in sorted(archives + sboms)]
    if any(not path.is_file() for path in paths):
        raise ValueError("all CLI archives and SBOMs are required before checksums")
    lines = []
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    return "\n".join(lines) + "\n"


def write_cli_checksums(args: argparse.Namespace) -> None:
    """Write the checksums that bind the six CLI archives and SBOMs."""

    _, _, checksum = cli_asset_paths(args.version)
    output = Path(args.output)
    expected = Path(args.assets)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.resolve() != (expected / checksum).resolve():
        raise ValueError("CLI checksum output must be inside release-assets")
    output.write_text(cli_checksum_content(expected, args.version), encoding="utf-8")


def validate_cli_assets(root: Path, version: str, hashes: dict[str, str]) -> dict[str, object]:
    """Validate the complete six-platform CLI asset boundary."""

    archives, sboms, checksum = cli_asset_paths(version)
    expected = set(archives + sboms + [checksum])
    if set(hashes) != expected:
        missing = sorted(expected - set(hashes))
        unexpected = sorted(set(hashes) - expected)
        raise ValueError(
            "CLI asset set must contain exactly six archives, six SBOMs, and one checksum file; "
            f"missing={missing!r}, unexpected={unexpected!r}"
        )

    checksum_path = root / checksum
    if checksum_path.read_text(encoding="utf-8") != cli_checksum_content(root, version):
        raise ValueError("CLI checksum file does not match the qualified archives and SBOMs")

    details = []
    for (goos, goarch, extension), archive_path, sbom_path in zip(
        CLI_TARGETS, archives, sboms, strict=True
    ):
        payload = json.loads((root / sbom_path).read_text(encoding="utf-8"))
        source = payload.get("metadata", {}).get("component", {})
        expected_source = Path(archive_path).stem.removesuffix(".tar")
        if source.get("type") != "file" or source.get("name") != expected_source:
            raise ValueError(f"CLI SBOM source does not match {archive_path}")
        if source.get("version") != version:
            raise ValueError(f"CLI SBOM version does not match {version}: {sbom_path}")
        details.append(
            {
                "archive": archive_path,
                "platform": goos,
                "architecture": goarch,
                "format": extension,
                "sha256": hashes[archive_path],
                "sbom": sbom_path,
                "sbom_sha256": hashes[sbom_path],
            }
        )
    return {"artifact_count": len(details), "artifacts": details}


def release_manifest(args: argparse.Namespace) -> dict[str, object]:
    """Build the immutable qualification manifest, including future CLI assets."""

    release = parse_release_tag(args.tag)
    if COMMIT_SHA.fullmatch(args.sha) is None:
        raise ValueError("commit SHA must contain exactly 40 lowercase hex characters")
    actual_tags = [
        line.strip()
        for line in Path(args.tags).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected_tags = image_references(args.repository, args.tag, args.sha)
    if actual_tags != expected_tags:
        raise ValueError("release manifest tags do not match the release identity")
    hashes = asset_hashes(Path(args.assets))
    cli = validate_cli_assets(Path(args.assets), release.version, hashes)
    return {
        "schema": "https://github.com/lxndrp/lzug/releases/manifest/v1",
        "tag": args.tag,
        "version": release.version,
        "revision": args.sha,
        "image": f"ghcr.io/{args.repository.lower()}",
        "image_tags": actual_tags,
        "assets": hashes,
        "cli": cli,
    }


def write_release_manifest(args: argparse.Namespace) -> None:
    """Write the exact qualification manifest consumed by the publish job."""

    payload = release_manifest(args)
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def check_release_manifest(args: argparse.Namespace) -> None:
    """Fail unless identity and qualified extension assets remain byte-identical."""

    expected = release_manifest(args)
    actual = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if actual != expected:
        raise ValueError("release manifest differs from the qualified inputs")


def write_release_inputs(args: argparse.Namespace) -> None:
    """Validate release inputs and write release notes and expected image tags."""

    release = parse_release_tag(args.tag)
    metadata = BuildMetadata.create(args.sha, args.tag)
    verify_tag_target(args.tag, args.sha)
    if metadata.identity != release.version:
        raise ValueError("release tag and build metadata identity differ")
    references = image_references(args.repository, args.tag, args.sha)
    changelog = Path(args.changelog).read_text(encoding="utf-8")
    changes = extract_changelog(changelog, release.version)

    Path(args.notes).write_text(f"# lzug {release.version}\n\n{changes}\n", encoding="utf-8")
    Path(args.tags).write_text("\n".join(references) + "\n", encoding="utf-8")

    if args.github_output:
        output = Path(args.github_output)
        with output.open("a", encoding="utf-8") as stream:
            stream.write(f"version={release.version}\n")
            stream.write(f"build_identity={metadata.identity}\n")
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
    issue_url = validate_github_url(args.issue_url)
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
- Image-SBOM: `{args.image_sbom_asset}` (CycloneDX; an Digest attestiert)
- Dependency-SBOM: `{args.dependency_sbom_asset}`
  (CycloneDX-Artefakt für Lizenz- und Lieferkettenreview)
- Build-Provenance: [signierter Herkunftsnachweis]({provenance_url})
- SBOM-Attestation: [signierter SBOM-Nachweis]({sbom_url})
- Betreiber-CLI: sechs versionierte Archive für Linux, macOS und Windows auf
  `amd64` und `arm64`, gebunden durch `{args.cli_manifest_asset}`
- Betreiber-CLI-SBOMs und Checksums: `{args.cli_checksums_asset}`
- CLI-Provenance: [signierter Herkunftsnachweis]({args.cli_provenance_url})
- Build-Lauf: [GitHub Actions]({args.run_url})
- Freigabe-Gate: [Release-Issue]({issue_url})

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

    manifest = commands.add_parser("manifest")
    manifest.add_argument("--tag", required=True)
    manifest.add_argument("--sha", required=True)
    manifest.add_argument("--repository", required=True)
    manifest.add_argument("--tags", required=True)
    manifest.add_argument("--assets", required=True)
    manifest.add_argument("--output", required=True)
    manifest.set_defaults(handler=write_release_manifest)

    cli_checksums = commands.add_parser("cli-checksums")
    cli_checksums.add_argument("--version", required=True)
    cli_checksums.add_argument("--assets", required=True)
    cli_checksums.add_argument("--output", required=True)
    cli_checksums.set_defaults(handler=write_cli_checksums)

    check_manifest = commands.add_parser("check-manifest")
    check_manifest.add_argument("--tag", required=True)
    check_manifest.add_argument("--sha", required=True)
    check_manifest.add_argument("--repository", required=True)
    check_manifest.add_argument("--tags", required=True)
    check_manifest.add_argument("--assets", required=True)
    check_manifest.add_argument("--manifest", required=True)
    check_manifest.set_defaults(handler=check_release_manifest)

    finalize = commands.add_parser("finalize")
    finalize.add_argument("--base", required=True)
    finalize.add_argument("--output", required=True)
    finalize.add_argument("--tags", required=True)
    finalize.add_argument("--image", required=True)
    finalize.add_argument("--digest", required=True)
    finalize.add_argument("--image-sbom-asset", required=True)
    finalize.add_argument("--dependency-sbom-asset", required=True)
    finalize.add_argument("--provenance-url", required=True)
    finalize.add_argument("--sbom-url", required=True)
    finalize.add_argument("--cli-provenance-url", required=True)
    finalize.add_argument("--cli-manifest-asset", required=True)
    finalize.add_argument("--cli-checksums-asset", required=True)
    finalize.add_argument("--run-url", required=True)
    finalize.add_argument("--issue-url", required=True)
    finalize.add_argument("--repository", required=True)
    finalize.set_defaults(handler=finalize_release_notes)
    return root


def main() -> None:
    """Run the selected release command."""

    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
