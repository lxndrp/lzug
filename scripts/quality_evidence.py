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
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("evidence timestamps must include a timezone")
    return result.astimezone(UTC)


def payload_items(payload: Any, key: str) -> list[dict[str, Any]]:
    pages = payload if isinstance(payload, list) else [payload]
    if not pages or any(
        not isinstance(page, dict)
        or not isinstance(page.get(key), list)
        or any(not isinstance(item, dict) for item in page[key])
        for page in pages
    ):
        raise ValueError(f"invalid GitHub API response: {key}")
    return [item for page in pages for item in page[key]]


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
    if not 0 < max_age_hours <= 24 or not required_artifacts:
        raise ValueError("evidence requires artifacts and a maximum age of at most 24 hours")
    artifacts = payload_items(artifacts_payload, "artifacts")
    runs = [
        run
        for run in payload_items(runs_payload, "workflow_runs")
        if run.get("head_sha") == target_sha
        and run.get("head_branch") == "master"
        and run.get("event") in QUALITY_EVENTS
        and str(run.get("id")) != current_run_id
    ]
    # A queued successor must not prevent the older run from doing the work.
    active = [
        run
        for run in runs
        if run.get("status") in ACTIVE_STATUSES
        and (current_run_id is None or int(run["id"]) < int(current_run_id))
    ]
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

    # Publication gates must not bypass a newer failed audit by selecting an
    # older complete run. Quality itself can reuse its deterministic artifacts
    # and retry the audits without rebuilding the product.
    if current_run_id is None and runs:
        try:
            latest = max(runs, key=lambda item: parse_time(item["run_started_at"]))
        except (KeyError, TypeError, ValueError, AttributeError):  # fmt: skip
            latest = {}
        if latest.get("status") != "completed" or latest.get("conclusion") != "success":
            return {
                "decision": "execute",
                "reason": "latest matching Quality attempt has no successful audit result",
                "run_id": None,
                "sha": target_sha,
            }

    artifacts_by_run: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        run_id = str((artifact.get("workflow_run") or {}).get("id", ""))
        if not run_id:
            continue
        artifacts_by_run.setdefault(run_id, []).append(artifact)

    successful = [
        run
        for run in runs
        if run.get("status") == "completed" and run.get("conclusion") == "success"
    ]
    for run in sorted(successful, key=lambda item: item.get("id", 0), reverse=True):
        run_id = str(run.get("id"))
        evidence = [
            artifact
            for artifact in artifacts_by_run.get(run_id, [])
            if artifact.get("name") in required_artifacts
        ]
        if {artifact["name"] for artifact in evidence} != required_artifacts:
            continue
        if len(evidence) != len(required_artifacts):
            continue
        try:
            # Workflow runs have no completed_at. Artifact creation timestamps
            # conservatively date the oldest required evidence, not the mutable
            # run.updated_at or the completion time of a later rerun.
            started = parse_time(run["run_started_at"])
            created = [parse_time(artifact["created_at"]) for artifact in evidence]
            expires = [parse_time(artifact["expires_at"]) for artifact in evidence]
            age_hours = (now - min(created)).total_seconds() / 3600
        except (KeyError, TypeError, ValueError, AttributeError):  # fmt: skip
            continue
        if not 0 <= age_hours <= max_age_hours or max(created) > now:
            continue
        # Reject artifacts retained from earlier attempts and ambiguous or
        # unavailable metadata. A reuse-only attempt cannot mint fresh evidence.
        if min(created) < started or min(expires) <= now:
            continue
        if any(
            artifact.get("expired") is not False
            or not isinstance(artifact.get("size_in_bytes"), int)
            or artifact["size_in_bytes"] <= 0
            or artifact["workflow_run"].get("head_sha") != target_sha
            or artifact["workflow_run"].get("head_branch") != "master"
            for artifact in evidence
        ):
            continue
        return {
            "decision": "reused",
            "reason": "recent successful Quality run has the complete evidence contract",
            "run_id": run.get("id"),
            "sha": target_sha,
            "age_hours": round(age_hours, 3),
            "evidence_created_at": min(created).isoformat(),
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
