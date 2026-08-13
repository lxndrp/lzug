#!/usr/bin/env python3
"""Report completed issue branches that still need a local merge closeout."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ISSUE_BRANCH = re.compile(r"^codex/(?P<issue>[1-9][0-9]*)-[a-z0-9][a-z0-9-]*$")
SUCCESS_RESULTS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
FAILURE_RESULTS = {
    "ACTION_REQUIRED",
    "CANCELLED",
    "ERROR",
    "FAILURE",
    "STALE",
    "STARTUP_FAILURE",
    "TIMED_OUT",
}
PENDING_RESULTS = {"EXPECTED", "IN_PROGRESS", "PENDING", "QUEUED", "REQUESTED", "WAITING"}


class CommandError(RuntimeError):
    """A required local command could not be executed."""


class Runner:
    """Small subprocess boundary that keeps discovery testable."""

    def run(self, *command: str, cwd: Path | None = None, check: bool = True) -> str:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            text=True,
            capture_output=True,
        )
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise CommandError(f"{' '.join(command)}: {detail}")
        return result.stdout


@dataclass(frozen=True)
class Worktree:
    path: str
    branch: str | None
    state: str
    changes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Artifact:
    branch: str
    issue_number: int
    local_branch: bool
    remote_branch: bool
    worktree: Worktree | None


@dataclass(frozen=True)
class Finding:
    branch: str
    issue_number: int
    issue_title: str | None
    issue_url: str | None
    issue_state: str
    pr_number: int | None
    pr_url: str | None
    pr_state: str
    ci_state: str
    review_state: str
    unresolved_review_threads: int | None
    worktree_path: str | None
    worktree_state: str
    changes: tuple[str, ...]
    local_branch: str
    remote_branch: str
    result: str
    action: str


def parse_worktrees(output: str) -> dict[str, Path]:
    """Return checked-out local branches and their worktree paths."""
    result: dict[str, Path] = {}
    path: Path | None = None
    for line in [*output.splitlines(), ""]:
        if line.startswith("worktree "):
            path = Path(line.removeprefix("worktree "))
        elif line.startswith("branch refs/heads/") and path is not None:
            result[line.removeprefix("branch refs/heads/")] = path
        elif not line:
            path = None
    return result


def parse_refs(output: str, prefix: str = "") -> set[str]:
    return {
        ref.removeprefix(prefix)
        for line in output.splitlines()
        if (ref := line.strip()).startswith(prefix)
    }


def parse_remote_heads(output: str) -> set[str]:
    """Extract branch names from ``git ls-remote --heads`` output."""
    result = set()
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].startswith("refs/heads/codex/"):
            result.add(fields[1].removeprefix("refs/heads/"))
    return result


def inspect_worktree(runner: Runner, path: Path, branch: str) -> Worktree:
    """Classify a worktree without modifying it."""
    try:
        output = runner.run(
            "git",
            "-c",
            "core.fsmonitor=false",
            "status",
            "--porcelain",
            "--untracked-files=all",
            cwd=path,
        )
    except CommandError as error:
        return Worktree(str(path), branch, "unknown", (str(error),))
    changes = tuple(line for line in output.splitlines() if line)
    return Worktree(str(path), branch, "dirty" if changes else "clean", changes)


def discover_artifacts(runner: Runner, repository_root: Path, remote: str) -> list[Artifact]:
    local = parse_refs(
        runner.run(
            "git",
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads/codex/",
            cwd=repository_root,
        )
    )
    remote_refs = parse_remote_heads(
        runner.run(
            "git",
            "ls-remote",
            "--heads",
            remote,
            "refs/heads/codex/*",
            cwd=repository_root,
        )
    )
    worktree_paths = parse_worktrees(
        runner.run("git", "worktree", "list", "--porcelain", cwd=repository_root)
    )

    artifacts: list[Artifact] = []
    for branch in sorted(local | remote_refs | set(worktree_paths)):
        match = ISSUE_BRANCH.fullmatch(branch)
        if match is None:
            continue
        worktree = None
        if branch in worktree_paths:
            worktree = inspect_worktree(runner, worktree_paths[branch], branch)
        artifacts.append(
            Artifact(
                branch=branch,
                issue_number=int(match.group("issue")),
                local_branch=branch in local,
                remote_branch=branch in remote_refs,
                worktree=worktree,
            )
        )
    return artifacts


def check_state(checks: Sequence[dict[str, Any]]) -> str:
    """Fold GitHub check runs and commit statuses into one explicit state."""
    if not checks:
        return "missing"
    results: list[str] = []
    for check in checks:
        value = check.get("conclusion") or check.get("state") or check.get("status")
        results.append(str(value or "PENDING").upper())
    if any(result in FAILURE_RESULTS for result in results):
        return "failed"
    if any(result in PENDING_RESULTS or result not in SUCCESS_RESULTS for result in results):
        return "pending"
    return "successful"


def review_state(pr: dict[str, Any], unresolved_threads: int | None) -> str:
    decision = str(pr.get("reviewDecision") or "").upper()
    if unresolved_threads is None:
        return "unknown"
    if unresolved_threads:
        return "unresolved"
    if decision == "CHANGES_REQUESTED":
        return "changes_requested"
    if decision == "REVIEW_REQUIRED":
        return "required"
    if decision == "APPROVED":
        return "approved"
    if pr.get("mergedAt") or str(pr.get("state", "")).upper() == "MERGED":
        return "complete"
    return "pending"


def classify(
    artifact: Artifact,
    issue: dict[str, Any] | None,
    pr: dict[str, Any] | None,
    unresolved_threads: int | None,
) -> Finding:
    issue_state = str((issue or {}).get("state") or "unknown").lower()
    pr_state = str((pr or {}).get("state") or "missing").lower()
    merged = bool(pr and (pr.get("mergedAt") or pr_state == "merged"))
    ci = check_state((pr or {}).get("statusCheckRollup") or [])
    review = review_state(pr or {}, unresolved_threads) if pr else "missing"
    worktree_state = artifact.worktree.state if artifact.worktree else "missing"

    if issue_state != "closed":
        result = "not_complete"
        action = "No closeout: the issue is not closed."
    elif not merged:
        result = "not_merged"
        action = "No closeout: no merged pull request was found for the branch."
    elif ci != "successful":
        result = "blocked_ci"
        action = f"No closeout: CI is {ci}; inspect the pull request checks."
    elif review in {"unknown", "unresolved", "changes_requested", "required", "pending"}:
        result = "blocked_review"
        action = f"No closeout: review is {review}; inspect review threads and comments."
    elif worktree_state in {"dirty", "unknown"}:
        result = "blocked_worktree"
        action = "Stop closeout and inspect the reported local changes; do not delete them."
    elif artifact.worktree:
        result = "ready"
        action = "Clean worktree: the implementation task may perform the documented closeout."
    else:
        result = "branches_only"
        action = "Worktree is already absent; only the reported remaining branches need closeout."

    return Finding(
        branch=artifact.branch,
        issue_number=artifact.issue_number,
        issue_title=(issue or {}).get("title"),
        issue_url=(issue or {}).get("url"),
        issue_state=issue_state,
        pr_number=(pr or {}).get("number"),
        pr_url=(pr or {}).get("url"),
        pr_state=pr_state,
        ci_state=ci,
        review_state=review,
        unresolved_review_threads=unresolved_threads,
        worktree_path=artifact.worktree.path if artifact.worktree else None,
        worktree_state=worktree_state,
        changes=artifact.worktree.changes if artifact.worktree else (),
        local_branch="present" if artifact.local_branch else "absent",
        remote_branch="present" if artifact.remote_branch else "absent",
        result=result,
        action=action,
    )


class GitHub:
    def __init__(self, runner: Runner, repository: str) -> None:
        self.runner = runner
        self.repository = repository
        self.owner, self.name = repository.split("/", 1)

    def issue(self, number: int) -> dict[str, Any] | None:
        return self._json_or_none(
            "gh",
            "issue",
            "view",
            str(number),
            "--repo",
            self.repository,
            "--json",
            "number,title,state,url",
        )

    def pull_request(self, branch: str) -> dict[str, Any] | None:
        output = self._json_or_none(
            "gh",
            "pr",
            "list",
            "--repo",
            self.repository,
            "--state",
            "all",
            "--head",
            branch,
            "--limit",
            "1",
            "--json",
            "number,url,state,mergedAt,reviewDecision,statusCheckRollup",
        )
        return output[0] if isinstance(output, list) and output else None

    def unresolved_threads(self, pr_number: int) -> int | None:
        query = (
            "query($owner:String!,$name:String!,$number:Int!){"
            "repository(owner:$owner,name:$name){pullRequest(number:$number){"
            "reviewThreads(first:100){nodes{isResolved}pageInfo{hasNextPage}}}}}"
        )
        response = self._json_or_none(
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={self.owner}",
            "-F",
            f"name={self.name}",
            "-F",
            f"number={pr_number}",
        )
        try:
            threads = response["data"]["repository"]["pullRequest"]["reviewThreads"]
            if threads["pageInfo"]["hasNextPage"]:
                return None
            return sum(not node["isResolved"] for node in threads["nodes"])
        except KeyError, TypeError:
            return None

    def _json_or_none(self, *command: str) -> Any:
        try:
            return json.loads(self.runner.run(*command))
        except CommandError, json.JSONDecodeError:
            return None


def render_text(findings: Sequence[Finding], repository: str) -> str:
    lines = [
        f"Closeout monitor: {repository}",
        "Mode: report only; no files or refs are changed.",
        "",
    ]
    if not findings:
        return "\n".join([*lines, "No codex issue artifacts found."])
    for finding in findings:
        unresolved = (
            finding.unresolved_review_threads
            if finding.unresolved_review_threads is not None
            else "unknown"
        )
        lines.extend(
            [
                f"[{finding.result}] #{finding.issue_number} "
                f"{finding.issue_title or '(unknown issue)'}",
                f"  branch: {finding.branch}",
                f"  issue: {finding.issue_state} ({finding.issue_url or 'unavailable'})",
                f"  pull request: {finding.pr_state} #{finding.pr_number or '-'} "
                f"({finding.pr_url or 'unavailable'})",
                f"  CI: {finding.ci_state}",
                f"  review: {finding.review_state}; unresolved threads: {unresolved}",
                f"  worktree: {finding.worktree_state} ({finding.worktree_path or 'absent'})",
                f"  local branch: {finding.local_branch}; remote branch: {finding.remote_branch}",
            ]
        )
        lines.extend(f"  change: {change}" for change in finding.changes)
        lines.extend([f"  action: {finding.action}", ""])
    return "\n".join(lines).rstrip()


def repository_name(runner: Runner, repository_root: Path) -> str:
    output = runner.run("gh", "repo", "view", "--json", "nameWithOwner", cwd=repository_root)
    try:
        return json.loads(output)["nameWithOwner"]
    except (json.JSONDecodeError, KeyError) as error:
        raise CommandError("gh repo view did not return nameWithOwner") from error


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository", help="GitHub repository as owner/name; defaults to gh repo view"
    )
    parser.add_argument(
        "--remote", default="origin", help="remote whose codex branches are inspected"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    arguments = parser.parse_args(argv)
    runner = Runner()
    try:
        root = Path(runner.run("git", "rev-parse", "--show-toplevel").strip())
        repository = arguments.repository or repository_name(runner, root)
        github = GitHub(runner, repository)
        findings = []
        for artifact in discover_artifacts(runner, root, arguments.remote):
            issue = github.issue(artifact.issue_number)
            pr = github.pull_request(artifact.branch)
            unresolved = github.unresolved_threads(pr["number"]) if pr else None
            findings.append(classify(artifact, issue, pr, unresolved))
    except CommandError as error:
        print(f"closeout monitor failed: {error}", file=sys.stderr)
        return 2

    if arguments.json:
        print(json.dumps([asdict(finding) for finding in findings], indent=2, sort_keys=True))
    else:
        print(render_text(findings, repository))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
