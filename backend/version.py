"""Canonical application version and build revision metadata."""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path


@cache
def _source_version() -> str:
    return (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()


def application_version() -> str:
    """Return the release version embedded in this source or image."""

    override = os.environ.get("LZUG_VERSION", "").strip()
    if override:
        return override
    return _source_version()


def build_revision() -> str:
    """Return the source commit recorded by the OCI build."""

    return os.environ.get("LZUG_REVISION", "unknown").strip() or "unknown"
