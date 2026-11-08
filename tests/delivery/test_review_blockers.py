from __future__ import annotations

import re
import unittest
from unittest.mock import patch

from scripts import review_blockers


class ReviewBlockerPathTests(unittest.TestCase):
    def test_reads_repository_relative_paths_from_english_and_german_sections(self) -> None:
        for heading in ("Affected paths:", "Betroffene Pfade:"):
            with self.subTest(heading=heading):
                self.assertEqual(
                    ["backend/src/module.py", "docs/guide.md"],
                    review_blockers.affected_paths(
                        "Finding details\n\n"
                        f"{heading}\n- `backend/src/module.py`\n"
                        "- docs/guide.md\n\n## Context",
                        issue=12,
                    ),
                )

    def test_rejects_ambiguous_paths(self) -> None:
        for path in ("../secret", "/absolute/path", "src/*.py", "src\\module.py"):
            with self.subTest(path=path), self.assertRaises(review_blockers.GitHubApiError):
                review_blockers.affected_paths(f"Affected paths:\n- {path}", issue=12)

    def test_path_overlap_covers_files_and_directories(self) -> None:
        self.assertTrue(review_blockers.paths_overlap("backend/src", "backend/src/module.py"))
        self.assertTrue(review_blockers.paths_overlap("backend/src/module.py", "backend/src"))
        self.assertTrue(review_blockers.paths_overlap("docs/guide.md", "docs/guide.md"))
        self.assertFalse(review_blockers.paths_overlap("docs/guide.md", "docs/other.md"))


class ReviewBlockerCheckTests(unittest.TestCase):
    def test_matching_issue_blocks_unless_pull_request_closes_it(self) -> None:
        issues = [
            {
                "number": 12,
                "state": "open",
                "html_url": "https://github.com/lxndrp/lzug/issues/12",
                "labels": [{"name": "review:blocking"}],
                "body": "Affected paths:\n- backend/src",
            },
            {
                "number": 13,
                "state": "open",
                "html_url": "https://github.com/lxndrp/lzug/issues/13",
                "labels": [{"name": "review:blocking"}],
                "body": "Affected paths:\n- backend/src",
            },
        ]

        def fake_request(url: str, _token: str):
            if "/pulls/5/files?" in url:
                return ([{"filename": "backend/src/module.py"}], None)
            if url.endswith("/pulls/5"):
                return ({"body": "Closes: #12", "changed_files": 1}, None)
            if "/issues?" in url:
                return (issues, None)
            self.fail(f"Unexpected API URL: {url}")

        with patch.object(review_blockers, "_request", side_effect=fake_request):
            result = review_blockers.check("lxndrp/lzug", 5, "token")

        self.assertEqual(
            [
                "- Issue [#13](https://github.com/lxndrp/lzug/issues/13) overlaps: "
                '`"backend/src/module.py"`'
            ],
            result,
        )

    def test_ignores_non_blocking_closed_and_unrelated_issues(self) -> None:
        issues = [
            {
                "number": number,
                "state": state,
                "html_url": f"https://github.com/lxndrp/lzug/issues/{number}",
                "labels": labels,
                "body": body,
            }
            for number, state, labels, body in (
                (12, "open", [{"name": "review:quality"}], "Affected paths:\n- backend/src"),
                (13, "closed", [{"name": "review:blocking"}], "Affected paths:\n- backend/src"),
                (14, "open", [{"name": "review:blocking"}], "Affected paths:\n- docs"),
            )
        ]

        def fake_request(url: str, _token: str):
            if "/pulls/5/files?" in url:
                return ([{"filename": "backend/src/module.py"}], None)
            if url.endswith("/pulls/5"):
                return ({"body": "", "changed_files": 1}, None)
            if "/issues?" in url:
                return (issues, None)
            self.fail(f"Unexpected API URL: {url}")

        with patch.object(review_blockers, "_request", side_effect=fake_request):
            self.assertEqual([], review_blockers.check("lxndrp/lzug", 5, "token"))

    def test_missing_issue_paths_fail_closed(self) -> None:
        def fake_request(url: str, _token: str):
            if "/pulls/5/files?" in url:
                return ([{"filename": "backend/src/module.py"}], None)
            if url.endswith("/pulls/5"):
                return ({"body": "", "changed_files": 1}, None)
            if "/issues?" in url:
                return (
                    [
                        {
                            "number": 12,
                            "state": "open",
                            "labels": [{"name": "review:blocking"}],
                            "body": "Finding without a path section",
                        }
                    ],
                    None,
                )
            self.fail(f"Unexpected API URL: {url}")

        with patch.object(review_blockers, "_request", side_effect=fake_request):
            with self.assertRaisesRegex(
                review_blockers.GitHubApiError, "does not declare its affected paths"
            ):
                review_blockers.check("lxndrp/lzug", 5, "token")

    def test_api_errors_are_not_treated_as_clear(self) -> None:
        with patch.object(
            review_blockers,
            "_request",
            side_effect=review_blockers.GitHubApiError("403 Forbidden"),
        ):
            with self.assertRaisesRegex(review_blockers.GitHubApiError, "403 Forbidden"):
                review_blockers.check("lxndrp/lzug", 5, "token")

    def test_renamed_file_matches_its_previous_path(self) -> None:
        issues = [
            {
                "number": 12,
                "state": "open",
                "html_url": "https://github.com/lxndrp/lzug/issues/12",
                "labels": [{"name": "review:blocking"}],
                "body": "Affected paths:\n- backend/src/module.py",
            }
        ]

        def fake_request(url: str, _token: str):
            if "/pulls/5/files?" in url:
                return (
                    [
                        {
                            "filename": "backend/src/renamed.py",
                            "previous_filename": "backend/src/module.py",
                            "status": "renamed",
                        }
                    ],
                    None,
                )
            if url.endswith("/pulls/5"):
                return ({"body": "", "changed_files": 1}, None)
            if "/issues?" in url:
                return (issues, None)
            self.fail(f"Unexpected API URL: {url}")

        with patch.object(review_blockers, "_request", side_effect=fake_request):
            result = review_blockers.check("lxndrp/lzug", 5, "token")

        self.assertEqual(
            [
                "- Issue [#12](https://github.com/lxndrp/lzug/issues/12) overlaps: "
                '`"backend/src/module.py"`'
            ],
            result,
        )

    def test_file_list_api_limit_fails_closed(self) -> None:
        files = [{"filename": f"src/file-{index}.py"} for index in range(3000)]

        def fake_request(url: str, _token: str):
            if "/pulls/5/files?" in url:
                page_match = re.search(r"[?&]page=(\d+)", url)
                page = int(page_match.group(1)) if page_match else 1
                return (files[(page - 1) * 100 : page * 100], None)
            if url.endswith("/pulls/5"):
                return ({"body": "", "changed_files": 3000}, None)
            self.fail(f"Unexpected API URL: {url}")

        with patch.object(review_blockers, "_request", side_effect=fake_request):
            with self.assertRaisesRegex(review_blockers.GitHubApiError, "API limit prevents"):
                review_blockers.check("lxndrp/lzug", 5, "token")
