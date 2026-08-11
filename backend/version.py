"""Runtime access to canonical application build metadata."""

from __future__ import annotations

import subprocess
from functools import cache
from pathlib import Path

from .build_metadata import BuildMetadata

BUILD_METADATA_PATH = Path(__file__).resolve().parent.parent / "build-metadata.json"


@cache
def build_metadata() -> BuildMetadata:
    """Read injected metadata or derive a development identity from Git."""

    if BUILD_METADATA_PATH.is_file():
        return BuildMetadata.read(BUILD_METADATA_PATH)

    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    return BuildMetadata.create(revision)


def application_version() -> str:
    """Return the canonical release or development identity."""

    return build_metadata().identity


def build_revision() -> str:
    """Return the full immutable source revision."""

    return build_metadata().revision
