#!/usr/bin/env python3
"""Verify the observable GoReleaser operator CLI artifact contract."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Any

TARGETS = (
    ("linux", "amd64", "tar.gz"),
    ("linux", "arm64", "tar.gz"),
    ("darwin", "amd64", "tar.gz"),
    ("darwin", "arm64", "tar.gz"),
    ("windows", "amd64", "zip"),
    ("windows", "arm64", "zip"),
)


def archive_name(version: str, goos: str, goarch: str, extension: str) -> str:
    return f"lzug-admin-{version}-{goos}-{goarch}.{extension}"


def expected_metadata(version: str, revision: str, tag: str | None) -> dict[str, Any]:
    return {
        "identity": version,
        "release": tag is not None,
        "revision": revision,
        "tag": tag,
    }


def read_archive(path: Path, binary: str) -> dict[str, Any]:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != 2 or set(names) != {binary, "build-metadata.json"}:
                raise ValueError(f"unexpected archive contents: {path}")
            return json.loads(archive.read("build-metadata.json"))

    with tarfile.open(path, mode="r:gz") as archive:
        names = archive.getnames()
        if len(names) != 2 or set(names) != {binary, "build-metadata.json"}:
            raise ValueError(f"unexpected archive contents: {path}")
        metadata = archive.extractfile("build-metadata.json")
        if metadata is None:
            raise ValueError(f"missing build metadata: {path}")
        return json.load(metadata)


def artifacts(dist: Path, artifact_type: str) -> dict[tuple[str, str], Path]:
    manifest = json.loads((dist / "artifacts.json").read_text(encoding="utf-8"))
    selected = {}
    for item in manifest:
        if item.get("type") != artifact_type:
            continue
        path = Path(item["path"])
        if not path.is_absolute():
            path = dist / path.relative_to("dist")
        target = (item["goos"], item["goarch"])
        if target in selected:
            raise ValueError(f"duplicate {artifact_type.lower()} target: {target}")
        selected[target] = path
    expected = {(goos, goarch) for goos, goarch, _extension in TARGETS}
    if set(selected) != expected:
        raise ValueError(f"unexpected {artifact_type.lower()} target matrix")
    return selected


def verify_dist(dist: Path, version: str, revision: str, tag: str | None) -> None:
    expected_names = {
        archive_name(version, goos, goarch, extension) for goos, goarch, extension in TARGETS
    }
    actual_names = {path.name for path in dist.iterdir() if path.name.endswith((".tar.gz", ".zip"))}
    if actual_names != expected_names:
        raise ValueError("GoReleaser did not create the exact six-archive contract")
    if list(dist.glob("*checksum*")):
        raise ValueError("GoReleaser created a forbidden checksum file")

    metadata = expected_metadata(version, revision, tag)
    for goos, goarch, extension in TARGETS:
        name = archive_name(version, goos, goarch, extension)
        binary = "lzug-admin.exe" if goos == "windows" else "lzug-admin"
        if read_archive(dist / name, binary) != metadata:
            raise ValueError(f"incorrect build metadata: {name}")

    binary_artifacts = artifacts(dist, "Binary")
    artifacts(dist, "Archive")
    host_os = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system())
    host_arch = {"x86_64": "amd64", "AMD64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(
        platform.machine()
    )
    if host_os and host_arch:
        output = subprocess.run(
            [binary_artifacts[(host_os, host_arch)], "--build-metadata"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if json.loads(output) != metadata:
            raise ValueError("host binary does not expose the expected build metadata")


def verify_reproducible(first: Path, second: Path) -> None:
    for goos, goarch, extension in TARGETS:
        matches = list(first.glob(f"lzug-admin-*-{goos}-{goarch}.{extension}"))
        if len(matches) != 1:
            raise ValueError(f"missing first archive for {goos}/{goarch}")
        if matches[0].read_bytes() != (second / matches[0].name).read_bytes():
            raise ValueError(f"archive is not byte-stable: {matches[0].name}")

    first_binaries = artifacts(first, "Binary")
    second_binaries = artifacts(second, "Binary")
    for target, binary in first_binaries.items():
        if binary.read_bytes() != second_binaries[target].read_bytes():
            raise ValueError(f"binary is not byte-stable: {target[0]}/{target[1]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", required=True, type=Path)
    parser.add_argument("--second", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--tag")
    args = parser.parse_args()

    verify_dist(args.first, args.version, args.revision, args.tag)
    verify_dist(args.second, args.version, args.revision, args.tag)
    verify_reproducible(args.first, args.second)


if __name__ == "__main__":
    main()
