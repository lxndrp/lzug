"""Fail a PR check when it overlaps an explicitly blocking open review issue."""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.github.com"
PER_PAGE = 100
MAX_PULL_REQUEST_FILES = 3000
ISSUE_CLOSING_REFERENCE = re.compile(
    r"\b(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\s*:?[ \t]+#(\d+)\b", re.IGNORECASE
)


class GitHubApiError(RuntimeError):
    """An API request failed or returned data outside the expected contract."""


def _request(url: str, token: str) -> tuple[object, str | None]:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
            return payload, response.headers.get("Link")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        raise GitHubApiError(f"GitHub API request failed for {url}: {error}") from error


def _pages(url: str, token: str) -> Iterator[list[dict[str, object]]]:
    page = 1
    while True:
        separator = "&" if "?" in url else "?"
        payload, _ = _request(
            f"{url}{separator}{urlencode({'page': page, 'per_page': PER_PAGE})}", token
        )
        if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
            raise GitHubApiError(f"GitHub API returned an invalid list for {url}")
        items = payload
        yield items
        if len(items) < PER_PAGE:
            return
        page += 1


def _valid_repo_path(value: object, *, issue: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GitHubApiError(f"Issue #{issue} has an empty or invalid affected path")
    path = value.removeprefix("./")
    if (
        path.startswith("/")
        or "\\" in path
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
        or any(segment in {"", ".", ".."} for segment in path.split("/"))
        or any(character in path for character in "*?[]{}")
    ):
        raise GitHubApiError(f"Issue #{issue} has an unsupported affected path: {value!r}")
    return path


def affected_paths(body: object, *, issue: int) -> list[str]:
    if not isinstance(body, str):
        raise GitHubApiError(f"Issue #{issue} has no readable body with affected paths")
    marker = re.search(r"(?im)^\s*(?:affected paths|betroffene pfade)\s*:\s*$", body)
    if marker is None:
        raise GitHubApiError(f"Issue #{issue} does not declare its affected paths")
    tail = body[marker.end() :]
    paths: list[str] = []
    for line in tail.splitlines():
        if line.strip() and not re.match(r"^\s*[-*+]\s+", line):
            if paths:
                break
            continue
        entry = re.match(r"^\s*[-*+]\s+(.+?)\s*$", line)
        if entry:
            paths.append(_valid_repo_path(entry.group(1).strip().strip("`"), issue=issue))
    if not paths:
        raise GitHubApiError(f"Issue #{issue} does not list any affected paths")
    return paths


def paths_overlap(finding_path: str, changed_path: str) -> bool:
    return (
        finding_path == changed_path
        or finding_path.startswith(changed_path + "/")
        or changed_path.startswith(finding_path + "/")
    )


def _has_blocking_label(issue: dict[str, object]) -> bool:
    labels = issue.get("labels")
    if not isinstance(labels, list) or any(not isinstance(label, dict) for label in labels):
        raise GitHubApiError(f"Issue #{issue.get('number', '?')} has unreadable labels")
    return any(label.get("name") == "review:blocking" for label in labels)


def check(repository: str, pull_number: int, token: str) -> list[str]:
    api_repo = f"{API}/repos/{repository}"
    pull_payload, _ = _request(f"{api_repo}/pulls/{pull_number}", token)
    if not isinstance(pull_payload, dict) or not isinstance(
        pull_payload.get("body"), (str, type(None))
    ):
        raise GitHubApiError(f"Pull request #{pull_number} has unreadable metadata")
    expected_file_count = pull_payload.get("changed_files")
    if not isinstance(expected_file_count, int) or isinstance(expected_file_count, bool):
        raise GitHubApiError(f"Pull request #{pull_number} has an unreadable changed-file count")
    if expected_file_count < 0:
        raise GitHubApiError(f"Pull request #{pull_number} has an invalid changed-file count")
    body = pull_payload.get("body") or ""
    closes = {int(number) for number in ISSUE_CLOSING_REFERENCE.findall(body)}

    changed: list[str] = []
    received_file_count = 0
    for page in _pages(f"{api_repo}/pulls/{pull_number}/files", token):
        for file in page:
            filename = file.get("filename")
            if not isinstance(filename, str) or not filename:
                raise GitHubApiError(f"Pull request #{pull_number} has an unreadable changed path")
            changed.append(filename)
            received_file_count += 1
            if file.get("status") == "renamed":
                previous_filename = file.get("previous_filename")
                if not isinstance(previous_filename, str) or not previous_filename:
                    raise GitHubApiError(
                        f"Pull request #{pull_number} has an unreadable renamed path"
                    )
                changed.append(previous_filename)

    if received_file_count != expected_file_count:
        raise GitHubApiError(
            f"Pull request #{pull_number} returned {received_file_count} changed files, "
            f"but its metadata reports {expected_file_count} changed files"
        )
    if expected_file_count >= MAX_PULL_REQUEST_FILES:
        raise GitHubApiError(
            f"Pull request #{pull_number} has at least {MAX_PULL_REQUEST_FILES} files; "
            "GitHub's file-list API limit prevents a complete blocker check"
        )

    blockers_url = f"{api_repo}/issues?{urlencode({'state': 'open', 'labels': 'review:blocking'})}"
    failures: list[str] = []
    for page in _pages(blockers_url, token):
        for issue in page:
            if "pull_request" in issue:
                continue
            number = issue.get("number")
            if not isinstance(number, int):
                raise GitHubApiError("GitHub returned an invalid open blocking issue")
            if issue.get("state") == "closed":
                continue
            if issue.get("state") != "open":
                raise GitHubApiError("GitHub returned an invalid open blocking issue")
            if not _has_blocking_label(issue):
                continue
            if number in closes:
                continue
            paths = affected_paths(issue.get("body"), issue=number)
            collisions = sorted(
                {
                    changed_path
                    for changed_path in changed
                    for path in paths
                    if paths_overlap(path, changed_path)
                }
            )
            if collisions:
                rendered = ", ".join(
                    f"`{json.dumps(path, ensure_ascii=True)}`" for path in collisions
                )
                failures.append(
                    f"- Issue [#{number}]({issue.get('html_url', '')}) overlaps: {rendered}"
                )
    return failures


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    pull_number = os.environ.get("PULL_REQUEST_NUMBER", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not repository or not re.fullmatch(r"[^/]+/[^/]+", repository):
        print("::error::GITHUB_REPOSITORY is missing or invalid")
        return 1
    if not pull_number.isdecimal() or not token:
        print("::error::Pull request number or read token is missing")
        return 1

    try:
        failures = check(repository, int(pull_number), token)
    except GitHubApiError as error:
        print(f"::error::Unable to evaluate review blockers: {error}")
        return 1
    if failures:
        print("::error::This pull request overlaps open review blockers:")
        print("\n".join(failures))
        return 1
    print("No open review blockers overlap this pull request.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
