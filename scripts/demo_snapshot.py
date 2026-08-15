#!/usr/bin/env python3
"""Validate the immutable source contract for one promoted demo snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from demo.identity import STABLE_VERSION, DemoIdentity, version_key  # noqa: E402


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


def validate_quality_runs(payload: Any, revision: str) -> dict[str, Any]:
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        raise SnapshotContractError("quality evidence response has an invalid shape")
    matches = [
        run
        for run in runs
        if isinstance(run, dict)
        and run.get("head_sha") == revision
        and run.get("head_branch") == "master"
        and run.get("event") == "push"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and run.get("path") == ".github/workflows/quality.yml"
    ]
    if not matches:
        raise SnapshotContractError(
            f"no successful complete master Quality workflow exists for {revision}"
        )
    return max(matches, key=lambda run: str(run.get("created_at", "")))


def validate_milestones(
    payload: Any, target_version: str, *, now: datetime | None = None
) -> dict[str, Any]:
    version_key(target_version)
    if not isinstance(payload, list):
        raise SnapshotContractError("milestone response has an invalid shape")
    matches = [
        milestone
        for milestone in payload
        if isinstance(milestone, dict)
        and milestone.get("title") == target_version
        and milestone.get("state") == "open"
    ]
    if len(matches) != 1:
        raise SnapshotContractError(
            f"target version {target_version} must identify exactly one open milestone"
        )
    milestone = matches[0]
    due_on = milestone.get("due_on")
    if not isinstance(due_on, str):
        raise SnapshotContractError("target milestone must have a future due date")
    try:
        due = datetime.fromisoformat(due_on.replace("Z", "+00:00"))
    except ValueError as error:
        raise SnapshotContractError("target milestone has an invalid due date") from error
    current = now or datetime.now(UTC)
    if due <= current:
        raise SnapshotContractError("target milestone due date is not in the future")
    return milestone


def validate_releases(payload: Any, target_version: str) -> None:
    target = version_key(target_version)
    if not isinstance(payload, list):
        raise SnapshotContractError("release response has an invalid shape")
    released: list[tuple[int, int, int]] = []
    for release in payload:
        if not isinstance(release, dict) or release.get("draft") is True:
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or STABLE_VERSION.fullmatch(tag) is None:
            continue
        if tag == target_version:
            raise SnapshotContractError("target version already has a product release")
        released.append(version_key(tag))
    if released and target <= max(released):
        raise SnapshotContractError("target version is not newer than the latest stable release")


def _read_json() -> Any:
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError as error:
        raise SnapshotContractError("input is not valid JSON") from error


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

    quality = commands.add_parser("validate-quality")
    quality.add_argument("--revision", required=True)

    milestone = commands.add_parser("validate-milestone")
    milestone.add_argument("--target-version", required=True)

    releases = commands.add_parser("validate-releases")
    releases.add_argument("--target-version", required=True)
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "identity":
            print(getattr(snapshot_identity(args.tag, args.revision), args.field))
        elif args.command == "validate-quality":
            run = validate_quality_runs(_read_json(), args.revision)
            print(run.get("html_url", run.get("id", "verified")))
        elif args.command == "validate-milestone":
            milestone = validate_milestones(_read_json(), args.target_version)
            print(milestone.get("html_url", milestone.get("number", "verified")))
        else:
            validate_releases(_read_json(), args.target_version)
            print("verified")
    except SnapshotContractError as error:
        raise SystemExit(f"Snapshot contract rejected: {error}") from error


if __name__ == "__main__":
    main()
