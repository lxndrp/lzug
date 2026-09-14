#!/usr/bin/env python3
"""Select complete Quality evidence for an exact master revision."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from typing import Any

ACTIVE_STATUSES = {"queued", "in_progress", "waiting", "requested", "pending"}
QUALITY_EVENTS = {"schedule", "workflow_dispatch"}


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def payload_items(payload: Any, key: str) -> list[dict[str, Any]]:
    pages = payload if isinstance(payload, list) else [payload]
    return [item for page in pages for item in page.get(key, [])]


def select_evidence(
    runs_payload: Any,
    artifacts_payload: Any,
    *,
    target_sha: str,
    current_run_id: str | None,
    now: datetime,
    max_age_hours: int = 24,
    required_artifacts: set[str],
    force_full: bool = False,
) -> dict[str, Any]:
    runs = [
        run for run in payload_items(runs_payload, "workflow_runs")
        if run.get("head_sha") == target_sha
        and run.get("head_branch") == "master"
        and run.get("event") in QUALITY_EVENTS
        and str(run.get("id")) != current_run_id
    ]
    active = [run for run in runs if run.get("status") in ACTIVE_STATUSES]
    if active:
        run = max(active, key=lambda item: item.get("id", 0))
        return {
            "decision": "in_progress",
            "reason": "matching Quality run is still active",
            "run_id": run.get("id"),
            "sha": target_sha,
        }
    if force_full:
        return {
            "decision": "execute",
            "reason": "explicit full Quality run requested",
            "run_id": None,
            "sha": target_sha,
        }

    artifacts_by_run: dict[str, set[str]] = {}
    expired_by_run: dict[str, set[str]] = {}
    for artifact in payload_items(artifacts_payload, "artifacts"):
        run_id = str((artifact.get("workflow_run") or {}).get("id", ""))
        if not run_id:
            continue
        name = str(artifact.get("name", ""))
        target = expired_by_run if artifact.get("expired") else artifacts_by_run
        target.setdefault(run_id, set()).add(name)

    successful = [
        run
        for run in runs
        if run.get("status") == "completed" and run.get("conclusion") == "success"
    ]
    for run in sorted(successful, key=lambda item: item.get("id", 0), reverse=True):
        try:
            age_hours = (now - parse_time(run["completed_at"])).total_seconds() / 3600
        except (KeyError, TypeError, ValueError):
            continue
        run_id = str(run.get("id"))
        available = artifacts_by_run.get(run_id, set())
        if age_hours < 0 or age_hours > max_age_hours or required_artifacts - available:
            continue
        if expired_by_run.get(run_id, set()) & required_artifacts:
            continue
        return {
            "decision": "reused",
            "reason": "recent successful Quality run has the complete evidence contract",
            "run_id": run.get("id"),
            "sha": target_sha,
            "age_hours": round(age_hours, 3),
        }
    return {
        "decision": "execute",
        "reason": "no reusable complete Quality evidence exists",
        "run_id": None,
        "sha": target_sha,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=argparse.FileType("r"), required=True)
    parser.add_argument("--artifacts", type=argparse.FileType("r"), required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--current-run-id")
    parser.add_argument("--now", required=True)
    parser.add_argument("--max-age-hours", type=int, default=24)
    parser.add_argument("--required-artifact", action="append", required=True)
    parser.add_argument("--force-full", action="store_true")
    args = parser.parse_args()
    result = select_evidence(
        json.load(args.runs),
        json.load(args.artifacts),
        target_sha=args.sha,
        current_run_id=args.current_run_id,
        now=parse_time(args.now),
        max_age_hours=args.max_age_hours,
        required_artifacts=set(args.required_artifact),
        force_full=args.force_full,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
