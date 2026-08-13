#!/usr/bin/env python3
"""Validate an already published GitHub Release before idempotent completion."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[0-9]+)?$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
CLI_TARGETS = (
    ("linux", "amd64", "tar.gz"),
    ("linux", "arm64", "tar.gz"),
    ("darwin", "amd64", "tar.gz"),
    ("darwin", "arm64", "tar.gz"),
    ("windows", "amd64", "zip"),
    ("windows", "arm64", "zip"),
)


def installable_archive_names(version: str) -> set[str]:
    """Return the six installable native CLI archive names."""

    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"invalid release version: {version}")
    return {
        f"lzug-admin-{version}-{goos}-{goarch}.{extension}"
        for goos, goarch, extension in CLI_TARGETS
    }


def expected_release_asset_names(version: str) -> set[str]:
    """Return the exact visible asset contract for one release generation."""

    archives = installable_archive_names(version)
    if version != "0.1.0":
        return archives | {f"lzug-{version}.sbom.cdx.json"}

    legacy_assets = {
        "lzug-0.1.0.checksums.txt",
        "lzug-0.1.0.cli.provenance.json",
        "lzug-0.1.0.dependencies.sbom.cdx.json",
        "lzug-0.1.0.image.sbom.cdx.json",
        "lzug-0.1.0.provenance.json",
        "lzug-0.1.0.release-manifest.json",
        "lzug-0.1.0.sbom-attestation.json",
        "lzug-admin-0.1.0.checksums.txt",
    }
    for goos, goarch, _extension in CLI_TARGETS:
        legacy_assets.add(f"lzug-admin-0.1.0-{goos}-{goarch}.sbom.cdx.json")
    return archives | legacy_assets


def validate_published_release(release: dict[str, Any], tag: str, version: str) -> None:
    """Reject a published release unless its identity and core assets are complete."""

    expected_assets = expected_release_asset_names(version)
    if tag != f"v{version}":
        raise ValueError(f"canonical tag {tag} does not match release version {version}")
    expected_prerelease = "-rc." in version
    if release.get("tag_name") != tag:
        raise ValueError(f"published release does not belong to canonical tag {tag}")
    if release.get("draft") is not False or not release.get("published_at"):
        raise ValueError(f"release for {tag} is not published")
    if release.get("prerelease") is not expected_prerelease:
        raise ValueError(f"published release prerelease state does not match {tag}")

    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError(f"published release for {tag} has no asset list")

    by_name: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
            raise ValueError(f"published release for {tag} contains malformed asset metadata")
        name = asset["name"]
        if name in by_name:
            raise ValueError(f"published release for {tag} contains duplicate asset {name}")
        by_name[name] = asset

    actual_assets = set(by_name)
    missing = sorted(expected_assets - actual_assets)
    if missing:
        raise ValueError(f"published release for {tag} is missing assets: {', '.join(missing)}")
    unexpected = sorted(actual_assets - expected_assets)
    if unexpected:
        raise ValueError(
            f"published release for {tag} contains unexpected assets: {', '.join(unexpected)}"
        )

    for name in sorted(expected_assets):
        asset = by_name[name]
        if asset.get("state") != "uploaded":
            raise ValueError(f"published release asset is not uploaded: {name}")
        size = asset.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError(f"published release asset is empty: {name}")
        digest = asset.get("digest")
        if not isinstance(digest, str) or not DIGEST_PATTERN.fullmatch(digest):
            raise ValueError(f"published release asset has no SHA-256 digest: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    release = json.load(sys.stdin)
    try:
        validate_published_release(release, args.tag, args.version)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Published release {args.tag} is complete; publication steps will be skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
