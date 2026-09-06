#!/usr/bin/env python3
"""Generate and verify the canonical lzug build metadata interface."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))

from backend.build_metadata import BuildMetadata  # noqa: E402


def git_output(*args: str) -> str:
    """Return one normalized value from the current Git repository."""

    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def resolve_revision(explicit: str | None) -> str:
    """Use an explicit immutable revision or the current Git commit."""

    return explicit or git_output("rev-parse", "HEAD")


def verify_tag_target(tag: str, revision: str) -> None:
    """Require an annotated release tag that resolves to the built commit."""

    if git_output("cat-file", "-t", tag) != "tag":
        raise ValueError(f"release tag {tag} must be an annotated Git tag")
    target = git_output("rev-list", "-n", "1", tag)
    if target != revision:
        raise ValueError(f"release tag {tag} points to {target}, not built commit {revision}")


def create_metadata(args: argparse.Namespace) -> BuildMetadata:
    """Resolve, validate, and optionally persist one build identity."""

    revision = resolve_revision(args.revision)
    metadata = BuildMetadata.create(revision, args.tag)
    if args.tag:
        verify_tag_target(args.tag, revision)
    if args.output:
        metadata.write(Path(args.output))
    return metadata


def parser() -> argparse.ArgumentParser:
    """Create the command-line contract used by local builds and CI."""

    root = argparse.ArgumentParser()
    root.add_argument("--revision")
    root.add_argument("--tag")
    root.add_argument("--output")
    root.add_argument("--field", choices=("identity", "revision", "release", "tag"), default="json")
    return root


def main() -> None:
    """Generate metadata and print either JSON or one requested field."""

    args = parser().parse_args()
    metadata = create_metadata(args)
    if args.field == "json":
        print(metadata.to_json(), end="")
    else:
        value = getattr(metadata, args.field)
        if isinstance(value, bool):
            print(str(value).lower())
        elif value is not None:
            print(value)


if __name__ == "__main__":
    main()
