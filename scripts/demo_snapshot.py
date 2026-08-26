#!/usr/bin/env python3
"""Validate the immutable source contract for one promoted demo snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from demo.identity import DemoIdentity  # noqa: E402


class SnapshotContractError(ValueError):
    """Signal incomplete or inconsistent snapshot promotion evidence."""


def snapshot_identity(tag: str, revision: str) -> DemoIdentity:
    try:
        identity = DemoIdentity.create(tag, revision)
    except ValueError as error:
        raise SnapshotContractError(str(error)) from error
    if not identity.is_snapshot:
        raise SnapshotContractError("snapshot promotion requires a demo snapshot tag")
    return identity


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    identity = commands.add_parser("identity")
    identity.add_argument("--tag", required=True)
    identity.add_argument("--revision", required=True)
    identity.add_argument(
        "--field",
        choices=("identity", "oci_tag", "target_version", "tag", "commit", "channel"),
        default="identity",
    )

    return root


def main() -> None:
    args = parser().parse_args()
    try:
        print(getattr(snapshot_identity(args.tag, args.revision), args.field))
    except SnapshotContractError as error:
        raise SystemExit(f"Snapshot contract rejected: {error}") from error


if __name__ == "__main__":
    main()
