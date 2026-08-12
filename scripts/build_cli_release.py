#!/usr/bin/env python3
"""Build the reproducible native operator CLI release archives."""

from __future__ import annotations

import argparse
import gzip
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.build_metadata import BuildMetadata  # noqa: E402

CLI_TARGETS = (
    ("linux", "amd64", "tar.gz"),
    ("linux", "arm64", "tar.gz"),
    ("darwin", "amd64", "tar.gz"),
    ("darwin", "arm64", "tar.gz"),
    ("windows", "amd64", "zip"),
    ("windows", "arm64", "zip"),
)


def artifact_stem(version: str, goos: str, goarch: str) -> str:
    """Return the versioned archive stem for one supported target."""

    return f"lzug-admin-{version}-{goos}-{goarch}"


def archive_name(version: str, goos: str, goarch: str, extension: str) -> str:
    """Return the exact published archive name for one supported target."""

    return f"{artifact_stem(version, goos, goarch)}.{extension}"


def sbom_name(version: str, goos: str, goarch: str, extension: str) -> str:
    """Return the exact published SBOM name paired with one archive."""

    del extension
    return f"{artifact_stem(version, goos, goarch)}.sbom.cdx.json"


def checksums_name(version: str) -> str:
    """Return the checksum file name for the native CLI asset set."""

    return f"lzug-admin-{version}.checksums.txt"


def binary_name(goos: str, goarch: str) -> str:
    """Return the unversioned binary name stored in an archive."""

    del goarch
    return "lzug-admin.exe" if goos == "windows" else "lzug-admin"


def build_command(
    output: Path,
    goos: str,
    goarch: str,
    metadata: BuildMetadata,
) -> list[str]:
    """Return the hermetic Go command used for one release binary."""

    ldflags = " ".join(
        (
            "-buildid=",
            "-s",
            "-w",
            f"-X main.applicationVersion={metadata.identity}",
            f"-X main.applicationRevision={metadata.revision}",
            f"-X main.applicationTag={metadata.tag or ''}",
        )
    )
    return [
        "go",
        "build",
        "-trimpath",
        "-buildvcs=false",
        f"-ldflags={ldflags}",
        "-o",
        str(output),
        "./cmd/lzug-admin",
    ]


def _tar_bytes(binary: bytes, metadata: bytes, name: str) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for member_name, content, mode in (
            (name, binary, 0o755),
            ("build-metadata.json", metadata, 0o644),
        ):
            info = tarfile.TarInfo(member_name)
            info.size = len(content)
            info.mode = mode
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(content))
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0) as output:
        output.write(stream.getvalue())
    return compressed.getvalue()


def _zip_bytes(binary: bytes, metadata: bytes, name: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for member_name, content, mode in (
            (name, binary, 0o755),
            ("build-metadata.json", metadata, 0o644),
        ):
            info = zipfile.ZipInfo(member_name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return output.getvalue()


def archive_binary(
    binary: Path,
    metadata: BuildMetadata,
    goos: str,
    goarch: str,
    extension: str,
    output: Path,
) -> None:
    """Create one deterministic archive containing a binary and metadata."""

    binary_bytes = binary.read_bytes()
    metadata_bytes = metadata.to_json().encode("utf-8")
    name = binary_name(goos, goarch)
    payload = (
        _tar_bytes(binary_bytes, metadata_bytes, name)
        if extension == "tar.gz"
        else _zip_bytes(binary_bytes, metadata_bytes, name)
    )
    output.write_bytes(payload)


def _run_build(
    output: Path,
    goos: str,
    goarch: str,
    metadata: BuildMetadata,
) -> None:
    environment = os.environ.copy()
    environment.update({"CGO_ENABLED": "0", "GOOS": goos, "GOARCH": goarch})
    subprocess.run(
        build_command(output, goos, goarch, metadata),
        cwd=ROOT,
        env=environment,
        check=True,
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"Go build did not produce a non-empty binary: {output}")


def build_release(
    version: str,
    revision: str,
    tag: str | None,
    output: Path,
    work_dir: Path | None = None,
) -> list[Path]:
    """Build all six targets and publish archives only after all builds pass."""

    metadata = BuildMetadata.create(revision, tag)
    if metadata.identity != version:
        raise ValueError("version must match the canonical build identity")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError(f"CLI output directory must be empty: {output}")

    temporary = None
    if work_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="lzug-cli-build-")
        build_root = Path(temporary.name)
    else:
        build_root = work_dir.resolve()
        build_root.mkdir(parents=True, exist_ok=True)
        if any(build_root.iterdir()):
            raise ValueError(f"CLI work directory must be empty: {build_root}")

    try:
        archive_root = build_root / "archives"
        binary_root = build_root / "binaries"
        archive_root.mkdir()
        binary_root.mkdir()
        archives: list[Path] = []
        for goos, goarch, extension in CLI_TARGETS:
            binary = binary_root / f"lzug-admin-{goos}-{goarch}"
            _run_build(binary, goos, goarch, metadata)
            archive = archive_root / archive_name(version, goos, goarch, extension)
            archive_binary(binary, metadata, goos, goarch, extension, archive)
            archives.append(archive)

        for archive in archives:
            shutil.copyfile(archive, output / archive.name)
        return [output / archive.name for archive in archives]
    finally:
        if temporary is not None:
            temporary.cleanup()


def parser() -> argparse.ArgumentParser:
    """Create the release builder CLI."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--tag")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--work-dir", type=Path)
    return parser


def main() -> None:
    """Build the six supported native CLI archives."""

    args = parser().parse_args()
    build_release(args.version, args.revision, args.tag, args.output, args.work_dir)


if __name__ == "__main__":
    main()
