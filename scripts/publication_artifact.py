#!/usr/bin/env python3
"""Select a recent Pages artifact from the exact successful publication revision."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def records(payload: Any, key: str) -> list[dict[str, Any]]:
    """Normalize GitHub's direct and --slurp API response shapes."""

    if isinstance(payload, list):
        values = [
            item
            for page in payload
            for item in (page.get(key, []) if isinstance(page, dict) else [])
        ]
    elif isinstance(payload, dict):
        values = payload.get(key, [])
    else:
        values = []
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, dict)]


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def reusable_run(
    runs_payload: Any,
    artifacts_payload: Any,
    *,
    revision: str,
    now: datetime,
) -> str | None:
    """Return a successful run id with one current, non-empty Pages artifact."""

    successful = {
        str(run.get("id")): run
        for run in records(runs_payload, "workflow_runs")
        if str(run.get("head_sha", "")).lower() == revision.lower()
        and run.get("head_branch") == "master"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and run.get("event") in {"push", "workflow_dispatch", "schedule"}
    }
    candidates: list[tuple[datetime, str]] = []
    for artifact in records(artifacts_payload, "artifacts"):
        run_id = str((artifact.get("workflow_run") or {}).get("id", ""))
        run = successful.get(run_id)
        if artifact.get("name") != "lzug-public-site" or run is None:
            continue
        if artifact.get("expired") is not False:
            continue
        size = artifact.get("size_in_bytes")
        if not isinstance(size, int) or size <= 0:
            continue
        created = parse_time(artifact.get("created_at"))
        expires = parse_time(artifact.get("expires_at"))
        if created is None or expires is None or created > now or expires <= now:
            continue
        candidates.append((created, run_id))
    return max(candidates)[1] if candidates else None


REPRODUCIBILITY_INPUTS = (
    ".github/workflows/publication.yml",
    ".mise.toml",
    ".python-version",
    "Taskfile.yml",
    "backend/fastapi_assembly.py",
    "frontend/.node-version",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/tsconfig",
    "frontend/tsconfig.app.json",
    "docs/publication/hugo.toml",
    "docs/publication/go.mod",
    "docs/publication/go.sum",
    "pyproject.toml",
    "uv.lock",
    "scripts/publication_metadata.py",
)


def needs_reproducibility_check(paths: list[str]) -> bool:
    """Select changes to publication generators, their configuration, or locks."""

    for path in paths:
        if path.startswith("docs/publication/") and not path.startswith(
            "docs/publication/content/"
        ):
            return True
        if path in REPRODUCIBILITY_INPUTS or (
            path.startswith("frontend/tsconfig") and path.endswith(".json")
        ):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--now")
    parser.add_argument("--changed-files", type=Path)
    parser.add_argument("--check-reproducibility", action="store_true")
    args = parser.parse_args()
    if args.check_reproducibility:
        paths = args.changed_files.read_text().splitlines() if args.changed_files else []
        print("true" if needs_reproducibility_check(paths) else "false")
        return
    if not all((args.runs, args.artifacts, args.revision, args.now)):
        parser.error("artifact selection requires --runs, --artifacts, --revision, and --now")
    now = parse_time(args.now)
    if now is None:
        raise SystemExit("--now must be an ISO-8601 timestamp")
    result = reusable_run(
        json.loads(args.runs.read_text()),
        json.loads(args.artifacts.read_text()),
        revision=args.revision,
        now=now,
    )
    print(result or "")


if __name__ == "__main__":
    main()
